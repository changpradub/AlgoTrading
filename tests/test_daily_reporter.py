"""
Unit Tests for DailyReporter (monitoring/daily_reporter.py)
Verifies:
1. Daily summary calculation from live account, positions, and closed trades
2. Telegram formatting and dispatch at market close
3. CLI argument handling for --daily-summary
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from bot import parse_arguments
from monitoring.daily_reporter import DailyReporter, DailySummaryReport, PositionSummary


@pytest.fixture
def mock_account():
    acc = MagicMock()
    acc.equity = "705.50"
    acc.cash = "650.00"
    acc.buying_power = "1300.00"
    acc.daytrade_count = 1
    acc.last_equity = "700.00"
    return acc


@pytest.fixture
def mock_position():
    pos = MagicMock()
    pos.symbol = "NVDA"
    pos.qty = "0.14"
    pos.avg_entry_price = "140.0"
    pos.current_price = "145.0"
    pos.market_value = "20.30"
    pos.unrealized_pl = "0.70"
    pos.unrealized_plpc = "0.0357"
    return pos


@pytest.mark.asyncio
async def test_generate_daily_summary(mock_account, mock_position):
    reporter = DailyReporter()

    mock_db_trades = [
        {"net_pnl": 2.50},
        {"net_pnl": 1.20},
        {"net_pnl": -0.80},
    ]

    with patch("monitoring.daily_reporter.alpaca_trading_client.get_account", new_callable=AsyncMock, return_value=mock_account), \
         patch("monitoring.daily_reporter.alpaca_trading_client.get_all_positions", new_callable=AsyncMock, return_value=[mock_position]), \
         patch("monitoring.daily_reporter.db_manager._pool", MagicMock()), \
         patch("monitoring.daily_reporter.db_manager.fetch", new_callable=AsyncMock, return_value=mock_db_trades):

        summary: DailySummaryReport = await reporter.generate_daily_summary()

        assert summary.equity == 705.50
        assert summary.cash == 650.00
        assert summary.buying_power == 1300.00
        assert summary.pdt_daytrade_count == 1
        assert summary.trades_count == 3
        assert summary.winning_trades == 2
        assert summary.losing_trades == 1
        assert round(summary.win_rate_pct, 1) == 66.7
        assert summary.daily_realized_pl == 2.90
        assert summary.daily_unrealized_pl == 0.70
        assert summary.total_daily_pl == 5.50  # equity 705.50 - last_equity 700.00
        assert len(summary.open_positions) == 1
        assert summary.open_positions[0].symbol == "NVDA"


@pytest.mark.asyncio
async def test_dispatch_daily_summary(mock_account, mock_position):
    reporter = DailyReporter()

    with patch("monitoring.daily_reporter.alpaca_trading_client.get_account", new_callable=AsyncMock, return_value=mock_account), \
         patch("monitoring.daily_reporter.alpaca_trading_client.get_all_positions", new_callable=AsyncMock, return_value=[mock_position]), \
         patch("monitoring.daily_reporter.db_manager._pool", None), \
         patch("monitoring.daily_reporter.dispatcher.notify_info", new_callable=AsyncMock) as mock_notify:

        summary = await reporter.dispatch_daily_summary()

        assert summary.equity == 705.50
        mock_notify.assert_called_once()
        sent_message = mock_notify.call_args[0][0]
        assert "สรุปผลการเทรดประจำวัน" in sent_message
        assert "NVDA" in sent_message


def test_cli_daily_summary_flag():
    test_args = ["bot.py", "--daily-summary"]
    with patch("sys.argv", test_args):
        args = parse_arguments()
        assert args.daily_summary is True
        assert args.health_only is False
