"""
Migration 001: Add missing funding_rate_snapshots and balance_snapshots tables

This migration creates the missing tables required for the arbitrage system:
- funding_rate_snapshots: For tracking funding rates across exchanges
- balance_snapshots: For tracking account balances with proper normalization

Uses the complete SQL from docker/init-db.sql for consistency.
"""

import logging
from typing import Dict, Any
import asyncpg

from db.connection import get_db_manager

logger = logging.getLogger(__name__)

MIGRATION_ID = "001"
MIGRATION_NAME = "add_missing_tables"


async def migrate_up() -> Dict[str, Any]:
    """
    Apply migration: Create funding_rate_snapshots and balance_snapshots tables.
    
    Returns:
        Dictionary with migration results
    """
    db = get_db_manager()
    
    result = {
        'success': False,
        'tables_created': [],
        'indexes_created': 0,
        'hypertables_created': [],
        'errors': []
    }
    
    try:
        # Check if tables already exist
        existing_tables = await _check_existing_tables(db)
        
        # Create funding_rate_snapshots table if not exists
        if 'funding_rate_snapshots' not in existing_tables:
            await _create_funding_rate_snapshots_table(db)
            result['tables_created'].append('funding_rate_snapshots')
            logger.info("Created funding_rate_snapshots table")
        else:
            logger.info("funding_rate_snapshots table already exists")
        
        # Create balance_snapshots table if not exists  
        if 'balance_snapshots' not in existing_tables:
            await _create_balance_snapshots_table(db)
            result['tables_created'].append('balance_snapshots')
            logger.info("Created balance_snapshots table")
        else:
            logger.info("balance_snapshots table already exists")
        
        # Create indexes for both tables
        indexes_created = await _create_table_indexes(db)
        result['indexes_created'] = indexes_created
        
        # Setup TimescaleDB hypertables
        hypertables = await _setup_hypertables(db)
        result['hypertables_created'] = hypertables
        
        # Apply retention policies
        await _apply_retention_policies(db)
        
        result['success'] = True
        logger.info(f"Migration {MIGRATION_ID} completed successfully")
        
    except Exception as e:
        error_msg = f"Migration {MIGRATION_ID} failed: {e}"
        logger.error(error_msg)
        result['errors'].append(error_msg)
        raise
    
    return result


async def migrate_down() -> Dict[str, Any]:
    """
    Rollback migration: Drop the created tables.
    
    Returns:
        Dictionary with rollback results
    """
    db = get_db_manager()
    
    result = {
        'success': False,
        'tables_dropped': [],
        'errors': []
    }
    
    try:
        # Drop tables in reverse order
        tables_to_drop = ['balance_snapshots', 'funding_rate_snapshots']
        
        for table_name in tables_to_drop:
            try:
                await db.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
                result['tables_dropped'].append(table_name)
                logger.info(f"Dropped table: {table_name}")
            except Exception as e:
                error_msg = f"Failed to drop table {table_name}: {e}"
                logger.error(error_msg)
                result['errors'].append(error_msg)
        
        result['success'] = len(result['errors']) == 0
        logger.info(f"Migration {MIGRATION_ID} rollback completed")
        
    except Exception as e:
        error_msg = f"Migration {MIGRATION_ID} rollback failed: {e}"
        logger.error(error_msg)
        result['errors'].append(error_msg)
        raise
    
    return result


async def _check_existing_tables(db) -> set:
    """Check which tables already exist."""
    query = """
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name IN ('funding_rate_snapshots', 'balance_snapshots')
    """
    rows = await db.fetch(query)
    return {row['table_name'] for row in rows}


async def _create_funding_rate_snapshots_table(db) -> None:
    """Create funding_rate_snapshots table with complete structure from init-db.sql."""
    
    # Table creation SQL from docker/init-db.sql (lines 131-150)
    create_table_sql = """
        CREATE TABLE IF NOT EXISTS funding_rate_snapshots (
            id BIGSERIAL,
            timestamp TIMESTAMPTZ NOT NULL,
            symbol_id INTEGER NOT NULL REFERENCES symbols(id),  -- Foreign key to symbols table
            
            -- Funding rate data
            funding_rate NUMERIC(12,8) NOT NULL,  -- Current funding rate (e.g., 0.00010000 for 0.01%)
            funding_time BIGINT NOT NULL,         -- Next funding time (Unix timestamp in milliseconds)
            
            -- Metadata
            created_at TIMESTAMPTZ DEFAULT NOW(),
            
            -- HFT Performance Constraints
            CONSTRAINT chk_funding_rate_bounds CHECK (funding_rate >= -1.0 AND funding_rate <= 1.0),
            CONSTRAINT chk_funding_time_valid CHECK (funding_time > 0),
            CONSTRAINT chk_funding_timestamp_valid CHECK (timestamp >= '2020-01-01'::timestamptz),
            
            -- Optimized primary key for time-series partitioning
            PRIMARY KEY (timestamp, symbol_id)
        );
    """
    
    await db.execute(create_table_sql)
    
    # Add table comment
    comment_sql = """
        COMMENT ON TABLE funding_rate_snapshots IS 
        'Funding rate snapshots for futures contracts with normalized symbol references';
    """
    await db.execute(comment_sql)


async def _create_balance_snapshots_table(db) -> None:
    """Create balance_snapshots table with complete structure from init-db.sql."""
    
    # Table creation SQL from docker/init-db.sql (lines 163-196)
    create_table_sql = """
        CREATE TABLE IF NOT EXISTS balance_snapshots (
            id BIGSERIAL,
            timestamp TIMESTAMPTZ NOT NULL,
            exchange_id INTEGER NOT NULL REFERENCES exchanges(id),  -- Foreign key to exchanges table
            
            -- Asset identification
            asset_name VARCHAR(20) NOT NULL,  -- BTC, USDT, ETH, etc.
            
            -- Balance data (HFT optimized with REAL/float types per PROJECT_GUIDES.md)
            available_balance REAL NOT NULL DEFAULT 0,
            locked_balance REAL NOT NULL DEFAULT 0,
            total_balance REAL GENERATED ALWAYS AS (available_balance + locked_balance) STORED,
            
            -- Exchange-specific fields (optional)
            frozen_balance REAL DEFAULT 0,  -- Some exchanges track frozen balances
            borrowing_balance REAL DEFAULT 0,  -- Margin/futures borrowing
            interest_balance REAL DEFAULT 0,  -- Interest accumulation
            
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
            CONSTRAINT chk_valid_balance_timestamp CHECK (timestamp >= '2020-01-01'::timestamptz),
            
            -- Optimized primary key for time-series partitioning
            PRIMARY KEY (timestamp, exchange_id, asset_name)
        );
    """
    
    await db.execute(create_table_sql)
    
    # Add table comment
    comment_sql = """
        COMMENT ON TABLE balance_snapshots IS 
        'Account balance snapshots across all exchanges with normalized schema relationships';
    """
    await db.execute(comment_sql)


async def _setup_hypertables(db) -> list:
    """Setup TimescaleDB hypertables for optimal performance."""
    hypertables_created = []
    
    # Convert funding_rate_snapshots to hypertable (1 hour chunks)
    try:
        await db.execute("""
            SELECT create_hypertable('funding_rate_snapshots', 'timestamp', 
                chunk_time_interval => INTERVAL '1 hour',
                if_not_exists => TRUE);
        """)
        hypertables_created.append('funding_rate_snapshots')
        logger.info("Created funding_rate_snapshots hypertable")
    except Exception as e:
        logger.warning(f"Failed to create funding_rate_snapshots hypertable: {e}")
    
    # Convert balance_snapshots to hypertable (6 hour chunks)
    try:
        await db.execute("""
            SELECT create_hypertable('balance_snapshots', 'timestamp', 
                chunk_time_interval => INTERVAL '6 hours',
                if_not_exists => TRUE);
        """)
        hypertables_created.append('balance_snapshots')
        logger.info("Created balance_snapshots hypertable")
    except Exception as e:
        logger.warning(f"Failed to create balance_snapshots hypertable: {e}")
    
    return hypertables_created


async def _create_table_indexes(db) -> int:
    """Create HFT-optimized indexes for both tables."""
    indexes_created = 0
    
    # Funding rate snapshots indexes (from init-db.sql lines 337-354)
    funding_indexes = [
        "CREATE INDEX IF NOT EXISTS idx_funding_rates_symbol_time ON funding_rate_snapshots(symbol_id, timestamp DESC);",
        "CREATE INDEX IF NOT EXISTS idx_funding_rates_time_symbol ON funding_rate_snapshots(timestamp DESC, symbol_id);",
        "CREATE INDEX IF NOT EXISTS idx_funding_rates_recent ON funding_rate_snapshots(timestamp DESC) WHERE timestamp > NOW() - INTERVAL '24 hours';",
        "CREATE INDEX IF NOT EXISTS idx_funding_rates_rate_range ON funding_rate_snapshots(funding_rate) WHERE ABS(funding_rate) > 0.0001;",
        "CREATE INDEX IF NOT EXISTS idx_funding_rates_funding_time ON funding_rate_snapshots(funding_time);"
    ]
    
    # Balance snapshots indexes (from init-db.sql lines 355-383)
    balance_indexes = [
        "CREATE INDEX IF NOT EXISTS idx_balance_snapshots_exchange_time ON balance_snapshots(exchange_id, timestamp DESC);",
        "CREATE INDEX IF NOT EXISTS idx_balance_snapshots_asset_time ON balance_snapshots(asset_name, timestamp DESC);",
        "CREATE INDEX IF NOT EXISTS idx_balance_snapshots_exchange_asset_time ON balance_snapshots(exchange_id, asset_name, timestamp DESC);",
        "CREATE INDEX IF NOT EXISTS idx_balance_snapshots_recent ON balance_snapshots(timestamp DESC) WHERE timestamp > NOW() - INTERVAL '24 hours';",
        "CREATE INDEX IF NOT EXISTS idx_balance_snapshots_asset_recent ON balance_snapshots(asset_name, exchange_id, timestamp DESC) WHERE timestamp > NOW() - INTERVAL '7 days';",
        "CREATE INDEX IF NOT EXISTS idx_balance_snapshots_active_balances ON balance_snapshots(exchange_id, asset_name, timestamp DESC) WHERE total_balance > 0;",
        "CREATE INDEX IF NOT EXISTS idx_balance_snapshots_exchange_recent ON balance_snapshots(exchange_id, timestamp DESC) WHERE timestamp > NOW() - INTERVAL '24 hours';"
    ]
    
    # Create all indexes
    all_indexes = funding_indexes + balance_indexes
    
    for index_sql in all_indexes:
        try:
            await db.execute(index_sql)
            indexes_created += 1
        except Exception as e:
            logger.warning(f"Failed to create index: {e}")
    
    logger.info(f"Created {indexes_created} indexes")
    return indexes_created


async def _apply_retention_policies(db) -> None:
    """Apply TimescaleDB retention policies for space optimization."""
    
    # Funding rates: Keep 7 days for analysis
    try:
        await db.execute("""
            SELECT add_retention_policy('funding_rate_snapshots', INTERVAL '7 days', if_not_exists => TRUE);
        """)
        logger.info("Applied retention policy for funding_rate_snapshots: 7 days")
    except Exception as e:
        logger.warning(f"Failed to apply retention policy for funding_rate_snapshots: {e}")
    
    # Balance snapshots: Keep 14 days for detailed analysis
    try:
        await db.execute("""
            SELECT add_retention_policy('balance_snapshots', INTERVAL '14 days', if_not_exists => TRUE);
        """)
        logger.info("Applied retention policy for balance_snapshots: 14 days")
    except Exception as e:
        logger.warning(f"Failed to apply retention policy for balance_snapshots: {e}")


async def get_migration_info() -> Dict[str, Any]:
    """
    Get information about this migration.
    
    Returns:
        Dictionary with migration metadata
    """
    return {
        'id': MIGRATION_ID,
        'name': MIGRATION_NAME,
        'description': 'Add missing funding_rate_snapshots and balance_snapshots tables',
        'tables_created': ['funding_rate_snapshots', 'balance_snapshots'],
        'dependencies': ['exchanges', 'symbols'],  # Required tables
        'version': '1.0.0'
    }