"""
Unit tests for core/technical.py
"""

import numpy as np
import pandas as pd
import pytest

from core.technical import TechnicalAnalysisEngine
from config.constants import WARMUP_BARS_MIN


@pytest.fixture
def sample_ohlcv_data():
    """Generate 150 bars of synthetic OHLCV data."""
    dates = pd.date_range("2026-01-01", periods=150, freq="1h")
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(150))
    high = close + np.random.uniform(0.5, 2.0, 150)
    low = close - np.random.uniform(0.5, 2.0, 150)
    open_p = close + np.random.uniform(-0.5, 0.5, 150)
    volume = np.random.uniform(1000, 50000, 150)

    df = pd.DataFrame({
        "open": open_p,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }, index=dates)
    return df


def test_warmup_validation(sample_ohlcv_data):
    engine = TechnicalAnalysisEngine()

    # Short DataFrame should fail warmup
    df_short = sample_ohlcv_data.iloc[:50]
    assert engine.is_warmed_up(df_short, min_bars=WARMUP_BARS_MIN) is False

    # Full 150 bars should pass warmup
    assert engine.is_warmed_up(sample_ohlcv_data, min_bars=WARMUP_BARS_MIN) is True


def test_indicator_calculation(sample_ohlcv_data):
    engine = TechnicalAnalysisEngine()
    df_calc = engine.calculate_indicators(sample_ohlcv_data)

    # Check that indicator columns exist
    assert "ema_20" in df_calc.columns
    assert "ema_50" in df_calc.columns
    assert "ema_200" in df_calc.columns
    assert "rsi" in df_calc.columns
    assert "atr" in df_calc.columns
    assert "swing_high" in df_calc.columns
    assert "swing_low" in df_calc.columns

    # Verify RSI is within bounds [0, 100]
    assert df_calc["rsi"].min() >= 0.0
    assert df_calc["rsi"].max() <= 100.0

    # Verify ATR is positive
    assert (df_calc["atr"].dropna() > 0).all()


def test_latest_snapshot(sample_ohlcv_data):
    engine = TechnicalAnalysisEngine()
    snapshot = engine.get_latest_snapshot(sample_ohlcv_data)

    assert "close" in snapshot
    assert "ema_fast" in snapshot
    assert "rsi" in snapshot
    assert "atr" in snapshot
    assert isinstance(snapshot["is_uptrend"], bool)
