"""
Position Manager Module
Manages active positions lifecycle:
1. Tracks open trades waiting for TP/SL bracket fill
2. Monitors bracket order status (TP/SL trigger detection)
3. Evaluates active exit conditions (Trend Reversal, Time-based Exit)
4. Logs trade completions to trades_log via TradeLogger

This module closes the gap between Order Submission and Trade Completion tracking.
Without it, the bot doesn't know when TP/SL triggers and trades_log stays incomplete.
See UNIFIED_PLAN.md Section 4.7, Section 4.8.
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional
import structlog
from alpaca.trading.models import Order

from config.settings import settings
from core.alpaca_client import alpaca_trading_client
from core.trade_logger import trade_logger, ActiveTradeRecord
from core.technical import technical_engine
from core.trailing_stop import trailing_stop_manager
from db.connection import db_manager
from notifications import dispatcher
from utils.timezone import now_utc, format_multi_tz_display

logger = structlog.get_logger(__name__)


class PositionManager:
    """
    Lifecycle manager for open trades:
    - Maintains in-memory registry of active trades awaiting TP/SL fill
    - Polls Alpaca order status to detect bracket fill events
    - Evaluates strategy-based exit conditions for active positions
    - Persists closures to trades_log via TradeLogger
    """

    def __init__(self):
        # symbol -> ActiveTradeRecord
        self._active_trades: Dict[str, ActiveTradeRecord] = {}

    @property
    def active_symbols(self) -> List[str]:
        """Symbols with tracked active trades."""
        return list(self._active_trades.keys())

    def has_active_trade(self, symbol: str) -> bool:
        return symbol.upper() in self._active_trades

    def register_trade(self, record: ActiveTradeRecord) -> None:
        """Register a newly opened trade for lifecycle tracking + trailing stop."""
        self._active_trades[record.symbol.upper()] = record

        # Register trailing stop tracking with ATR from signal
        atr = record.take_profit - record.entry_price  # approximate ATR from TP distance
        if atr <= 0:
            atr = record.entry_price - record.stop_loss  # fallback from SL distance
        trailing_stop_manager.register_position(
            symbol=record.symbol,
            entry_price=record.entry_price,
            stop_loss=record.stop_loss,
            atr=max(0.01, atr / 3.0),  # reverse the 3.0x multiplier to get raw ATR
        )

        logger.info(
            "Trade registered for lifecycle tracking",
            symbol=record.symbol,
            entry_price=record.entry_price,
            tp=record.take_profit,
            sl=record.stop_loss,
            alpaca_id=record.alpaca_order_id,
        )

    def unregister_trade(self, symbol: str) -> Optional[ActiveTradeRecord]:
        """Remove trade from active tracking + trailing stop."""
        trailing_stop_manager.unregister_position(symbol.upper())
        return self._active_trades.pop(symbol.upper(), None)

    async def sync_from_broker(self) -> None:
        """
        Synchronize active trades registry with actual Alpaca positions.
        Called at startup to restore tracking state from broker reality.
        """
        try:
            broker_positions = await alpaca_trading_client.get_all_positions()
            broker_symbols = {p.symbol.upper() for p in broker_positions}

            # Remove trades from tracking if position no longer exists at broker
            stale_symbols = [s for s in self._active_trades if s not in broker_symbols]
            for symbol in stale_symbols:
                trade = self._active_trades.pop(symbol)
                logger.info(
                    "Trade removed from tracking (position no longer at broker)",
                    symbol=symbol,
                )
                # Mark trade as closed if we have a DB record
                if trade.db_trade_id is not None:
                    await trade_logger.log_trade_closed(
                        trade_id=trade.db_trade_id,
                        symbol=symbol,
                        qty=trade.qty,
                        entry_price=trade.entry_price,
                        exit_price=trade.entry_price,  # Unknown exit price
                        exit_time=now_utc(),
                        exit_reason="broker_position_closed",
                    )

            # Detect broker positions we're not tracking yet (recovery from restart)
            for p in broker_positions:
                sym = p.symbol.upper()
                if sym not in self._active_trades:
                    # Try to find matching open trade in DB
                    db_trade = None
                    if db_manager.is_connected:
                        try:
                            db_trade = await db_manager.fetchrow(
                                """
                                SELECT id, entry_price, entry_time, strategy_name
                                FROM trades_log
                                WHERE symbol = $1 AND exit_reason = 'open'
                                ORDER BY entry_time DESC LIMIT 1
                                """,
                                sym,
                            )
                        except Exception as e:
                            logger.warning("Failed to lookup trade in DB", error=str(e))

                    entry_price = float(db_trade["entry_price"]) if db_trade else float(p.avg_entry_price)
                    entry_time = db_trade["entry_time"] if db_trade else now_utc()
                    db_id = int(db_trade["id"]) if db_trade else None

                    # Try to find TP/SL from open bracket orders
                    tp_price, sl_price = await self._find_bracket_prices(sym)

                    record = ActiveTradeRecord(
                        db_trade_id=db_id,
                        db_order_id=None,
                        symbol=sym,
                        side="buy",
                        qty=float(p.qty),
                        entry_price=entry_price,
                        entry_time=entry_time,
                        take_profit=tp_price,
                        stop_loss=sl_price,
                        alpaca_order_id="",
                        client_order_id="",
                    )
                    self._active_trades[sym] = record
                    logger.info(
                        "Recovered active trade from broker position",
                        symbol=sym,
                        qty=float(p.qty),
                        entry=entry_price,
                        tp=tp_price,
                        sl=sl_price,
                    )

        except Exception as e:
            logger.error("Failed to sync active trades from broker", error=str(e))

    async def _find_bracket_prices(self, symbol: str) -> tuple[float, float]:
        """
        Look up TP and SL prices from Alpaca open orders for a symbol.
        Returns (take_profit, stop_loss). Defaults to 0.0 if not found.
        """
        tp_price = 0.0
        sl_price = 0.0

        try:
            open_orders = await alpaca_trading_client.get_open_orders()
            for order in open_orders:
                if order.symbol.upper() != symbol.upper():
                    continue
                # Alpaca bracket order legs have order_class attributes
                order_type = getattr(order, "order_type", "")
                limit_price = float(order.limit_price) if order.limit_price else 0.0
                stop_price = float(order.stop_price) if order.stop_price else 0.0

                if order_type == "limit" and limit_price > 0:
                    tp_price = limit_price
                elif order_type == "stop" and stop_price > 0:
                    sl_price = stop_price
        except Exception as e:
            logger.warning("Failed to find bracket prices from orders", error=str(e))

        return tp_price, sl_price

    async def check_bracket_fills(self) -> List[str]:
        """
        Poll Alpaca positions and orders to detect TP/SL fill events.
        Returns list of symbols that were closed.
        """
        closed_symbols: List[str] = []

        if not self._active_trades:
            return closed_symbols

        try:
            # Get current broker positions
            broker_positions = await alpaca_trading_client.get_all_positions()
            broker_symbols = {p.symbol.upper() for p in broker_positions}

            # Check each tracked trade
            for symbol, trade in list(self._active_trades.items()):
                if symbol not in broker_symbols:
                    # Position is gone → bracket order (TP or SL) must have filled
                    exit_price, exit_reason = await self._determine_exit_details(trade)

                    logger.info(
                        "Bracket fill detected! Position closed.",
                        symbol=symbol,
                        exit_price=exit_price,
                        exit_reason=exit_reason,
                    )

                    # Log to trades_log
                    if trade.db_trade_id is not None:
                        await trade_logger.log_trade_closed(
                            trade_id=trade.db_trade_id,
                            symbol=symbol,
                            qty=trade.qty,
                            entry_price=trade.entry_price,
                            exit_price=exit_price,
                            exit_time=now_utc(),
                            exit_reason=exit_reason,
                        )

                    self._active_trades.pop(symbol)
                    closed_symbols.append(symbol)

        except Exception as e:
            logger.error("Error checking bracket fills", error=str(e))

        return closed_symbols

    async def _determine_exit_details(
        self, trade: ActiveTradeRecord
    ) -> tuple[float, str]:
        """
        Determine how a trade was closed by checking recent Alpaca order history.
        Returns (exit_price, exit_reason).
        """
        try:
            # Look at recent closed/filled orders for this symbol
            raw_client = alpaca_trading_client._ensure_client()
            from alpaca.trading.requests import GetOrdersRequest
            from alpaca.trading.enums import QueryOrderStatus

            req = GetOrdersRequest(
                status=QueryOrderStatus.CLOSED,
                symbols=[trade.symbol.upper()],
                limit=10,
            )
            recent_orders = await asyncio.to_thread(
                lambda: raw_client.get_orders(filter=req)
            )

            for order in recent_orders:
                if order.status.value != "filled":
                    continue
                filled_price = float(order.filled_avg_price) if order.filled_avg_price else 0.0

                # Determine if this was TP or SL
                order_type = order.order_type.value if hasattr(order.order_type, "value") else str(order.order_type)

                if order_type == "limit" and filled_price > 0:
                    # Limit order filled → likely Take Profit
                    if filled_price >= trade.entry_price:
                        return filled_price, "take_profit"
                    else:
                        return filled_price, "strategy_exit"
                elif order_type == "stop" and filled_price > 0:
                    # Stop order filled → Stop Loss
                    return filled_price, "stop_loss"
                elif filled_price > 0:
                    # Market close or manual
                    return filled_price, "manual_exit"

        except Exception as e:
            logger.warning("Could not determine exit details from orders", error=str(e))

        # Fallback: estimate from bracket prices
        if trade.stop_loss > 0 and trade.take_profit > 0:
            # Can't determine which triggered, use mid-point estimate
            return trade.stop_loss, "stop_loss"

        return trade.entry_price, "unknown"

    async def evaluate_exit_conditions(
        self,
        df_1h_map: Dict[str, "pd.DataFrame"],
    ) -> List[str]:
        """
        Evaluate active exit conditions for tracked positions.
        Returns list of symbols that should be closed by the strategy.

        Exit conditions:
        1. Trend Reversal: EMA 20 crosses below EMA 50 on LTF
        2. RSI Overbought: RSI > 75 (momentum exhaustion)
        3. Time-based: Holding > 20 bars (~20 hours / ~3 trading days) without TP hit
        """
        exit_candidates: List[str] = []

        for symbol, trade in list(self._active_trades.items()):
            if symbol not in df_1h_map:
                continue

            df = df_1h_map[symbol]
            if df.empty or len(df) < 50:
                continue

            calc = technical_engine.calculate_indicators(df)
            curr = calc.iloc[-1]

            ema_20 = float(curr.get("ema_20", 0))
            ema_50 = float(curr.get("ema_50", 0))
            rsi = float(curr.get("rsi", 50))
            current_price = float(curr["close"])

            # Calculate holding duration (approximate bars since entry)
            holding_bars = len(df[df.index >= trade.entry_time]) if hasattr(df.index, '__len__') else 0

            exit_reason = None

            # Condition 0: Trailing Stop Breach — dynamic SL has been hit
            trailing_state = trailing_stop_manager.update(symbol, current_price)
            if trailing_state and trailing_stop_manager.should_exit(symbol, current_price):
                exit_reason = "trailing_stop"
                logger.info(
                    "Exit signal: Trailing stop breached",
                    symbol=symbol,
                    current_price=current_price,
                    trailing_sl=trailing_state.current_sl,
                )

            # Condition 1: Trend Reversal — EMA 20 crossed below EMA 50
            elif ema_20 > 0 and ema_50 > 0 and ema_20 < ema_50:
                exit_reason = "trend_reversal"
                logger.info(
                    "Exit signal: Trend reversal (EMA 20 < EMA 50)",
                    symbol=symbol,
                    ema_20=ema_20,
                    ema_50=ema_50,
                )

            # Condition 2: RSI Overbought (momentum exhaustion)
            elif rsi >= 75.0:
                exit_reason = "rsi_overbought"
                logger.info(
                    "Exit signal: RSI overbought",
                    symbol=symbol,
                    rsi=rsi,
                )

            # Condition 3: Time-based exit (holding too long without progress)
            elif holding_bars >= 20 and current_price <= trade.entry_price * 1.005:
                exit_reason = "time_based_exit"
                logger.info(
                    "Exit signal: Time-based (holding too long with no progress)",
                    symbol=symbol,
                    holding_bars=holding_bars,
                    current_price=current_price,
                    entry_price=trade.entry_price,
                )

            if exit_reason:
                exit_candidates.append(symbol)

        return exit_candidates

    async def execute_strategy_exit(self, symbol: str) -> bool:
        """
        Close a position via market sell order when strategy signals exit.
        """
        trade = self._active_trades.get(symbol.upper())
        if not trade:
            logger.warning("No active trade to exit", symbol=symbol)
            return False

        try:
            # 1. Cancel any remaining bracket legs (TP/SL orders)
            open_orders = await alpaca_trading_client.get_open_orders()
            for order in open_orders:
                if order.symbol.upper() == symbol.upper():
                    try:
                        await alpaca_trading_client.cancel_order_by_id(str(order.id))
                        logger.info("Cancelled bracket leg", order_id=str(order.id), symbol=symbol)
                    except Exception as e:
                        logger.warning("Failed to cancel bracket leg", error=str(e))

            # 2. Submit market sell order
            from alpaca.trading.requests import MarketOrderRequest
            from alpaca.trading.enums import OrderSide, TimeInForce

            sell_req = MarketOrderRequest(
                symbol=symbol.upper(),
                qty=trade.qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.GTC,
            )

            raw_client = alpaca_trading_client._ensure_client()
            sell_order = await asyncio.to_thread(raw_client.submit_order, sell_req)

            # 3. Wait for fill
            alpaca_id = str(sell_order.id)
            start = asyncio.get_event_loop().time()
            exit_price = trade.entry_price  # fallback

            while (asyncio.get_event_loop().time() - start) < 30:
                order_status = await asyncio.to_thread(
                    raw_client.get_order_by_id, alpaca_id
                )
                status = order_status.status.value if hasattr(order_status.status, "value") else str(order_status.status)
                if status in ("filled", "partially_filled"):
                    exit_price = float(order_status.filled_avg_price or trade.entry_price)
                    break
                elif status in ("canceled", "rejected", "expired"):
                    logger.error("Strategy exit order failed", symbol=symbol, status=status)
                    return False
                await asyncio.sleep(1.0)

            # 4. Log trade close
            if trade.db_trade_id is not None:
                await trade_logger.log_trade_closed(
                    trade_id=trade.db_trade_id,
                    symbol=symbol,
                    qty=trade.qty,
                    entry_price=trade.entry_price,
                    exit_price=exit_price,
                    exit_time=now_utc(),
                    exit_reason="strategy_exit",
                )

            self._active_trades.pop(symbol.upper(), None)
            logger.info(
                "Strategy exit executed successfully",
                symbol=symbol,
                exit_price=exit_price,
            )
            return True

        except Exception as e:
            logger.error("Failed to execute strategy exit", symbol=symbol, error=str(e))
            return False


# Global Position Manager singleton
position_manager = PositionManager()
