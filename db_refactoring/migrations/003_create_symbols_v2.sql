-- Migration 003 v2: Create symbols table with corrected schema
-- Purpose: Create symbols table with proper column names and symbol_type enum
-- Performance: Optimized for HFT operations with proper indexing and foreign key constraints
-- Dependencies: Requires 002_create_exchanges.sql

-- Enable timing for performance monitoring
\timing on

-- Transaction wrapper for atomic migration
BEGIN;

-- Drop existing symbols table if it exists
DROP TABLE IF EXISTS symbols CASCADE;

-- Create symbol type enum
CREATE TYPE symbol_type_enum AS ENUM ('SPOT', 'FUTURES');

-- Create symbols table with corrected schema
CREATE TABLE IF NOT EXISTS symbols (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    
    -- Foreign key relationship to exchanges
    exchange_id SMALLINT NOT NULL REFERENCES exchanges(id) ON DELETE CASCADE,
    
    -- Symbol identification (part of unique key)
    symbol_base VARCHAR(20) NOT NULL,               -- BTC, ETH, BNB, etc.
    symbol_quote VARCHAR(20) NOT NULL,              -- USDT, USD, BTC, etc.
    symbol_type symbol_type_enum NOT NULL DEFAULT 'SPOT', -- SPOT or FUTURES
    exchange_symbol VARCHAR(50) NOT NULL,           -- Exchange-specific format (BTCUSDT, BTC/USDT, etc.)
    is_active BOOLEAN NOT NULL DEFAULT true,
    
    -- Trading rules and precision
    price_precision SMALLINT NOT NULL DEFAULT 8,    -- Price decimal precision
    quantity_precision SMALLINT NOT NULL DEFAULT 8, -- Quantity decimal precision  
    min_order_size NUMERIC(20,8),                   -- Minimum order size in base asset
    max_order_size NUMERIC(20,8),                   -- Maximum order size in base asset
    tick_size NUMERIC(20,8),                        -- Minimum price increment
    step_size NUMERIC(20,8),                        -- Minimum quantity increment
    min_notional NUMERIC(20,8),                     -- Minimum notional value
    
    -- Metadata and monitoring
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    
    -- Unique constraints to prevent duplicates
    UNIQUE(exchange_id, symbol_base, symbol_quote, symbol_type),
    UNIQUE(exchange_id, exchange_symbol),
    
    -- Data validation constraints
    CONSTRAINT chk_symbols_assets_different CHECK (symbol_base != symbol_quote),
    CONSTRAINT chk_symbols_positive_precision CHECK (
        price_precision > 0 AND quantity_precision > 0 AND
        price_precision <= 18 AND quantity_precision <= 18
    ),
    CONSTRAINT chk_symbols_valid_order_sizes CHECK (
        min_order_size IS NULL OR max_order_size IS NULL OR min_order_size <= max_order_size
    ),
    CONSTRAINT chk_symbols_positive_sizes CHECK (
        (min_order_size IS NULL OR min_order_size > 0) AND
        (max_order_size IS NULL OR max_order_size > 0) AND
        (tick_size IS NULL OR tick_size > 0) AND
        (step_size IS NULL OR step_size > 0) AND
        (min_notional IS NULL OR min_notional > 0)
    )
);

-- Create performance indexes
CREATE INDEX IF NOT EXISTS idx_symbols_exchange_assets ON symbols(exchange_id, symbol_base, symbol_quote, symbol_type);
CREATE INDEX IF NOT EXISTS idx_symbols_exchange_symbol ON symbols(exchange_id, exchange_symbol);
CREATE INDEX IF NOT EXISTS idx_symbols_active ON symbols(exchange_id, is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_symbols_base_quote ON symbols(symbol_base, symbol_quote);
CREATE INDEX IF NOT EXISTS idx_symbols_type ON symbols(symbol_type);

-- Covering index for cache operations
CREATE INDEX IF NOT EXISTS idx_symbols_cache_load ON symbols(
    id, exchange_id, symbol_base, symbol_quote, symbol_type, 
    exchange_symbol, price_precision, quantity_precision, is_active
) WHERE is_active = true;

-- Create symbol lookup function with symbol_type support
CREATE OR REPLACE FUNCTION get_symbol_id(
    p_exchange_enum TEXT,
    p_symbol_base TEXT, 
    p_symbol_quote TEXT,
    p_symbol_type TEXT DEFAULT 'SPOT'
) RETURNS INTEGER AS $$
DECLARE
    symbol_id INTEGER;
BEGIN
    SELECT s.id INTO symbol_id
    FROM symbols s
    JOIN exchanges e ON s.exchange_id = e.id
    WHERE e.enum_value = p_exchange_enum
      AND UPPER(s.symbol_base) = UPPER(p_symbol_base)
      AND UPPER(s.symbol_quote) = UPPER(p_symbol_quote)
      AND s.symbol_type = p_symbol_type::symbol_type_enum
      AND s.is_active = true
      AND e.is_active = true;
    
    RETURN symbol_id;
END;
$$ LANGUAGE plpgsql STABLE;

-- Populate symbols from existing book_ticker_snapshots data
INSERT INTO symbols (
    exchange_id, 
    symbol_base, 
    symbol_quote, 
    symbol_type,
    exchange_symbol,
    price_precision,
    quantity_precision
)
SELECT DISTINCT 
    e.id as exchange_id,
    bts.symbol_base,
    bts.symbol_quote,
    CASE 
        WHEN e.market_type = 'FUTURES' THEN 'FUTURES'::symbol_type_enum
        ELSE 'SPOT'::symbol_type_enum
    END as symbol_type,
    CONCAT(bts.symbol_base, bts.symbol_quote) as exchange_symbol,
    8 as price_precision,
    8 as quantity_precision
FROM book_ticker_snapshots bts
JOIN exchanges e ON UPPER(bts.exchange) = UPPER(e.enum_value)
WHERE e.is_active = true
ON CONFLICT (exchange_id, symbol_base, symbol_quote, symbol_type) DO UPDATE SET
    exchange_symbol = EXCLUDED.exchange_symbol,
    updated_at = NOW();

-- Create update trigger for symbols
CREATE OR REPLACE FUNCTION update_symbols_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_symbols_updated_at ON symbols;
CREATE TRIGGER trigger_symbols_updated_at
    BEFORE UPDATE ON symbols
    FOR EACH ROW
    EXECUTE FUNCTION update_symbols_updated_at();

COMMIT;

-- Display final status
SELECT 
    'symbols' as table_name,
    COUNT(*) as row_count,
    COUNT(CASE WHEN symbol_type = 'SPOT' THEN 1 END) as spot_count,
    COUNT(CASE WHEN symbol_type = 'FUTURES' THEN 1 END) as futures_count
FROM symbols;

-- Show symbols per exchange
SELECT 
    e.name as exchange_name,
    s.symbol_type,
    COUNT(*) as symbol_count
FROM symbols s
JOIN exchanges e ON s.exchange_id = e.id
WHERE s.is_active = true
GROUP BY e.name, s.symbol_type
ORDER BY e.name, s.symbol_type;

-- Show indexes created
SELECT 
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes 
WHERE tablename = 'symbols'
ORDER BY indexname;

\echo ''
\echo '✅ Migration 003 v2 completed successfully!'
\echo '📊 Symbols table created with corrected schema and symbol_type enum'
\echo '🔧 Unique constraints include symbol_type to prevent SPOT/FUTURES duplicates'
\echo '🚀 HFT-optimized indexes and constraints applied'
\echo ''