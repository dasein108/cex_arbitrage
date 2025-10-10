"""
Migration 002: Add next_funding_time field to funding_rate_snapshots

Adds an optional next_funding_time datetime field to the funding_rate_snapshots table
for enhanced funding rate analytics and easier datetime-based queries.

This field provides the funding time in datetime format for easier analysis,
complementing the existing funding_time field which remains in Unix timestamp format.
"""

import logging
from typing import Dict, Any
import asyncpg

from db.connection import get_db_manager

logger = logging.getLogger(__name__)

MIGRATION_ID = "002"
MIGRATION_NAME = "add_next_funding_time"


async def migrate_up() -> Dict[str, Any]:
    """Apply migration: Add next_funding_time field to funding_rate_snapshots."""
    db = get_db_manager()
    
    result = {
        'success': False,
        'tables_modified': [],
        'columns_added': [],
        'indexes_created': 0,
        'errors': []
    }
    
    try:
        # Check if column already exists
        column_exists = await db.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns 
                WHERE table_schema = 'public' 
                AND table_name = 'funding_rate_snapshots' 
                AND column_name = 'next_funding_time'
            )
        """)
        
        if column_exists:
            logger.info(f"Column next_funding_time already exists in funding_rate_snapshots")
            result['success'] = True
            return result
        
        # Add the next_funding_time column
        await db.execute("""
            ALTER TABLE funding_rate_snapshots 
            ADD COLUMN next_funding_time TIMESTAMPTZ;
        """)
        result['columns_added'].append('next_funding_time')
        result['tables_modified'].append('funding_rate_snapshots')
        
        # Add comment to document the field purpose
        await db.execute("""
            COMMENT ON COLUMN funding_rate_snapshots.next_funding_time IS 
            'Next funding time as datetime for easier analysis (complements funding_time Unix timestamp)';
        """)
        
        # Create index for datetime-based queries
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_funding_rate_next_funding_time 
            ON funding_rate_snapshots(next_funding_time) 
            WHERE next_funding_time IS NOT NULL;
        """)
        result['indexes_created'] += 1
        
        # Populate existing records with converted values
        # Convert funding_time (Unix timestamp in milliseconds) to next_funding_time (datetime)
        updated_rows = await db.execute("""
            UPDATE funding_rate_snapshots 
            SET next_funding_time = to_timestamp(funding_time / 1000.0)
            WHERE next_funding_time IS NULL 
            AND funding_time IS NOT NULL 
            AND funding_time > 0;
        """)
        
        logger.info(f"Updated {updated_rows.split()[-1] if updated_rows else '0'} existing records with next_funding_time")
        
        result['success'] = True
        logger.info(f"Migration {MIGRATION_ID} completed successfully")
        
    except Exception as e:
        error_msg = f"Migration {MIGRATION_ID} failed: {e}"
        logger.error(error_msg)
        result['errors'].append(error_msg)
        raise
    
    return result


async def migrate_down() -> Dict[str, Any]:
    """Rollback migration: Remove next_funding_time field from funding_rate_snapshots."""
    db = get_db_manager()
    
    try:
        # Drop the index first
        await db.execute("DROP INDEX IF EXISTS idx_funding_rate_next_funding_time")
        
        # Drop the column
        await db.execute("ALTER TABLE funding_rate_snapshots DROP COLUMN IF EXISTS next_funding_time")
        
        logger.info(f"Migration {MIGRATION_ID} rollback completed")
        return {
            'success': True, 
            'columns_dropped': ['next_funding_time'],
            'indexes_dropped': ['idx_funding_rate_next_funding_time']
        }
    except Exception as e:
        logger.error(f"Migration {MIGRATION_ID} rollback failed: {e}")
        raise


async def get_migration_info() -> Dict[str, Any]:
    """Get information about this migration."""
    return {
        'id': MIGRATION_ID,
        'name': MIGRATION_NAME,
        'description': 'Add next_funding_time datetime field to funding_rate_snapshots table',
        'tables_modified': ['funding_rate_snapshots'],
        'columns_added': ['next_funding_time'],
        'dependencies': ['funding_rate_snapshots'],
        'version': '1.0.0'
    }