"""
Unit tests for utils/timezone.py
"""

from datetime import datetime, timezone
import pytest
from utils.timezone import (
    now_utc,
    now_eastern,
    now_bangkok,
    to_utc,
    to_eastern,
    to_bangkok,
    format_iso_utc,
    format_multi_tz_display,
)


def test_now_utc_is_timezone_aware():
    utc = now_utc()
    assert utc.tzinfo is not None
    assert utc.tzinfo == timezone.utc


def test_to_bangkok_has_plus_seven_offset():
    utc = datetime(2026, 9, 22, 12, 0, 0, tzinfo=timezone.utc)
    bkk = to_bangkok(utc)
    # Bangkok is UTC+7
    assert bkk.hour == 19
    assert bkk.utcoffset().total_seconds() == 7 * 3600


def test_to_eastern_and_dst():
    # September is in Daylight Saving Time (EDT, UTC-4)
    utc_sept = datetime(2026, 9, 22, 14, 0, 0, tzinfo=timezone.utc)
    et_sept = to_eastern(utc_sept)
    assert et_sept.hour == 10
    assert et_sept.utcoffset().total_seconds() == -4 * 3600

    # January is in Standard Time (EST, UTC-5)
    utc_jan = datetime(2026, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
    et_jan = to_eastern(utc_jan)
    assert et_jan.hour == 9
    assert et_jan.utcoffset().total_seconds() == -5 * 3600


def test_format_iso_utc():
    dt = datetime(2026, 9, 22, 10, 30, 45, tzinfo=timezone.utc)
    formatted = format_iso_utc(dt)
    assert formatted == "2026-09-22T10:30:45Z"


def test_format_multi_tz_display():
    dt = datetime(2026, 9, 22, 14, 0, 0, tzinfo=timezone.utc)
    display = format_multi_tz_display(dt)
    assert "ET" in display
    assert "ICT" in display
