-- =============================================================================
-- Migration: Fix Symbol Column Issue
-- Version: 002
-- Date: 2025-09-21
-- Description: Remove legacy symbol column that has NOT NULL constraint
-- =============================================================================

-- Begin transaction for atomic migration
BEGIN;

-- Handle legacy symbol column removal
DO $$ 
BEGIN
    -- Check if legacy symbol column exists and remove it
    IF EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'trades' AND column_name = 'symbol') THEN
        RAISE NOTICE 'Removing legacy symbol column from trades table';
        
        -- Drop the view first as it depends on the table
        DROP VIEW IF EXISTS trades_with_symbol CASCADE;
        
        -- First, drop any constraints that depend on the symbol column
        ALTER TABLE trades DROP CONSTRAINT IF EXISTS trades_pkey CASCADE;
        
        -- Drop the symbol column 
        ALTER TABLE trades DROP COLUMN symbol;
        
        -- Recreate the primary key with correct columns
        ALTER TABLE trades ADD CONSTRAINT trades_pkey 
            PRIMARY KEY (timestamp, exchange, symbol_base, symbol_quote, id);
        
        RAISE NOTICE 'Legacy symbol column removed successfully';
    ELSE
        RAISE NOTICE 'No legacy symbol column found - table is already migrated';
    END IF;
    
    -- Ensure symbol_base and symbol_quote are NOT NULL
    ALTER TABLE trades ALTER COLUMN symbol_base SET NOT NULL;
    ALTER TABLE trades ALTER COLUMN symbol_quote SET NOT NULL;
    
    -- Make sure timestamp is TIMESTAMPTZ NOT NULL (only if not already)
    IF (SELECT data_type FROM information_schema.columns WHERE table_name = 'trades' AND column_name = 'timestamp') != 'timestamp with time zone' THEN
        ALTER TABLE trades ALTER COLUMN timestamp TYPE TIMESTAMPTZ;
    END IF;
    ALTER TABLE trades ALTER COLUMN timestamp SET NOT NULL;
    
END $$;

-- Recreate the view with proper structure
CREATE OR REPLACE VIEW trades_with_symbol AS
SELECT 
    id,
    timestamp,
    exchange,
    symbol_base || '_' || symbol_quote as symbol,  -- Reconstructed symbol with underscore
    symbol_base,
    symbol_quote,
    price,
    quantity,
    side,
    trade_id,
    quote_quantity,
    is_buyer,
    is_maker,
    created_at
FROM trades;

-- Recreate indexes if they were dropped
CREATE INDEX IF NOT EXISTS idx_trades_exchange_symbol_time 
    ON trades(exchange, symbol_base, symbol_quote, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_trades_symbol_time 
    ON trades(symbol_base, symbol_quote, timestamp DESC);

-- Add comment to document the fix
COMMENT ON TABLE trades IS 'Trade data table - Fixed in migration 002 to remove legacy symbol column and ensure proper schema';

COMMIT;

-- =============================================================================
-- Migration Complete
-- =============================================================================
-- Changes made:
-- 1. Removed legacy symbol column with NOT NULL constraint
-- 2. Ensured symbol_base and symbol_quote are NOT NULL
-- 3. Recreated primary key with correct columns
-- 4. Recreated essential indexes
-- =============================================================================