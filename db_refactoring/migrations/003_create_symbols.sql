-- Migration 003: Create symbols reference table
-- Purpose: Create normalized symbols table with exchange relationships
-- Performance: Optimized for HFT symbol resolution (<1μs cache lookups)
-- Dependencies: 002_create_exchanges.sql must be completed first

-- Enable timing for performance monitoring
\timing on

-- Transaction wrapper for atomic migration
BEGIN;

-- Verify prerequisite: exchanges table exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'exchanges') THEN
        RAISE EXCEPTION 'exchanges table not found - run migration 002_create_exchanges.sql first';
    END IF;
END;
$$;

-- Create symbols reference table
CREATE TABLE IF NOT EXISTS symbols (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    
    -- Foreign key relationship to exchanges
    exchange_id SMALLINT NOT NULL REFERENCES exchanges(id) ON DELETE CASCADE,
    
    -- Symbol identification
    base_asset VARCHAR(20) NOT NULL,               -- BTC, ETH, BNB, etc.
    quote_asset VARCHAR(20) NOT NULL,              -- USDT, USD, BTC, etc.
    symbol_string VARCHAR(50) NOT NULL,            -- Exchange-specific format (BTCUSDT, BTC/USDT, etc.)
    is_active BOOLEAN NOT NULL DEFAULT true,
    
    -- Trading rules and precision
    precision_base SMALLINT NOT NULL DEFAULT 8,    -- Base asset decimal precision
    precision_quote SMALLINT NOT NULL DEFAULT 8,   -- Quote asset decimal precision  
    precision_price SMALLINT NOT NULL DEFAULT 8,   -- Price decimal precision
    min_order_size NUMERIC(20,8),                  -- Minimum order size in base asset
    max_order_size NUMERIC(20,8),                  -- Maximum order size in base asset
    tick_size NUMERIC(20,8),                       -- Minimum price increment
    step_size NUMERIC(20,8),                       -- Minimum quantity increment
    
    -- Metadata and monitoring
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    last_seen TIMESTAMPTZ DEFAULT NOW() NOT NULL,  -- Last time symbol was observed in market data
    
    -- Unique constraints to prevent duplicates
    UNIQUE(exchange_id, base_asset, quote_asset),
    UNIQUE(exchange_id, symbol_string),
    
    -- Data validation constraints
    CONSTRAINT chk_symbols_assets_different CHECK (base_asset != quote_asset),
    CONSTRAINT chk_symbols_positive_precision CHECK (
        precision_base > 0 AND precision_quote > 0 AND precision_price > 0 AND
        precision_base <= 18 AND precision_quote <= 18 AND precision_price <= 18
    ),
    CONSTRAINT chk_symbols_valid_order_sizes CHECK (
        min_order_size IS NULL OR max_order_size IS NULL OR min_order_size <= max_order_size
    ),
    CONSTRAINT chk_symbols_positive_sizes CHECK (
        (min_order_size IS NULL OR min_order_size > 0) AND
        (max_order_size IS NULL OR max_order_size > 0) AND
        (tick_size IS NULL OR tick_size > 0) AND
        (step_size IS NULL OR step_size > 0)
    )
);

-- Performance indexes for HFT operations
-- Primary lookup pattern: exchange + base + quote (most common for symbol resolution)
CREATE INDEX IF NOT EXISTS idx_symbols_exchange_assets ON symbols(exchange_id, base_asset, quote_asset);

-- Secondary lookup: exchange + symbol_string (for exchange-specific symbol formats)
CREATE INDEX IF NOT EXISTS idx_symbols_exchange_string ON symbols(exchange_id, symbol_string);

-- Filter active symbols efficiently
CREATE INDEX IF NOT EXISTS idx_symbols_active ON symbols(exchange_id, is_active) WHERE is_active = true;

-- Cross-exchange symbol analysis (find same asset pairs across exchanges)
CREATE INDEX IF NOT EXISTS idx_symbols_base_quote ON symbols(base_asset, quote_asset);

-- Monitoring and maintenance queries
CREATE INDEX IF NOT EXISTS idx_symbols_last_seen ON symbols(last_seen DESC);

-- Covering index for cache loading (includes all fields needed for symbol cache)
CREATE INDEX IF NOT EXISTS idx_symbols_cache_load ON symbols(
    id, exchange_id, base_asset, quote_asset, symbol_string, 
    precision_base, precision_quote, precision_price, is_active
) WHERE is_active = true;

-- Create function for automatic updated_at timestamp
CREATE OR REPLACE FUNCTION update_symbols_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for automatic timestamp updates
DROP TRIGGER IF EXISTS trigger_symbols_updated_at ON symbols;
CREATE TRIGGER trigger_symbols_updated_at
    BEFORE UPDATE ON symbols
    FOR EACH ROW
    EXECUTE FUNCTION update_symbols_updated_at();

-- Create function to extract unique symbols from current market data
-- This will be used to populate the symbols table with existing data
CREATE OR REPLACE FUNCTION extract_current_symbols()
RETURNS TABLE(
    exchange_name TEXT,
    exchange_id SMALLINT,
    base_asset TEXT,
    quote_asset TEXT,
    symbol_count BIGINT
) AS $$
BEGIN
    -- Extract unique symbol combinations from book_ticker_snapshots
    -- and map them to exchange IDs
    RETURN QUERY
    SELECT 
        bts.exchange,
        e.id as exchange_id,
        bts.symbol_base,
        bts.symbol_quote,
        COUNT(*) as symbol_count
    FROM book_ticker_snapshots bts
    JOIN exchanges e ON UPPER(e.name) = UPPER(bts.exchange) 
                     OR UPPER(e.enum_value) = UPPER(bts.exchange)
                     OR UPPER(e.display_name) LIKE '%' || UPPER(bts.exchange) || '%'
    GROUP BY bts.exchange, e.id, bts.symbol_base, bts.symbol_quote
    ORDER BY bts.exchange, bts.symbol_base, bts.symbol_quote;
END;
$$ LANGUAGE plpgsql;

-- Populate symbols table with existing market data
-- This extracts all unique symbol combinations from current book_ticker_snapshots
INSERT INTO symbols (
    exchange_id, 
    base_asset, 
    quote_asset, 
    symbol_string,
    precision_base,
    precision_quote, 
    precision_price,
    last_seen
)
SELECT DISTINCT
    mapping.exchange_id,
    mapping.base_asset,
    mapping.quote_asset,
    CONCAT(mapping.base_asset, mapping.quote_asset) as symbol_string,  -- Default format
    8 as precision_base,    -- Default precision, will be updated with real data later
    8 as precision_quote,   -- Default precision
    8 as precision_price,   -- Default precision
    NOW() as last_seen
FROM extract_current_symbols() mapping
ON CONFLICT (exchange_id, base_asset, quote_asset) DO UPDATE SET
    symbol_string = EXCLUDED.symbol_string,
    last_seen = EXCLUDED.last_seen,
    updated_at = NOW();

-- Add helpful table and column comments for documentation
COMMENT ON TABLE symbols IS 
    'Reference table for trading symbols with exchange relationships and trading rules. Optimized for sub-microsecond symbol resolution in HFT operations.';

COMMENT ON COLUMN symbols.id IS 
    'Primary key - auto-generated symbol identifier for foreign key relationships in market data tables';

COMMENT ON COLUMN symbols.exchange_id IS 
    'Foreign key to exchanges table - establishes which exchange this symbol belongs to';

COMMENT ON COLUMN symbols.base_asset IS 
    'Base trading asset (e.g., BTC in BTC/USDT pair)';

COMMENT ON COLUMN symbols.quote_asset IS 
    'Quote trading asset (e.g., USDT in BTC/USDT pair)';

COMMENT ON COLUMN symbols.symbol_string IS 
    'Exchange-specific symbol format (e.g., BTCUSDT for most exchanges, BTC/USDT for others)';

COMMENT ON COLUMN symbols.precision_base IS 
    'Decimal precision for base asset quantities';

COMMENT ON COLUMN symbols.precision_quote IS 
    'Decimal precision for quote asset quantities';

COMMENT ON COLUMN symbols.precision_price IS 
    'Decimal precision for price values';

COMMENT ON COLUMN symbols.min_order_size IS 
    'Minimum order size in base asset units';

COMMENT ON COLUMN symbols.max_order_size IS 
    'Maximum order size in base asset units';

COMMENT ON COLUMN symbols.tick_size IS 
    'Minimum price increment for orders';

COMMENT ON COLUMN symbols.step_size IS 
    'Minimum quantity increment for orders';

COMMENT ON COLUMN symbols.last_seen IS 
    'Last timestamp when this symbol was observed in market data - used for symbol lifecycle management';

-- Create helper view for easy symbol lookups
CREATE OR REPLACE VIEW symbol_details AS
SELECT 
    s.id,
    s.exchange_id,
    e.name as exchange_name,
    e.enum_value as exchange_enum,
    e.display_name as exchange_display_name,
    e.market_type,
    s.base_asset,
    s.quote_asset,
    s.symbol_string,
    CONCAT(s.base_asset, '/', s.quote_asset) as standard_symbol,
    s.is_active,
    s.precision_base,
    s.precision_quote,
    s.precision_price,
    s.min_order_size,
    s.max_order_size,
    s.tick_size,
    s.step_size,
    s.created_at,
    s.updated_at,
    s.last_seen
FROM symbols s
JOIN exchanges e ON s.exchange_id = e.id;

COMMENT ON VIEW symbol_details IS 
    'Convenient view combining symbol and exchange information for queries and debugging';

-- Create function for efficient symbol ID lookup (will be used by cache)
CREATE OR REPLACE FUNCTION get_symbol_id(
    p_exchange_enum TEXT,
    p_base_asset TEXT, 
    p_quote_asset TEXT
) RETURNS INTEGER AS $$
DECLARE
    symbol_id INTEGER;
BEGIN
    SELECT s.id INTO symbol_id
    FROM symbols s
    JOIN exchanges e ON s.exchange_id = e.id
    WHERE e.enum_value = p_exchange_enum
      AND UPPER(s.base_asset) = UPPER(p_base_asset)
      AND UPPER(s.quote_asset) = UPPER(p_quote_asset)
      AND s.is_active = true
      AND e.is_active = true;
    
    RETURN symbol_id;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION get_symbol_id IS 
    'Fast symbol ID lookup by exchange enum and asset pair - optimized for HFT cache integration';

-- Verify data integrity and migration success
DO $$
DECLARE
    symbol_count INTEGER;
    active_symbol_count INTEGER;
    exchange_count INTEGER;
    symbols_per_exchange RECORD;
BEGIN
    -- Check that symbols were populated
    SELECT COUNT(*) INTO symbol_count FROM symbols;
    SELECT COUNT(*) INTO active_symbol_count FROM symbols WHERE is_active = true;
    SELECT COUNT(*) INTO exchange_count FROM exchanges WHERE is_active = true;
    
    IF symbol_count = 0 THEN
        RAISE EXCEPTION 'No symbols were populated - check book_ticker_snapshots data exists';
    END IF;
    
    IF active_symbol_count = 0 THEN
        RAISE EXCEPTION 'No active symbols found - check is_active defaults';
    END IF;
    
    RAISE NOTICE 'Migration successful: % total symbols, % active symbols across % exchanges', 
                 symbol_count, active_symbol_count, exchange_count;
    
    -- Show symbols per exchange for verification
    FOR symbols_per_exchange IN
        SELECT 
            e.name as exchange_name,
            COUNT(*) as symbol_count
        FROM symbols s
        JOIN exchanges e ON s.exchange_id = e.id
        WHERE s.is_active = true
        GROUP BY e.name
        ORDER BY e.name
    LOOP
        RAISE NOTICE 'Exchange %: % active symbols', 
                     symbols_per_exchange.exchange_name, 
                     symbols_per_exchange.symbol_count;
    END LOOP;
END;
$$;

-- Performance validation queries
-- These should complete in <1ms for HFT compliance

-- Test 1: Symbol ID lookup by exchange enum and assets (most common operation)
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT get_symbol_id('MEXC_SPOT', 'BTC', 'USDT');

-- Test 2: Get all symbols for an exchange (cache loading)
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT id, base_asset, quote_asset, symbol_string, precision_base, precision_quote
FROM symbols s
JOIN exchanges e ON s.exchange_id = e.id
WHERE e.enum_value = 'MEXC_SPOT' AND s.is_active = true;

-- Test 3: Cross-exchange symbol discovery
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT 
    base_asset,
    quote_asset,
    COUNT(*) as exchange_count,
    ARRAY_AGG(e.name ORDER BY e.name) as exchanges
FROM symbols s
JOIN exchanges e ON s.exchange_id = e.id
WHERE s.is_active = true AND e.is_active = true
GROUP BY base_asset, quote_asset
HAVING COUNT(*) > 1
ORDER BY exchange_count DESC, base_asset, quote_asset
LIMIT 10;

COMMIT;

-- Display final migration status
SELECT 
    'SYMBOLS MIGRATION SUMMARY' as status,
    COUNT(*) as total_symbols,
    COUNT(*) FILTER (WHERE is_active = true) as active_symbols,
    COUNT(DISTINCT exchange_id) as exchanges_with_symbols,
    COUNT(DISTINCT base_asset) as unique_base_assets,
    COUNT(DISTINCT quote_asset) as unique_quote_assets
FROM symbols;

-- Show sample symbols per exchange for verification
SELECT 
    e.name as exchange,
    e.market_type,
    COUNT(*) as symbol_count,
    ARRAY_AGG(CONCAT(s.base_asset, '/', s.quote_asset) ORDER BY s.base_asset, s.quote_asset) 
        FILTER (WHERE ROW_NUMBER() OVER (PARTITION BY e.id ORDER BY s.base_asset, s.quote_asset) <= 5) as sample_symbols
FROM symbols s
JOIN exchanges e ON s.exchange_id = e.id
WHERE s.is_active = true
GROUP BY e.id, e.name, e.market_type
ORDER BY e.name;

-- Show cross-exchange symbols (symbols available on multiple exchanges)
SELECT 
    CONCAT(base_asset, '/', quote_asset) as symbol_pair,
    COUNT(*) as exchange_count,
    ARRAY_AGG(e.name ORDER BY e.name) as available_exchanges
FROM symbols s
JOIN exchanges e ON s.exchange_id = e.id
WHERE s.is_active = true AND e.is_active = true
GROUP BY base_asset, quote_asset
HAVING COUNT(*) > 1
ORDER BY exchange_count DESC, base_asset, quote_asset
LIMIT 10;

\echo ''
\echo '✅ Migration 003 completed successfully!'
\echo '📊 Symbols table created with exchange relationships and performance indexes'
\echo '🔗 Foreign key constraints established with exchanges table'
\echo '🚀 Ready for Phase 1.3: Cache infrastructure implementation'
\echo ''