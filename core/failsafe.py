"""
Fail-Safe & Emergency Mode Manager Module
Manages system degradation states: NORMAL, SAFE_MODE, and KILL_SWITCH.
Guarantees resilience against API outages, repeated runtime errors, and unexpected volatility.
See UNIFIED_PLAN.md Section 4.5 & Section 8.
"""

from datetime import datetime
from enum import Enum
import json
from typing import Any, Dict, Optional
import structlog

from core.alpaca_client import alpaca_trading_client
from core.risk_engine import risk_engine
from db.connection import db_manager
from notifications import dispatcher
from utils.timezone import now_utc, format_multi_tz_display

logger = structlog.get_logger(__name__)


class SystemState(str, Enum):
    NORMAL = "NORMAL"
    SAFE_MODE = "SAFE_MODE"
    KILL_SWITCH = "KILL_SWITCH"


class SafeModeManager:
    """
    Coordinates fail-safe triggers, rate-limit backoff defenses,
    and the emergency Kill Switch.
    """

    def __init__(self, max_consecutive_errors: int = 3):
        self.state: SystemState = SystemState.NORMAL
        self.consecutive_errors: int = 0
        self.max_consecutive_errors = max_consecutive_errors
        self.reason: Optional[str] = None
        self.activated_at: Optional[datetime] = None

    @property
    def is_safe_mode(self) -> bool:
        return self.state == SystemState.SAFE_MODE

    @property
    def is_kill_switched(self) -> bool:
        return self.state == SystemState.KILL_SWITCH

    @property
    def can_trade(self) -> bool:
        return self.state == SystemState.NORMAL and not risk_engine.is_kill_switched

    def record_success(self) -> None:
        """Reset consecutive error counter on successful cycle or operation."""
        if self.consecutive_errors > 0:
            logger.info("Consecutive error counter reset to 0", previous_count=self.consecutive_errors)
            self.consecutive_errors = 0

    async def record_error(self, error_type: str, details: str) -> None:
        """
        Record a transient or unexpected error.
        If errors breach the threshold, automatically degrade to SAFE_MODE.
        """
        self.consecutive_errors += 1
        logger.warning(
            "Runtime error recorded",
            error_type=error_type,
            details=details,
            consecutive_count=self.consecutive_errors,
            threshold=self.max_consecutive_errors,
        )

        if self.consecutive_errors >= self.max_consecutive_errors and self.state == SystemState.NORMAL:
            reason = (
                f"Consecutive errors reached limit ({self.consecutive_errors}/{self.max_consecutive_errors}): "
                f"[{error_type}] {details}"
            )
            await self.enter_safe_mode(reason)

    async def enter_safe_mode(self, reason: str) -> None:
        """
        Enter SAFE_MODE:
        - Suspends opening new positions.
        - Keeps existing Bracket Orders active to protect capital.
        - Dispatches Telegram alert.
        - Records event in DB.
        """
        self.state = SystemState.SAFE_MODE
        self.reason = reason
        self.activated_at = now_utc()

        logger.warning("SYSTEM ENTERED SAFE MODE", reason=reason)

        # 1. Dispatch Telegram Warning
        tz_time = format_multi_tz_display(self.activated_at)
        alert_text = (
            f"⚠️ *SYSTEM ALERT: SAFE MODE ACTIVATED*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"• *Status:* SAFE MODE (No new trades)\n"
            f"• *Reason:* {reason}\n"
            f"• *Time:* {tz_time}\n"
            f"• *Action:* Active bracket orders remain monitored.\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        )
        try:
            await dispatcher.notify_warning(alert_text)
        except Exception as e:
            logger.error("Failed to send safe mode alert via dispatcher", error=str(e))

        # 2. Record to Database if available
        if db_manager.is_connected:
            try:
                await db_manager.execute(
                    """
                    INSERT INTO system_events (event_type, message, details)
                    VALUES ($1, $2, $3)
                    """,
                    "safe_mode",
                    reason,
                    json.dumps({"state": self.state.value, "activated_at": self.activated_at.isoformat()}),
                )
            except Exception as e:
                logger.error("Failed to persist safe mode event to DB", error=str(e))

    async def activate_kill_switch(self, reason: str) -> None:
        """
        Activate Emergency KILL SWITCH:
        - Sets state to KILL_SWITCH.
        - Halts all trading and signal evaluations.
        - Cancels all pending/open orders at Alpaca.
        - Dispatches CRITICAL alert via Telegram.
        - Persists to database.
        """
        self.state = SystemState.KILL_SWITCH
        self.reason = reason
        self.activated_at = now_utc()
        risk_engine.activate_kill_switch(reason)

        logger.critical("EMERGENCY KILL SWITCH ACTIVATED", reason=reason)

        # 1. Cancel all open orders at Alpaca
        orders_canceled = False
        try:
            await alpaca_trading_client.cancel_all_orders()
            orders_canceled = True
            logger.info("All open orders canceled successfully via Kill Switch")
        except Exception as e:
            logger.error("Failed to cancel open orders during Kill Switch activation", error=str(e))

        # 2. Dispatch Critical Telegram Alert
        tz_time = format_multi_tz_display(self.activated_at)
        cancel_status = "All pending orders canceled." if orders_canceled else "Order cancellation attempted."
        alert_text = (
            f"🚨 *CRITICAL EMERGENCY: KILL SWITCH TRIGGERED*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"• *Status:* SYSTEM HALTED\n"
            f"• *Reason:* {reason}\n"
            f"• *Orders Action:* {cancel_status}\n"
            f"• *Time:* {tz_time}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"Manual intervention required to restore trading."
        )
        try:
            await dispatcher.notify_critical(alert_text)
        except Exception as e:
            logger.error("Failed to send kill switch alert via dispatcher", error=str(e))

        # 3. Persist to Database if available
        if db_manager.is_connected:
            try:
                await db_manager.execute(
                    """
                    INSERT INTO risk_events (event_type, description, severity, action_taken)
                    VALUES ($1, $2, $3, $4)
                    """,
                    "kill_switch",
                    reason,
                    "critical",
                    "Cancelled all orders and halted trading",
                )
                await db_manager.execute(
                    """
                    INSERT INTO system_events (event_type, message, details)
                    VALUES ($1, $2, $3)
                    """,
                    "kill_switch",
                    reason,
                    json.dumps({"state": self.state.value, "activated_at": self.activated_at.isoformat()}),
                )
            except Exception as e:
                logger.error("Failed to persist kill switch event to DB", error=str(e))

    async def reset_to_normal(self, reason: str = "Manual recovery") -> None:
        """
        Reset system back to NORMAL state:
        - Deactivates Kill Switch in Risk Engine.
        - Clears error counter and state.
        - Dispatches INFO notification.
        """
        old_state = self.state
        self.state = SystemState.NORMAL
        self.reason = None
        self.consecutive_errors = 0
        self.activated_at = None
        risk_engine.deactivate_kill_switch()

        logger.info("System state restored to NORMAL", previous_state=old_state.value, reason=reason)

        alert_text = (
            f"✅ *SYSTEM RECOVERY: RETURNED TO NORMAL*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"• *Status:* NORMAL (Trading active)\n"
            f"• *Recovery Reason:* {reason}\n"
            f"• *Previous State:* {old_state.value}\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        )
        try:
            await dispatcher.notify_info(alert_text)
        except Exception as e:
            logger.error("Failed to send recovery alert via dispatcher", error=str(e))

        if db_manager.is_connected:
            try:
                await db_manager.execute(
                    """
                    INSERT INTO system_events (event_type, message, details)
                    VALUES ($1, $2, $3)
                    """,
                    "state_reset",
                    f"Reset to NORMAL: {reason}",
                    json.dumps({"restored_at": now_utc().isoformat()}),
                )
            except Exception as e:
                logger.error("Failed to persist reset event to DB", error=str(e))


# Global Safe Mode Manager singleton
safe_mode_manager = SafeModeManager()
