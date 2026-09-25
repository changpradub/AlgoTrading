-- =============================================================================
-- Migration 002: Support Open Trade Tracking in trades_log
-- Allows trades to be logged at entry time with exit_reason = 'open'
-- and updated later when TP/SL triggers.
-- Reference: P0-1 Trade Logging Fix
-- =============================================================================

-- 1. Make exit_price nullable / allow 0 for open trades
-- (Already NUMERIC NOT NULL in 001 — we use 0.0 as sentinel value for open trades)
-- No schema change needed; we use exit_reason = 'open' as the marker.

-- 2. Add index for fast lookup of open trades
CREATE INDEX IF NOT EXISTS idx_trades_log_exit_reason ON trades_log(exit_reason);

-- 3. Add index for daily P/L calculation queries
CREATE INDEX IF NOT EXISTS idx_trades_log_exit_time_reason ON trades_log(exit_time DESC, exit_reason)
    WHERE exit_reason != 'open';

-- 4. Add realized_pl column alias (net_pnl is the canonical column)
-- No schema change needed; daily_reporter already uses net_pnl.
