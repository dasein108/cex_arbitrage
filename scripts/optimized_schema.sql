-- =============================================================================
-- OPTIMIZED CEX ARBITRAGE DATABASE SCHEMA - MINIMAL SPACE USAGE
-- =============================================================================
-- This schema is optimized for HFT systems with strict space constraints
-- Target: <5GB database size for sustainable 25GB disk operation
-- Focus: Essential data only, aggressive compression, minimal retention

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- =============================================================================
-- OPTIMIZED PRIMARY DATA TABLE - BOOK TICKER SNAPSHOTS
-- =============================================================================
-- Simplified structure focusing only on essential L1 data for arbitrage

CREATE TABLE IF NOT EXISTS book_ticker_snapshots_optimized (
    -- Optimized timestamp (no separate ID needed)
    timestamp TIMESTAMPTZ NOT NULL,
    
    -- Compact exchange representation (use SMALLINT for known exchanges)
    exchange_id SMALLINT NOT NULL, -- MEXC=1, GATEIO=2, etc. (saves ~15 bytes per row vs VARCHAR)
    
    -- Optimized symbol representation
    symbol_id INTEGER NOT NULL, -- Pre-computed symbol ID lookup (saves ~40 bytes per row)
    
    -- Essential L1 data only (reduced precision for space savings)
    bid_price NUMERIC(16,6) NOT NULL, -- Reduced from (20,8) - sufficient for crypto
    bid_qty NUMERIC(16,6) NOT NULL,   -- Reduced precision
    ask_price NUMERIC(16,6) NOT NULL,
    ask_qty NUMERIC(16,6) NOT NULL,
    
    -- Minimal metadata (removed non-essential fields)
    sequence_number INTEGER, -- Reduced from BIGINT
    
    -- Constraints (simplified)
    CONSTRAINT chk_positive_prices_opt CHECK (bid_price > 0 AND ask_price > 0),
    CONSTRAINT chk_positive_quantities_opt CHECK (bid_qty > 0 AND ask_qty > 0),
    CONSTRAINT chk_bid_ask_spread_opt CHECK (ask_price >= bid_price),
    
    -- Optimized primary key (timestamp first for TimescaleDB)
    PRIMARY KEY (timestamp, exchange_id, symbol_id)
);

-- Convert to hypertable with aggressive chunking for HFT workloads
SELECT create_hypertable(
    'book_ticker_snapshots_optimized', 
    'timestamp',
    chunk_time_interval => INTERVAL '15 minutes', -- Smaller chunks for better compression
    if_not_exists => TRUE
);

-- Enable compression (TimescaleDB feature for space savings)
ALTER TABLE book_ticker_snapshots_optimized SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'exchange_id, symbol_id',
    timescaledb.compress_orderby = 'timestamp'
);

-- =============================================================================
-- EXCHANGE AND SYMBOL LOOKUP TABLES (NORMALIZATION FOR SPACE SAVINGS)
-- =============================================================================

-- Exchange lookup table (replaces VARCHAR storage)
CREATE TABLE IF NOT EXISTS exchanges (
    id SMALLINT PRIMARY KEY,
    name VARCHAR(10) NOT NULL UNIQUE, -- Shortened length
    display_name VARCHAR(20)
);

-- Insert known exchanges
INSERT INTO exchanges (id, name, display_name) VALUES 
(1, 'mexc', 'MEXC'),
(2, 'gateio', 'Gate.io'),
(3, 'binance', 'Binance'),
(4, 'okx', 'OKX')
ON CONFLICT (id) DO NOTHING;

-- Symbol lookup table (massive space savings for repeated symbols)
CREATE TABLE IF NOT EXISTS symbols (
    id SERIAL PRIMARY KEY,
    base_asset VARCHAR(10) NOT NULL,
    quote_asset VARCHAR(10) NOT NULL,
    symbol_name VARCHAR(20) NOT NULL UNIQUE, -- e.g., 'BTC-USDT'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(base_asset, quote_asset)
);

-- Pre-populate common trading pairs
INSERT INTO symbols (base_asset, quote_asset, symbol_name) VALUES 
('BTC', 'USDT', 'BTC-USDT'),
('ETH', 'USDT', 'ETH-USDT'),
('BNB', 'USDT', 'BNB-USDT'),
('ADA', 'USDT', 'ADA-USDT'),
('SOL', 'USDT', 'SOL-USDT'),
('XRP', 'USDT', 'XRP-USDT'),
('DOGE', 'USDT', 'DOGE-USDT'),
('AVAX', 'USDT', 'AVAX-USDT'),
('DOT', 'USDT', 'DOT-USDT'),
('MATIC', 'USDT', 'MATIC-USDT')
ON CONFLICT (symbol_name) DO NOTHING;

-- =============================================================================
-- MINIMAL ARBITRAGE OPPORTUNITIES TABLE
-- =============================================================================
-- Store only actionable arbitrage opportunities (not all price differences)

CREATE TABLE IF NOT EXISTS arbitrage_opportunities_optimized (
    timestamp TIMESTAMPTZ NOT NULL,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),
    
    -- Exchange IDs instead of names
    exchange_buy_id SMALLINT NOT NULL REFERENCES exchanges(id),
    exchange_sell_id SMALLINT NOT NULL REFERENCES exchanges(id),
    
    -- Essential arbitrage data
    buy_price NUMERIC(16,6) NOT NULL,
    sell_price NUMERIC(16,6) NOT NULL,
    spread_bps SMALLINT NOT NULL, -- Integer basis points (saves space)
    
    -- Volume data (simplified)
    max_volume_usd NUMERIC(12,2), -- Reduced precision
    
    -- Execution tracking (minimal)
    executed BOOLEAN DEFAULT FALSE,
    
    PRIMARY KEY (timestamp, symbol_id, exchange_buy_id, exchange_sell_id)
);

-- Convert to hypertable
SELECT create_hypertable(
    'arbitrage_opportunities_optimized', 
    'timestamp',
    chunk_time_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- Enable compression
ALTER TABLE arbitrage_opportunities_optimized SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol_id, exchange_buy_id, exchange_sell_id',
    timescaledb.compress_orderby = 'timestamp'
);

-- =============================================================================
-- SYSTEM MONITORING TABLE (ESSENTIAL ONLY)
-- =============================================================================

CREATE TABLE IF NOT EXISTS system_status (
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    exchange_id SMALLINT NOT NULL REFERENCES exchanges(id),
    status SMALLINT NOT NULL, -- 0=disconnected, 1=connected, 2=error
    latency_ms SMALLINT, -- Sufficient range for HFT latency
    error_count SMALLINT DEFAULT 0,
    
    PRIMARY KEY (timestamp, exchange_id)
);

-- Short retention for system status (1 day only)
SELECT create_hypertable(
    'system_status', 
    'timestamp',
    chunk_time_interval => INTERVAL '2 hours',
    if_not_exists => TRUE
);

-- =============================================================================
-- OPTIMIZED INDEXES (MINIMAL SET FOR HFT PERFORMANCE)
-- =============================================================================

-- Critical index for real-time arbitrage queries
CREATE INDEX IF NOT EXISTS idx_book_ticker_optimized_recent 
    ON book_ticker_snapshots_optimized(exchange_id, symbol_id, timestamp DESC)
    WHERE timestamp > NOW() - INTERVAL '1 hour';

-- Index for arbitrage opportunity scanning
CREATE INDEX IF NOT EXISTS idx_arbitrage_opps_optimized_spread 
    ON arbitrage_opportunities_optimized(spread_bps DESC, timestamp DESC)
    WHERE executed = FALSE AND timestamp > NOW() - INTERVAL '1 hour';

-- =============================================================================
-- AGGRESSIVE RETENTION POLICIES (HFT-OPTIMIZED)
-- =============================================================================

-- Very aggressive retention for space savings
-- Keep only 24 hours of L1 data (sufficient for most HFT strategies)
SELECT add_retention_policy(
    'book_ticker_snapshots_optimized', 
    INTERVAL '24 hours', 
    if_not_exists => TRUE
);

-- Keep arbitrage opportunities for 48 hours (for analysis)
SELECT add_retention_policy(
    'arbitrage_opportunities_optimized', 
    INTERVAL '48 hours', 
    if_not_exists => TRUE
);

-- Keep system status for 24 hours only
SELECT add_retention_policy(
    'system_status', 
    INTERVAL '24 hours', 
    if_not_exists => TRUE
);

-- =============================================================================
-- COMPRESSION POLICIES (AGGRESSIVE SPACE SAVINGS)
-- =============================================================================

-- Compress data after 1 hour (when it's no longer real-time critical)
SELECT add_compression_policy(
    'book_ticker_snapshots_optimized',
    INTERVAL '1 hour',
    if_not_exists => TRUE
);

SELECT add_compression_policy(
    'arbitrage_opportunities_optimized',
    INTERVAL '2 hours',
    if_not_exists => TRUE
);

SELECT add_compression_policy(
    'system_status',
    INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- =============================================================================
-- HELPER FUNCTIONS FOR DATA INSERTION
-- =============================================================================

-- Function to get or create symbol ID
CREATE OR REPLACE FUNCTION get_symbol_id(base_asset_param TEXT, quote_asset_param TEXT)
RETURNS INTEGER AS $$
DECLARE
    symbol_id_result INTEGER;
    symbol_name_param TEXT;
BEGIN
    symbol_name_param := base_asset_param || '-' || quote_asset_param;
    
    SELECT id INTO symbol_id_result 
    FROM symbols 
    WHERE symbol_name = symbol_name_param;
    
    IF symbol_id_result IS NULL THEN
        INSERT INTO symbols (base_asset, quote_asset, symbol_name)
        VALUES (base_asset_param, quote_asset_param, symbol_name_param)
        RETURNING id INTO symbol_id_result;
    END IF;
    
    RETURN symbol_id_result;
END;
$$ LANGUAGE plpgsql;

-- Function to get exchange ID by name
CREATE OR REPLACE FUNCTION get_exchange_id(exchange_name_param TEXT)
RETURNS SMALLINT AS $$
DECLARE
    exchange_id_result SMALLINT;
BEGIN
    SELECT id INTO exchange_id_result 
    FROM exchanges 
    WHERE name = LOWER(exchange_name_param);
    
    IF exchange_id_result IS NULL THEN
        RAISE EXCEPTION 'Unknown exchange: %', exchange_name_param;
    END IF;
    
    RETURN exchange_id_result;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- VIEW FOR BACKWARD COMPATIBILITY
-- =============================================================================

-- Create view that matches original schema for application compatibility
CREATE OR REPLACE VIEW book_ticker_snapshots AS
SELECT 
    b.timestamp,
    e.name as exchange,
    s.base_asset as symbol_base,
    s.quote_asset as symbol_quote,
    b.bid_price,
    b.bid_qty,
    b.ask_price,
    b.ask_qty,
    b.sequence_number::BIGINT,
    'snapshot' as update_type,
    b.timestamp as created_at
FROM book_ticker_snapshots_optimized b
JOIN exchanges e ON b.exchange_id = e.id
JOIN symbols s ON b.symbol_id = s.id;

-- =============================================================================
-- SPACE ESTIMATION AND MONITORING
-- =============================================================================

-- Function to estimate space savings
CREATE OR REPLACE FUNCTION estimate_space_savings()
RETURNS TABLE(
    metric TEXT,
    old_size_estimate TEXT,
    new_size_estimate TEXT,
    savings_percent INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        'Per row space savings'::TEXT,
        '~180 bytes'::TEXT,
        '~45 bytes'::TEXT,
        75;
    
    RETURN QUERY
    SELECT 
        'Daily data (1M rows)'::TEXT,
        '~180 MB'::TEXT,
        '~45 MB'::TEXT,
        75;
        
    RETURN QUERY
    SELECT 
        'With compression'::TEXT,
        '~45 MB'::TEXT,
        '~15 MB'::TEXT,
        67;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- DATABASE USERS AND PERMISSIONS
-- =============================================================================

-- Create optimized database user
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'arbitrage_user') THEN
        CREATE ROLE arbitrage_user WITH LOGIN PASSWORD 'prod_password_2024';
    END IF;
END
$$;

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE arbitrage_data TO arbitrage_user;
GRANT ALL ON SCHEMA public TO arbitrage_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO arbitrage_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO arbitrage_user;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO arbitrage_user;

-- Set table ownership
ALTER TABLE book_ticker_snapshots_optimized OWNER TO arbitrage_user;
ALTER TABLE arbitrage_opportunities_optimized OWNER TO arbitrage_user;
ALTER TABLE system_status OWNER TO arbitrage_user;
ALTER TABLE exchanges OWNER TO arbitrage_user;
ALTER TABLE symbols OWNER TO arbitrage_user;

COMMIT;

-- =============================================================================
-- USAGE EXAMPLES
-- =============================================================================

/*
-- Insert data using helper functions:
INSERT INTO book_ticker_snapshots_optimized (
    timestamp, exchange_id, symbol_id, bid_price, bid_qty, ask_price, ask_qty
) VALUES (
    NOW(),
    get_exchange_id('mexc'),
    get_symbol_id('BTC', 'USDT'),
    50000.123456,
    1.500000,
    50010.234567,
    2.100000
);

-- Query using the compatibility view:
SELECT * FROM book_ticker_snapshots 
WHERE exchange = 'mexc' 
AND symbol_base = 'BTC' 
AND timestamp > NOW() - INTERVAL '1 hour';

-- Check space savings:
SELECT * FROM estimate_space_savings();
*/