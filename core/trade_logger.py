"""
Trade Logger Module
Persists all order submissions, fill events, and completed trades to PostgreSQL.
This module bridges Order Execution Engine → Database, enabling:
- Daily P/L calculation from trades_log
- Max Daily Loss enforcement (Risk Engine reads trades_log)
- Performance tracking & historical analysis

Without this module, trades_log stays empty and critical safety checks fail.
See UNIFIED_PLAN.md Section 4.7, Section 5.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import json
import structlog

from db.connection import db_manager
from notifications import dispatcher
from utils.timezone import now_utc, format_multi_tz_display

logger = structlog.get_logger(__name__)


@dataclass
class ActiveTradeRecord:
    """Tracks an open trade that is waiting for TP/SL fill."""
    db_trade_id: Optional[int]
    db_order_id: Optional[int]
    symbol: str
    side: str
    qty: float
    entry_price: float
    entry_time: datetime
    take_profit: float
    stop_loss: float
    alpaca_order_id: str
    client_order_id: str
    strategy_name: str = "SwingTrendPullback"


class TradeLogger:
    """Persists order events and trade completions to PostgreSQL."""

    async def log_order_submitted(
        self,
        alpaca_order_id: str,
        client_order_id: str,
        symbol: str,
        side: str,
        qty: float,
        status: str,
        filled_qty: float = 0.0,
        filled_avg_price: float = 0.0,
        take_profit_price: float = 0.0,
        stop_loss_price: float = 0.0,
    ) -> Optional[int]:
        """
        Record a submitted order into the `orders` table.
        Returns the DB record ID if successful.
        """
        if not db_manager.is_connected:
            logger.warning("DB not connected; order log skipped", symbol=symbol)
            return None

        try:
            order_db_id = await db_manager.fetchval(
                """
                INSERT INTO orders (
                    alpaca_order_id, client_order_id, symbol, side,
                    order_type, qty, filled_qty, status, bracket_role
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING id
                """,
                alpaca_order_id,
                client_order_id,
                symbol.upper(),
                side.lower(),
                "market",
                qty,
                filled_qty,
                status,
                "entry",
            )
            logger.info(
                "Order logged to DB",
                db_id=order_db_id,
                symbol=symbol,
                alpaca_id=alpaca_order_id,
            )
            return order_db_id
        except Exception as e:
            logger.error("Failed to log order to DB", symbol=symbol, error=str(e))
            return None

    async def log_order_filled(
        self,
        alpaca_order_id: str,
        filled_qty: float,
        filled_avg_price: float,
    ) -> None:
        """Update order record when fill is confirmed."""
        if not db_manager.is_connected:
            return

        try:
            await db_manager.execute(
                """
                UPDATE orders SET
                    status = 'filled',
                    filled_qty = $2,
                    filled_at = NOW()
                WHERE alpaca_order_id = $1
                """,
                alpaca_order_id,
                filled_qty,
            )
        except Exception as e:
            logger.error("Failed to update order fill in DB", error=str(e))

    async def log_trade_opened(
        self,
        symbol: str,
        side: str,
        qty: float,
        entry_price: float,
        entry_time: datetime,
        take_profit: float,
        stop_loss: float,
        alpaca_order_id: str,
        strategy_name: str = "SwingTrendPullback",
    ) -> Optional[ActiveTradeRecord]:
        """
        Record a new open trade entry into `trades_log` with exit fields as placeholders.
        The trade is marked as open (exit_price = 0, exit_time = entry_time as placeholder).
        When the trade closes (TP/SL triggered), we UPDATE with real exit data.
        """
        if not db_manager.is_connected:
            logger.warning("DB not connected; trade open log skipped", symbol=symbol)
            return ActiveTradeRecord(
                db_trade_id=None,
                db_order_id=None,
                symbol=symbol,
                side=side,
                qty=qty,
                entry_price=entry_price,
                entry_time=entry_time,
                take_profit=take_profit,
                stop_loss=stop_loss,
                alpaca_order_id=alpaca_order_id,
                client_order_id="",
                strategy_name=strategy_name,
            )

        try:
            # Insert with placeholder exit values (will be updated on close)
            trade_id = await db_manager.fetchval(
                """
                INSERT INTO trades_log (
                    symbol, side, qty, entry_price, exit_price,
                    gross_pnl, net_pnl, entry_time, exit_time,
                    exit_reason, strategy_name
                )
                VALUES ($1, $2, $3, $4, 0.0, 0.0, 0.0, $5, $5, 'open', $6)
                RETURNING id
                """,
                symbol.upper(),
                side.lower(),
                qty,
                entry_price,
                entry_time,
                strategy_name,
            )
            logger.info(
                "Trade opened and logged to DB",
                trade_id=trade_id,
                symbol=symbol,
                entry_price=entry_price,
                tp=take_profit,
                sl=stop_loss,
            )
            return ActiveTradeRecord(
                db_trade_id=trade_id,
                db_order_id=None,
                symbol=symbol,
                side=side,
                qty=qty,
                entry_price=entry_price,
                entry_time=entry_time,
                take_profit=take_profit,
                stop_loss=stop_loss,
                alpaca_order_id=alpaca_order_id,
                client_order_id="",
                strategy_name=strategy_name,
            )
        except Exception as e:
            logger.error("Failed to log trade open to DB", symbol=symbol, error=str(e))
            return None

    async def log_trade_closed(
        self,
        trade_id: int,
        symbol: str,
        qty: float,
        entry_price: float,
        exit_price: float,
        exit_time: datetime,
        exit_reason: str,
    ) -> None:
        """
        Update a trade in `trades_log` with actual exit data when TP/SL triggers.
        Calculates realized P&L.
        """
        gross_pnl = round((exit_price - entry_price) * qty, 4)
        net_pnl = gross_pnl  # Zero commission on Alpaca

        if not db_manager.is_connected:
            logger.warning(
                "DB not connected; trade close log skipped",
                symbol=symbol,
                gross_pnl=gross_pnl,
            )
            return

        try:
            await db_manager.execute(
                """
                UPDATE trades_log SET
                    exit_price = $2,
                    gross_pnl = $3,
                    net_pnl = $4,
                    exit_time = $5,
                    exit_reason = $6
                WHERE id = $1
                """,
                trade_id,
                exit_price,
                gross_pnl,
                net_pnl,
                exit_time,
                exit_reason,
            )
            logger.info(
                "Trade closed and updated in DB",
                trade_id=trade_id,
                symbol=symbol,
                exit_price=exit_price,
                exit_reason=exit_reason,
                net_pnl=net_pnl,
            )
        except Exception as e:
            logger.error(
                "Failed to log trade close to DB",
                trade_id=trade_id,
                error=str(e),
            )

        # Notify Telegram of trade closure
        try:
            pl_sign = "+" if net_pnl >= 0 else ""
            emoji = "🟢" if net_pnl >= 0 else "🔴"
            reason_label = {
                "take_profit": "ถึงเป้าทำกำไร (TP)",
                "stop_loss": "ถึงจุดตัดขาดทุน (SL)",
                "gap_stop_loss": "Gap ข้ามคืน (ราคาเปิด < SL)",
                "strategy_exit": "กลยุทธ์สั่งปิด",
                "manual_exit": "ปิดด้วยตนเอง",
            }.get(exit_reason, exit_reason)

            close_msg = (
                f"{emoji} <b>ปิด Position สำเร็จ: {symbol.upper()}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"• <b>เหตุผล:</b> {reason_label}\n"
                f"• <b>จำนวน:</b> {qty:.4f} หุ้น\n"
                f"• <b>ราคาเข้า:</b> ${entry_price:.2f}\n"
                f"• <b>ราคาออก:</b> ${exit_price:.2f}\n"
                f"• <b>กำไร/ขาดทุน:</b> <b>{pl_sign}${net_pnl:.2f}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━"
            )
            await dispatcher.notify_trade(
                symbol=symbol,
                action=f"CLOSE ({exit_reason})",
                details={
                    "qty": qty,
                    "price": f"${exit_price:.2f}",
                    "pnl": f"{pl_sign}${net_pnl:.2f}",
                },
            )
        except Exception as e:
            logger.warning("Failed to notify trade close", error=str(e))


# Global Trade Logger singleton
trade_logger = TradeLogger()
