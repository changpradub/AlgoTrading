"""
State Management & Reconciliation Module
Maintains stateless execution integrity by synchronizing database records
with actual Alpaca broker state upon bot startup and after trade executions.
Rule: No new orders may be placed without completing state reconciliation.
See UNIFIED_PLAN.md Section 4.8.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
import structlog

from core.alpaca_client import alpaca_trading_client
from db.connection import db_manager

logger = structlog.get_logger(__name__)


@dataclass
class ReconciliationReport:
    is_synchronized: bool
    broker_positions_count: int
    db_positions_count: int
    matched_symbols: List[str]
    mismatches: List[str]
    account_equity: float
    buying_power: float
    pdt_daytrade_count: int


class StateManager:
    """Manages bot state recovery and broker-database reconciliation."""

    def __init__(self):
        self._is_reconciled = False

    @property
    def is_reconciled(self) -> bool:
        return self._is_reconciled

    async def reconcile_state(self) -> ReconciliationReport:
        """
        Query actual broker state and reconcile with PostgreSQL.
        Detects orphaned orders or ghost positions.
        """
        logger.info("Commencing State Reconciliation with Alpaca...")

        # 1. Fetch live account & positions from Alpaca
        account = await alpaca_trading_client.get_account()
        broker_positions = await alpaca_trading_client.get_all_positions()

        equity = float(account.equity)
        buying_power = float(account.buying_power)
        pdt_count = int(account.daytrade_count)

        broker_symbols = {p.symbol.upper(): float(p.qty) for p in broker_positions}

        # 2. Query database positions if connected
        db_symbols: Dict[str, float] = {}
        mismatches: List[str] = []

        if db_manager.is_connected:
            rows = await db_manager.fetch("SELECT symbol, qty FROM positions WHERE qty > 0")
            for r in rows:
                db_symbols[r["symbol"].upper()] = float(r["qty"])

            # Detect differences
            all_symbols = set(broker_symbols.keys()).union(set(db_symbols.keys()))
            for sym in all_symbols:
                b_qty = broker_symbols.get(sym, 0.0)
                d_qty = db_symbols.get(sym, 0.0)
                if abs(b_qty - d_qty) > 0.0001:
                    mismatch_desc = f"{sym}: Broker has {b_qty} shares, DB has {d_qty} shares."
                    mismatches.append(mismatch_desc)
                    logger.warning("Position mismatch detected", detail=mismatch_desc)

            # Synchronize DB positions table to match broker reality
            await self._sync_db_positions(broker_positions)

            # Record portfolio state snapshot
            await db_manager.execute(
                """
                INSERT INTO portfolio_state (equity, cash, buying_power, daytrade_count)
                VALUES ($1, $2, $3, $4)
                """,
                equity,
                float(account.cash),
                buying_power,
                pdt_count,
            )
        else:
            logger.info("Database not connected; skipping DB reconciliation sync.")

        matched = [s for s in broker_symbols.keys() if s in db_symbols]
        is_synchronized = len(mismatches) == 0

        report = ReconciliationReport(
            is_synchronized=is_synchronized,
            broker_positions_count=len(broker_symbols),
            db_positions_count=len(db_symbols),
            matched_symbols=matched,
            mismatches=mismatches,
            account_equity=equity,
            buying_power=buying_power,
            pdt_daytrade_count=pdt_count,
        )

        self._is_reconciled = True
        logger.info(
            "State reconciliation completed",
            synchronized=is_synchronized,
            equity=equity,
            broker_positions=len(broker_symbols),
        )
        return report

    async def _sync_db_positions(self, broker_positions) -> None:
        """Overwrite DB positions with verified broker positions."""
        if not db_manager.is_connected:
            return

        async with db_manager.connection() as conn:
            async with conn.transaction():
                # Clear stale positions
                await conn.execute("DELETE FROM positions")
                for p in broker_positions:
                    await conn.execute(
                        """
                        INSERT INTO positions (symbol, qty, avg_entry_price, current_price, market_value, unrealized_pl, unrealized_plpc)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        """,
                        p.symbol.upper(),
                        float(p.qty),
                        float(p.avg_entry_price),
                        float(p.current_price),
                        float(p.market_value),
                        float(p.unrealized_pl),
                        float(p.unrealized_plpc),
                    )


# Global State Manager singleton
state_manager = StateManager()
