"""
System Health Check & Heartbeat Monitor
Monitors runtime health, API latencies, DB responsiveness, and issues periodic heartbeats.
See UNIFIED_PLAN.md Section 8 & Section 11.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
import time
from typing import Any, Dict, Optional
import structlog

from core.alpaca_client import alpaca_trading_client
from core.failsafe import safe_mode_manager
from core.risk_engine import risk_engine
from db.connection import db_manager
from notifications import dispatcher
from utils.timezone import now_utc, format_multi_tz_display

logger = structlog.get_logger(__name__)


@dataclass
class ComponentHealth:
    name: str
    is_healthy: bool
    latency_ms: float
    details: str


@dataclass
class SystemHealthReport:
    timestamp: datetime
    overall_healthy: bool
    components: Dict[str, ComponentHealth]
    safe_mode_state: str
    kill_switch_active: bool


class HealthMonitor:
    """Performs proactive diagnostics and dispatches heartbeats."""

    async def check_alpaca(self) -> ComponentHealth:
        """Measure Alpaca API clock ping latency."""
        start = time.perf_counter()
        try:
            clock = await alpaca_trading_client.get_clock()
            latency = (time.perf_counter() - start) * 1000.0
            status_desc = f"Market {'Open' if clock.is_open else 'Closed'}"
            safe_mode_manager.record_success()
            return ComponentHealth(
                name="Alpaca Broker API",
                is_healthy=True,
                latency_ms=round(latency, 2),
                details=status_desc,
            )
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000.0
            err_msg = str(e)
            await safe_mode_manager.record_error("AlpacaPingError", err_msg)
            return ComponentHealth(
                name="Alpaca Broker API",
                is_healthy=False,
                latency_ms=round(latency, 2),
                details=f"Error: {err_msg}",
            )

    async def check_database(self) -> ComponentHealth:
        """Check PostgreSQL database pool connectivity."""
        if not db_manager.is_connected:
            try:
                await db_manager.connect()
            except Exception:
                pass

        if not db_manager.is_connected:
            return ComponentHealth(
                name="PostgreSQL Database",
                is_healthy=False,
                latency_ms=0.0,
                details="Offline / Disconnected",
            )

        start = time.perf_counter()
        try:
            val = await db_manager.fetchval("SELECT 1")
            latency = (time.perf_counter() - start) * 1000.0
            is_ok = val == 1
            return ComponentHealth(
                name="PostgreSQL Database",
                is_healthy=is_ok,
                latency_ms=round(latency, 2),
                details="Connected & Responsive" if is_ok else "Unexpected response",
            )
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000.0
            return ComponentHealth(
                name="PostgreSQL Database",
                is_healthy=False,
                latency_ms=round(latency, 2),
                details=f"DB Ping Failed: {e}",
            )

    async def run_diagnostics(self) -> SystemHealthReport:
        """Run all diagnostic checks."""
        alpaca_health = await self.check_alpaca()
        db_health = await self.check_database()

        components = {
            "alpaca": alpaca_health,
            "database": db_health,
        }

        overall_healthy = (
            alpaca_health.is_healthy
            and not safe_mode_manager.is_safe_mode
            and not risk_engine.is_kill_switched
        )

        report = SystemHealthReport(
            timestamp=now_utc(),
            overall_healthy=overall_healthy,
            components=components,
            safe_mode_state=safe_mode_manager.state.value,
            kill_switch_active=risk_engine.is_kill_switched,
        )

        logger.info(
            "Health check completed",
            overall_healthy=overall_healthy,
            alpaca_ms=alpaca_health.latency_ms,
            db_ms=db_health.latency_ms,
            state=report.safe_mode_state,
        )
        return report

    async def send_heartbeat(self) -> SystemHealthReport:
        """
        Execute diagnostics and dispatch Telegram heartbeat message.
        Useful for scheduled cron or periodic health pings.
        """
        report = await self.run_diagnostics()
        tz_time = format_multi_tz_display(report.timestamp)
        emoji = "💚" if report.overall_healthy else "💛"
        alpaca_h = report.components["alpaca"]
        db_h = report.components["database"]

        status_text = "ทำงานปกติ (OPERATIONAL)" if report.overall_healthy else "ต้องตรวจสอบ (ATTENTION NEEDED)"
        kill_switch_text = "เปิดใช้งานฉุกเฉิน 🚨" if report.kill_switch_active else "ปิดอยู่ (ปลอดภัย 🛡️)"
        alpaca_status = f"ปกติ ({alpaca_h.latency_ms:.1f}ms - {alpaca_h.details})" if alpaca_h.is_healthy else f"ขัดข้อง ({alpaca_h.details})"

        msg = (
            f"{emoji} <b>สัญญาณชีพตรวจเช็คระบบ (SYSTEM HEARTBEAT)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>สถานะรวม:</b> {status_text}\n"
            f"• <b>โหมดความปลอดภัย:</b> {report.safe_mode_state}\n"
            f"• <b>คิลสวิตช์:</b> {kill_switch_text}\n"
            f"• <b>Alpaca Broker API:</b> {alpaca_status}\n"
            f"• <b>Database (PostgreSQL):</b> {db_h.details} ({db_h.latency_ms:.1f}ms)\n"
            f"• <b>เวลา:</b> {tz_time}\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        )

        try:
            if report.overall_healthy:
                await dispatcher.notify_info(msg)
            else:
                await dispatcher.notify_warning(msg)
        except Exception as e:
            logger.error("Failed to send heartbeat message", error=str(e))

        return report


# Global Health Monitor singleton
health_monitor = HealthMonitor()
