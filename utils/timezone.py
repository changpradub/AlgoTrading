"""
Timezone Utilities
Ensures consistent handling across UTC (database storage), US Eastern (market hours),
and Asia/Bangkok (developer notifications).
All database timestamps MUST be stored in UTC.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Optional

from config.constants import MARKET_TIMEZONE, BANGKOK_TIMEZONE, UTC_TIMEZONE

TZ_UTC = ZoneInfo(UTC_TIMEZONE)
TZ_EASTERN = ZoneInfo(MARKET_TIMEZONE)
TZ_BANGKOK = ZoneInfo(BANGKOK_TIMEZONE)


def now_utc() -> datetime:
    """Return current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def now_eastern() -> datetime:
    """Return current timezone-aware US Eastern datetime."""
    return datetime.now(TZ_EASTERN)


def now_bangkok() -> datetime:
    """Return current timezone-aware Asia/Bangkok datetime."""
    return datetime.now(TZ_BANGKOK)


def to_utc(dt: datetime) -> datetime:
    """
    Convert any datetime to timezone-aware UTC.
    If naive, assumes it was already UTC.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_eastern(dt: datetime) -> datetime:
    """Convert any datetime to US Eastern time."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TZ_EASTERN)


def to_bangkok(dt: datetime) -> datetime:
    """Convert any datetime to Asia/Bangkok time (UTC+7)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TZ_BANGKOK)


def format_iso_utc(dt: Optional[datetime] = None) -> str:
    """Format datetime as ISO 8601 string in UTC with 'Z' suffix."""
    d = to_utc(dt) if dt else now_utc()
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def is_daylight_saving(dt: Optional[datetime] = None) -> bool:
    """Check whether Daylight Saving Time (EDT) is in effect in New York."""
    d = to_eastern(dt) if dt else now_eastern()
    return bool(d.dst())


def format_multi_tz_display(dt: Optional[datetime] = None) -> str:
    """
    Format a datetime showing both US Eastern and Bangkok time.
    Example: '2026-09-22 10:30:00 ET (21:30:00 ICT)'
    """
    et = to_eastern(dt) if dt else now_eastern()
    ict = to_bangkok(dt) if dt else now_bangkok()
    return f"{et.strftime('%Y-%m-%d %H:%M:%S')} ET ({ict.strftime('%H:%M:%S')} ICT)"
