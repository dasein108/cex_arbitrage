-- =============================================================================
-- Balance Snapshots Migration
-- =============================================================================
-- Adds balance snapshot functionality to existing normalized schema
-- Follows PROJECT_GUIDES.md float-only policy for HFT performance

-- Balance snapshots table - NORMALIZED SCHEMA (follows existing pattern)
CREATE TABLE IF NOT EXISTS balance_snapshots (
    id BIGSERIAL,
    timestamp TIMESTAMPTZ NOT NULL,
    exchange_id INTEGER NOT NULL REFERENCES exchanges(id),  -- Foreign key to exchanges table
    
    -- Asset identification
    asset_name VARCHAR(20) NOT NULL,  -- BTC, USDT, ETH, etc.
    
    -- Balance data (HFT optimized with float-only policy)
    available_balance REAL NOT NULL DEFAULT 0,  -- Using REAL (float) per PROJECT_GUIDES.md
    locked_balance REAL NOT NULL DEFAULT 0,     -- Using REAL (float) per PROJECT_GUIDES.md
    total_balance REAL GENERATED ALWAYS AS (available_balance + locked_balance) STORED,
    
    -- Exchange-specific fields (optional) - all using REAL for consistency
    frozen_balance REAL DEFAULT 0,     -- Some exchanges track frozen balances
    borrowing_balance REAL DEFAULT 0,  -- Margin/futures borrowing
    interest_balance REAL DEFAULT 0,   -- Interest accumulation
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- HFT Performance Constraints
    CONSTRAINT chk_positive_balances CHECK (
        available_balance >= 0 AND 
        locked_balance >= 0 AND 
        frozen_balance >= 0 AND 
        borrowing_balance >= 0
    ),
    CONSTRAINT chk_valid_asset_name CHECK (asset_name ~ '^[A-Z0-9]+$'),
    CONSTRAINT chk_valid_timestamp CHECK (timestamp >= '2020-01-01'::timestamptz),
    
    -- Optimized primary key for time-series partitioning
    PRIMARY KEY (timestamp, exchange_id, asset_name)
);

-- Convert to TimescaleDB hypertable (optimized for balance collection frequency)
SELECT create_hypertable('balance_snapshots', 'timestamp', 
    chunk_time_interval => INTERVAL '6 hours',  -- Balance data changes less frequently than market data
    if_not_exists => TRUE);

-- =============================================================================
-- HFT-OPTIMIZED INDEXES FOR BALANCE SNAPSHOTS
-- =============================================================================

-- Core indexes for balance_snapshots (sub-10ms queries)
CREATE INDEX IF NOT EXISTS idx_balance_snapshots_exchange_time 
    ON balance_snapshots(exchange_id, timestamp DESC);
    
CREATE INDEX IF NOT EXISTS idx_balance_snapshots_asset_time 
    ON balance_snapshots(asset_name, timestamp DESC);
    
CREATE INDEX IF NOT EXISTS idx_balance_snapshots_exchange_asset_time 
    ON balance_snapshots(exchange_id, asset_name, timestamp DESC);

-- Index for recent balance queries (most common pattern) - Removed WHERE clause to avoid immutable function error
CREATE INDEX IF NOT EXISTS idx_balance_snapshots_recent 
    ON balance_snapshots(timestamp DESC);

-- Index for asset-specific queries across exchanges - Removed WHERE clause to avoid immutable function error
CREATE INDEX IF NOT EXISTS idx_balance_snapshots_asset_recent 
    ON balance_snapshots(asset_name, exchange_id, timestamp DESC);

-- Index for non-zero balances (analytics optimization)
CREATE INDEX IF NOT EXISTS idx_balance_snapshots_active_balances 
    ON balance_snapshots(exchange_id, asset_name, timestamp DESC) 
    WHERE total_balance > 0;

-- Index for specific exchange lookups (performance optimization) - Removed WHERE clause to avoid immutable function error
CREATE INDEX IF NOT EXISTS idx_balance_snapshots_exchange_recent
    ON balance_snapshots(exchange_id, timestamp DESC);

-- =============================================================================
-- DATA RETENTION POLICY
-- =============================================================================

-- Balance snapshots: Keep 14 days for detailed analysis (HFT server optimized)
SELECT add_retention_policy('balance_snapshots', INTERVAL '14 days', if_not_exists => TRUE);

-- =============================================================================
-- TABLE OWNERSHIP AND PERMISSIONS
-- =============================================================================

-- Table ownership
ALTER TABLE balance_snapshots OWNER TO arbitrage_user;

-- Grant permissions
GRANT ALL PRIVILEGES ON balance_snapshots TO arbitrage_user;
GRANT SELECT ON balance_snapshots TO readonly_user;

-- Table comment
COMMENT ON TABLE balance_snapshots IS 'Account balance snapshots across all exchanges with normalized schema relationships and float-only data types for HFT performance';

-- Column comments for documentation
COMMENT ON COLUMN balance_snapshots.available_balance IS 'Available balance for trading (REAL type per PROJECT_GUIDES.md float-only policy)';
COMMENT ON COLUMN balance_snapshots.locked_balance IS 'Balance locked in orders (REAL type per PROJECT_GUIDES.md float-only policy)';
COMMENT ON COLUMN balance_snapshots.total_balance IS 'Total balance computed as available + locked (REAL type, generated column)';
COMMENT ON COLUMN balance_snapshots.frozen_balance IS 'Frozen balance (exchange-specific, REAL type)';
COMMENT ON COLUMN balance_snapshots.borrowing_balance IS 'Borrowing balance for margin/futures (REAL type)';
COMMENT ON COLUMN balance_snapshots.interest_balance IS 'Interest accumulation (REAL type)';

-- =============================================================================
-- VALIDATION FUNCTIONS (HFT-OPTIMIZED)
-- =============================================================================

-- Function to validate balance snapshot data before insertion
CREATE OR REPLACE FUNCTION validate_balance_snapshot_data()
RETURNS TRIGGER AS $$
BEGIN
    -- Validate asset name format (uppercase alphanumeric)
    IF NEW.asset_name !~ '^[A-Z0-9]+$' THEN
        RAISE EXCEPTION 'Invalid asset name format: %', NEW.asset_name;
    END IF;
    
    -- Validate timestamp is not in future (with 1 hour tolerance)
    IF NEW.timestamp > NOW() + INTERVAL '1 hour' THEN
        RAISE EXCEPTION 'Timestamp cannot be more than 1 hour in the future: %', NEW.timestamp;
    END IF;
    
    -- Validate exchange_id exists
    IF NOT EXISTS (SELECT 1 FROM exchanges WHERE id = NEW.exchange_id) THEN
        RAISE EXCEPTION 'Invalid exchange_id: %', NEW.exchange_id;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for validation (only on INSERT to maintain performance)
CREATE TRIGGER trg_validate_balance_snapshot_data
    BEFORE INSERT ON balance_snapshots
    FOR EACH ROW
    EXECUTE FUNCTION validate_balance_snapshot_data();

-- =============================================================================
-- PERFORMANCE TESTING FUNCTION
-- =============================================================================

-- Function to test balance snapshot performance
CREATE OR REPLACE FUNCTION test_balance_snapshot_performance()
RETURNS TABLE(
    operation TEXT,
    duration_ms NUMERIC,
    target_ms NUMERIC,
    status TEXT
) AS $$
DECLARE
    start_time TIMESTAMPTZ;
    end_time TIMESTAMPTZ;
    test_exchange_id INTEGER;
    test_records INTEGER;
BEGIN
    -- Get a test exchange ID
    SELECT id INTO test_exchange_id FROM exchanges LIMIT 1;
    
    -- Test 1: Single INSERT performance
    start_time := clock_timestamp();
    INSERT INTO balance_snapshots (
        timestamp, exchange_id, asset_name, available_balance, locked_balance
    ) VALUES (
        NOW(), test_exchange_id, 'TEST', 100.0, 50.0
    );
    end_time := clock_timestamp();
    
    RETURN QUERY SELECT 
        'Single INSERT'::TEXT,
        EXTRACT(epoch FROM (end_time - start_time)) * 1000,
        5.0::NUMERIC,
        CASE WHEN EXTRACT(epoch FROM (end_time - start_time)) * 1000 <= 5.0 
             THEN 'PASS' ELSE 'FAIL' END;
    
    -- Test 2: Latest balance query performance
    start_time := clock_timestamp();
    PERFORM * FROM balance_snapshots bs
    JOIN exchanges e ON bs.exchange_id = e.id
    WHERE bs.exchange_id = test_exchange_id
    AND bs.asset_name = 'TEST'
    ORDER BY bs.timestamp DESC
    LIMIT 1;
    end_time := clock_timestamp();
    
    RETURN QUERY SELECT 
        'Latest balance query'::TEXT,
        EXTRACT(epoch FROM (end_time - start_time)) * 1000,
        3.0::NUMERIC,
        CASE WHEN EXTRACT(epoch FROM (end_time - start_time)) * 1000 <= 3.0 
             THEN 'PASS' ELSE 'FAIL' END;
    
    -- Test 3: Historical query performance (24 hours)
    start_time := clock_timestamp();
    SELECT COUNT(*) INTO test_records FROM balance_snapshots bs
    WHERE bs.exchange_id = test_exchange_id
    AND bs.timestamp >= NOW() - INTERVAL '24 hours';
    end_time := clock_timestamp();
    
    RETURN QUERY SELECT 
        'Historical query (24h)'::TEXT,
        EXTRACT(epoch FROM (end_time - start_time)) * 1000,
        10.0::NUMERIC,
        CASE WHEN EXTRACT(epoch FROM (end_time - start_time)) * 1000 <= 10.0 
             THEN 'PASS' ELSE 'FAIL' END;
    
    -- Cleanup test data
    DELETE FROM balance_snapshots WHERE asset_name = 'TEST';
END;
$$ LANGUAGE plpgsql;

COMMIT;