"""
Position Sizing Calculator Module
Computes safe trade allocations based on risk capital, tranche sizing, and ATR Gap Factor.
Supports Alpaca fractional shares down to 4 decimal places.
See UNIFIED_PLAN.md Section 4.6.
"""

from dataclasses import dataclass
import structlog

from config.settings import settings
from config.constants import DEFAULT_TRANCHE_SIZE_USD

logger = structlog.get_logger(__name__)


@dataclass
class PositionSizeResult:
    shares: float
    notional_usd: float
    risk_usd: float
    is_valid: bool
    reason: str


class PositionSizingCalculator:
    """Calculates risk-adjusted position size."""

    def __init__(
        self,
        risk_per_trade_pct: float = 0.02,  # 2% max risk per trade
        tranche_budget_usd: float = settings.TRADE_BUDGET_PER_TRANCHE_USD,
        max_position_usd: float = settings.MAX_POSITION_SIZE_USD,
        min_trade_usd: float = 1.0,        # Alpaca minimum order value
    ):
        self.risk_per_trade_pct = risk_per_trade_pct
        self.tranche_budget_usd = tranche_budget_usd
        self.max_position_usd = max_position_usd
        self.min_trade_usd = min_trade_usd

    def calculate(
        self,
        equity: float,
        buying_power: float,
        entry_price: float,
        stop_loss: float,
        risk_factor: float = 1.0,
    ) -> PositionSizeResult:
        """
        Calculate trade shares and notional size.
        """
        if entry_price <= 0 or stop_loss >= entry_price:
            return PositionSizeResult(
                shares=0.0,
                notional_usd=0.0,
                risk_usd=0.0,
                is_valid=False,
                reason="Invalid price parameters: Stop loss must be below entry price.",
            )

        if buying_power < self.min_trade_usd:
            return PositionSizeResult(
                shares=0.0,
                notional_usd=0.0,
                risk_usd=0.0,
                is_valid=False,
                reason=f"Insufficient buying power: ${buying_power:.2f} < ${self.min_trade_usd:.2f}.",
            )

        # 1. Calculate Risk Capital
        risk_per_share = entry_price - stop_loss
        max_risk_capital = equity * self.risk_per_trade_pct
        shares_by_risk = max_risk_capital / risk_per_share

        # 2. Bound by Tranche Budget & Buying Power
        effective_budget = min(self.tranche_budget_usd, self.max_position_usd, buying_power)
        shares_by_budget = effective_budget / entry_price

        # 3. Choose the more conservative size & apply gap risk factor
        raw_shares = min(shares_by_risk, shares_by_budget) * max(0.1, risk_factor)

        # 4. Round to 4 decimal places for fractional shares
        shares = round(raw_shares, 4)
        notional_usd = round(shares * entry_price, 2)
        actual_risk_usd = round(shares * risk_per_share, 2)

        if notional_usd < self.min_trade_usd:
            return PositionSizeResult(
                shares=0.0,
                notional_usd=notional_usd,
                risk_usd=actual_risk_usd,
                is_valid=False,
                reason=f"Calculated trade size (${notional_usd:.2f}) below minimum (${self.min_trade_usd:.2f}).",
            )

        logger.info(
            "Position size calculated",
            shares=shares,
            notional=notional_usd,
            risk=actual_risk_usd,
            risk_factor=risk_factor,
        )

        return PositionSizeResult(
            shares=shares,
            notional_usd=notional_usd,
            risk_usd=actual_risk_usd,
            is_valid=True,
            reason="Position sized successfully.",
        )


# Global Position Sizing Calculator singleton
position_calculator = PositionSizingCalculator()
