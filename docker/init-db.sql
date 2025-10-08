-- =============================================================================
-- CEX Arbitrage Database Schema Initialization
-- =============================================================================
-- This script initializes the database schema for the CEX arbitrage system
-- Optimized for time-series data collection with TimescaleDB

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- =============================================================================
-- NORMALIZED SCHEMA TABLES
-- =============================================================================

-- Exchanges table - stores supported exchange configurations
CREATE TABLE IF NOT EXISTS exchanges (
    id SERIAL PRIMARY KEY,
    enum_value VARCHAR(30) NOT NULL UNIQUE,  -- MEXC_SPOT, GATEIO_SPOT, GATEIO_FUTURES
    exchange_name VARCHAR(20) NOT NULL,      -- MEXC, GATEIO, GATEIO
    market_type VARCHAR(10) NOT NULL,        -- SPOT, FUTURES
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT chk_enum_format CHECK (enum_value ~ '^[A-Z]+_(SPOT|FUTURES)$'),
    CONSTRAINT chk_market_type CHECK (market_type IN ('SPOT', 'FUTURES'))
);

-- Symbols table - stores trading symbols with exchange relationship
CREATE TABLE IF NOT EXISTS symbols (
    id SERIAL PRIMARY KEY,
    exchange_id INTEGER NOT NULL REFERENCES exchanges(id),
    symbol_base VARCHAR(20) NOT NULL,        -- BTC, ETH, etc.
    symbol_quote VARCHAR(20) NOT NULL,       -- USDT, USDC, etc.
    exchange_symbol VARCHAR(30) NOT NULL,    -- BTCUSDT (exchange format)
    symbol_type VARCHAR(10) DEFAULT 'SPOT',  -- SPOT, FUTURES
    is_active BOOLEAN DEFAULT TRUE,
    precision_price INTEGER DEFAULT 8,
    precision_quantity INTEGER DEFAULT 8,
    min_quantity NUMERIC(20,8),
    min_notional NUMERIC(20,8),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Unique constraint to prevent duplicate symbols per exchange
    CONSTRAINT uk_symbols_exchange_symbol UNIQUE (exchange_id, symbol_base, symbol_quote, symbol_type),
    CONSTRAINT uk_symbols_exchange_format UNIQUE (exchange_id, exchange_symbol, symbol_type),
    CONSTRAINT chk_symbol_type CHECK (symbol_type IN ('SPOT', 'FUTURES')),
    CONSTRAINT chk_positive_precision CHECK (precision_price > 0 AND precision_quantity > 0)
);

-- Book ticker snapshots table (main data collection table) - NORMALIZED SCHEMA
CREATE TABLE IF NOT EXISTS book_ticker_snapshots (
    id BIGSERIAL,
    timestamp TIMESTAMPTZ NOT NULL,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),  -- Foreign key to symbols table
    
    -- L1 orderbook data (HFT optimized)
    bid_price NUMERIC(20,8) NOT NULL,
    bid_qty NUMERIC(20,8) NOT NULL,
    ask_price NUMERIC(20,8) NOT NULL,
    ask_qty NUMERIC(20,8) NOT NULL,
    
    -- Metadata
    sequence_number BIGINT,
    update_type VARCHAR(10) DEFAULT 'snapshot',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- HFT Performance Constraints
    CONSTRAINT chk_positive_prices CHECK (bid_price > 0 AND ask_price > 0),
    CONSTRAINT chk_positive_quantities CHECK (bid_qty > 0 AND ask_qty > 0),
    CONSTRAINT chk_bid_ask_spread CHECK (ask_price >= bid_price),
    
    -- Optimized primary key for time-series partitioning
    PRIMARY KEY (timestamp, symbol_id)
);

-- Convert to TimescaleDB hypertable (optimized for smaller server)
SELECT create_hypertable('book_ticker_snapshots', 'timestamp', 
    chunk_time_interval => INTERVAL '30 minutes',  -- Smaller chunks for better performance
    if_not_exists => TRUE);

-- Orderbook depth table (L2+ data) - NORMALIZED SCHEMA
CREATE TABLE IF NOT EXISTS orderbook_depth (
    id BIGSERIAL,
    timestamp TIMESTAMPTZ NOT NULL,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),  -- Foreign key to symbols table
    level INTEGER NOT NULL CHECK (level >= 1 AND level <= 20),
    
    -- Bid/ask levels
    bid_price NUMERIC(20,8),
    bid_size NUMERIC(20,8),
    ask_price NUMERIC(20,8),
    ask_size NUMERIC(20,8),
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    PRIMARY KEY (timestamp, symbol_id, level)
);

-- Convert to hypertable (optimized)
SELECT create_hypertable('orderbook_depth', 'timestamp',
    chunk_time_interval => INTERVAL '30 minutes',
    if_not_exists => TRUE);

-- Trade data table - NORMALIZED SCHEMA (matches TradeSnapshot model but with symbol_id)
CREATE TABLE IF NOT EXISTS trade_snapshots (
    id BIGSERIAL,
    timestamp TIMESTAMPTZ NOT NULL,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),  -- Foreign key to symbols table
    
    -- Core trade data
    price NUMERIC(20,8) NOT NULL,
    quantity NUMERIC(20,8) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('buy', 'sell')),
    trade_id TEXT,
    
    -- Extended trade information
    quote_quantity NUMERIC(20,8),
    is_buyer BOOLEAN,
    is_maker BOOLEAN,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- HFT optimized constraints
    CONSTRAINT chk_positive_trade_price CHECK (price > 0),
    CONSTRAINT chk_positive_trade_quantity CHECK (quantity > 0),
    
    PRIMARY KEY (timestamp, symbol_id, id)
);

-- Funding rate snapshots table - NORMALIZED SCHEMA (matches FundingRateSnapshot model)
CREATE TABLE IF NOT EXISTS funding_rate_snapshots (
    id BIGSERIAL,
    timestamp TIMESTAMPTZ NOT NULL,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),  -- Foreign key to symbols table
    
    -- Funding rate data
    funding_rate NUMERIC(12,8) NOT NULL,  -- Current funding rate (e.g., 0.00010000 for 0.01%)
    funding_time BIGINT NOT NULL,         -- Next funding time (Unix timestamp in milliseconds)
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- HFT Performance Constraints
    CONSTRAINT chk_funding_rate_bounds CHECK (funding_rate >= -1.0 AND funding_rate <= 1.0),
    CONSTRAINT chk_funding_time_valid CHECK (funding_time > 0),
    CONSTRAINT chk_funding_timestamp_valid CHECK (timestamp >= '2020-01-01'::timestamptz),
    
    -- Optimized primary key for time-series partitioning
    PRIMARY KEY (timestamp, symbol_id)
);

-- Convert to hypertable (optimized)  
SELECT create_hypertable('trade_snapshots', 'timestamp',
    chunk_time_interval => INTERVAL '30 minutes',
    if_not_exists => TRUE);

-- Convert funding rate snapshots to hypertable (optimized for funding rate collection)
SELECT create_hypertable('funding_rate_snapshots', 'timestamp', 
    chunk_time_interval => INTERVAL '1 hour',  -- Hourly chunks for funding data
    if_not_exists => TRUE);

-- =============================================================================
-- INSERT INITIAL EXCHANGE DATA
-- =============================================================================

-- Insert supported exchanges with proper enum values
INSERT INTO exchanges (enum_value, exchange_name, market_type, is_active) VALUES
    ('MEXC_SPOT', 'MEXC', 'SPOT', TRUE),
    ('GATEIO_SPOT', 'GATEIO', 'SPOT', TRUE),
    ('GATEIO_FUTURES', 'GATEIO', 'FUTURES', TRUE)
ON CONFLICT (enum_value) DO NOTHING;

-- =============================================================================
-- ANALYTICS TABLES
-- =============================================================================

-- Analytics table for computed arbitrage metrics - NORMALIZED SCHEMA
CREATE TABLE IF NOT EXISTS arbitrage_opportunities (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),  -- Foreign key to symbols table
    
    -- Opportunity details (using exchange IDs for consistency)
    buy_exchange_id INTEGER NOT NULL REFERENCES exchanges(id),
    sell_exchange_id INTEGER NOT NULL REFERENCES exchanges(id),
    buy_price NUMERIC(20,8) NOT NULL,
    sell_price NUMERIC(20,8) NOT NULL,
    spread_bps NUMERIC(10,4) NOT NULL,
    
    -- Volume and liquidity
    max_volume_usd NUMERIC(15,2),
    buy_liquidity NUMERIC(20,8),
    sell_liquidity NUMERIC(20,8),
    
    -- Metadata
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    duration_ms INTEGER,
    executed BOOLEAN DEFAULT FALSE,
    
    -- Performance constraints
    CONSTRAINT chk_positive_spread CHECK (spread_bps > 0),
    CONSTRAINT chk_valid_prices CHECK (buy_price > 0 AND sell_price > 0),
    CONSTRAINT chk_arbitrage_logic CHECK (sell_price > buy_price)
);

-- Order flow imbalance metrics - NORMALIZED SCHEMA
CREATE TABLE IF NOT EXISTS order_flow_metrics (
    timestamp TIMESTAMPTZ NOT NULL,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),  -- Foreign key to symbols table
    
    -- OFI calculations
    ofi_score NUMERIC(8,6) CHECK (ofi_score >= -1 AND ofi_score <= 1),
    ofi_normalized NUMERIC(8,6),
    
    -- Price metrics
    microprice NUMERIC(20,8),
    mid_price NUMERIC(20,8),
    spread_bps NUMERIC(10,4),
    
    -- Volume metrics
    bid_volume_usd NUMERIC(15,2),
    ask_volume_usd NUMERIC(15,2),
    volume_imbalance NUMERIC(8,6),
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Performance constraints
    CONSTRAINT chk_ofi_bounds CHECK (ofi_score >= -1 AND ofi_score <= 1),
    CONSTRAINT chk_positive_mid_price CHECK (mid_price > 0),
    
    PRIMARY KEY (timestamp, symbol_id)
);

-- Convert to hypertable
SELECT create_hypertable('order_flow_metrics', 'timestamp',
    chunk_time_interval => INTERVAL '1 hour',
    if_not_exists => TRUE);

-- System monitoring table - NORMALIZED SCHEMA
CREATE TABLE IF NOT EXISTS collector_status (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    
    -- Connection status (using exchange_id for consistency)
    exchange_id INTEGER NOT NULL REFERENCES exchanges(id),
    status VARCHAR(20) NOT NULL CHECK (status IN ('connected', 'disconnected', 'error', 'connecting')),
    
    -- Performance metrics
    messages_per_second NUMERIC(10,2),
    latency_ms NUMERIC(8,2),
    error_count INTEGER DEFAULT 0,
    
    -- Metadata
    last_message_at TIMESTAMPTZ,
    error_message TEXT,
    
    -- Performance constraints
    CONSTRAINT chk_positive_metrics CHECK (messages_per_second >= 0 AND latency_ms >= 0)
);

-- =============================================================================
-- HFT-OPTIMIZED INDEXES FOR NORMALIZED SCHEMA
-- =============================================================================

-- Core indexes for exchanges and symbols tables (foundational)
CREATE INDEX IF NOT EXISTS idx_exchanges_enum_value ON exchanges(enum_value);
CREATE INDEX IF NOT EXISTS idx_exchanges_active ON exchanges(is_active) WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_symbols_exchange_id ON symbols(exchange_id);
CREATE INDEX IF NOT EXISTS idx_symbols_base_quote ON symbols(symbol_base, symbol_quote);
CREATE INDEX IF NOT EXISTS idx_symbols_active ON symbols(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_symbols_exchange_symbol ON symbols(exchange_id, exchange_symbol);

-- HFT-critical indexes for book_ticker_snapshots (sub-millisecond queries)
CREATE INDEX IF NOT EXISTS idx_book_ticker_symbol_time 
    ON book_ticker_snapshots(symbol_id, timestamp DESC);
    
CREATE INDEX IF NOT EXISTS idx_book_ticker_time_symbol 
    ON book_ticker_snapshots(timestamp DESC, symbol_id);
    
-- Composite index for exchange + symbol queries (via JOIN optimization)
CREATE INDEX IF NOT EXISTS idx_book_ticker_recent 
    ON book_ticker_snapshots(timestamp DESC) WHERE timestamp > NOW() - INTERVAL '1 hour';

-- HFT-optimized indexes for trade_snapshots
CREATE INDEX IF NOT EXISTS idx_trade_snapshots_symbol_time 
    ON trade_snapshots(symbol_id, timestamp DESC);
    
CREATE INDEX IF NOT EXISTS idx_trade_snapshots_side_time 
    ON trade_snapshots(side, timestamp DESC);
    
CREATE INDEX IF NOT EXISTS idx_trade_snapshots_recent 
    ON trade_snapshots(timestamp DESC) WHERE timestamp > NOW() - INTERVAL '1 hour';

-- HFT-optimized indexes for funding_rate_snapshots
CREATE INDEX IF NOT EXISTS idx_funding_rates_symbol_time 
    ON funding_rate_snapshots(symbol_id, timestamp DESC);
    
CREATE INDEX IF NOT EXISTS idx_funding_rates_time_symbol 
    ON funding_rate_snapshots(timestamp DESC, symbol_id);

-- Index for recent funding rates (most common query pattern)
CREATE INDEX IF NOT EXISTS idx_funding_rates_recent 
    ON funding_rate_snapshots(timestamp DESC) WHERE timestamp > NOW() - INTERVAL '24 hours';

-- Index for funding rate range queries (analytics)
CREATE INDEX IF NOT EXISTS idx_funding_rates_rate_range 
    ON funding_rate_snapshots(funding_rate) WHERE ABS(funding_rate) > 0.0001;

-- Index for funding time queries (next funding events)
CREATE INDEX IF NOT EXISTS idx_funding_rates_funding_time 
    ON funding_rate_snapshots(funding_time);

-- Indexes for arbitrage_opportunities table (normalized)
CREATE INDEX IF NOT EXISTS idx_arbitrage_opps_symbol_time 
    ON arbitrage_opportunities(symbol_id, timestamp DESC);
    
CREATE INDEX IF NOT EXISTS idx_arbitrage_opps_spread_desc 
    ON arbitrage_opportunities(spread_bps DESC);
    
CREATE INDEX IF NOT EXISTS idx_arbitrage_opps_detected_recent 
    ON arbitrage_opportunities(detected_at DESC) WHERE detected_at > NOW() - INTERVAL '1 day';
    
CREATE INDEX IF NOT EXISTS idx_arbitrage_opps_exchanges 
    ON arbitrage_opportunities(buy_exchange_id, sell_exchange_id);

-- Indexes for order_flow_metrics table
CREATE INDEX IF NOT EXISTS idx_order_flow_symbol_time 
    ON order_flow_metrics(symbol_id, timestamp DESC);
    
CREATE INDEX IF NOT EXISTS idx_order_flow_ofi_score 
    ON order_flow_metrics(ofi_score DESC) WHERE ABS(ofi_score) > 0.1;

-- Indexes for collector_status table (normalized)
CREATE INDEX IF NOT EXISTS idx_collector_status_exchange_time 
    ON collector_status(exchange_id, timestamp DESC);
    
CREATE INDEX IF NOT EXISTS idx_collector_status_status 
    ON collector_status(status, timestamp DESC);
    
CREATE INDEX IF NOT EXISTS idx_collector_status_recent 
    ON collector_status(timestamp DESC) WHERE timestamp > NOW() - INTERVAL '1 hour';

-- Indexes for orderbook_depth table
CREATE INDEX IF NOT EXISTS idx_orderbook_depth_symbol_time_level 
    ON orderbook_depth(symbol_id, timestamp DESC, level);

-- =============================================================================
-- TIMESCALEDB CONTINUOUS AGGREGATES (NORMALIZED SCHEMA)
-- =============================================================================

-- 1-minute aggregates for book ticker data (normalized schema with JOINs)
CREATE MATERIALIZED VIEW IF NOT EXISTS book_ticker_1min
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 minute', bts.timestamp) AS bucket,
    bts.symbol_id,
    s.symbol_base,
    s.symbol_quote,
    e.enum_value as exchange,
    FIRST(bts.bid_price, bts.timestamp) as open_bid,
    MAX(bts.bid_price) as high_bid,
    MIN(bts.bid_price) as low_bid,
    LAST(bts.bid_price, bts.timestamp) as close_bid,
    FIRST(bts.ask_price, bts.timestamp) as open_ask,
    MAX(bts.ask_price) as high_ask,
    MIN(bts.ask_price) as low_ask,
    LAST(bts.ask_price, bts.timestamp) as close_ask,
    AVG((bts.bid_price + bts.ask_price) / 2) as avg_mid_price,
    AVG(bts.ask_price - bts.bid_price) as avg_spread,
    COUNT(*) as update_count
FROM book_ticker_snapshots bts
JOIN symbols s ON bts.symbol_id = s.id
JOIN exchanges e ON s.exchange_id = e.id
GROUP BY bucket, bts.symbol_id, s.symbol_base, s.symbol_quote, e.enum_value;

-- Refresh policy for continuous aggregates
SELECT add_continuous_aggregate_policy('book_ticker_1min',
    start_offset => INTERVAL '1 hour',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute',
    if_not_exists => TRUE);

-- =============================================================================
-- HFT-OPTIMIZED DATA RETENTION POLICIES
-- =============================================================================

-- Production-ready retention policies for 4GB server with HFT requirements
-- Raw time-series data: Keep 7 days for detailed analysis
SELECT add_retention_policy('book_ticker_snapshots', INTERVAL '7 days', if_not_exists => TRUE);
SELECT add_retention_policy('orderbook_depth', INTERVAL '7 days', if_not_exists => TRUE);
SELECT add_retention_policy('trade_snapshots', INTERVAL '7 days', if_not_exists => TRUE);

-- Funding rates: Keep 90 days for analysis and backtesting
SELECT add_retention_policy('funding_rate_snapshots', INTERVAL '90 days', if_not_exists => TRUE);

-- Metrics and analytics: Keep 30 days
SELECT add_retention_policy('order_flow_metrics', INTERVAL '30 days', if_not_exists => TRUE);

-- Arbitrage opportunities: Keep 90 days for backtesting
SELECT add_retention_policy('arbitrage_opportunities', INTERVAL '90 days', if_not_exists => TRUE);

-- System monitoring: Keep 30 days
SELECT add_retention_policy('collector_status', INTERVAL '30 days', if_not_exists => TRUE);

-- Create database user with appropriate permissions
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'readonly_user') THEN
        CREATE ROLE readonly_user WITH LOGIN PASSWORD 'readonly_password_2024';
    END IF;
END
$$;

-- =============================================================================
-- USER PERMISSIONS AND OWNERSHIP (NORMALIZED SCHEMA)
-- =============================================================================

-- Grant read-only access to readonly user
GRANT CONNECT ON DATABASE arbitrage_data TO readonly_user;
GRANT USAGE ON SCHEMA public TO readonly_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO readonly_user;

-- Grant default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON SEQUENCES TO readonly_user;

-- Grant specific permissions for data collector user (full access)
GRANT ALL PRIVILEGES ON DATABASE arbitrage_data TO arbitrage_user;
GRANT ALL ON SCHEMA public TO arbitrage_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO arbitrage_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO arbitrage_user;

-- Ensure arbitrage_user owns all the normalized schema tables
ALTER TABLE exchanges OWNER TO arbitrage_user;
ALTER TABLE symbols OWNER TO arbitrage_user;
ALTER TABLE book_ticker_snapshots OWNER TO arbitrage_user;
ALTER TABLE orderbook_depth OWNER TO arbitrage_user;
ALTER TABLE trade_snapshots OWNER TO arbitrage_user;
ALTER TABLE funding_rate_snapshots OWNER TO arbitrage_user;
ALTER TABLE arbitrage_opportunities OWNER TO arbitrage_user;
ALTER TABLE order_flow_metrics OWNER TO arbitrage_user;
ALTER TABLE collector_status OWNER TO arbitrage_user;

-- Grant usage on continuous aggregate
ALTER MATERIALIZED VIEW book_ticker_1min OWNER TO arbitrage_user;

-- =============================================================================
-- SCHEMA VALIDATION AND FINAL OPTIMIZATIONS
-- =============================================================================

-- Add table comments for documentation
COMMENT ON TABLE exchanges IS 'Supported cryptocurrency exchanges with enum values matching ExchangeEnum';
COMMENT ON TABLE symbols IS 'Trading symbols normalized by exchange with foreign key relationships';
COMMENT ON TABLE book_ticker_snapshots IS 'L1 orderbook snapshots optimized for HFT sub-millisecond queries';
COMMENT ON TABLE trade_snapshots IS 'Individual trade executions with normalized symbol references';
COMMENT ON TABLE funding_rate_snapshots IS 'Funding rate snapshots for futures contracts with normalized symbol references';
COMMENT ON TABLE arbitrage_opportunities IS 'Detected arbitrage opportunities with exchange relationships';
COMMENT ON TABLE order_flow_metrics IS 'Order flow imbalance calculations for market analysis';
COMMENT ON TABLE collector_status IS 'Real-time system monitoring and health checks';

-- Final constraint validations
ALTER TABLE book_ticker_snapshots ADD CONSTRAINT chk_valid_timestamp 
    CHECK (timestamp >= '2020-01-01'::timestamptz AND timestamp <= NOW() + INTERVAL '1 hour');
    
ALTER TABLE trade_snapshots ADD CONSTRAINT chk_valid_trade_timestamp 
    CHECK (timestamp >= '2020-01-01'::timestamptz AND timestamp <= NOW() + INTERVAL '1 hour');

COMMIT;