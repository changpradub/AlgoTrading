"""
Telegram Bot Notifier Module
Asynchronously dispatches formatted trading alerts and risk events to Telegram channel/group.
See UNIFIED_PLAN.md Section 4.9.
"""

from typing import Any, Dict, Optional
import aiohttp
import structlog

from config.settings import settings
from notifications.notifier import BaseNotifier, AlertSeverity, dispatcher
from utils.timezone import now_utc, format_multi_tz_display

logger = structlog.get_logger(__name__)


class TelegramNotifier(BaseNotifier):
    """Async Telegram notification delivery."""

    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None):
        self.token = token or settings.TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or settings.TELEGRAM_CHAT_ID
        self.enabled = settings.TELEGRAM_ENABLED and bool(self.token) and bool(self.chat_id)

    async def _send_payload(self, text: str) -> bool:
        if not self.enabled:
            logger.debug("Telegram notification skipped (disabled or missing token/chat_id)")
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=10.0) as response:
                    if response.status == 200:
                        return True
                    error_text = await response.text()
                    logger.warning("Telegram API error response", status=response.status, response=error_text)
                    return False
        except Exception as e:
            logger.error("Failed to dispatch Telegram message", error=str(e))
            return False

    async def send_message(self, text: str, severity: AlertSeverity = AlertSeverity.INFO) -> bool:
        icon_map = {
            AlertSeverity.INFO: "ℹ️ <b>[ข้อมูลระบบ]</b>",
            AlertSeverity.WARNING: "⚠️ <b>[แจ้งเตือน]</b>",
            AlertSeverity.CRITICAL: "🛑 <b>[แจ้งเตือนวิกฤต]</b>",
        }
        icon = icon_map.get(severity, "ℹ️")
        time_str = format_multi_tz_display(now_utc())
        formatted_message = f"{icon} {text}\n<code>{time_str}</code>"
        return await self._send_payload(formatted_message)

    async def send_trade_event(self, symbol: str, action: str, details: Dict[str, Any]) -> bool:
        time_str = format_multi_tz_display(now_utc())
        qty = details.get("qty", "N/A")
        price = details.get("price", "N/A")
        tp = details.get("tp", "N/A")
        sl = details.get("sl", "N/A")

        text = (
            f"🎯 <b>คำสั่งซื้อขายสำเร็จ: {action.upper()} {symbol.upper()}</b>\n"
            f"• <b>จำนวน:</b> {qty} หุ้น\n"
            f"• <b>ราคาที่ได้ (Entry):</b> {price}\n"
            f"• <b>เป้าทำกำไร (TP):</b> {tp}\n"
            f"• <b>จุดตัดขาดทุน (SL):</b> {sl}\n"
            f"<code>{time_str}</code>"
        )
        return await self._send_payload(text)

    async def send_risk_event(self, event_type: str, message: str, details: Optional[Dict[str, Any]] = None) -> bool:
        time_str = format_multi_tz_display(now_utc())
        detail_lines = ""
        if details:
            for k, v in details.items():
                detail_lines += f"\n• <b>{k}:</b> {v}"

        text = (
            f"🚨 <b>แจ้งเตือนความเสี่ยง (Risk Event): {event_type.upper()}</b>\n"
            f"{message}{detail_lines}\n"
            f"<code>{time_str}</code>"
        )
        return await self._send_payload(text)


# Register telegram notifier with global dispatcher
telegram_notifier = TelegramNotifier()
dispatcher.register(telegram_notifier)
