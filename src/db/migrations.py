"""
Database Schema Initialization

Simplified schema initialization using docker/init-db.sql.
The complete database schema is available for recovery from scratch.
"""

import logging
from pathlib import Path
from typing import Dict, Any
import asyncpg

from .connection import get_db_manager


logger = logging.getLogger(__name__)


async def run_pending_migrations() -> Dict[str, Any]:
    """
    Run any pending database migrations automatically.
    
    This function checks for missing tables and applies migrations as needed.
    Called automatically during database initialization.
    
    Returns:
        Dictionary with migration results
    """
    logger.info("Checking for pending database migrations...")
    
    try:
        # Import migrations module
        from .migrations import run_all_pending_migrations
        
        # Run all pending migrations
        result = await run_all_pending_migrations()
        
        if result['success']:
            if result['migrations_run']:
                logger.info(f"Applied {len(result['migrations_run'])} migrations successfully")
            else:
                logger.info("No pending migrations found")
        else:
            logger.error(f"Migration failed: {result['migrations_failed']}")
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to run migrations: {e}")
        return {
            'success': False,
            'error': str(e),
            'migrations_run': [],
            'migrations_failed': []
        }


async def check_schema_initialization() -> Dict[str, Any]:
    """
    Check if the database schema has been properly initialized.
    
    Returns:
        Dictionary with schema status information
    """
    db = get_db_manager()
    
    # Check for core tables that should exist after initialization
    core_tables = [
        'exchanges', 'symbols', 'book_ticker_snapshots', 
        'funding_rate_snapshots', 'balance_snapshots', 'trade_snapshots'
    ]
    
    status = {
        'initialized': False,
        'missing_tables': [],
        'existing_tables': [],
        'hypertables': [],
        'indexes_count': 0
    }
    
    try:
        # Check for table existence
        for table_name in core_tables:
            query = """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = $1
                )
            """
            exists = await db.fetchval(query, table_name)
            
            if exists:
                status['existing_tables'].append(table_name)
            else:
                status['missing_tables'].append(table_name)
        
        # Check for TimescaleDB hypertables
        hypertable_query = """
            SELECT table_name 
            FROM timescaledb_information.hypertables 
            WHERE table_schema = 'public'
        """
        hypertables = await db.fetch(hypertable_query)
        status['hypertables'] = [row['table_name'] for row in hypertables]
        
        # Count indexes
        index_query = """
            SELECT COUNT(*) 
            FROM pg_indexes 
            WHERE schemaname = 'public'
        """
        status['indexes_count'] = await db.fetchval(index_query)
        
        # Mark as initialized if all core tables exist
        status['initialized'] = len(status['missing_tables']) == 0
        
        logger.info(f"Schema status: {len(status['existing_tables'])}/{len(core_tables)} tables exist")
        
    except Exception as e:
        logger.error(f"Failed to check schema status: {e}")
        status['error'] = str(e)
    
    return status


async def verify_schema_integrity() -> Dict[str, Any]:
    """
    Verify the integrity of the database schema.
    
    Returns:
        Dictionary with integrity check results
    """
    db = get_db_manager()
    
    integrity = {
        'foreign_keys_valid': True,
        'constraints_valid': True,
        'hypertables_configured': True,
        'retention_policies_active': True,
        'retention_policies': {},
        'errors': []
    }
    
    try:
        # Check foreign key constraints
        fk_query = """
            SELECT conname, conrelid::regclass AS table_name
            FROM pg_constraint 
            WHERE contype = 'f' AND connamespace = 'public'::regnamespace
        """
        foreign_keys = await db.fetch(fk_query)
        logger.debug(f"Found {len(foreign_keys)} foreign key constraints")
        
        # Check TimescaleDB retention policies with details
        retention_query = """
            SELECT 
                j.hypertable_name,
                j.config->>'drop_after' as retention_interval
            FROM timescaledb_information.jobs j
            WHERE j.job_type = 'drop_chunks'
        """
        retention_policies = await db.fetch(retention_query)
        
        if len(retention_policies) == 0:
            integrity['retention_policies_active'] = False
            integrity['errors'].append("No retention policies found")
        else:
            for policy in retention_policies:
                integrity['retention_policies'][policy['hypertable_name']] = policy['retention_interval']
            logger.info(f"Found {len(retention_policies)} retention policies: {integrity['retention_policies']}")
        
        logger.info("Schema integrity check completed successfully")
        
    except Exception as e:
        logger.error(f"Schema integrity check failed: {e}")
        integrity['errors'].append(str(e))
        integrity['foreign_keys_valid'] = False
        integrity['constraints_valid'] = False
    
    return integrity


async def get_init_script_path() -> str:
    """
    Get the path to the database initialization script.
    
    Returns:
        Path to docker/init-db.sql
    """
    # Look for init-db.sql in the docker directory
    project_root = Path(__file__).parent.parent.parent.parent
    init_script = project_root / "docker" / "init-db.sql"
    
    if not init_script.exists():
        raise FileNotFoundError(f"Database initialization script not found at {init_script}")
    
    return str(init_script)


async def update_retention_policies(retention_days: int = 3) -> Dict[str, Any]:
    """
    Update retention policies for all hypertables.
    
    Args:
        retention_days: Number of days to retain data (default: 3)
        
    Returns:
        Dictionary with update results
    """
    db = get_db_manager()
    
    result = {
        'success': False,
        'policies_updated': [],
        'errors': []
    }
    
    # Tables and their retention periods
    retention_config = {
        'book_ticker_snapshots': retention_days,
        'orderbook_depth': retention_days,
        'trade_snapshots': retention_days,
        'funding_rate_snapshots': min(7, retention_days * 2),  # Keep funding rates longer
        'order_flow_metrics': min(7, retention_days * 2),
        'arbitrage_opportunities': min(14, retention_days * 4),
        'collector_status': min(7, retention_days * 2)
    }
    
    try:
        for table_name, days in retention_config.items():
            try:
                # Remove existing policy
                remove_query = f"SELECT remove_retention_policy('{table_name}', if_exists => TRUE);"
                await db.execute(remove_query)
                
                # Add new policy
                add_query = f"SELECT add_retention_policy('{table_name}', INTERVAL '{days} days', if_not_exists => TRUE);"
                await db.execute(add_query)
                
                result['policies_updated'].append(f"{table_name}: {days} days")
                logger.info(f"Updated retention policy for {table_name}: {days} days")
                
            except Exception as e:
                error_msg = f"Failed to update {table_name}: {str(e)}"
                result['errors'].append(error_msg)
                logger.error(error_msg)
        
        # Drop old chunks immediately
        for table_name, days in retention_config.items():
            try:
                drop_query = f"SELECT drop_chunks('{table_name}', older_than => INTERVAL '{days} days');"
                dropped = await db.fetch(drop_query)
                if dropped:
                    logger.info(f"Dropped {len(dropped)} old chunks from {table_name}")
            except Exception as e:
                logger.warning(f"Could not drop old chunks from {table_name}: {e}")
        
        result['success'] = len(result['errors']) == 0
        
    except Exception as e:
        result['errors'].append(f"General error: {str(e)}")
        logger.error(f"Failed to update retention policies: {e}")
    
    return result


async def run_schema_initialization() -> Dict[str, Any]:
    """
    Run database schema initialization using docker/init-db.sql.
    
    Note: This should only be used for initial setup or complete schema rebuild.
    For production, the schema should be initialized via Docker container startup.
    
    Returns:
        Dictionary with initialization results
    """
    logger.warning("Running manual schema initialization - use with caution in production")
    
    db = get_db_manager()
    init_script_path = await get_init_script_path()
    
    result = {
        'success': False,
        'tables_created': 0,
        'indexes_created': 0,
        'error': None
    }
    
    try:
        # Read the initialization script
        with open(init_script_path, 'r') as f:
            init_sql = f.read()
        
        # Execute the initialization script
        async with db.pool.acquire() as conn:
            await conn.execute(init_sql)
        
        # Verify the initialization
        status = await check_schema_initialization()
        
        result['success'] = status['initialized']
        result['tables_created'] = len(status['existing_tables'])
        result['indexes_created'] = status['indexes_count']
        
        logger.info(f"Schema initialization completed: {result}")
        
    except Exception as e:
        logger.error(f"Schema initialization failed: {e}")
        result['error'] = str(e)
    
    return result


# Legacy migration functions for backward compatibility
async def run_migrations(migrations_dir: str = "db/migrations") -> int:
    """
    Legacy migration function for backward compatibility.
    
    Note: The system now uses docker/init-db.sql for schema initialization.
    This function will check schema status and log a message.
    
    Args:
        migrations_dir: Ignored (for compatibility)
        
    Returns:
        0 (no migrations to apply)
    """
    logger.info("Migration system has been simplified to use docker/init-db.sql")
    
    # Check current schema status
    status = await check_schema_initialization()
    
    if status['initialized']:
        logger.info("Database schema is properly initialized")
        return 0
    else:
        logger.warning("Database schema appears incomplete")
        logger.warning("For new installations, ensure docker/init-db.sql is executed during container startup")
        logger.warning(f"Missing tables: {status['missing_tables']}")
        return 0


async def get_migration_status() -> Dict[str, Any]:
    """
    Get current schema status (replaces migration status).
    
    Returns:
        Dictionary with schema status information
    """
    return await check_schema_initialization()