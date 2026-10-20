"""
Unit Tests for Master Trading Bot (bot.py)
Verifies:
1. Initialization & parameters
2. Graceful shutdown signaling
3. Pipeline execution cycle with mock components
4. CLI flag handling
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pandas as pd
import pytest

from bot import TradingBot, parse_arguments
from core.ai_sentiment import GatekeeperDecision, GatekeeperAction
from core.order_execution import OrderExecutionReport
from core.position_sizing import PositionSizeResult
from core.risk_engine import RiskValidationResult
from core.scheduler import MarketClockSnapshot, MarketPhase
from core.startup_recovery import StartupRecoveryReport
from core.state_manager import ReconciliationReport
from core.strategy import TradingSignal, SignalType
from config.settings import settings
from utils.timezone import now_utc


@pytest.fixture
def sample_bars_df():
    """Create a sample OHLCV DataFrame with 120 bars (exceeds 100 warmup bars).
    The last bar timestamp is at now_utc() to prevent data staleness check from triggering."""
    rows = []
    base_time = now_utc()
    price = 140.0
    for i in range(120):
        # Last bar (i=119) will be at base_time - 0 minutes = current time
        t = base_time - pd.Timedelta(minutes=(120 - i - 1) * 5)
        rows.append({
            "timestamp": t,
            "open": price,
            "high": price + 1.0,
            "low": price - 1.0,
            "close": price + 0.2,
            "volume": 10000.0,
            "trade_count": 50,
            "vwap": price + 0.1,
        })
        price += 0.1
    df = pd.DataFrame(rows)
    df.set_index("timestamp", inplace=True)
    return df


@pytest.mark.asyncio
async def test_bot_initialization():
    bot = TradingBot(dry_run=True, single_cycle=True, scan_interval_sec=5)
    assert bot.dry_run is True
    assert bot.single_cycle is True
    assert bot.scan_interval_sec == 5
    assert not bot._stop_event.is_set()


@pytest.mark.asyncio
async def test_bot_trigger_shutdown():
    bot = TradingBot()
    assert not bot._stop_event.is_set()
    bot.trigger_shutdown()
    assert bot._stop_event.is_set()


@pytest.mark.asyncio
async def test_bot_startup_recovery_flow():
    bot = TradingBot(dry_run=True, single_cycle=True)

    mock_recovery_report = StartupRecoveryReport(
        timestamp=now_utc(),
        broker_connected=True,
        db_connected=True,
        equity=700.0,
        buying_power=700.0,
        pdt_daytrade_count=0,
        pdt_allowed_remaining=3,
        open_positions_count=0,
        open_orders_count=0,
        reconciliation_report=None,
        gap_alerts=[],
        system_ready=True,
        notes=["Test OK"],
    )

    with patch("bot.db_manager.connect", new_callable=AsyncMock) as mock_db, \
         patch("bot.startup_recovery_engine.run_recovery", new_callable=AsyncMock, return_value=mock_recovery_report), \
         patch("bot.dispatcher.notify_info", new_callable=AsyncMock) as mock_notify:

        success = await bot.initialize()
        assert success is True
        assert mock_db.called
        assert mock_notify.called


@pytest.mark.asyncio
async def test_bot_pipeline_cycle_buy_execution(sample_bars_df):
    """Test full pipeline when strategy emits BUY, AI approves, and order executes."""
    bot = TradingBot(dry_run=False, single_cycle=True)

    mock_recon = ReconciliationReport(
        is_synchronized=True,
        broker_positions_count=0,
        db_positions_count=0,
        matched_symbols=[],
        mismatches=[],
        account_equity=700.0,
        buying_power=700.0,
        pdt_daytrade_count=0,
    )

    buy_signal = TradingSignal(
        symbol="NVDA",
        signal_type=SignalType.BUY,
        entry_price=140.0,
        stop_loss=135.0,
        take_profit=150.0,
        risk_reward_ratio=2.0,
        timeframe="1H",
        indicator_snapshot={"atr": 2.5},
    )

    ai_decision = GatekeeperDecision(
        approved=True,
        symbol="NVDA",
        action=GatekeeperAction.PASS,
        sentiment_report=None,
        reason="AI approved",
    )

    risk_result = RiskValidationResult(
        approved=True,
        reason="Risk checks passed",
        risk_factor=1.0,
    )

    size_result = PositionSizeResult(
        shares=0.14,
        notional_usd=19.60,
        risk_usd=0.70,
        is_valid=True,
        reason="Sized OK",
    )

    order_report = OrderExecutionReport(
        client_order_id="bot_nvda_12345",
        alpaca_order_id="alpaca_id_999",
        symbol="NVDA",
        status="new",
        filled_qty=0.0,
        filled_avg_price=0.0,
        expected_price=140.0,
        slippage_usd=0.0,
        slippage_pct=0.0,
        take_profit_price=150.0,
        stop_loss_price=135.0,
        submitted_at=now_utc(),
    )

    with patch("bot.state_manager.reconcile_state", new_callable=AsyncMock, return_value=mock_recon), \
         patch("bot.alpaca_trading_client.get_all_positions", new_callable=AsyncMock, return_value=[]), \
         patch("bot.alpaca_trading_client.get_open_orders", new_callable=AsyncMock, return_value=[]), \
         patch("bot.position_manager.check_bracket_fills", new_callable=AsyncMock, return_value=[]), \
         patch("bot.position_manager.evaluate_exit_conditions", new_callable=AsyncMock, return_value=[]), \
         patch("bot.market_data_client.get_historical_bars", new_callable=AsyncMock, return_value=sample_bars_df), \
         patch("bot.swing_strategy.evaluate", return_value=buy_signal), \
         patch("bot.ai_gatekeeper.evaluate_signal_gatekeeper", new_callable=AsyncMock, return_value=ai_decision), \
         patch("bot.risk_engine.validate_signal", return_value=risk_result), \
         patch("bot.position_calculator.calculate", return_value=size_result), \
         patch("bot.order_engine.submit_bracket_buy", new_callable=AsyncMock, return_value=order_report) as mock_submit, \
         patch("bot.trade_logger.log_order_submitted", new_callable=AsyncMock, return_value=1), \
         patch("bot.trade_logger.log_trade_opened", new_callable=AsyncMock, return_value=None), \
         patch("bot.db_manager") as mock_db:

        mock_db.is_connected = False
        with patch.object(settings, "TARGET_SYMBOLS", "NVDA"):
            await bot._run_regular_hours_pipeline()
            assert mock_submit.called
            mock_submit.assert_called_once_with(
                symbol="NVDA",
                qty=0.14,
                expected_price=140.0,
                take_profit_price=150.0,
                stop_loss_price=135.0,
            )


@pytest.mark.asyncio
async def test_bot_pipeline_indicator_warmup_guard():
    """Verify that insufficient historical bars (< 100) abort signal generation."""
    bot = TradingBot(dry_run=True, single_cycle=True)

    short_df = pd.DataFrame({"close": [140.0] * 50})  # only 50 bars

    mock_recon = ReconciliationReport(
        is_synchronized=True,
        broker_positions_count=0,
        db_positions_count=0,
        matched_symbols=[],
        mismatches=[],
        account_equity=700.0,
        buying_power=700.0,
        pdt_daytrade_count=0,
    )

    with patch("bot.state_manager.reconcile_state", new_callable=AsyncMock, return_value=mock_recon), \
         patch("bot.alpaca_trading_client.get_all_positions", new_callable=AsyncMock, return_value=[]), \
         patch("bot.alpaca_trading_client.get_open_orders", new_callable=AsyncMock, return_value=[]), \
         patch("bot.market_data_client.get_historical_bars", new_callable=AsyncMock, return_value=short_df), \
         patch("bot.swing_strategy.evaluate") as mock_strategy:

        with patch.object(settings, "TARGET_SYMBOLS", "NVDA"):
            await bot._run_regular_hours_pipeline()
            # Strategy must NOT be called if warmup incomplete
            assert not mock_strategy.called


def test_cli_argument_parsing():
    test_args = ["bot.py", "--dry-run", "--single-cycle"]
    with patch("sys.argv", test_args):
        args = parse_arguments()
        assert args.dry_run is True
        assert args.single_cycle is True
        assert args.pre_market_only is False
        assert args.health_only is False


@pytest.mark.asyncio
async def test_bot_staleness_check_blocks_truly_stale_data():
    """Verify that data older than threshold skips strategy evaluation."""
    from datetime import timedelta
    bot = TradingBot(dry_run=True, single_cycle=True)

    # DataFrame with bars from 10 days ago (truly stale)
    old_time = now_utc() - timedelta(days=10)
    rows = []
    for i in range(120):
        t = old_time - pd.Timedelta(minutes=(120 - i - 1) * 60)
        rows.append({
            "timestamp": t,
            "open": 140.0,
            "high": 141.0,
            "low": 139.0,
            "close": 140.5,
            "volume": 10000.0,
        })
    stale_df = pd.DataFrame(rows).set_index("timestamp")

    mock_recon = ReconciliationReport(
        is_synchronized=True,
        broker_positions_count=0,
        db_positions_count=0,
        matched_symbols=[],
        mismatches=[],
        account_equity=700.0,
        buying_power=700.0,
        pdt_daytrade_count=0,
    )

    with patch("bot.state_manager.reconcile_state", new_callable=AsyncMock, return_value=mock_recon), \
         patch("bot.alpaca_trading_client.get_all_positions", new_callable=AsyncMock, return_value=[]), \
         patch("bot.alpaca_trading_client.get_open_orders", new_callable=AsyncMock, return_value=[]), \
         patch("bot.market_data_client.get_historical_bars", new_callable=AsyncMock, return_value=stale_df), \
         patch("bot.swing_strategy.evaluate") as mock_strategy:

        with patch.object(settings, "TARGET_SYMBOLS", "NVDA"):
            await bot._run_regular_hours_pipeline()
            # Stale data must cause early return BEFORE strategy evaluation
            assert not mock_strategy.called


@pytest.mark.asyncio
async def test_bot_staleness_check_early_session_allows_overnight():
    """Verify that during first 75 min of market open, overnight/weekend close (< 4 days) is accepted."""
    from datetime import timedelta
    bot = TradingBot(dry_run=True, single_cycle=True)

    # Bar from 18 hours ago (overnight from yesterday's close)
    yesterday_close = now_utc() - timedelta(hours=18)
    rows = []
    for i in range(120):
        t = yesterday_close - pd.Timedelta(minutes=(120 - i - 1) * 60)
        rows.append({
            "timestamp": t,
            "open": 140.0,
            "high": 141.0,
            "low": 139.0,
            "close": 140.5,
            "volume": 10000.0,
        })
    overnight_df = pd.DataFrame(rows).set_index("timestamp")

    mock_recon = ReconciliationReport(
        is_synchronized=True,
        broker_positions_count=0,
        db_positions_count=0,
        matched_symbols=[],
        mismatches=[],
        account_equity=700.0,
        buying_power=700.0,
        pdt_daytrade_count=0,
    )

    # Market is in REGULAR_HOURS with 6.0 hours left to close (first 30 min of session)
    mock_status = MarketClockSnapshot(
        is_open=True,
        phase=MarketPhase.REGULAR_HOURS,
        timestamp_utc=now_utc(),
        next_open_utc=now_utc() + timedelta(days=1),
        next_close_utc=now_utc() + timedelta(hours=6),
        time_to_open_seconds=0.0,
        time_to_close_seconds=6.0 * 3600,  # 6 hours left (> 5.25h)
    )

    with patch("bot.state_manager.reconcile_state", new_callable=AsyncMock, return_value=mock_recon), \
         patch("bot.market_scheduler.get_market_status", new_callable=AsyncMock, return_value=mock_status), \
         patch("bot.alpaca_trading_client.get_all_positions", new_callable=AsyncMock, return_value=[]), \
         patch("bot.alpaca_trading_client.get_open_orders", new_callable=AsyncMock, return_value=[]), \
         patch("bot.market_data_client.get_historical_bars", new_callable=AsyncMock, return_value=overnight_df), \
         patch("bot.swing_strategy.evaluate", return_value=TradingSignal(symbol="NVDA", signal_type=SignalType.HOLD, entry_price=140.0, stop_loss=0, take_profit=0, risk_reward_ratio=0, timeframe="1H")) as mock_strategy:

        with patch.object(settings, "TARGET_SYMBOLS", "NVDA"):
            await bot._run_regular_hours_pipeline()
            # Strategy SHOULD be called because overnight bar is within opening tolerance
            assert mock_strategy.called
