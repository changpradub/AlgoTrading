"""
Risk Management Engine
The final defensive gatekeeper before any order is dispatched to the broker.
Enforces:
1. Hard-coded Max Daily Loss
2. Pattern Day Trading (PDT) Rule Protection (SEC rule for accounts < $25,000)
3. Max Concurrent Positions
4. Duplicate Order Prevention
5. Overnight Gap Risk Assessment (ATR-based)
6. Emergency Kill Switch
See UNIFIED_PLAN.md Section 4.5.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
import structlog

from config.constants import (
    PDT_MAX_DAY_TRADES,
    PDT_MIN_EQUITY_THRESHOLD_USD,
    DEFAULT_MAX_CONCURRENT_POSITIONS,
)
from config.settings import settings
from core.strategy import TradingSignal, SignalType

logger = structlog.get_logger(__name__)


@dataclass
class RiskValidationResult:
    approved: bool
    reason: str
    risk_factor: float = 1.0  # Multiplier for sizing (e.g. 0.5 if gap risk elevated)
    kill_switch_active: bool = False


class RiskEngine:
    """Rigorous risk compliance engine."""

    def __init__(
        self,
        max_daily_loss_usd: float = settings.MAX_DAILY_LOSS_USD,
        max_positions: int = settings.MAX_CONCURRENT_POSITIONS,
        pdt_limit: int = PDT_MAX_DAY_TRADES,
        pdt_equity_threshold: float = PDT_MIN_EQUITY_THRESHOLD_USD,
    ):
        self.max_daily_loss_usd = max_daily_loss_usd
        self.max_positions = max_positions
        self.pdt_limit = pdt_limit
        self.pdt_equity_threshold = pdt_equity_threshold
        self._kill_switch_active = False

    def activate_kill_switch(self, reason: str) -> None:
        """Trigger emergency kill switch."""
        self._kill_switch_active = True
        logger.critical("EMERGENCY KILL SWITCH ACTIVATED", reason=reason)

    def deactivate_kill_switch(self) -> None:
        """Deactivate kill switch after manual review."""
        self._kill_switch_active = False
        logger.info("Kill switch deactivated manually.")

    @property
    def is_kill_switched(self) -> bool:
        return self._kill_switch_active

    def check_daily_loss(self, current_daily_loss_usd: float) -> tuple[bool, str]:
        """Check if daily loss exceeds hard-coded threshold."""
        if current_daily_loss_usd >= self.max_daily_loss_usd:
            return False, f"Max daily loss breached: ${current_daily_loss_usd:.2f} >= ${self.max_daily_loss_usd:.2f}"
        return True, "Daily loss within bounds."

    def check_pdt_compliance(
        self,
        equity: float,
        pdt_count_5_days: int,
        intending_day_trade: bool = False,
    ) -> tuple[bool, str]:
        """
        Enforce SEC Pattern Day Trading Rule:
        Accounts under $25,000 cannot execute > 3 day trades in rolling 5 business days.
        """
        if equity >= self.pdt_equity_threshold:
            return True, "Account equity exceeds $25,000 threshold (PDT exempt)."

        if pdt_count_5_days >= self.pdt_limit:
            if intending_day_trade:
                return False, f"PDT Limit reached ({pdt_count_5_days}/{self.pdt_limit}). Same-day exit prohibited."
            logger.warning(
                "PDT count maxed out. Long positions must be held overnight.",
                pdt_count=pdt_count_5_days,
            )

        return True, f"PDT count acceptable ({pdt_count_5_days}/{self.pdt_limit})."

    def assess_gap_risk(self, atr: float, price: float) -> tuple[float, str]:
        """
        Assess overnight gap risk using ATR as percentage of price.
        High volatility requires scaling down position size.
        """
        if price <= 0:
            return 1.0, "Invalid price."

        atr_pct = (atr / price) * 100.0
        # If ATR > 5% of price, overnight gap risk is high -> reduce size to 50%
        if atr_pct >= 5.0:
            return 0.5, f"High overnight gap risk (ATR is {atr_pct:.1f}% of price). Sizing reduced by 50%."
        # If ATR > 3% of price -> reduce size to 75%
        if atr_pct >= 3.0:
            return 0.75, f"Moderate overnight gap risk (ATR is {atr_pct:.1f}% of price). Sizing reduced by 25%."

        return 1.0, f"Normal volatility (ATR is {atr_pct:.1f}% of price)."

    def validate_signal(
        self,
        signal: TradingSignal,
        equity: float,
        current_daily_loss: float,
        open_positions: List[str],
        open_order_symbols: List[str],
        pdt_count_5_days: int,
    ) -> RiskValidationResult:
        """
        Master validation function.
        Rejects signal if ANY safety invariant is violated.
        """
        # 1. Kill Switch Check
        if self._kill_switch_active:
            return RiskValidationResult(
                approved=False,
                reason="Kill switch is active. All trading halted.",
                kill_switch_active=True,
            )

        # Only validate BUY signals
        if signal.signal_type != SignalType.BUY:
            return RiskValidationResult(approved=False, reason="Signal is not BUY.")

        # 2. Hard-coded Daily Loss Limit
        loss_ok, loss_msg = self.check_daily_loss(current_daily_loss)
        if not loss_ok:
            self.activate_kill_switch(loss_msg)
            return RiskValidationResult(approved=False, reason=loss_msg, kill_switch_active=True)

        # 3. Duplicate Order Check
        if signal.symbol in open_order_symbols:
            return RiskValidationResult(
                approved=False,
                reason=f"Open order already exists for {signal.symbol}. Preventing duplicate.",
            )

        # 4. Existing Position Check (No pyramiding in V1)
        if signal.symbol in open_positions:
            return RiskValidationResult(
                approved=False,
                reason=f"Position already open for {signal.symbol}. Max 1 position per symbol in V1.",
            )

        # 5. Max Concurrent Positions
        if len(open_positions) >= self.max_positions:
            return RiskValidationResult(
                approved=False,
                reason=f"Max concurrent positions reached ({len(open_positions)}/{self.max_positions}).",
            )

        # 6. PDT Compliance Check
        pdt_ok, pdt_msg = self.check_pdt_compliance(equity, pdt_count_5_days)
        if not pdt_ok:
            return RiskValidationResult(approved=False, reason=pdt_msg)

        # 7. Bracket Order Integrity Check
        if signal.stop_loss >= signal.entry_price or signal.take_profit <= signal.entry_price:
            return RiskValidationResult(
                approved=False,
                reason=f"Invalid Bracket targets: Entry=${signal.entry_price}, SL=${signal.stop_loss}, TP=${signal.take_profit}.",
            )

        # 8. Overnight Gap Risk Factor
        atr = float(signal.indicator_snapshot.get("atr", signal.risk_per_share))
        gap_factor, gap_msg = self.assess_gap_risk(atr, signal.entry_price)

        logger.info(
            "Signal approved by Risk Engine",
            symbol=signal.symbol,
            gap_factor=gap_factor,
            gap_assessment=gap_msg,
        )

        return RiskValidationResult(
            approved=True,
            reason="All risk parameters validated.",
            risk_factor=gap_factor,
        )


# Global Risk Engine singleton
risk_engine = RiskEngine()
