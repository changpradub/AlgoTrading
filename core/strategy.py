"""
Strategy Engine Module
Implements multi-timeframe Swing Trend-Pullback Strategy (1H/4H entry with 1D trend confirmation).
Outputs structured Trading Signals with mandatory Stop Loss & Take Profit targets.
See UNIFIED_PLAN.md Section 4.3.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
import pandas as pd
import structlog

from core.technical import technical_engine
from utils.timezone import now_utc

logger = structlog.get_logger(__name__)


class SignalType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class TradingSignal:
    symbol: str
    signal_type: SignalType
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward_ratio: float
    timeframe: str
    indicator_snapshot: Dict[str, Any] = field(default_factory=dict)
    timestamp_utc: datetime = field(default_factory=now_utc)
    reason: str = ""

    @property
    def risk_per_share(self) -> float:
        return max(0.01, self.entry_price - self.stop_loss)

    @property
    def reward_per_share(self) -> float:
        return max(0.0, self.take_profit - self.entry_price)


class BaseStrategy(ABC):
    """Abstract Strategy Base Class."""

    @abstractmethod
    def evaluate(
        self,
        symbol: str,
        df_ltf: pd.DataFrame,
        df_htf: Optional[pd.DataFrame] = None,
    ) -> TradingSignal:
        """Evaluate market data and return TradingSignal."""
        pass


class SwingTrendPullbackStrategy(BaseStrategy):
    """
    Swing Trend-Pullback Strategy:
    1. HTF (1D): Verifies Bullish Trend (Daily Close > Daily EMA 50)
    2. LTF (1H/4H): Identifies Pullback to EMA 20 with RSI recovery
    3. Mandatory Bracket Targets:
       - Stop Loss: Entry - 2.0 * ATR
       - Take Profit: Entry + 3.0 * ATR (R:R = 1.5)
    """

    def __init__(
        self,
        sl_atr_multiplier: float = 2.0,
        tp_atr_multiplier: float = 3.0,
        rsi_oversold_threshold: float = 45.0,
        pullback_tolerance_pct: float = 0.015,  # within 1.5% of EMA 20
    ):
        self.sl_atr_multiplier = sl_atr_multiplier
        self.tp_atr_multiplier = tp_atr_multiplier
        self.rsi_oversold_threshold = rsi_oversold_threshold
        self.pullback_tolerance_pct = pullback_tolerance_pct

    def evaluate(
        self,
        symbol: str,
        df_ltf: pd.DataFrame,
        df_htf: Optional[pd.DataFrame] = None,
    ) -> TradingSignal:
        # 1. Warmup Validation
        if not technical_engine.is_warmed_up(df_ltf):
            return TradingSignal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                entry_price=0.0,
                stop_loss=0.0,
                take_profit=0.0,
                risk_reward_ratio=0.0,
                timeframe="LTF",
                reason=f"Warmup incomplete: only {len(df_ltf)} bars available.",
            )

        # 2. HTF Trend Confirmation (if available)
        htf_bullish = True
        if df_htf is not None and not df_htf.empty and len(df_htf) >= 50:
            df_htf_calc = technical_engine.calculate_indicators(df_htf)
            htf_last = df_htf_calc.iloc[-1]
            htf_bullish = bool(htf_last["close"] >= htf_last["ema_50"])

        if not htf_bullish:
            return TradingSignal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                entry_price=float(df_ltf.iloc[-1]["close"]),
                stop_loss=0.0,
                take_profit=0.0,
                risk_reward_ratio=0.0,
                timeframe="1H",
                reason="HTF (Daily) trend is bearish (Close < EMA 50). Long signals blocked.",
            )

        # 3. Calculate LTF Indicators
        ltf_calc = technical_engine.calculate_indicators(df_ltf)
        curr = ltf_calc.iloc[-1]
        prev = ltf_calc.iloc[-2]

        close = float(curr["close"])
        ema_fast = float(curr["ema_20"])
        ema_medium = float(curr["ema_50"])
        rsi = float(curr["rsi"])
        atr = float(curr["atr"])
        volume_ratio = float(curr.get("volume_ratio", 1.0))
        macd_hist = float(curr.get("macd_histogram", 0.0))
        macd_hist_prev = float(prev.get("macd_histogram", 0.0))
        market_regime = str(curr.get("market_regime", "RANGING"))

        # 4. Check Pullback & Entry Conditions
        # Condition A: General Uptrend on LTF (EMA 20 > EMA 50)
        trend_ok = ema_fast >= ema_medium

        # Condition B: Pullback near EMA 20 (close within pullback_tolerance_pct of ema_fast)
        dist_to_ema = abs(close - ema_fast) / ema_fast
        near_ema = dist_to_ema <= self.pullback_tolerance_pct

        # Condition C: RSI oversold or turning up from low territory
        rsi_rebounding = (curr["rsi"] > prev["rsi"]) and (curr["rsi"] <= 55.0)

        # Condition D: Bullish Candle (close >= open)
        candle_bullish = float(curr["close"]) >= float(curr["open"])

        # Condition E (NEW): Volume Confirmation — current volume >= 80% of 20-bar average
        volume_confirmed = volume_ratio >= 0.8

        # Condition F (NEW): MACD Momentum — histogram positive or rising
        macd_supportive = (macd_hist > 0) or (macd_hist > macd_hist_prev)

        # Condition G (NEW): Market Regime — block entries in VOLATILE regime
        regime_ok = market_regime != "VOLATILE"

        snapshot = {
            "close": close,
            "ema_20": ema_fast,
            "ema_50": ema_medium,
            "rsi": rsi,
            "atr": atr,
            "htf_bullish": htf_bullish,
            "volume_ratio": round(volume_ratio, 2),
            "macd_histogram": round(macd_hist, 4),
            "market_regime": market_regime,
        }

        # Block entry if Market Regime is VOLATILE
        if not regime_ok:
            return TradingSignal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                entry_price=close,
                stop_loss=0.0,
                take_profit=0.0,
                risk_reward_ratio=0.0,
                timeframe="1H",
                indicator_snapshot=snapshot,
                reason=f"Market regime is VOLATILE (ATR% too high). Entry blocked.",
            )

        if trend_ok and near_ema and rsi_rebounding and candle_bullish and volume_confirmed and macd_supportive:
            # Calculate Bracket Targets
            sl = round(max(0.01, close - (self.sl_atr_multiplier * atr)), 2)
            tp = round(close + (self.tp_atr_multiplier * atr), 2)
            rr = round((tp - close) / max(0.01, close - sl), 2)

            logger.info(
                "BUY Signal generated",
                symbol=symbol,
                price=close,
                sl=sl,
                tp=tp,
                rr=rr,
                volume_ratio=round(volume_ratio, 2),
                macd_hist=round(macd_hist, 4),
                regime=market_regime,
            )

            return TradingSignal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                entry_price=close,
                stop_loss=sl,
                take_profit=tp,
                risk_reward_ratio=rr,
                timeframe="1H",
                indicator_snapshot=snapshot,
                reason="Trend pullback to EMA 20 with RSI rebound, volume confirmation, MACD support, and HTF confirmation.",
            )

        # Build detailed HOLD reason for debugging
        hold_reasons = []
        if not trend_ok:
            hold_reasons.append("EMA20 < EMA50 (no uptrend)")
        if not near_ema:
            hold_reasons.append(f"price too far from EMA20 ({dist_to_ema:.1%})")
        if not rsi_rebounding:
            hold_reasons.append(f"RSI not rebounding (RSI={rsi:.1f})")
        if not candle_bullish:
            hold_reasons.append("bearish candle")
        if not volume_confirmed:
            hold_reasons.append(f"low volume (ratio={volume_ratio:.2f})")
        if not macd_supportive:
            hold_reasons.append("MACD histogram negative & declining")

        return TradingSignal(
            symbol=symbol,
            signal_type=SignalType.HOLD,
            entry_price=close,
            stop_loss=0.0,
            take_profit=0.0,
            risk_reward_ratio=0.0,
            timeframe="1H",
            indicator_snapshot=snapshot,
            reason=f"No entry: {'; '.join(hold_reasons)}.",
        )

    def evaluate_exit(self, symbol: str, df_ltf: pd.DataFrame, df_htf: Optional[pd.DataFrame] = None) -> TradingSignal:
        """
        Evaluate if an active position should be actively closed (SELL signal) before hitting SL/TP.
        Exit if trend completely breaks down.
        """
        from core.technical import technical_engine
        if not technical_engine.is_warmed_up(df_ltf):
            return TradingSignal(symbol=symbol, signal_type=SignalType.HOLD, entry_price=0, stop_loss=0, take_profit=0, risk_reward_ratio=0, timeframe="LTF")
            
        ltf_calc = technical_engine.calculate_indicators(df_ltf)
        curr = ltf_calc.iloc[-1]
        close = float(curr["close"])
        ema_medium = float(curr["ema_50"])
        
        # Active Exit Condition: 1H price breaks significantly below 1H EMA 50
        if close < ema_medium * 0.995:  # 0.5% buffer to avoid false wicks
            return TradingSignal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                entry_price=close,
                stop_loss=0.0,
                take_profit=0.0,
                risk_reward_ratio=0.0,
                timeframe="1H",
                indicator_snapshot={"close": close, "ema_50": ema_medium},
                reason="Trend breakdown: Price closed significantly below 1H EMA 50. Active exit triggered."
            )
            
        return TradingSignal(
            symbol=symbol, 
            signal_type=SignalType.HOLD, 
            entry_price=close, 
            stop_loss=0.0, 
            take_profit=0.0, 
            risk_reward_ratio=0.0, 
            timeframe="1H"
        )


# Global default strategy instance
swing_strategy = SwingTrendPullbackStrategy()
