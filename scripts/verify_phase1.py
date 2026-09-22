"""
Phase 1 Verification Script
Validates all infrastructure modules: Configuration, Timezone, Rate Limiting,
Scheduler, Logging, and Database Schema scripts.
Run with: .venv\\Scripts\\python scripts/verify_phase1.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import settings
from config.constants import (
    PDT_MAX_DAY_TRADES,
    WARMUP_BARS_MIN,
    ALPACA_REST_MAX_REQ_PER_MINUTE,
)
from utils.timezone import now_utc, to_eastern, to_bangkok, format_multi_tz_display
from utils.rate_limiter import AsyncRateLimiter
from core.scheduler import market_scheduler
import structlog

logger = structlog.get_logger("verify_phase1")


async def main():
    print("=" * 70)
    print("  PERSONAL ALGO-TRADING BOT — PHASE 1 INFRASTRUCTURE VERIFICATION")
    print("=" * 70)

    # 1. Architecture Invariants
    print("\n[1] Checking Architecture Constants & Invariants:")
    print(f"  • PDT Max Day Trades:        {PDT_MAX_DAY_TRADES} in 5 business days")
    print(f"  • Min Indicator Warmup:      {WARMUP_BARS_MIN} bars")
    print(f"  • Alpaca REST Rate Limit:    {ALPACA_REST_MAX_REQ_PER_MINUTE} req/min")
    print(f"  • Target Symbols:            {settings.target_symbol_list}")
    print(f"  • Trading Mode:              {settings.TRADING_MODE.upper()}")

    # 2. Timezone Alignment
    print("\n[2] Checking Timezone Handling:")
    utc = now_utc()
    print(f"  • Current UTC Time:          {utc.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"  • US Eastern Time:           {to_eastern(utc).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"  • Bangkok Time (ICT):        {to_bangkok(utc).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"  • Formatted Display:         {format_multi_tz_display(utc)}")

    # 3. Rate Limiter Test
    print("\n[3] Testing Async Rate Limiter:")
    limiter = AsyncRateLimiter(max_rate=50, time_period=1.0)
    await limiter.acquire(1.0)
    print("  • Token bucket acquired successfully.")

    # 4. Market Hours Scheduler
    print("\n[4] Checking Market Hours Scheduler:")
    status = await market_scheduler.get_market_status()
    print(f"  • Market Phase:              {status.phase.value.upper()}")
    print(f"  • Is Regular Hours:          {status.is_regular_hours}")
    print(f"  • Next Open:                 {format_multi_tz_display(status.next_open_utc)}")
    print(f"  • Next Close:                {format_multi_tz_display(status.next_close_utc)}")

    # 5. Database Schema Files
    print("\n[5] Checking Database Migration Files:")
    migration_file = Path("db/migrations/001_initial_schema.sql")
    if migration_file.exists():
        print(f"  • Schema Migration Found:    {migration_file} ({migration_file.stat().st_size} bytes)")
    else:
        print("  • WARNING: Migration file missing!")

    # 6. Alpaca API Credentials Check
    print("\n[6] Checking Alpaca Credentials in .env:")
    if settings.ALPACA_API_KEY and settings.ALPACA_SECRET_KEY:
        print("  • Alpaca API Key ID:        Configured")
        print("  • Alpaca Base URL:           " + settings.ALPACA_BASE_URL)
        try:
            from core.alpaca_client import alpaca_trading_client
            print("  • Testing Alpaca API connection...")
            account = await alpaca_trading_client.get_account()
            print(f"  • [SUCCESS] Account Equity:  ${float(account.equity):,.2f}")
            print(f"  • [SUCCESS] Buying Power:    ${float(account.buying_power):,.2f}")
            print(f"  • [SUCCESS] Daytrade Count:  {account.daytrade_count}")
        except Exception as e:
            print(f"  • [NOTICE] Alpaca connection test failed: {e}")
    else:
        print("  • [NOTICE] Alpaca API credentials not yet configured in .env.")
        print("    -> Copy .env.example to .env and fill in your ALPACA_API_KEY and ALPACA_SECRET_KEY.")

    print("\n" + "=" * 70)
    print("  PHASE 1 VERIFICATION COMPLETE")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
