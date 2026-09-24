"""
Daily Performance & Summary Reporter Module
Calculates daily trading performance, Realized & Unrealized P/L,
Win/Loss statistics, overnight positions, and sends a structured
summary report in Thai to Telegram when the market closes.
See UNIFIED_PLAN.md Section 4.9 & Section 6.
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any, Dict, List, Optional
import structlog

from core.alpaca_client import alpaca_trading_client
from db.connection import db_manager
from notifications import dispatcher
from utils.timezone import now_utc, to_eastern, format_multi_tz_display

logger = structlog.get_logger(__name__)


@dataclass
class PositionSummary:
    symbol: str
    qty: float
    avg_entry_price: float
    current_price: float
    market_value: float
    unrealized_pl: float
    unrealized_plpc: float


@dataclass
class DailySummaryReport:
    report_date: date
    timestamp_utc: datetime
    equity: float
    cash: float
    buying_power: float
    daily_realized_pl: float
    daily_unrealized_pl: float
    total_daily_pl: float
    daily_return_pct: float
    trades_count: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    pdt_daytrade_count: int
    open_positions: List[PositionSummary] = field(default_factory=list)


class DailyReporter:
    """Computes daily trading performance and delivers Telegram summaries at market close."""

    async def generate_daily_summary(self) -> DailySummaryReport:
        """Fetch live account, positions, and query database for completed trades today."""
        now = now_utc()
        et_today = to_eastern(now).date()

        # 1. Fetch live account from Alpaca
        account = await alpaca_trading_client.get_account()
        equity = float(account.equity)
        cash = float(account.cash)
        buying_power = float(account.buying_power)
        pdt_count = int(account.daytrade_count) if account.daytrade_count is not None else 0

        # Calculate daily change from Alpaca account if available
        last_equity = float(getattr(account, "last_equity", equity))
        daily_total_diff = equity - last_equity
        daily_return_pct = (daily_total_diff / last_equity * 100.0) if last_equity > 0 else 0.0

        # 2. Fetch live open positions
        positions = await alpaca_trading_client.get_all_positions()
        open_positions: List[PositionSummary] = []
        total_unrealized_pl = 0.0

        for p in positions:
            u_pl = float(p.unrealized_pl)
            total_unrealized_pl += u_pl
            open_positions.append(
                PositionSummary(
                    symbol=p.symbol.upper(),
                    qty=float(p.qty),
                    avg_entry_price=float(p.avg_entry_price),
                    current_price=float(p.current_price),
                    market_value=float(p.market_value),
                    unrealized_pl=u_pl,
                    unrealized_plpc=float(p.unrealized_plpc) * 100.0,
                )
            )

        # 3. Query DB for closed trades today
        realized_pl = 0.0
        trades_count = 0
        winning_trades = 0
        losing_trades = 0

        if db_manager.is_connected:
            try:
                rows = await db_manager.fetch(
                    """
                    SELECT net_pnl
                    FROM trades_log
                    WHERE exit_time >= CURRENT_DATE AND exit_time IS NOT NULL
                    """
                )
                trades_count = len(rows)
                for r in rows:
                    pnl = float(r["net_pnl"])
                    realized_pl += pnl
                    if pnl > 0:
                        winning_trades += 1
                    elif pnl < 0:
                        losing_trades += 1
            except Exception as e:
                logger.warning("Could not query today's trades from trades_log", error=str(e))

        win_rate = (winning_trades / trades_count * 100.0) if trades_count > 0 else 0.0

        realized_pl = round(realized_pl, 2)
        total_unrealized_pl = round(total_unrealized_pl, 2)
        daily_total_diff = round(daily_total_diff, 2)

        return DailySummaryReport(
            report_date=et_today,
            timestamp_utc=now,
            equity=equity,
            cash=cash,
            buying_power=buying_power,
            daily_realized_pl=realized_pl,
            daily_unrealized_pl=total_unrealized_pl,
            total_daily_pl=daily_total_diff if daily_total_diff != 0 else round(realized_pl + total_unrealized_pl, 2),
            daily_return_pct=round(daily_return_pct, 2),
            trades_count=trades_count,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate_pct=round(win_rate, 2),
            pdt_daytrade_count=pdt_count,
            open_positions=open_positions,
        )

    async def dispatch_daily_summary(self) -> DailySummaryReport:
        """Generate and dispatch daily summary report to Telegram."""
        summary = await self.generate_daily_summary()
        time_str = format_multi_tz_display(summary.timestamp_utc)

        pl_sign = "+" if summary.total_daily_pl >= 0 else ""
        pct_sign = "+" if summary.daily_return_pct >= 0 else ""
        header_emoji = "🟢" if summary.total_daily_pl >= 0 else "🔴"

        # Format open positions section
        positions_lines = ""
        if summary.open_positions:
            positions_lines = "\n📈 <b>หุ้นที่ถือครองข้ามคืน (Overnight Positions):</b>\n"
            for p in summary.open_positions:
                pos_pl_sign = "+" if p.unrealized_pl >= 0 else ""
                positions_lines += (
                    f"• <b>{p.symbol}</b>: {p.qty:.4f} หุ้น | ทุน ${p.avg_entry_price:.2f} | ปัจจุบัน ${p.current_price:.2f}\n"
                    f"  กำไร/ขาดทุน: <b>{pos_pl_sign}${p.unrealized_pl:.2f} ({pos_pl_sign}{p.unrealized_plpc:.2f}%)</b>\n"
                )
        else:
            positions_lines = "\n💼 <i>ไม่มีหุ้นถือครองค้างคืน (100% Cash)</i>\n"

        message = (
            f"{header_emoji} <b>สรุปผลการเทรดประจำวัน (DAILY P/L SUMMARY)</b>\n"
            f"<code>{time_str}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>มูลค่าพอร์ตสุทธิ (Equity):</b> ${summary.equity:,.2f}\n"
            f"• <b>กำลังซื้อ (Buying Power):</b> ${summary.buying_power:,.2f}\n"
            f"• <b>ผลตอบแทนวันนี้:</b> <b>{pl_sign}${summary.total_daily_pl:,.2f} ({pct_sign}{summary.daily_return_pct:.2f}%)</b>\n"
            f"  - กำไรรับรู้แล้ว (Realized): ${summary.daily_realized_pl:,.2f}\n"
            f"  - กำไรยังไม่ปิด (Unrealized): ${summary.daily_unrealized_pl:,.2f}\n"
            f"• <b>คำสั่งที่ปิดวันนี้:</b> {summary.trades_count} ไม้ (ชนะ {summary.winning_trades} / แพ้ {summary.losing_trades})\n"
            f"• <b>Win Rate:</b> {summary.win_rate_pct:.1f}%\n"
            f"• <b>โควตา Day Trade (PDT):</b> ใช้ไป {summary.pdt_daytrade_count}/3 ครั้ง\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
            f"{positions_lines}"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🛡️ <i>ตลาดปิดทำการแล้ว บอทเข้าสู่โหมดสแตนด์บาย (Idle)</i>"
        )

        try:
            await dispatcher.notify_info(message)
            logger.info("Daily P/L summary dispatched to Telegram successfully", equity=summary.equity)
        except Exception as e:
            logger.error("Failed to dispatch daily summary notification", error=str(e))

        return summary


# Global Daily Reporter singleton
daily_reporter = DailyReporter()
