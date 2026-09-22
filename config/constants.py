"""
Core Architectural Constants & Invariants
These values are hard-coded constraints designed to protect capital and guarantee safety.
See UNIFIED_PLAN.md Section 4.5 & Section 7.
"""

from typing import Final

# ------------------------------------------------------------------------------
# 1. Pattern Day Trader (PDT) Rule Constraints
# SEC Rule: Accounts with equity < $25,000 may not make more than 3 day trades
# within a rolling 5-business-day window.
# ------------------------------------------------------------------------------
PDT_MAX_DAY_TRADES: Final[int] = 3
PDT_ROLLING_BUSINESS_DAYS: Final[int] = 5
PDT_MIN_EQUITY_THRESHOLD_USD: Final[float] = 25_000.0

# ------------------------------------------------------------------------------
# 2. Indicator Warmup Constraints
# No trading signals may be generated until sufficient historical bars have loaded.
# ------------------------------------------------------------------------------
WARMUP_BARS_MIN: Final[int] = 100

# ------------------------------------------------------------------------------
# 3. Rate Limiting Constraints
# Alpaca REST API rate limit is 200 requests/minute.
# We set an internal ceiling slightly lower for a safety cushion.
# ------------------------------------------------------------------------------
ALPACA_REST_MAX_REQ_PER_MINUTE: Final[int] = 200
ALPACA_REST_SAFETY_REQ_PER_MINUTE: Final[int] = 180

# ------------------------------------------------------------------------------
# 4. Market Hours (US Eastern Time)
# ------------------------------------------------------------------------------
MARKET_TIMEZONE: Final[str] = "America/New_York"
BANGKOK_TIMEZONE: Final[str] = "Asia/Bangkok"
UTC_TIMEZONE: Final[str] = "UTC"

REGULAR_MARKET_OPEN_TIME_ET: Final[str] = "09:30"
REGULAR_MARKET_CLOSE_TIME_ET: Final[str] = "16:00"
PRE_MARKET_OPEN_TIME_ET: Final[str] = "04:00"
AFTER_MARKET_CLOSE_TIME_ET: Final[str] = "20:00"

# ------------------------------------------------------------------------------
# 5. Risk & Position Limits (Hard-coded safety defaults)
# ------------------------------------------------------------------------------
DEFAULT_INITIAL_CAPITAL_USD: Final[float] = 700.0
DEFAULT_MAX_DAILY_LOSS_PCT: Final[float] = 0.02  # 2% of equity ($14 on $700)
DEFAULT_TRANCHE_SIZE_USD: Final[float] = 20.0     # ~$20 per tranche
DEFAULT_MAX_CONCURRENT_POSITIONS: Final[int] = 3
MAX_SLIPPAGE_TOLERANCE_PCT: Final[float] = 0.005  # 0.5% max acceptable slippage
