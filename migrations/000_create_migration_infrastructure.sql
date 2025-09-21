-- =============================================================================
-- Migration Infrastructure Setup
-- Version: 000 (Bootstrap)
-- Date: 2025-01-01
-- Description: Create migration tracking infrastructure
-- =============================================================================

-- Begin transaction for atomic setup
BEGIN;

-- Create migration history table to track applied migrations
CREATE TABLE IF NOT EXISTS migration_history (
    id SERIAL PRIMARY KEY,
    version VARCHAR(10) NOT NULL UNIQUE,
    description TEXT NOT NULL,
    applied_at TIMESTAMPTZ DEFAULT NOW(),
    applied_by VARCHAR(100) DEFAULT CURRENT_USER,
    checksum VARCHAR(64),  -- For future integrity checking
    execution_time_ms INTEGER,
    
    CONSTRAINT chk_version_format CHECK (version ~ '^\d{3}$')
);

-- Create index for quick version lookups
CREATE INDEX IF NOT EXISTS idx_migration_history_version 
    ON migration_history(version);

CREATE INDEX IF NOT EXISTS idx_migration_history_applied_at 
    ON migration_history(applied_at DESC);

-- Grant permissions
GRANT ALL PRIVILEGES ON migration_history TO arbitrage_user;
GRANT SELECT ON migration_history TO readonly_user;

-- Set table owner
ALTER TABLE migration_history OWNER TO arbitrage_user;

-- Add initial migration record
INSERT INTO migration_history (version, description, applied_at) 
VALUES ('000', 'Create migration infrastructure', NOW())
ON CONFLICT (version) DO NOTHING;

-- Create function to check if migration was applied
CREATE OR REPLACE FUNCTION is_migration_applied(migration_version VARCHAR(10)) 
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM migration_history 
        WHERE version = migration_version
    );
END;
$$ LANGUAGE plpgsql;

-- Create function to get migration status
CREATE OR REPLACE FUNCTION get_migration_status()
RETURNS TABLE (
    version VARCHAR(10),
    description TEXT,
    applied_at TIMESTAMPTZ,
    applied_by VARCHAR(100)
) AS $$
BEGIN
    RETURN QUERY 
    SELECT 
        mh.version, 
        mh.description, 
        mh.applied_at, 
        mh.applied_by
    FROM migration_history mh
    ORDER BY mh.version;
END;
$$ LANGUAGE plpgsql;

-- Grant execute permissions on functions
GRANT EXECUTE ON FUNCTION is_migration_applied(VARCHAR) TO arbitrage_user, readonly_user;
GRANT EXECUTE ON FUNCTION get_migration_status() TO arbitrage_user, readonly_user;

COMMIT;

-- =============================================================================
-- Migration Infrastructure Created
-- =============================================================================
-- Created:
-- 1. migration_history table for tracking applied migrations
-- 2. Indexes for efficient lookups
-- 3. Helper functions for migration status checking
-- 4. Proper permissions and ownership
-- =============================================================================