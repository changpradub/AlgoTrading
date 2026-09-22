"""
Notification Base Interface & Multi-Notifier Dispatcher
Coordinates alerts across channels (Telegram, Console, etc.) based on severity.
See UNIFIED_PLAN.md Section 4.9.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional
import structlog

logger = structlog.get_logger(__name__)


class AlertSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class BaseNotifier(ABC):
    """Abstract base class for notification channels."""

    @abstractmethod
    async def send_message(self, text: str, severity: AlertSeverity = AlertSeverity.INFO) -> bool:
        """Send formatted message to the channel."""
        pass

    @abstractmethod
    async def send_trade_event(self, symbol: str, action: str, details: Dict[str, Any]) -> bool:
        """Send order/fill event alert."""
        pass

    @abstractmethod
    async def send_risk_event(self, event_type: str, message: str, details: Optional[Dict[str, Any]] = None) -> bool:
        """Send risk breach or threshold alert."""
        pass


class NotificationDispatcher:
    """Dispatches notifications to all registered active notifiers."""

    def __init__(self):
        self._notifiers: List[BaseNotifier] = []

    def register(self, notifier: BaseNotifier) -> None:
        self._notifiers.append(notifier)

    async def notify_info(self, text: str) -> None:
        for n in self._notifiers:
            try:
                await n.send_message(text, AlertSeverity.INFO)
            except Exception as e:
                logger.error("Notifier error", notifier=type(n).__name__, error=str(e))

    async def notify_warning(self, text: str) -> None:
        for n in self._notifiers:
            try:
                await n.send_message(text, AlertSeverity.WARNING)
            except Exception as e:
                logger.error("Notifier error", notifier=type(n).__name__, error=str(e))

    async def notify_critical(self, text: str) -> None:
        for n in self._notifiers:
            try:
                await n.send_message(text, AlertSeverity.CRITICAL)
            except Exception as e:
                logger.error("Notifier error", notifier=type(n).__name__, error=str(e))

    async def notify_trade(self, symbol: str, action: str, details: Dict[str, Any]) -> None:
        for n in self._notifiers:
            try:
                await n.send_trade_event(symbol, action, details)
            except Exception as e:
                logger.error("Notifier error", notifier=type(n).__name__, error=str(e))

    async def notify_risk(self, event_type: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        for n in self._notifiers:
            try:
                await n.send_risk_event(event_type, message, details)
            except Exception as e:
                logger.error("Notifier error", notifier=type(n).__name__, error=str(e))


dispatcher = NotificationDispatcher()
