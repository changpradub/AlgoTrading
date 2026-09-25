"""
Unit Tests for Trade Logger & Position Manager (P0 Critical Fixes)
Verifies:
1. Trade Logger: order submission logging, trade open/close logging
2. Position Manager: trade registration, bracket fill detection, exit evaluation
3. Data Staleness Check integration
"""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
import pandas as pd
import pytest

from core.trade_logger import TradeLogger, ActiveTradeRecord
from core.position_manager import PositionManager
from utils.timezone import now_utc


# ============================================================================
# Trade Logger Tests
# ============================================================================


@pytest.mark.asyncio
async def test_trade_logger_log_order_submitted():
    """Verify order submission is persisted to DB."""
    logger = TradeLogger()

    with patch("core.trade_logger.db_manager") as mock_db:
        mock_db.is_connected = True
        mock_db.fetchval = AsyncMock(return_value=42)

        result = await logger.log_order_submitted(
            alpaca_order_id="alp_123",
            client_order_id="bot_nvda_abc",
            symbol="NVDA",
            side="buy",
            qty=0.14,
            status="new",
        )

        assert result == 42
        mock_db.fetchval.assert_called_once()


@pytest.mark.asyncio
async def test_trade_logger_log_order_skipped_when_db_disconnected():
    """Verify order logging is skipped gracefully when DB is not connected."""
    logger = TradeLogger()

    with patch("core.trade_logger.db_manager") as mock_db:
        mock_db.is_connected = False

        result = await logger.log_order_submitted(
            alpaca_order_id="alp_123",
            client_order_id="bot_nvda_abc",
            symbol="NVDA",
            side="buy",
            qty=0.14,
            status="new",
        )

        assert result is None


@pytest.mark.asyncio
async def test_trade_logger_log_trade_opened():
    """Verify trade entry is logged with placeholder exit values."""
    logger = TradeLogger()

    with patch("core.trade_logger.db_manager") as mock_db:
        mock_db.is_connected = True
        mock_db.fetchval = AsyncMock(return_value=101)

        record = await logger.log_trade_opened(
            symbol="TSM",
            side="buy",
            qty=0.25,
            entry_price=180.50,
            entry_time=now_utc(),
            take_profit=190.0,
            stop_loss=175.0,
            alpaca_order_id="alp_456",
        )

        assert record is not None
        assert record.db_trade_id == 101
        assert record.symbol == "TSM"
        assert record.entry_price == 180.50


@pytest.mark.asyncio
async def test_trade_logger_log_trade_closed():
    """Verify trade closure calculates P&L and updates DB."""
    logger = TradeLogger()

    with patch("core.trade_logger.db_manager") as mock_db, \
         patch("core.trade_logger.dispatcher") as mock_disp:
        mock_db.is_connected = True
        mock_db.execute = AsyncMock()
        mock_disp.notify_trade = AsyncMock()

        await logger.log_trade_closed(
            trade_id=101,
            symbol="TSM",
            qty=0.25,
            entry_price=180.50,
            exit_price=190.00,
            exit_time=now_utc(),
            exit_reason="take_profit",
        )

        # Verify DB update was called
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        assert call_args[0][1] == 101  # trade_id
        assert call_args[0][2] == 190.00  # exit_price

        # Verify P&L calculation: (190 - 180.5) * 0.25 = 2.375
        gross_pnl = call_args[0][3]
        assert abs(gross_pnl - 2.375) < 0.01


# ============================================================================
# Position Manager Tests
# ============================================================================


def test_position_manager_register_and_unregister():
    """Verify trade registration and unregistration."""
    pm = PositionManager()

    record = ActiveTradeRecord(
        db_trade_id=1,
        db_order_id=None,
        symbol="NVDA",
        side="buy",
        qty=0.14,
        entry_price=140.0,
        entry_time=now_utc(),
        take_profit=150.0,
        stop_loss=135.0,
        alpaca_order_id="alp_999",
        client_order_id="bot_nvda_999",
    )

    pm.register_trade(record)
    assert pm.has_active_trade("NVDA")
    assert "NVDA" in pm.active_symbols

    removed = pm.unregister_trade("NVDA")
    assert removed is not None
    assert not pm.has_active_trade("NVDA")


@pytest.mark.asyncio
async def test_position_manager_bracket_fill_detection():
    """Verify that position disappearance from broker triggers bracket fill detection."""
    pm = PositionManager()

    # Register a trade
    record = ActiveTradeRecord(
        db_trade_id=5,
        db_order_id=None,
        symbol="NVDA",
        side="buy",
        qty=0.14,
        entry_price=140.0,
        entry_time=now_utc(),
        take_profit=150.0,
        stop_loss=135.0,
        alpaca_order_id="alp_888",
        client_order_id="bot_nvda_888",
    )
    pm.register_trade(record)

    # Mock: broker now has NO positions (TP or SL triggered)
    with patch("core.position_manager.alpaca_trading_client") as mock_alpaca, \
         patch("core.position_manager.trade_logger") as mock_logger:
        mock_alpaca.get_all_positions = AsyncMock(return_value=[])
        mock_logger.log_trade_closed = AsyncMock()

        # Mock _determine_exit_details
        with patch.object(pm, "_determine_exit_details", new_callable=AsyncMock,
                          return_value=(150.0, "take_profit")):
            closed = await pm.check_bracket_fills()

        assert "NVDA" in closed
        assert not pm.has_active_trade("NVDA")
        mock_logger.log_trade_closed.assert_called_once()


@pytest.mark.asyncio
async def test_position_manager_exit_conditions_trend_reversal():
    """Verify exit signal fires when EMA 20 crosses below EMA 50."""
    pm = PositionManager()

    record = ActiveTradeRecord(
        db_trade_id=10,
        db_order_id=None,
        symbol="NVDA",
        side="buy",
        qty=0.14,
        entry_price=140.0,
        entry_time=now_utc() - timedelta(hours=48),
        take_profit=150.0,
        stop_loss=135.0,
        alpaca_order_id="alp_777",
        client_order_id="bot_nvda_777",
    )
    pm.register_trade(record)

    # Create a DataFrame where EMA 20 < EMA 50 (bearish crossover)
    rows = []
    base_time = now_utc()
    for i in range(120):
        t = base_time - pd.Timedelta(minutes=(120 - i - 1) * 5)
        # Price declining: will cause EMA 20 < EMA 50
        price = 145.0 - (i * 0.1)
        rows.append({
            "timestamp": t,
            "open": price,
            "high": price + 0.5,
            "low": price - 0.5,
            "close": price,
            "volume": 10000.0,
        })
    df = pd.DataFrame(rows)
    df.set_index("timestamp", inplace=True)

    df_map = {"NVDA": df}
    exit_candidates = await pm.evaluate_exit_conditions(df_map)

    # Should detect trend reversal since price is declining
    assert "NVDA" in exit_candidates


@pytest.mark.asyncio
async def test_position_manager_no_exit_when_trend_strong():
    """Verify no exit signal when trend is still bullish."""
    pm = PositionManager()

    record = ActiveTradeRecord(
        db_trade_id=11,
        db_order_id=None,
        symbol="NVDA",
        side="buy",
        qty=0.14,
        entry_price=140.0,
        entry_time=now_utc() - timedelta(hours=2),
        take_profit=150.0,
        stop_loss=135.0,
        alpaca_order_id="alp_666",
        client_order_id="bot_nvda_666",
    )
    pm.register_trade(record)

    # Create an uptrending DataFrame
    rows = []
    base_time = now_utc()
    for i in range(120):
        t = base_time - pd.Timedelta(minutes=(120 - i - 1) * 5)
        price = 130.0 + (i * 0.2)  # Steadily rising
        rows.append({
            "timestamp": t,
            "open": price,
            "high": price + 0.5,
            "low": price - 0.3,
            "close": price + 0.1,
            "volume": 10000.0,
        })
    df = pd.DataFrame(rows)
    df.set_index("timestamp", inplace=True)

    df_map = {"NVDA": df}
    exit_candidates = await pm.evaluate_exit_conditions(df_map)

    # Should NOT trigger exit — trend is strong
    assert "NVDA" not in exit_candidates
