-- =============================================================================
-- Safe Database Schema Updates for CEX Arbitrage
-- =============================================================================
-- This script contains safe, non-breaking schema updates that can be applied
-- to existing databases without data loss or service interruption

-- Add new columns if they don't exist (safe operations)
DO $$ 
BEGIN
    -- Add spread column to book_ticker_snapshots if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='book_ticker_snapshots' AND column_name='spread') THEN
        ALTER TABLE book_ticker_snapshots ADD COLUMN spread NUMERIC(20,8);
        CREATE INDEX IF NOT EXISTS book_ticker_spread_idx ON book_ticker_snapshots (spread, timestamp DESC);
        RAISE NOTICE 'Added spread column to book_ticker_snapshots';
    END IF;
    
    -- Add volume_24h column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='book_ticker_snapshots' AND column_name='volume_24h') THEN
        ALTER TABLE book_ticker_snapshots ADD COLUMN volume_24h NUMERIC(20,8);
        CREATE INDEX IF NOT EXISTS book_ticker_volume_idx ON book_ticker_snapshots (volume_24h, timestamp DESC);
        RAISE NOTICE 'Added volume_24h column to book_ticker_snapshots';
    END IF;
    
    -- Add price_change_24h column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='book_ticker_snapshots' AND column_name='price_change_24h') THEN
        ALTER TABLE book_ticker_snapshots ADD COLUMN price_change_24h NUMERIC(8,4);
        RAISE NOTICE 'Added price_change_24h column to book_ticker_snapshots';
    END IF;
    
    -- Add count column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='book_ticker_snapshots' AND column_name='count') THEN
        ALTER TABLE book_ticker_snapshots ADD COLUMN count BIGINT;
        RAISE NOTICE 'Added count column to book_ticker_snapshots';
    END IF;
    
    -- Add connection_id to collector_status if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='collector_status' AND column_name='connection_id') THEN
        ALTER TABLE collector_status ADD COLUMN connection_id VARCHAR(100);
        CREATE INDEX IF NOT EXISTS idx_collector_connection_id ON collector_status (connection_id);
        RAISE NOTICE 'Added connection_id column to collector_status';
    END IF;
    
END $$;

-- Update or add new indexes for better performance
CREATE INDEX IF NOT EXISTS idx_book_ticker_recent ON book_ticker_snapshots (timestamp DESC) 
    WHERE timestamp > NOW() - INTERVAL '1 day';

CREATE INDEX IF NOT EXISTS idx_book_ticker_spread_opportunities ON book_ticker_snapshots (spread, timestamp DESC) 
    WHERE spread IS NOT NULL;

-- Update retention policies if needed
DO $$
BEGIN
    -- Remove old retention policy if exists and add updated one
    PERFORM remove_retention_policy('book_ticker_snapshots', if_exists => TRUE);
    PERFORM add_retention_policy('book_ticker_snapshots', INTERVAL '30 days', if_not_exists => TRUE);
    
    PERFORM remove_retention_policy('collector_status', if_exists => TRUE);
    PERFORM add_retention_policy('collector_status', INTERVAL '7 days', if_not_exists => TRUE);
    
    RAISE NOTICE 'Updated retention policies';
END $$;

-- Add new continuous aggregate for 5-minute intervals if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.continuous_aggregates 
        WHERE materialization_hypertable_name = 'book_ticker_5min'
    ) THEN
        CREATE MATERIALIZED VIEW book_ticker_5min
        WITH (timescaledb.continuous) AS
        SELECT 
            time_bucket('5 minutes', timestamp) AS bucket,
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
            COUNT(*) as update_count,
            AVG(volume_24h) as avg_volume_24h
        FROM book_ticker_snapshots
        GROUP BY bucket, exchange, symbol_base, symbol_quote;
        
        -- Add refresh policy
        PERFORM add_continuous_aggregate_policy('book_ticker_5min',
            start_offset => INTERVAL '1 hour',
            end_offset => INTERVAL '5 minutes',
            schedule_interval => INTERVAL '5 minutes',
            if_not_exists => TRUE);
            
        RAISE NOTICE 'Created book_ticker_5min continuous aggregate';
    END IF;
END $$;

-- Ensure all permissions are correctly set
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO arbitrage_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO arbitrage_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;

-- Update table ownership if needed
DO $$
DECLARE
    table_name text;
BEGIN
    FOR table_name IN 
        SELECT tablename FROM pg_tables WHERE schemaname = 'public'
    LOOP
        EXECUTE format('ALTER TABLE %I OWNER TO arbitrage_user', table_name);
    END LOOP;
    RAISE NOTICE 'Updated table ownership';
END $$;

\echo 'Database schema updates completed successfully!'