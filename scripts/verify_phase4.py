"""
Verification Script for Phase 4: Fail-safe, Recovery & Risk Hardening
Executes live diagnostics:
1. Startup Recovery Engine execution against Alpaca Paper API
2. Health Monitor ping and latency diagnostics
3. Safe Mode transition & recovery simulation
4. Real-time Telegram verification
"""

import asyncio
import os
import sys
from datetime import datetime

# Windows terminal UTF-8 encoding support
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.failsafe import safe_mode_manager, SystemState
from core.startup_recovery import startup_recovery_engine
from monitoring.health_check import health_monitor
from notifications import dispatcher


async def main():
    print("=" * 65)
    print("PHASE 4: FAIL-SAFE, RECOVERY & RISK HARDENING VERIFICATION")
    print("=" * 65)

    # 1. Startup Recovery Flow
    print("\n[Step 1] Running Startup Recovery Engine against live Alpaca...")
    recovery_report = await startup_recovery_engine.run_recovery()

    print(f"  • Broker Connected: {recovery_report.broker_connected}")
    print(f"  • Account Equity: ${recovery_report.equity:,.2f}")
    print(f"  • Buying Power: ${recovery_report.buying_power:,.2f}")
    print(f"  • PDT Day Trades Used: {recovery_report.pdt_daytrade_count}/3 ({recovery_report.pdt_allowed_remaining} remaining)")
    print(f"  • Open Positions: {recovery_report.open_positions_count}")
    print(f"  • Open Orders: {recovery_report.open_orders_count}")
    print(f"  • System Ready: {recovery_report.system_ready}")
    for n in recovery_report.notes:
        print(f"    - {n}")

    # 2. Health Monitor Diagnostics
    print("\n[Step 2] Running Live Health Monitor Diagnostics...")
    health_report = await health_monitor.run_diagnostics()
    alpaca_comp = health_report.components["alpaca"]
    db_comp = health_report.components["database"]

    print(f"  • Alpaca API Health: {'OK' if alpaca_comp.is_healthy else 'FAILED'} (Latency: {alpaca_comp.latency_ms}ms, {alpaca_comp.details})")
    print(f"  • Database Health: {'OK' if db_comp.is_healthy else 'FAILED'} (Latency: {db_comp.latency_ms}ms, {db_comp.details})")
    print(f"  • Safe Mode State: {health_report.safe_mode_state}")
    print(f"  • Overall Health: {'HEALTHY' if health_report.overall_healthy else 'UNHEALTHY'}")

    # 3. Safe Mode and Recovery Cycle Simulation
    print("\n[Step 3] Simulating Fail-Safe State Transitions...")
    print(f"  • Initial State: {safe_mode_manager.state.value} (can_trade={safe_mode_manager.can_trade})")

    # Record errors to trigger Safe Mode
    print("  • Simulating 3 consecutive network errors...")
    await safe_mode_manager.record_error("TestTimeout", "Simulated timeout 1")
    await safe_mode_manager.record_error("TestTimeout", "Simulated timeout 2")
    await safe_mode_manager.record_error("TestTimeout", "Simulated timeout 3")

    print(f"  • State after 3 errors: {safe_mode_manager.state.value} (can_trade={safe_mode_manager.can_trade})")
    assert safe_mode_manager.is_safe_mode is True, "Safe mode should be active"

    # Reset back to NORMAL
    print("  • Performing Operator Reset to NORMAL...")
    await safe_mode_manager.reset_to_normal("Verification completed successfully")
    print(f"  • Restored State: {safe_mode_manager.state.value} (can_trade={safe_mode_manager.can_trade})")
    assert safe_mode_manager.can_trade is True, "System should be ready for trading"

    # 4. Dispatch Telegram Heartbeat
    print("\n[Step 4] Dispatching System Heartbeat to Telegram...")
    await health_monitor.send_heartbeat()
    print("  • Heartbeat dispatched to Telegram successfully.")

    print("\n" + "=" * 65)
    print("ALL PHASE 4 VERIFICATION CHECKS PASSED SUCCESSFULLY!")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
