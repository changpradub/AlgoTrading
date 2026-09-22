-- =============================================================================
-- Migration 001: Initial Database Schema for Personal Algo-Trading Bot
-- All timestamps are stored in UTC (TIMESTAMPTZ)
-- Reference: UNIFIED_PLAN.md Section 5
-- =============================================================================

-- 1. Bot State & Configuration
CREATE TABLE IF NOT EXISTS bot_state (
    key VARCHAR(64) PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
);

CREATE TABLE IF NOT EXISTS strategy_config (
    strategy_name VARCHAR(64) PRIMARY KEY,
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
);

-- 2. Portfolio State Snapshots
CREATE TABLE IF NOT EXISTS portfolio_state (
    id BIGSERIAL PRIMARY KEY,
    equity NUMERIC(14, 4) NOT NULL,
    cash NUMERIC(14, 4) NOT NULL,
    buying_power NUMERIC(14, 4) NOT NULL,
    daytrade_count INT NOT NULL DEFAULT 0,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
);
CREATE INDEX IF NOT EXISTS idx_portfolio_state_recorded_at ON portfolio_state(recorded_at DESC);

-- 3. Orders History & Status
CREATE TABLE IF NOT EXISTS orders (
    id BIGSERIAL PRIMARY KEY,
    alpaca_order_id VARCHAR(64) UNIQUE,
    client_order_id VARCHAR(64) NOT NULL UNIQUE,
    symbol VARCHAR(16) NOT NULL,
    side VARCHAR(8) NOT NULL,            -- 'buy', 'sell'
    order_type VARCHAR(16) NOT NULL,      -- 'market', 'limit', 'stop', 'stop_limit'
    qty NUMERIC(12, 4) NOT NULL,
    filled_qty NUMERIC(12, 4) NOT NULL DEFAULT 0,
    limit_price NUMERIC(12, 4),
    stop_price NUMERIC(12, 4),
    status VARCHAR(32) NOT NULL,          -- 'new', 'partially_filled', 'filled', 'canceled', 'rejected'
    parent_order_id VARCHAR(64),
    bracket_role VARCHAR(16),             -- 'entry', 'take_profit', 'stop_loss'
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    filled_at TIMESTAMPTZ,
    canceled_at TIMESTAMPTZ,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_submitted_at ON orders(submitted_at DESC);

-- 4. Current & Historical Positions
CREATE TABLE IF NOT EXISTS positions (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(16) NOT NULL UNIQUE,
    qty NUMERIC(12, 4) NOT NULL,
    avg_entry_price NUMERIC(12, 4) NOT NULL,
    current_price NUMERIC(12, 4) NOT NULL,
    market_value NUMERIC(14, 4) NOT NULL,
    unrealized_pl NUMERIC(12, 4) NOT NULL,
    unrealized_plpc NUMERIC(8, 4) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
);

-- 5. Completed Trades Log
CREATE TABLE IF NOT EXISTS trades_log (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(16) NOT NULL,
    side VARCHAR(8) NOT NULL,
    qty NUMERIC(12, 4) NOT NULL,
    entry_price NUMERIC(12, 4) NOT NULL,
    exit_price NUMERIC(12, 4) NOT NULL,
    gross_pnl NUMERIC(12, 4) NOT NULL,
    net_pnl NUMERIC(12, 4) NOT NULL,
    entry_time TIMESTAMPTZ NOT NULL,
    exit_time TIMESTAMPTZ NOT NULL,
    exit_reason VARCHAR(64) NOT NULL,    -- 'take_profit', 'stop_loss', 'strategy_exit', 'kill_switch'
    strategy_name VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
);
CREATE INDEX IF NOT EXISTS idx_trades_log_symbol ON trades_log(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_log_exit_time ON trades_log(exit_time DESC);

-- 6. Pattern Day Trading (PDT) Counter Table
-- Tracks day trades (buy + sell in same day) to enforce the 3-trades-in-5-days rule
CREATE TABLE IF NOT EXISTS pdt_trades (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(16) NOT NULL,
    entry_order_id VARCHAR(64) NOT NULL,
    exit_order_id VARCHAR(64) NOT NULL,
    trade_date DATE NOT NULL,
    qty NUMERIC(12, 4) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
);
CREATE INDEX IF NOT EXISTS idx_pdt_trades_trade_date ON pdt_trades(trade_date DESC);

-- 7. Signals & Technical Indicator Snapshots
CREATE TABLE IF NOT EXISTS signals (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(16) NOT NULL,
    signal_type VARCHAR(16) NOT NULL,    -- 'BUY', 'SELL', 'HOLD'
    timeframe VARCHAR(16) NOT NULL,      -- '1H', '4H', '1D'
    price NUMERIC(12, 4) NOT NULL,
    indicator_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_executed BOOLEAN NOT NULL DEFAULT FALSE,
    rejection_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
);
CREATE INDEX IF NOT EXISTS idx_signals_created_at ON signals(created_at DESC);

-- 8. AI Sentiment Analysis (Phase 3)
CREATE TABLE IF NOT EXISTS ai_analysis (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(16) NOT NULL,
    headline TEXT NOT NULL,
    sentiment VARCHAR(16) NOT NULL,      -- 'positive', 'neutral', 'negative'
    confidence NUMERIC(4, 3) NOT NULL,   -- 0.000 to 1.000
    risk_event BOOLEAN NOT NULL DEFAULT FALSE,
    impact VARCHAR(16) NOT NULL,         -- 'low', 'medium', 'high'
    raw_response JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
);
CREATE INDEX IF NOT EXISTS idx_ai_analysis_created_at ON ai_analysis(created_at DESC);

-- 9. News Cache
CREATE TABLE IF NOT EXISTS news_cache (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(16) NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    source VARCHAR(64),
    url TEXT,
    published_at TIMESTAMPTZ NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
);
CREATE INDEX IF NOT EXISTS idx_news_cache_published ON news_cache(symbol, published_at DESC);

-- 10. Risk Events & System Lifecycle Events
CREATE TABLE IF NOT EXISTS risk_events (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(64) NOT NULL,     -- 'max_daily_loss', 'pdt_limit_reached', 'gap_warning'
    symbol VARCHAR(16),
    description TEXT NOT NULL,
    severity VARCHAR(16) NOT NULL,       -- 'warning', 'critical'
    action_taken TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
);

CREATE TABLE IF NOT EXISTS system_events (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(64) NOT NULL,     -- 'bot_started', 'bot_stopped', 'safe_mode', 'kill_switch'
    message TEXT NOT NULL,
    details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
);
