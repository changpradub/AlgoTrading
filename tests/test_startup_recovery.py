"""
Unit tests for StartupRecoveryEngine (Phase 4)
"""

from datetime import datetime
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from core.startup_recovery import StartupRecoveryEngine, StartupRecoveryReport
from core.state_manager import ReconciliationReport
from core.failsafe import safe_mode_manager, SystemState
from core.risk_engine import risk_engine


@pytest.fixture
def recovery_engine():
    safe_mode_manager.state = SystemState.NORMAL
    risk_engine.deactivate_kill_switch()
    return StartupRecoveryEngine()


@pytest.mark.asyncio
async def test_startup_recovery_success_flow(recovery_engine):
    mock_account = MagicMock()
    mock_account.status = "ACTIVE"
    mock_account.equity = "750.50"
    mock_account.cash = "700.00"
    mock_account.buying_power = "1400.00"
    mock_account.daytrade_count = 1

    mock_reconcile = ReconciliationReport(
        is_synchronized=True,
        broker_positions_count=1,
        db_positions_count=1,
        matched_symbols=["NVDA"],
        mismatches=[],
        account_equity=750.50,
        buying_power=1400.00,
        pdt_daytrade_count=1,
    )

    mock_pos = MagicMock()
    mock_pos.symbol = "NVDA"
    mock_pos.qty = "0.5"
    mock_pos.avg_entry_price = "120.0"
    mock_pos.current_price = "121.5"
    mock_pos.unrealized_pl = "0.75"
    mock_pos.unrealized_plpc = "0.0125"  # +1.25%

    with patch("core.alpaca_client.alpaca_trading_client.get_account", new_callable=AsyncMock, return_value=mock_account), \
         patch("core.state_manager.state_manager.reconcile_state", new_callable=AsyncMock, return_value=mock_reconcile), \
         patch("core.alpaca_client.alpaca_trading_client.get_all_positions", new_callable=AsyncMock, return_value=[mock_pos]), \
         patch("core.alpaca_client.alpaca_trading_client.get_open_orders", new_callable=AsyncMock, return_value=[]), \
         patch("notifications.dispatcher.notify_info", new_callable=AsyncMock) as mock_info:

        report = await recovery_engine.run_recovery()

        assert report.broker_connected is True
        assert report.equity == 750.50
        assert report.pdt_daytrade_count == 1
        assert report.pdt_allowed_remaining == 2
        assert report.open_positions_count == 1
        assert report.open_orders_count == 0
        assert len(report.gap_alerts) == 0
        assert report.system_ready is True
        mock_info.assert_called_once()


@pytest.mark.asyncio
async def test_startup_recovery_detects_gap_risk(recovery_engine):
    mock_account = MagicMock()
    mock_account.status = "ACTIVE"
    mock_account.equity = "700.00"
    mock_account.cash = "650.00"
    mock_account.buying_power = "1300.00"
    mock_account.daytrade_count = 0

    # Position with -4.5% overnight gap down
    mock_pos = MagicMock()
    mock_pos.symbol = "TSM"
    mock_pos.qty = "1.0"
    mock_pos.avg_entry_price = "150.0"
    mock_pos.current_price = "143.25"
    mock_pos.unrealized_pl = "-6.75"
    mock_pos.unrealized_plpc = "-0.045"  # -4.5%

    with patch("core.alpaca_client.alpaca_trading_client.get_account", new_callable=AsyncMock, return_value=mock_account), \
         patch("core.state_manager.state_manager.reconcile_state", new_callable=AsyncMock), \
         patch("core.alpaca_client.alpaca_trading_client.get_all_positions", new_callable=AsyncMock, return_value=[mock_pos]), \
         patch("core.alpaca_client.alpaca_trading_client.get_open_orders", new_callable=AsyncMock, return_value=[]), \
         patch("notifications.dispatcher.notify_info", new_callable=AsyncMock):

        report = await recovery_engine.run_recovery()

        assert len(report.gap_alerts) == 1
        assert report.gap_alerts[0].symbol == "TSM"
        assert report.gap_alerts[0].unrealized_plpc == -4.5
        assert any("Overnight adverse move" in note for note in report.notes)


@pytest.mark.asyncio
async def test_startup_recovery_pdt_limit_exhausted(recovery_engine):
    mock_account = MagicMock()
    mock_account.status = "ACTIVE"
    mock_account.equity = "1200.00"  # Under $25k
    mock_account.cash = "1200.00"
    mock_account.buying_power = "2400.00"
    mock_account.daytrade_count = 3  # All 3 used

    with patch("core.alpaca_client.alpaca_trading_client.get_account", new_callable=AsyncMock, return_value=mock_account), \
         patch("core.state_manager.state_manager.reconcile_state", new_callable=AsyncMock), \
         patch("core.alpaca_client.alpaca_trading_client.get_all_positions", new_callable=AsyncMock, return_value=[]), \
         patch("core.alpaca_client.alpaca_trading_client.get_open_orders", new_callable=AsyncMock, return_value=[]), \
         patch("notifications.dispatcher.notify_info", new_callable=AsyncMock):

        report = await recovery_engine.run_recovery()

        assert report.pdt_daytrade_count == 3
        assert report.pdt_allowed_remaining == 0
        assert any("PDT Quota Exhausted" in note for note in report.notes)
