"""
Trailing Stop Manager Module
Dynamically adjusts Stop Loss upward as price moves in favorable direction.
Prevents giving back profits on winning trades.

Rules:
- SL never moves down (only up or stays)
- Activation: price must first move > 1.5×ATR above entry
- Trail method: SL follows at entry + (profit × trail_factor)

See UNIFIED_PLAN.md Section 4.5.
"""

from dataclasses import dataclass
from typing import Dict, Optional
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class TrailingStopState:
    """State for a single position's trailing stop."""
    symbol: str
    entry_price: float
    original_sl: float
    current_sl: float
    highest_price: float
    atr_at_entry: float
    is_activated: bool = False


class TrailingStopManager:
    """
    Manages dynamic trailing stop losses for active positions.
    
    Activation tiers:
    1. Price moves > 1.5×ATR above entry → move SL to breakeven (entry price)
    2. Price moves > 2.5×ATR above entry → move SL to entry + 1.0×ATR
    3. Price moves > 3.5×ATR above entry → move SL to entry + 2.0×ATR
    
    After activation, SL tracks at: highest_price - trail_distance
    where trail_distance = max(1.0×ATR, initial risk × 0.5)
    """

    def __init__(
        self,
        activation_atr_multiple: float = 1.5,
        trail_atr_multiple: float = 1.0,
    ):
        self.activation_atr_multiple = activation_atr_multiple
        self.trail_atr_multiple = trail_atr_multiple
        # symbol -> TrailingStopState
        self._states: Dict[str, TrailingStopState] = {}

    def register_position(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        atr: float,
    ) -> TrailingStopState:
        """Register a new position for trailing stop management."""
        state = TrailingStopState(
            symbol=symbol.upper(),
            entry_price=entry_price,
            original_sl=stop_loss,
            current_sl=stop_loss,
            highest_price=entry_price,
            atr_at_entry=atr,
        )
        self._states[symbol.upper()] = state
        logger.info(
            "Position registered for trailing stop",
            symbol=symbol,
            entry=entry_price,
            sl=stop_loss,
            atr=atr,
        )
        return state

    def unregister_position(self, symbol: str) -> None:
        """Remove a position from trailing stop tracking."""
        self._states.pop(symbol.upper(), None)

    def update(self, symbol: str, current_price: float) -> Optional[TrailingStopState]:
        """
        Update trailing stop based on current price.
        Returns updated state if SL was adjusted, None if position not tracked.
        The SL value NEVER moves down.
        """
        state = self._states.get(symbol.upper())
        if state is None:
            return None

        atr = state.atr_at_entry
        entry = state.entry_price
        old_sl = state.current_sl

        # Update highest observed price
        if current_price > state.highest_price:
            state.highest_price = current_price

        profit_in_atr = (state.highest_price - entry) / atr if atr > 0 else 0.0

        # Tier 1: Price moved > 1.5×ATR → breakeven
        if profit_in_atr >= self.activation_atr_multiple and not state.is_activated:
            state.is_activated = True
            new_sl = entry  # breakeven
            if new_sl > state.current_sl:
                state.current_sl = round(new_sl, 2)
                logger.info(
                    "Trailing stop ACTIVATED: moved to breakeven",
                    symbol=symbol,
                    new_sl=state.current_sl,
                    profit_atr=round(profit_in_atr, 2),
                )

        # Tier 2: Price moved > 2.5×ATR → SL to entry + 1.0×ATR
        if profit_in_atr >= 2.5:
            new_sl = entry + (1.0 * atr)
            if new_sl > state.current_sl:
                state.current_sl = round(new_sl, 2)
                logger.info(
                    "Trailing stop TIER 2: SL moved to entry + 1×ATR",
                    symbol=symbol,
                    new_sl=state.current_sl,
                )

        # Tier 3: Price moved > 3.5×ATR → SL to entry + 2.0×ATR
        if profit_in_atr >= 3.5:
            new_sl = entry + (2.0 * atr)
            if new_sl > state.current_sl:
                state.current_sl = round(new_sl, 2)
                logger.info(
                    "Trailing stop TIER 3: SL moved to entry + 2×ATR",
                    symbol=symbol,
                    new_sl=state.current_sl,
                )

        # Dynamic trail: SL follows at highest_price - trail_distance
        if state.is_activated:
            trail_distance = max(self.trail_atr_multiple * atr, (entry - state.original_sl) * 0.5)
            dynamic_sl = state.highest_price - trail_distance
            if dynamic_sl > state.current_sl:
                state.current_sl = round(dynamic_sl, 2)

        # Log if SL changed
        if state.current_sl != old_sl:
            logger.info(
                "Trailing stop updated",
                symbol=symbol,
                old_sl=old_sl,
                new_sl=state.current_sl,
                highest_price=state.highest_price,
                profit_atr=round(profit_in_atr, 2),
            )

        return state

    def get_state(self, symbol: str) -> Optional[TrailingStopState]:
        """Get current trailing stop state for a symbol."""
        return self._states.get(symbol.upper())

    def should_exit(self, symbol: str, current_price: float) -> bool:
        """Check if current price has breached the trailing stop."""
        state = self.update(symbol, current_price)
        if state is None:
            return False
        return current_price <= state.current_sl

    @property
    def tracked_symbols(self) -> list[str]:
        return list(self._states.keys())


# Global Trailing Stop Manager singleton
trailing_stop_manager = TrailingStopManager()
