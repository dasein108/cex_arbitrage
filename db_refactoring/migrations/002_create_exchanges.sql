-- Migration 002: Create exchanges reference table
-- Purpose: Create normalized exchanges table to replace string-based exchange storage
-- Performance: Optimized for HFT operations with proper indexing
-- Dependencies: None (can run independently)

-- Enable timing for performance monitoring
\timing on

-- Transaction wrapper for atomic migration
BEGIN;

-- Create exchanges reference table
CREATE TABLE IF NOT EXISTS exchanges (
    id SMALLINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    
    -- Core identification
    name VARCHAR(50) UNIQUE NOT NULL,              -- MEXC_SPOT, GATEIO_SPOT, GATEIO_FUTURES
    enum_value VARCHAR(50) UNIQUE NOT NULL,        -- Maps to ExchangeEnum values in application
    display_name VARCHAR(100) NOT NULL,            -- User-friendly display name
    market_type VARCHAR(20) NOT NULL,              -- SPOT, FUTURES, OPTIONS
    is_active BOOLEAN NOT NULL DEFAULT true,
    
    -- Configuration
    base_url VARCHAR(255),                         -- REST API base URL
    websocket_url VARCHAR(255),                    -- WebSocket connection URL
    rate_limit_requests_per_second INTEGER,        -- API rate limit configuration
    precision_default SMALLINT DEFAULT 8,          -- Default precision for this exchange
    
    -- Audit trail
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    
    -- Constraints
    CONSTRAINT chk_exchanges_market_type CHECK (market_type IN ('SPOT', 'FUTURES', 'OPTIONS')),
    CONSTRAINT chk_exchanges_precision CHECK (precision_default > 0 AND precision_default <= 18),
    CONSTRAINT chk_exchanges_rate_limit CHECK (rate_limit_requests_per_second IS NULL OR rate_limit_requests_per_second > 0)
);

-- Performance indexes for HFT operations
-- Primary lookup by enum value (most common operation)
CREATE INDEX IF NOT EXISTS idx_exchanges_enum_value ON exchanges(enum_value);

-- Filter active exchanges efficiently
CREATE INDEX IF NOT EXISTS idx_exchanges_active ON exchanges(is_active) WHERE is_active = true;

-- Group by market type for specialized queries
CREATE INDEX IF NOT EXISTS idx_exchanges_market_type ON exchanges(market_type);

-- Covering index for cache loading (includes all fields needed for cache)
CREATE INDEX IF NOT EXISTS idx_exchanges_cache_load ON exchanges(id, name, enum_value, display_name, market_type, is_active)
WHERE is_active = true;

-- Updated timestamp index for monitoring
CREATE INDEX IF NOT EXISTS idx_exchanges_updated_at ON exchanges(updated_at DESC);

-- Populate with current exchanges from ExchangeEnum
-- Data must match the enum values in src/exchanges/structs/enums.py
INSERT INTO exchanges (name, enum_value, display_name, market_type, base_url, websocket_url, rate_limit_requests_per_second, precision_default) VALUES
    -- MEXC Spot Trading
    ('MEXC_SPOT', 'MEXC_SPOT', 'MEXC Spot Trading', 'SPOT', 
     'https://api.mexc.com', 'wss://wbs.mexc.com/ws', 100, 8),
     
    -- Gate.io Spot Trading
    ('GATEIO_SPOT', 'GATEIO_SPOT', 'Gate.io Spot Trading', 'SPOT', 
     'https://api.gateio.ws', 'wss://api.gateio.ws/ws/v4/', 100, 8),
     
    -- Gate.io Futures Trading
    ('GATEIO_FUTURES', 'GATEIO_FUTURES', 'Gate.io Futures Trading', 'FUTURES', 
     'https://api.gateio.ws', 'wss://fx-ws.gateio.ws/v4/ws/', 100, 8)
     
ON CONFLICT (enum_value) DO UPDATE SET
    name = EXCLUDED.name,
    display_name = EXCLUDED.display_name,
    market_type = EXCLUDED.market_type,
    base_url = EXCLUDED.base_url,
    websocket_url = EXCLUDED.websocket_url,
    rate_limit_requests_per_second = EXCLUDED.rate_limit_requests_per_second,
    precision_default = EXCLUDED.precision_default,
    updated_at = NOW();

-- Create function for automatic updated_at timestamp
CREATE OR REPLACE FUNCTION update_exchanges_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for automatic timestamp updates
DROP TRIGGER IF EXISTS trigger_exchanges_updated_at ON exchanges;
CREATE TRIGGER trigger_exchanges_updated_at
    BEFORE UPDATE ON exchanges
    FOR EACH ROW
    EXECUTE FUNCTION update_exchanges_updated_at();

-- Add helpful table and column comments for documentation
COMMENT ON TABLE exchanges IS 
    'Reference table for supported cryptocurrency exchanges with metadata and configuration. Optimized for HFT operations with sub-millisecond lookup performance.';

COMMENT ON COLUMN exchanges.id IS 
    'Primary key - auto-generated exchange identifier for foreign key relationships';

COMMENT ON COLUMN exchanges.name IS 
    'Exchange name matching application naming convention (e.g., MEXC_SPOT, GATEIO_FUTURES)';

COMMENT ON COLUMN exchanges.enum_value IS 
    'Maps directly to ExchangeEnum values in src/exchanges/structs/enums.py for type-safe integration';

COMMENT ON COLUMN exchanges.display_name IS 
    'Human-readable exchange name for UI display and logging';

COMMENT ON COLUMN exchanges.market_type IS 
    'Trading market type: SPOT for spot trading, FUTURES for derivatives, OPTIONS for options trading';

COMMENT ON COLUMN exchanges.is_active IS 
    'Soft delete flag - inactive exchanges are hidden from active operations but preserved for historical data';

COMMENT ON COLUMN exchanges.base_url IS 
    'REST API base URL for this exchange';

COMMENT ON COLUMN exchanges.websocket_url IS 
    'WebSocket connection URL for real-time data feeds';

COMMENT ON COLUMN exchanges.rate_limit_requests_per_second IS 
    'API rate limit configuration for request throttling';

COMMENT ON COLUMN exchanges.precision_default IS 
    'Default decimal precision for price and quantity values on this exchange';

-- Verify data integrity and constraints
DO $$
DECLARE
    exchange_count INTEGER;
    active_count INTEGER;
BEGIN
    -- Check that exchanges were inserted
    SELECT COUNT(*) INTO exchange_count FROM exchanges;
    SELECT COUNT(*) INTO active_count FROM exchanges WHERE is_active = true;
    
    IF exchange_count = 0 THEN
        RAISE EXCEPTION 'No exchanges were inserted - migration failed';
    END IF;
    
    IF active_count = 0 THEN
        RAISE EXCEPTION 'No active exchanges found - check is_active defaults';
    END IF;
    
    RAISE NOTICE 'Migration successful: % total exchanges, % active', exchange_count, active_count;
END;
$$;

-- Performance validation query
-- This should complete in <1ms for HFT compliance
EXPLAIN (ANALYZE, BUFFERS) 
SELECT id, name, enum_value, display_name, market_type
FROM exchanges 
WHERE enum_value = 'MEXC_SPOT' AND is_active = true;

COMMIT;

-- Display final status
SELECT 
    COUNT(*) as total_exchanges,
    COUNT(*) FILTER (WHERE is_active = true) as active_exchanges,
    COUNT(*) FILTER (WHERE market_type = 'SPOT') as spot_exchanges,
    COUNT(*) FILTER (WHERE market_type = 'FUTURES') as futures_exchanges
FROM exchanges;

-- Show all created exchanges for verification
SELECT 
    id,
    name,
    enum_value,
    display_name,
    market_type,
    is_active,
    rate_limit_requests_per_second,
    created_at
FROM exchanges
ORDER BY market_type, name;

\echo ''
\echo '✅ Migration 002 completed successfully!'
\echo '📊 Exchanges table created with proper indexes and constraints'
\echo '🚀 Ready for Phase 1.2: Symbol table creation'
\echo ''