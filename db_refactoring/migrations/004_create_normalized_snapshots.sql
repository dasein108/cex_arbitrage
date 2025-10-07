-- Migration 004: Create normalized snapshot tables
-- Purpose: Create normalized book ticker and trade snapshot tables using foreign key relationships
-- Performance: Optimized for HFT operations with proper indexing and foreign key constraints
-- Dependencies: Requires 002_create_exchanges.sql and 003_create_symbols.sql

-- Enable timing for performance monitoring
\timing on

-- Transaction wrapper for atomic migration
BEGIN;

-- Create normalized book ticker snapshots table
CREATE TABLE IF NOT EXISTS normalized_book_ticker_snapshots (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    
    -- Foreign key relationships
    exchange_id SMALLINT NOT NULL REFERENCES exchanges(id) ON DELETE CASCADE,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    
    -- Book ticker data
    bid_price NUMERIC(20,8) NOT NULL,
    bid_qty NUMERIC(20,8) NOT NULL,
    ask_price NUMERIC(20,8) NOT NULL,
    ask_qty NUMERIC(20,8) NOT NULL,
    
    -- Timing
    timestamp TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    
    -- Constraints
    CONSTRAINT chk_normalized_book_ticker_positive_prices CHECK (
        bid_price > 0 AND ask_price > 0 AND bid_qty >= 0 AND ask_qty >= 0
    ),
    CONSTRAINT chk_normalized_book_ticker_spread CHECK (ask_price >= bid_price)
);

-- Create normalized trade snapshots table
CREATE TABLE IF NOT EXISTS normalized_trade_snapshots (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    
    -- Foreign key relationships
    exchange_id SMALLINT NOT NULL REFERENCES exchanges(id) ON DELETE CASCADE,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    
    -- Trade data
    price NUMERIC(20,8) NOT NULL,
    quantity NUMERIC(20,8) NOT NULL,
    side VARCHAR(10) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    
    -- Optional trade metadata
    trade_id VARCHAR(100),
    quote_quantity NUMERIC(20,8),
    is_buyer BOOLEAN,
    is_maker BOOLEAN,
    
    -- Timing
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    
    -- Constraints
    CONSTRAINT chk_normalized_trade_positive_values CHECK (
        price > 0 AND quantity > 0
    ),
    CONSTRAINT chk_normalized_trade_side CHECK (side IN ('buy', 'sell'))
);

-- Performance indexes for normalized book ticker snapshots
-- Time-series queries (most common)
CREATE INDEX IF NOT EXISTS idx_normalized_book_ticker_timestamp ON normalized_book_ticker_snapshots(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_normalized_book_ticker_exchange_timestamp ON normalized_book_ticker_snapshots(exchange_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_normalized_book_ticker_symbol_timestamp ON normalized_book_ticker_snapshots(symbol_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_normalized_book_ticker_exchange_symbol_timestamp ON normalized_book_ticker_snapshots(exchange_id, symbol_id, timestamp DESC);

-- Arbitrage analysis queries
CREATE INDEX IF NOT EXISTS idx_normalized_book_ticker_symbol_exchange ON normalized_book_ticker_snapshots(symbol_id, exchange_id, timestamp DESC);

-- Covering index for common queries
CREATE INDEX IF NOT EXISTS idx_normalized_book_ticker_covering ON normalized_book_ticker_snapshots(
    exchange_id, symbol_id, timestamp DESC
) INCLUDE (bid_price, ask_price, bid_qty, ask_qty);

-- Performance indexes for normalized trade snapshots
-- Time-series queries
CREATE INDEX IF NOT EXISTS idx_normalized_trade_timestamp ON normalized_trade_snapshots(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_normalized_trade_exchange_timestamp ON normalized_trade_snapshots(exchange_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_normalized_trade_symbol_timestamp ON normalized_trade_snapshots(symbol_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_normalized_trade_exchange_symbol_timestamp ON normalized_trade_snapshots(exchange_id, symbol_id, timestamp DESC);

-- Trade analysis queries
CREATE INDEX IF NOT EXISTS idx_normalized_trade_side ON normalized_trade_snapshots(side, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_normalized_trade_symbol_side ON normalized_trade_snapshots(symbol_id, side, timestamp DESC);

-- Trade ID lookups (when available)
CREATE INDEX IF NOT EXISTS idx_normalized_trade_trade_id ON normalized_trade_snapshots(trade_id) WHERE trade_id IS NOT NULL;

-- Covering index for common analytics queries
CREATE INDEX IF NOT EXISTS idx_normalized_trade_covering ON normalized_trade_snapshots(
    exchange_id, symbol_id, timestamp DESC
) INCLUDE (price, quantity, side);

-- Partitioning preparation (for future scaling)
-- Note: These comments document the partitioning strategy for when the tables grow large
-- Recommended partitioning: PARTITION BY RANGE (timestamp) with daily/weekly partitions

-- Table comments for documentation
COMMENT ON TABLE normalized_book_ticker_snapshots IS 
    'Normalized book ticker snapshots using foreign key relationships for optimal performance and referential integrity. Optimized for HFT arbitrage analysis.';

COMMENT ON TABLE normalized_trade_snapshots IS 
    'Normalized trade snapshots using foreign key relationships for optimal performance and referential integrity. Optimized for trade analysis and volume tracking.';

-- Column comments for normalized book ticker snapshots
COMMENT ON COLUMN normalized_book_ticker_snapshots.exchange_id IS 
    'Foreign key reference to exchanges table for normalized exchange identification';

COMMENT ON COLUMN normalized_book_ticker_snapshots.symbol_id IS 
    'Foreign key reference to symbols table for normalized symbol identification';

COMMENT ON COLUMN normalized_book_ticker_snapshots.timestamp IS 
    'Exchange-provided timestamp for the book ticker data';

COMMENT ON COLUMN normalized_book_ticker_snapshots.created_at IS 
    'Database insertion timestamp for audit and latency tracking';

-- Column comments for normalized trade snapshots
COMMENT ON COLUMN normalized_trade_snapshots.exchange_id IS 
    'Foreign key reference to exchanges table for normalized exchange identification';

COMMENT ON COLUMN normalized_trade_snapshots.symbol_id IS 
    'Foreign key reference to symbols table for normalized symbol identification';

COMMENT ON COLUMN normalized_trade_snapshots.side IS 
    'Trade side: buy or sell from the perspective of the taker';

COMMENT ON COLUMN normalized_trade_snapshots.trade_id IS 
    'Exchange-specific trade identifier when available';

COMMENT ON COLUMN normalized_trade_snapshots.is_buyer IS 
    'Whether the trade was executed by a buyer (true) or seller (false)';

COMMENT ON COLUMN normalized_trade_snapshots.is_maker IS 
    'Whether the trade was executed against a maker order (true) or taker order (false)';

-- Create a view for easy querying with exchange and symbol names
CREATE OR REPLACE VIEW v_normalized_book_ticker_with_names AS
SELECT 
    nbt.id,
    e.name AS exchange_name,
    e.display_name AS exchange_display_name,
    s.symbol_base,
    s.symbol_quote,
    s.exchange_symbol,
    nbt.bid_price,
    nbt.bid_qty,
    nbt.ask_price,
    nbt.ask_qty,
    (nbt.ask_price - nbt.bid_price) AS spread,
    ((nbt.ask_price - nbt.bid_price) / ((nbt.ask_price + nbt.bid_price) / 2) * 100) AS spread_percentage,
    nbt.timestamp,
    nbt.created_at
FROM normalized_book_ticker_snapshots nbt
JOIN exchanges e ON nbt.exchange_id = e.id
JOIN symbols s ON nbt.symbol_id = s.id
WHERE e.is_active = true AND s.is_active = true;

-- Create a view for normalized trades with names
CREATE OR REPLACE VIEW v_normalized_trades_with_names AS
SELECT 
    nt.id,
    e.name AS exchange_name,
    e.display_name AS exchange_display_name,
    s.symbol_base,
    s.symbol_quote,
    s.exchange_symbol,
    nt.price,
    nt.quantity,
    nt.side,
    nt.trade_id,
    nt.quote_quantity,
    nt.is_buyer,
    nt.is_maker,
    (nt.price * nt.quantity) AS notional_value,
    nt.timestamp,
    nt.created_at
FROM normalized_trade_snapshots nt
JOIN exchanges e ON nt.exchange_id = e.id
JOIN symbols s ON nt.symbol_id = s.id
WHERE e.is_active = true AND s.is_active = true;

-- Performance validation query for book ticker snapshots
-- This should complete in <10ms for HFT compliance
EXPLAIN (ANALYZE, BUFFERS) 
SELECT exchange_id, symbol_id, bid_price, ask_price, timestamp
FROM normalized_book_ticker_snapshots 
WHERE exchange_id = 1 AND symbol_id = 1 
ORDER BY timestamp DESC 
LIMIT 100;

-- Performance validation query for trade snapshots
-- This should complete in <10ms for HFT compliance
EXPLAIN (ANALYZE, BUFFERS) 
SELECT exchange_id, symbol_id, price, quantity, side, timestamp
FROM normalized_trade_snapshots 
WHERE exchange_id = 1 AND symbol_id = 1 
ORDER BY timestamp DESC 
LIMIT 100;

COMMIT;

-- Display final status
SELECT 
    'normalized_book_ticker_snapshots' as table_name,
    COUNT(*) as row_count
FROM normalized_book_ticker_snapshots
UNION ALL
SELECT 
    'normalized_trade_snapshots' as table_name,
    COUNT(*) as row_count
FROM normalized_trade_snapshots;

-- Show indexes created
SELECT 
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes 
WHERE tablename IN ('normalized_book_ticker_snapshots', 'normalized_trade_snapshots')
ORDER BY tablename, indexname;

\echo ''
\echo '✅ Migration 004 completed successfully!'
\echo '📊 Normalized snapshot tables created with foreign key relationships'
\echo '🚀 HFT-optimized indexes and constraints applied'
\echo '🔗 Views created for easy querying with exchange and symbol names'
\echo ''