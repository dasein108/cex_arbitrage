-- =============================================================================
-- CEX Arbitrage Database Schema Initialization
-- =============================================================================
-- This script initializes the database schema for the CEX arbitrage system
-- Optimized for time-series data collection with TimescaleDB

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Book ticker snapshots table (main data collection table)
CREATE TABLE IF NOT EXISTS book_ticker_snapshots (
    id BIGSERIAL,
    timestamp TIMESTAMPTZ NOT NULL,
    exchange VARCHAR(20) NOT NULL,
    symbol_base VARCHAR(20) NOT NULL,  -- Changed to match app expectations
    symbol_quote VARCHAR(20) NOT NULL,  -- Added quote currency
    
    -- L1 orderbook data (matching app expectations)
    bid_price NUMERIC(20,8) NOT NULL,
    bid_qty NUMERIC(20,8) NOT NULL,  -- Changed from bid_size to bid_qty
    ask_price NUMERIC(20,8) NOT NULL,
    ask_qty NUMERIC(20,8) NOT NULL,  -- Changed from ask_size to ask_qty
    
    -- Metadata
    sequence_number BIGINT,
    update_type VARCHAR(10) DEFAULT 'snapshot',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT chk_positive_prices CHECK (bid_price > 0 AND ask_price > 0),
    CONSTRAINT chk_positive_quantities CHECK (bid_qty > 0 AND ask_qty > 0),  -- Updated column names
    CONSTRAINT chk_bid_ask_spread CHECK (ask_price >= bid_price),
    
    PRIMARY KEY (timestamp, exchange, symbol_base, symbol_quote)
);

-- Convert to TimescaleDB hypertable (optimized for smaller server)
SELECT create_hypertable('book_ticker_snapshots', 'timestamp', 
    chunk_time_interval => INTERVAL '30 minutes',  -- Smaller chunks for better performance
    if_not_exists => TRUE);

-- Orderbook depth table (L2+ data)
CREATE TABLE IF NOT EXISTS orderbook_depth (
    id BIGSERIAL,
    timestamp TIMESTAMPTZ NOT NULL,
    exchange VARCHAR(20) NOT NULL,
    symbol VARCHAR(30) NOT NULL,
    level INTEGER NOT NULL CHECK (level >= 1 AND level <= 20),
    
    -- Bid/ask levels
    bid_price NUMERIC(20,8),
    bid_size NUMERIC(20,8),
    ask_price NUMERIC(20,8),
    ask_size NUMERIC(20,8),
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    PRIMARY KEY (timestamp, exchange, symbol, level)
);

-- Convert to hypertable (optimized)
SELECT create_hypertable('orderbook_depth', 'timestamp',
    chunk_time_interval => INTERVAL '30 minutes',
    if_not_exists => TRUE);

-- Trade data table
CREATE TABLE IF NOT EXISTS trades (
    id BIGSERIAL,
    timestamp TIMESTAMPTZ NOT NULL,
    exchange VARCHAR(20) NOT NULL,
    symbol_base VARCHAR(20) NOT NULL,
    symbol_quote VARCHAR(20) NOT NULL,
    
    price NUMERIC(20,8) NOT NULL,
    quantity NUMERIC(20,8) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('buy', 'sell')),
    trade_id TEXT,
    
    -- Additional fields for complete trade data
    quote_quantity NUMERIC(20,8),
    is_buyer BOOLEAN,
    is_maker BOOLEAN,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    PRIMARY KEY (timestamp, exchange, symbol_base, symbol_quote, id)
);

-- Convert to hypertable (optimized)  
SELECT create_hypertable('trades', 'timestamp',
    chunk_time_interval => INTERVAL '30 minutes',
    if_not_exists => TRUE);

-- Analytics tables for computed metrics
CREATE TABLE IF NOT EXISTS arbitrage_opportunities (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(30) NOT NULL,
    
    -- Opportunity details
    exchange_buy VARCHAR(20) NOT NULL,
    exchange_sell VARCHAR(20) NOT NULL,
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
    executed BOOLEAN DEFAULT FALSE
);

-- Order flow imbalance metrics
CREATE TABLE IF NOT EXISTS order_flow_metrics (
    timestamp TIMESTAMPTZ NOT NULL,
    exchange VARCHAR(20) NOT NULL,
    symbol VARCHAR(30) NOT NULL,
    
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
    
    PRIMARY KEY (timestamp, exchange, symbol)
);

-- Convert to hypertable
SELECT create_hypertable('order_flow_metrics', 'timestamp',
    chunk_time_interval => INTERVAL '1 hour',
    if_not_exists => TRUE);

-- System monitoring table
CREATE TABLE IF NOT EXISTS collector_status (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    
    -- Connection status
    exchange VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL, -- 'connected', 'disconnected', 'error'
    
    -- Performance metrics
    messages_per_second NUMERIC(10,2),
    latency_ms NUMERIC(8,2),
    error_count INTEGER DEFAULT 0,
    
    -- Metadata
    last_message_at TIMESTAMPTZ,
    error_message TEXT
);

-- Indexes for optimal query performance
CREATE INDEX IF NOT EXISTS idx_book_ticker_exchange_symbol_time 
    ON book_ticker_snapshots(exchange, symbol_base, symbol_quote, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_book_ticker_symbol_time 
    ON book_ticker_snapshots(symbol_base, symbol_quote, timestamp DESC);

-- Create indexes for arbitrage_opportunities table
CREATE INDEX IF NOT EXISTS idx_arbitrage_opps_timestamp_symbol 
    ON arbitrage_opportunities(timestamp, symbol);

CREATE INDEX IF NOT EXISTS idx_arbitrage_opps_spread_desc 
    ON arbitrage_opportunities(spread_bps DESC);

CREATE INDEX IF NOT EXISTS idx_arbitrage_opps_detected_at 
    ON arbitrage_opportunities(detected_at);

CREATE INDEX IF NOT EXISTS idx_arbitrage_opps_symbol_time 
    ON arbitrage_opportunities(symbol, timestamp DESC);

-- Create indexes for collector_status table
CREATE INDEX IF NOT EXISTS idx_collector_status_timestamp_exchange 
    ON collector_status(timestamp, exchange);

CREATE INDEX IF NOT EXISTS idx_collector_status_status 
    ON collector_status(status);

-- Create indexes for trades table
CREATE INDEX IF NOT EXISTS idx_trades_exchange_symbol_time 
    ON trades(exchange, symbol_base, symbol_quote, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_trades_symbol_time 
    ON trades(symbol_base, symbol_quote, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_trades_side_time 
    ON trades(side, timestamp DESC);

-- Continuous aggregates for performance (TimescaleDB feature)
CREATE MATERIALIZED VIEW IF NOT EXISTS book_ticker_1min
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 minute', timestamp) AS bucket,
    exchange,
    symbol_base,
    symbol_quote,
    FIRST(bid_price, timestamp) as open_bid,
    MAX(bid_price) as high_bid,
    MIN(bid_price) as low_bid,
    LAST(bid_price, timestamp) as close_bid,
    FIRST(ask_price, timestamp) as open_ask,
    MAX(ask_price) as high_ask,
    MIN(ask_price) as low_ask,
    LAST(ask_price, timestamp) as close_ask,
    AVG((bid_price + ask_price) / 2) as avg_mid_price,
    AVG(ask_price - bid_price) as avg_spread,
    COUNT(*) as update_count
FROM book_ticker_snapshots
GROUP BY bucket, exchange, symbol_base, symbol_quote;

-- Refresh policy for continuous aggregates
SELECT add_continuous_aggregate_policy('book_ticker_1min',
    start_offset => INTERVAL '1 hour',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute',
    if_not_exists => TRUE);

-- Data retention policies (keep 30 days of raw data, 1 year of aggregates)
-- Optimized retention policies for 4GB server (7 days instead of 30)
SELECT add_retention_policy('book_ticker_snapshots', INTERVAL '7 days', if_not_exists => TRUE);
SELECT add_retention_policy('orderbook_depth', INTERVAL '7 days', if_not_exists => TRUE);
SELECT add_retention_policy('trades', INTERVAL '7 days', if_not_exists => TRUE);

-- Create database user with appropriate permissions
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'readonly_user') THEN
        CREATE ROLE readonly_user WITH LOGIN PASSWORD 'readonly_password_2024';
    END IF;
END
$$;

-- Grant read-only access to readonly user
GRANT CONNECT ON DATABASE arbitrage_data TO readonly_user;
GRANT USAGE ON SCHEMA public TO readonly_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO readonly_user;

-- Grant default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly_user;

-- Grant specific permissions for data collector user
GRANT ALL PRIVILEGES ON DATABASE arbitrage_data TO arbitrage_user;
GRANT ALL ON SCHEMA public TO arbitrage_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO arbitrage_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO arbitrage_user;

-- Ensure arbitrage_user owns the tables
ALTER TABLE book_ticker_snapshots OWNER TO arbitrage_user;
ALTER TABLE orderbook_depth OWNER TO arbitrage_user;
ALTER TABLE trades OWNER TO arbitrage_user;
ALTER TABLE arbitrage_opportunities OWNER TO arbitrage_user;
ALTER TABLE order_flow_metrics OWNER TO arbitrage_user;
ALTER TABLE collector_status OWNER TO arbitrage_user;

COMMIT;