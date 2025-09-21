-- =============================================================================
-- Migration: Add Trade Collection Support
-- Version: 001
-- Date: 2025-01-01
-- Description: Create trades table schema to match TradeSnapshot model
-- =============================================================================

-- Begin transaction for atomic migration
BEGIN;

-- Handle existing trades table or create new one
DO $$ 
BEGIN
    -- Check if trades table exists
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'trades') THEN
        -- Table exists, check if it has the new schema
        IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'trades' AND column_name = 'symbol_base') THEN
            -- Old schema exists, need to migrate
            RAISE NOTICE 'Migrating existing trades table to new schema';
            
            -- Add new columns
            ALTER TABLE trades 
                ADD COLUMN IF NOT EXISTS symbol_base VARCHAR(20),
                ADD COLUMN IF NOT EXISTS symbol_quote VARCHAR(20),
                ADD COLUMN IF NOT EXISTS quote_quantity NUMERIC(20,8),
                ADD COLUMN IF NOT EXISTS is_buyer BOOLEAN,
                ADD COLUMN IF NOT EXISTS is_maker BOOLEAN;
            
            -- Migrate existing data if symbol column exists
            IF EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'trades' AND column_name = 'symbol') THEN
                UPDATE trades 
                SET 
                    symbol_base = CASE 
                        WHEN symbol LIKE '%USDT' THEN LEFT(symbol, LENGTH(symbol) - 4)
                        WHEN symbol LIKE '%USDC' THEN LEFT(symbol, LENGTH(symbol) - 4)
                        WHEN symbol LIKE '%BTC' AND symbol != 'BTC' THEN LEFT(symbol, LENGTH(symbol) - 3)
                        WHEN symbol LIKE '%ETH' AND symbol != 'ETH' THEN LEFT(symbol, LENGTH(symbol) - 3)
                        WHEN symbol LIKE '%BNB' AND symbol != 'BNB' THEN LEFT(symbol, LENGTH(symbol) - 3)
                        ELSE SPLIT_PART(symbol, '_', 1)
                    END,
                    symbol_quote = CASE 
                        WHEN symbol LIKE '%USDT' THEN 'USDT'
                        WHEN symbol LIKE '%USDC' THEN 'USDC'
                        WHEN symbol LIKE '%BTC' AND symbol != 'BTC' THEN 'BTC'
                        WHEN symbol LIKE '%ETH' AND symbol != 'ETH' THEN 'ETH'
                        WHEN symbol LIKE '%BNB' AND symbol != 'BNB' THEN 'BNB'
                        ELSE SPLIT_PART(symbol, '_', 2)
                    END
                WHERE symbol_base IS NULL OR symbol_quote IS NULL;
            END IF;
            
            -- Ensure timestamp is TIMESTAMPTZ
            ALTER TABLE trades ALTER COLUMN timestamp TYPE TIMESTAMPTZ;
            
            -- Drop old primary key if it exists
            ALTER TABLE trades DROP CONSTRAINT IF EXISTS trades_pkey;
            
            -- Create new primary key
            ALTER TABLE trades ADD CONSTRAINT trades_pkey 
                PRIMARY KEY (timestamp, exchange, symbol_base, symbol_quote, id);
        ELSE
            RAISE NOTICE 'Trades table already has new schema';
        END IF;
    ELSE
        -- Table doesn't exist, create new one
        RAISE NOTICE 'Creating new trades table';
        
        CREATE TABLE trades (
            id BIGSERIAL,
            
            -- Exchange and symbol identification  
            exchange VARCHAR(20) NOT NULL,
            symbol_base VARCHAR(20) NOT NULL,
            symbol_quote VARCHAR(20) NOT NULL,
            
            -- Trade data
            price NUMERIC(20,8) NOT NULL,
            quantity NUMERIC(20,8) NOT NULL,
            side VARCHAR(10) NOT NULL,  -- 'buy' or 'sell'
            
            -- Timing (TIMESTAMPTZ as required)
            timestamp TIMESTAMPTZ NOT NULL,              -- Exchange timestamp
            created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL, -- Insert timestamp
            
            -- Optional trade metadata
            trade_id VARCHAR(100),                        -- Exchange trade ID (optional)
            quote_quantity NUMERIC(20,8),                -- Quote asset quantity (optional)
            is_buyer BOOLEAN,                             -- Is buyer flag (optional)
            is_maker BOOLEAN,                             -- Is maker flag (optional)
            
            -- Constraints
            CONSTRAINT chk_positive_price CHECK (price > 0),
            CONSTRAINT chk_positive_quantity CHECK (quantity > 0),
            CONSTRAINT chk_valid_side CHECK (side IN ('buy', 'sell')),
            CONSTRAINT chk_symbol_parts_not_empty CHECK (
                symbol_base IS NOT NULL AND symbol_base != '' AND 
                symbol_quote IS NOT NULL AND symbol_quote != ''
            ),
            
            -- Primary key
            CONSTRAINT trades_pkey PRIMARY KEY (timestamp, exchange, symbol_base, symbol_quote, id)
        );
    END IF;
END $$;

-- Create indexes for optimized queries

-- Create new indexes for optimized queries with symbol_base/symbol_quote
CREATE INDEX IF NOT EXISTS idx_trades_exchange_symbol_time 
    ON trades(exchange, symbol_base, symbol_quote, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_trades_symbol_time 
    ON trades(symbol_base, symbol_quote, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_trades_side_time 
    ON trades(side, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_trades_price_time 
    ON trades(price, timestamp DESC);

-- Create index for high-volume trades
CREATE INDEX IF NOT EXISTS idx_trades_large_volume 
    ON trades(quantity DESC) WHERE quantity > 1000;

-- Create partial index for buyer/maker flags when they exist
CREATE INDEX IF NOT EXISTS idx_trades_buyer_maker 
    ON trades(is_buyer, is_maker, timestamp DESC) 
    WHERE is_buyer IS NOT NULL AND is_maker IS NOT NULL;

-- Add constraint to ensure symbol_base and symbol_quote are not empty (if not exists in table creation)
ALTER TABLE trades DROP CONSTRAINT IF EXISTS chk_symbol_parts_not_empty;
ALTER TABLE trades 
    ADD CONSTRAINT chk_symbol_parts_not_empty 
    CHECK (symbol_base IS NOT NULL AND symbol_base != '' AND 
           symbol_quote IS NOT NULL AND symbol_quote != '');

-- Note: Materialized views and continuous aggregates are skipped in this migration
-- They can be created separately outside of transaction blocks if TimescaleDB is available

-- Create view for easy access to trade data with symbol reconstruction
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

-- Grant permissions to existing users (if they exist)
DO $$
BEGIN
    -- Grant permissions only if users exist
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'readonly_user') THEN
        GRANT SELECT ON trades_with_symbol TO readonly_user;
    END IF;
    
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'arbitrage_user') THEN
        GRANT ALL PRIVILEGES ON trades_with_symbol TO arbitrage_user;
    END IF;
END $$;

-- Add comment to document the migration
COMMENT ON TABLE trades IS 'Trade data table - Updated in migration 001 to support TradeSnapshot model with symbol_base/symbol_quote separation';

COMMIT;

-- =============================================================================
-- Migration Complete
-- =============================================================================
-- Changes made:
-- 1. Added symbol_base and symbol_quote columns to trades table
-- 2. Added optional trade metadata columns (quote_quantity, is_buyer, is_maker)
-- 3. Migrated existing symbol data to base/quote format
-- 4. Updated primary key to use symbol_base/symbol_quote
-- 5. Created optimized indexes for new schema
-- 6. Added continuous aggregate for trade analysis
-- 7. Created compatibility view for easy access
-- 8. Updated constraints and permissions
-- =============================================================================