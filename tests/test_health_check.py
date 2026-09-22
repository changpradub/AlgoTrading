"""
Unit tests for HealthMonitor (Phase 4)
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from monitoring.health_check import HealthMonitor, SystemHealthReport
from core.failsafe import safe_mode_manager, SystemState
from core.risk_engine import risk_engine


@pytest.fixture
def monitor():
    safe_mode_manager.state = SystemState.NORMAL
    risk_engine.deactivate_kill_switch()
    return HealthMonitor()


@pytest.mark.asyncio
async def test_health_monitor_alpaca_success(monitor):
    mock_clock = MagicMock()
    mock_clock.is_open = True

    with patch("core.alpaca_client.alpaca_trading_client.get_clock", new_callable=AsyncMock, return_value=mock_clock):
        comp = await monitor.check_alpaca()
        assert comp.is_healthy is True
        assert comp.latency_ms >= 0.0
        assert "Market Open" in comp.details


@pytest.mark.asyncio
async def test_health_monitor_alpaca_failure_records_error(monitor):
    with patch("core.alpaca_client.alpaca_trading_client.get_clock", new_callable=AsyncMock, side_effect=ConnectionError("Alpaca unreachable")):
        comp = await monitor.check_alpaca()
        assert comp.is_healthy is False
        assert "Alpaca unreachable" in comp.details
        assert safe_mode_manager.consecutive_errors == 1


@pytest.mark.asyncio
async def test_health_monitor_diagnostics_and_heartbeat(monitor):
    mock_clock = MagicMock()
    mock_clock.is_open = False

    with patch("core.alpaca_client.alpaca_trading_client.get_clock", new_callable=AsyncMock, return_value=mock_clock), \
         patch("notifications.dispatcher.notify_info", new_callable=AsyncMock) as mock_info:

        report = await monitor.send_heartbeat()
        assert report.overall_healthy is True
        assert report.safe_mode_state == "NORMAL"
        assert report.kill_switch_active is False
        mock_info.assert_called_once()
