"""
Unit tests for SafeModeManager and Emergency Controls (Phase 4)
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from core.failsafe import SafeModeManager, SystemState, safe_mode_manager
from core.risk_engine import risk_engine
from core.order_execution import OrderExecutionEngine


@pytest.fixture
def clean_failsafe():
    mgr = SafeModeManager(max_consecutive_errors=3)
    risk_engine.deactivate_kill_switch()
    return mgr


@pytest.mark.asyncio
async def test_failsafe_initial_state(clean_failsafe):
    mgr = clean_failsafe
    assert mgr.state == SystemState.NORMAL
    assert mgr.is_safe_mode is False
    assert mgr.is_kill_switched is False
    assert mgr.can_trade is True
    assert mgr.consecutive_errors == 0


@pytest.mark.asyncio
async def test_failsafe_error_accumulation_triggers_safemode(clean_failsafe):
    mgr = clean_failsafe

    with patch("notifications.dispatcher.notify_warning", new_callable=AsyncMock) as mock_warn:
        await mgr.record_error("TimeoutError", "Request timed out")
        assert mgr.consecutive_errors == 1
        assert mgr.state == SystemState.NORMAL
        mock_warn.assert_not_called()

        await mgr.record_error("TimeoutError", "Request timed out 2")
        assert mgr.consecutive_errors == 2
        assert mgr.state == SystemState.NORMAL

        # 3rd error breaches threshold -> triggers SAFE_MODE
        await mgr.record_error("TimeoutError", "Request timed out 3")
        assert mgr.consecutive_errors == 3
        assert mgr.state == SystemState.SAFE_MODE
        assert mgr.is_safe_mode is True
        assert mgr.can_trade is False
        mock_warn.assert_called_once()


@pytest.mark.asyncio
async def test_failsafe_record_success_resets_counter(clean_failsafe):
    mgr = clean_failsafe
    await mgr.record_error("APIError", "Bad gateway")
    assert mgr.consecutive_errors == 1

    mgr.record_success()
    assert mgr.consecutive_errors == 0


@pytest.mark.asyncio
async def test_failsafe_kill_switch_activation(clean_failsafe):
    mgr = clean_failsafe

    with patch("core.alpaca_client.alpaca_trading_client.cancel_all_orders", new_callable=AsyncMock) as mock_cancel, \
         patch("notifications.dispatcher.notify_critical", new_callable=AsyncMock) as mock_crit:

        await mgr.activate_kill_switch("Max Daily Loss Breached: $15.50 >= $14.00")

        assert mgr.state == SystemState.KILL_SWITCH
        assert mgr.is_kill_switched is True
        assert mgr.can_trade is False
        assert risk_engine.is_kill_switched is True
        mock_cancel.assert_called_once()
        mock_crit.assert_called_once()


@pytest.mark.asyncio
async def test_failsafe_reset_to_normal(clean_failsafe):
    mgr = clean_failsafe
    mgr.state = SystemState.SAFE_MODE
    mgr.consecutive_errors = 3
    risk_engine.activate_kill_switch("Manual test")

    with patch("notifications.dispatcher.notify_info", new_callable=AsyncMock) as mock_info:
        await mgr.reset_to_normal("Operator manually verified system health")

        assert mgr.state == SystemState.NORMAL
        assert mgr.consecutive_errors == 0
        assert mgr.can_trade is True
        assert risk_engine.is_kill_switched is False
        mock_info.assert_called_once()


@pytest.mark.asyncio
async def test_order_engine_blocked_under_safe_mode():
    engine = OrderExecutionEngine()
    safe_mode_manager.state = SystemState.SAFE_MODE

    try:
        report = await engine.submit_bracket_buy(
            symbol="NVDA",
            qty=0.15,
            expected_price=120.0,
            take_profit_price=125.0,
            stop_loss_price=117.0,
        )

        assert report.status == "rejected"
        assert "Trading blocked" in report.error_message
    finally:
        safe_mode_manager.state = SystemState.NORMAL
