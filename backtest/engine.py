"""
Backtesting Engine Module
Simulates strategy execution over historical data with realistic Bracket Orders,
Slippage modeling, and Overnight Gap Risk simulation.
See UNIFIED_PLAN.md Section 4.5 & Phase 2.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
import pandas as pd
import structlog

from core.position_sizing import position_calculator
from core.strategy import BaseStrategy, SignalType, swing_strategy

logger = structlog.get_logger(__name__)


@dataclass
class BacktestTrade:
    symbol: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    qty: float
    gross_pnl: float
    net_pnl: float
    return_pct: float
    exit_reason: str  # 'take_profit', 'stop_loss', 'gap_stop_loss'
    holding_bars: int


@dataclass
class BacktestResult:
    symbol: str
    initial_capital: float
    final_equity: float
    total_net_pnl: float
    total_return_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    profit_factor: float
    max_drawdown_pct: float
    avg_trade_pnl: float
    trades: List[BacktestTrade] = field(default_factory=list)


class BacktestEngine:
    """Event-driven bar-by-bar backtesting engine."""

    def __init__(
        self,
        initial_capital: float = 700.0,
        slippage_pct: float = 0.001,  # 0.1% execution slippage
        commission_per_trade: float = 0.0,  # Zero commission (Alpaca)
        strategy: Optional[BaseStrategy] = None,
    ):
        self.initial_capital = initial_capital
        self.slippage_pct = slippage_pct
        self.commission_per_trade = commission_per_trade
        self.strategy = strategy or swing_strategy

    def run(
        self,
        symbol: str,
        df_ltf: pd.DataFrame,
        df_htf: Optional[pd.DataFrame] = None,
        warmup_bars: int = 100,
    ) -> BacktestResult:
        """
        Run backtest on OHLCV DataFrame with slippage and gap simulation.
        """
        if len(df_ltf) <= warmup_bars:
            raise ValueError(f"Data length ({len(df_ltf)}) is insufficient for warmup ({warmup_bars}).")

        equity = self.initial_capital
        peak_equity = equity
        max_drawdown_pct = 0.0

        trades: List[BacktestTrade] = []
        active_position: Optional[dict] = None

        # Iterate bar by bar starting after warmup
        for i in range(warmup_bars, len(df_ltf)):
            current_bar = df_ltf.iloc[i]
            prev_bar = df_ltf.iloc[i - 1]
            timestamp = df_ltf.index[i]
            prev_timestamp = df_ltf.index[i - 1]

            # 1. Manage Active Position (Exit Check)
            if active_position is not None:
                active_position["holding_bars"] += 1
                sl = active_position["stop_loss"]
                tp = active_position["take_profit"]
                qty = active_position["qty"]
                entry_price = active_position["entry_price"]

                exit_price = None
                exit_reason = None

                # Check Overnight Gap Risk (First bar of new day)
                is_new_day = timestamp.date() > prev_timestamp.date()
                if is_new_day and current_bar["open"] < sl:
                    # Gapped down below Stop Loss! Exit at market open price (worse than SL)
                    exit_price = float(current_bar["open"]) * (1.0 - self.slippage_pct)
                    exit_reason = "gap_stop_loss"

                # Standard Stop Loss check
                elif current_bar["low"] <= sl:
                    exit_price = sl * (1.0 - self.slippage_pct)
                    exit_reason = "stop_loss"

                # Standard Take Profit check
                elif current_bar["high"] >= tp:
                    exit_price = tp * (1.0 - self.slippage_pct)
                    exit_reason = "take_profit"

                if exit_price is not None and exit_reason is not None:
                    gross_pnl = (exit_price - entry_price) * qty
                    net_pnl = gross_pnl - (self.commission_per_trade * 2)
                    ret_pct = ((exit_price - entry_price) / entry_price) * 100.0

                    trade = BacktestTrade(
                        symbol=symbol,
                        entry_time=active_position["entry_time"],
                        exit_time=timestamp,
                        entry_price=entry_price,
                        exit_price=round(exit_price, 2),
                        qty=qty,
                        gross_pnl=round(gross_pnl, 2),
                        net_pnl=round(net_pnl, 2),
                        return_pct=round(ret_pct, 2),
                        exit_reason=exit_reason,
                        holding_bars=active_position["holding_bars"],
                    )
                    trades.append(trade)
                    equity += net_pnl
                    peak_equity = max(peak_equity, equity)
                    active_position = None

            # Track Drawdown
            dd_pct = ((peak_equity - equity) / peak_equity) * 100.0 if peak_equity > 0 else 0.0
            max_drawdown_pct = max(max_drawdown_pct, dd_pct)

            # 2. Check for New Entry Signal if flat
            if active_position is None:
                # Slice historical view up to current bar to prevent lookahead bias
                df_slice = df_ltf.iloc[: i + 1]

                # Align HTF slice if provided
                htf_slice = None
                if df_htf is not None and not df_htf.empty:
                    htf_slice = df_htf[df_htf.index <= timestamp]

                signal = self.strategy.evaluate(symbol, df_slice, htf_slice)

                if signal.signal_type == SignalType.BUY:
                    # Calculate position size with slippage
                    actual_entry_price = signal.entry_price * (1.0 + self.slippage_pct)
                    size_res = position_calculator.calculate(
                        equity=equity,
                        buying_power=equity,
                        entry_price=actual_entry_price,
                        stop_loss=signal.stop_loss,
                    )

                    if size_res.is_valid and size_res.shares > 0:
                        active_position = {
                            "symbol": symbol,
                            "entry_time": timestamp,
                            "entry_price": actual_entry_price,
                            "qty": size_res.shares,
                            "stop_loss": signal.stop_loss,
                            "take_profit": signal.take_profit,
                            "holding_bars": 0,
                        }

        # 3. Compile Performance Metrics
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t.net_pnl > 0)
        losing_trades = sum(1 for t in trades if t.net_pnl <= 0)
        win_rate = (winning_trades / total_trades * 100.0) if total_trades > 0 else 0.0

        gross_profits = sum(t.net_pnl for t in trades if t.net_pnl > 0)
        gross_losses = abs(sum(t.net_pnl for t in trades if t.net_pnl < 0))
        profit_factor = (gross_profits / gross_losses) if gross_losses > 0 else (gross_profits if gross_profits > 0 else 1.0)

        total_net_pnl = equity - self.initial_capital
        total_return_pct = (total_net_pnl / self.initial_capital) * 100.0
        avg_trade_pnl = (total_net_pnl / total_trades) if total_trades > 0 else 0.0

        return BacktestResult(
            symbol=symbol,
            initial_capital=self.initial_capital,
            final_equity=round(equity, 2),
            total_net_pnl=round(total_net_pnl, 2),
            total_return_pct=round(total_return_pct, 2),
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate_pct=round(win_rate, 2),
            profit_factor=round(profit_factor, 2),
            max_drawdown_pct=round(max_drawdown_pct, 2),
            avg_trade_pnl=round(avg_trade_pnl, 2),
            trades=trades,
        )
