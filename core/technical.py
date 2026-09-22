"""
Technical Analysis Engine & Indicator Warmup Module
Calculates EMA, RSI, ATR, Support/Resistance levels and validates Warmup invariants.
See UNIFIED_PLAN.md Section 4.2 & Section 7.
"""

from typing import Dict, Optional, Tuple
import numpy as np
import pandas as pd
import structlog

from config.constants import WARMUP_BARS_MIN

logger = structlog.get_logger(__name__)


class TechnicalAnalysisEngine:
    """Computes technical indicators and validates data sufficiency."""

    def __init__(
        self,
        ema_fast: int = 20,
        ema_medium: int = 50,
        ema_slow: int = 200,
        rsi_period: int = 14,
        atr_period: int = 14,
        swing_window: int = 20,
    ):
        self.ema_fast = ema_fast
        self.ema_medium = ema_medium
        self.ema_slow = ema_slow
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        self.swing_window = swing_window

    def is_warmed_up(self, df: pd.DataFrame, min_bars: int = WARMUP_BARS_MIN) -> bool:
        """
        Guarantees that sufficient historical bars exist before generating signals.
        Invariant: Never generate signals without full indicator warmup.
        """
        if df is None or df.empty:
            return False
        return len(df) >= min_bars

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate all core technical indicators on OHLCV DataFrame.
        Expected columns: open, high, low, close, volume.
        """
        if df.empty:
            return df

        df = df.copy()

        # 1. Exponential Moving Averages (EMA)
        df[f"ema_{self.ema_fast}"] = df["close"].ewm(span=self.ema_fast, adjust=False).mean()
        df[f"ema_{self.ema_medium}"] = df["close"].ewm(span=self.ema_medium, adjust=False).mean()
        df[f"ema_{self.ema_slow}"] = df["close"].ewm(span=self.ema_slow, adjust=False).mean()

        # 2. Relative Strength Index (RSI - Wilder's smoothing)
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1.0 / self.rsi_period, min_periods=self.rsi_period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1.0 / self.rsi_period, min_periods=self.rsi_period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        df["rsi"] = 100 - (100 / (1 + rs))
        df["rsi"] = df["rsi"].fillna(50.0)

        # 3. Average True Range (ATR)
        high = df["high"]
        low = df["low"]
        prev_close = df["close"].shift(1)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df["atr"] = tr.ewm(alpha=1.0 / self.atr_period, min_periods=self.atr_period, adjust=False).mean()

        # 4. Support & Resistance (Swing Highs and Swing Lows)
        df["swing_high"] = df["high"].rolling(window=self.swing_window).max()
        df["swing_low"] = df["low"].rolling(window=self.swing_window).min()

        # 5. Volatility & Trend Filters
        df["atr_pct"] = (df["atr"] / df["close"]) * 100.0
        df["is_uptrend"] = (df[f"ema_{self.ema_fast}"] > df[f"ema_{self.ema_medium}"]) & (
            df[f"ema_{self.ema_medium}"] > df[f"ema_{self.ema_slow}"]
        )

        return df

    def get_latest_snapshot(self, df: pd.DataFrame) -> Dict[str, float]:
        """Extract latest calculated indicator values as a dictionary."""
        if not self.is_warmed_up(df):
            raise ValueError(
                f"Insufficient bars for warmup: {len(df)} available, {WARMUP_BARS_MIN} required."
            )

        calculated = self.calculate_indicators(df)
        last_row = calculated.iloc[-1]

        return {
            "close": float(last_row["close"]),
            "ema_fast": float(last_row[f"ema_{self.ema_fast}"]),
            "ema_medium": float(last_row[f"ema_{self.ema_medium}"]),
            "ema_slow": float(last_row[f"ema_{self.ema_slow}"]),
            "rsi": float(last_row["rsi"]),
            "atr": float(last_row["atr"]),
            "atr_pct": float(last_row["atr_pct"]),
            "swing_high": float(last_row["swing_high"]),
            "swing_low": float(last_row["swing_low"]),
            "is_uptrend": bool(last_row["is_uptrend"]),
        }


# Global technical engine singleton
technical_engine = TechnicalAnalysisEngine()
