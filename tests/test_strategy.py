"""
Unit tests for core/strategy.py
"""

import numpy as np
import pandas as pd
import pytest

from core.strategy import SwingTrendPullbackStrategy, SignalType


@pytest.fixture
def trending_ohlcv_data():
    """Generate 120 bars of an upward trending market with a pullback."""
    dates = pd.date_range("2026-01-01", periods=120, freq="1h")
    # Upward trend
    trend = np.linspace(100, 150, 120)
    # Dip at the end for pullback
    trend[-5:] = [148, 147, 146, 146.5, 147.2]

    df = pd.DataFrame({
        "open": trend - 0.2,
        "high": trend + 1.0,
        "low": trend - 1.0,
        "close": trend,
        "volume": [10000] * 120,
    }, index=dates)
    return df


def test_strategy_insufficient_warmup():
    strategy = SwingTrendPullbackStrategy()
    df_short = pd.DataFrame({"close": [100] * 50})
    signal = strategy.evaluate("NVDA", df_short)

    assert signal.signal_type == SignalType.HOLD
    assert "Warmup incomplete" in signal.reason


def test_strategy_bearish_htf_blocks_long(trending_ohlcv_data):
    strategy = SwingTrendPullbackStrategy()

    # Create bearish HTF data where close < EMA 50
    dates_htf = pd.date_range("2025-01-01", periods=60, freq="1D")
    df_htf = pd.DataFrame({
        "open": [100] * 60,
        "high": [102] * 60,
        "low": [98] * 60,
        "close": np.linspace(120, 80, 60),  # Declining
        "volume": [50000] * 60,
    }, index=dates_htf)

    signal = strategy.evaluate("NVDA", trending_ohlcv_data, df_htf=df_htf)
    assert signal.signal_type == SignalType.HOLD
    assert "HTF (Daily) trend is bearish" in signal.reason


def test_strategy_bracket_order_parameters(trending_ohlcv_data):
    strategy = SwingTrendPullbackStrategy()
    signal = strategy.evaluate("NVDA", trending_ohlcv_data)

    if signal.signal_type == SignalType.BUY:
        # Invariants: Stop Loss < Entry Price < Take Profit
        assert signal.stop_loss < signal.entry_price
        assert signal.take_profit > signal.entry_price
        assert signal.risk_reward_ratio >= 1.0
        assert signal.risk_per_share > 0
        assert signal.reward_per_share > 0
