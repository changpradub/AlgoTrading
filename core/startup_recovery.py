"""
Startup Recovery Engine
Automated reconciliation and sanity checks executed upon bot boot/reboot.
Enforces:
1. Broker & DB connectivity validation
2. Account & Position state reconciliation (No Order Without Reconcile)
3. Pattern Day Trading (PDT) quota verification (< $25,000 equity)
4. Overnight Gap Risk assessment on open positions
5. Automated Telegram Startup Health Report
See UNIFIED_PLAN.md Section 4.8 & Section 8.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
import structlog

from core.alpaca_client import alpaca_trading_client
from core.failsafe import safe_mode_manager
from core.risk_engine import risk_engine
from core.state_manager import state_manager, ReconciliationReport
from db.connection import db_manager
from notifications import dispatcher
from utils.timezone import now_utc, format_multi_tz_display

logger = structlog.get_logger(__name__)


@dataclass
class GapRiskAlert:
    symbol: str
    qty: float
    avg_entry_price: float
    current_price: float
    unrealized_pl: float
    unrealized_plpc: float
    warning_message: str


@dataclass
class StartupRecoveryReport:
    timestamp: datetime
    broker_connected: bool
    db_connected: bool
    equity: float
    buying_power: float
    pdt_daytrade_count: int
    pdt_allowed_remaining: int
    open_positions_count: int
    open_orders_count: int
    reconciliation_report: Optional[ReconciliationReport]
    gap_alerts: List[GapRiskAlert] = field(default_factory=list)
    system_ready: bool = False
    notes: List[str] = field(default_factory=list)


class StartupRecoveryEngine:
    """Executes safe startup reconciliation sequence."""

    async def run_recovery(self) -> StartupRecoveryReport:
        """
        Execute full 5-step startup recovery sequence.
        Returns StartupRecoveryReport and dispatches Telegram notification.
        """
        boot_time = now_utc()
        notes: List[str] = []
        gap_alerts: List[GapRiskAlert] = []

        logger.info("Initializing Startup Recovery sequence...")

        # Step 1: Connectivity Checks
        broker_connected = False
        db_connected = db_manager.is_connected
        account = None

        try:
            account = await alpaca_trading_client.get_account()
            broker_connected = True
            logger.info("Alpaca connection verified", status=account.status)
        except Exception as e:
            err_msg = f"Failed to connect to Alpaca during startup: {e}"
            logger.error(err_msg)
            notes.append(f"❌ Broker connection failed: {e}")
            await safe_mode_manager.enter_safe_mode(err_msg)

        if not db_connected:
            notes.append("ℹ️ Database running in standalone/unconnected mode.")

        # Step 2: State Reconciliation (if broker connected)
        reconcile_report: Optional[ReconciliationReport] = None
        open_positions = []
        open_orders = []

        if broker_connected and account is not None:
            try:
                reconcile_report = await state_manager.reconcile_state()
                open_positions = await alpaca_trading_client.get_all_positions()
                open_orders = await alpaca_trading_client.get_open_orders()
                notes.append(f"✅ Reconciled with Alpaca: {len(open_positions)} positions, {len(open_orders)} open orders.")
            except Exception as e:
                err_msg = f"State reconciliation failed: {e}"
                logger.error(err_msg)
                notes.append(f"⚠️ Reconciliation error: {e}")
                await safe_mode_manager.enter_safe_mode(err_msg)

        equity = float(account.equity) if account else 0.0
        buying_power = float(account.buying_power) if account else 0.0
        pdt_count = int(account.daytrade_count) if (account and account.daytrade_count is not None) else 0
        pdt_remaining = max(0, 3 - pdt_count)

        # Step 3: Pattern Day Trading (PDT) Check
        if equity < 25000.0:
            if pdt_count >= 3:
                notes.append(f"⚠️ PDT Quota Exhausted ({pdt_count}/3). Same-day closes strictly prohibited!")
            else:
                notes.append(f"🛡️ PDT Check: {pdt_count}/3 used. {pdt_remaining} day-trade(s) remaining.")
        else:
            notes.append("🛡️ PDT Check: Exempt (Equity >= $25,000).")

        # Step 4: Overnight Gap Risk Assessment on Open Positions
        if open_positions:
            for p in open_positions:
                try:
                    qty = float(p.qty)
                    entry_price = float(p.avg_entry_price)
                    current_price = float(p.current_price)
                    unrealized_pl = float(p.unrealized_pl)
                    unrealized_plpc = float(p.unrealized_plpc) * 100.0  # as percentage

                    # Alert if position has dropped > 3% overnight
                    if unrealized_plpc <= -3.0:
                        warn = (
                            f"Overnight adverse move on {p.symbol}: {unrealized_plpc:.2f}% "
                            f"(Unrealized: ${unrealized_pl:.2f})"
                        )
                        gap_alerts.append(
                            GapRiskAlert(
                                symbol=p.symbol,
                                qty=qty,
                                avg_entry_price=entry_price,
                                current_price=current_price,
                                unrealized_pl=unrealized_pl,
                                unrealized_plpc=unrealized_plpc,
                                warning_message=warn,
                            )
                        )
                        notes.append(f"⚠️ {warn}")
                except Exception as e:
                    logger.error("Error assessing gap risk for position", symbol=p.symbol, error=str(e))

        # Step 5: Ready State Evaluation
        system_ready = broker_connected and not safe_mode_manager.is_safe_mode and not risk_engine.is_kill_switched

        report = StartupRecoveryReport(
            timestamp=boot_time,
            broker_connected=broker_connected,
            db_connected=db_connected,
            equity=equity,
            buying_power=buying_power,
            pdt_daytrade_count=pdt_count,
            pdt_allowed_remaining=pdt_remaining,
            open_positions_count=len(open_positions),
            open_orders_count=len(open_orders),
            reconciliation_report=reconcile_report,
            gap_alerts=gap_alerts,
            system_ready=system_ready,
            notes=notes,
        )

        # Dispatch Telegram Startup Report
        await self._dispatch_startup_notification(report)
        logger.info("Startup Recovery completed successfully", system_ready=system_ready)
        return report

    async def _dispatch_startup_notification(self, report: StartupRecoveryReport) -> None:
        """Format and dispatch the startup report to Telegram."""
        tz_time = format_multi_tz_display(report.timestamp)
        status_emoji = "🟢" if report.system_ready else "🔴"
        status_text = "READY FOR TRADING" if report.system_ready else "HALTED / SAFE MODE"

        gap_section = ""
        if report.gap_alerts:
            gap_section = "\n*⚠️ Overnight Gap Risk Alerts:*\n"
            for g in report.gap_alerts:
                gap_section += f"  • {g.symbol}: {g.unrealized_plpc:+.2f}% (${g.unrealized_pl:+.2f})\n"

        notes_section = "\n".join([f"• {n}" for n in report.notes])

        message = (
            f"{status_emoji} *ALGO-TRADING BOT: STARTUP RECOVERY REPORT*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"• *Status:* {status_text}\n"
            f"• *Time:* {tz_time}\n"
            f"• *Equity:* ${report.equity:,.2f} | *Cash BP:* ${report.buying_power:,.2f}\n"
            f"• *PDT Status:* {report.pdt_daytrade_count}/3 used ({report.pdt_allowed_remaining} left)\n"
            f"• *Active Positions:* {report.open_positions_count}\n"
            f"• *Pending Orders:* {report.open_orders_count}\n"
            f"{gap_section}"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"*System Diagnostic:*\n"
            f"{notes_section}\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        )

        try:
            if report.system_ready:
                await dispatcher.notify_info(message)
            else:
                await dispatcher.notify_warning(message)
        except Exception as e:
            logger.error("Failed to send startup recovery notification", error=str(e))


# Global Startup Recovery singleton
startup_recovery_engine = StartupRecoveryEngine()
