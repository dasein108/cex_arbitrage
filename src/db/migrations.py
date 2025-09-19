"""
Database Migration Runner

Automatic database schema migration system.
Ensures database schema is up-to-date on application startup.
"""

import os
import logging
from pathlib import Path
from typing import List, Tuple
import asyncpg

from .connection import get_db_manager


logger = logging.getLogger(__name__)


async def create_migrations_table() -> None:
    """
    Create migrations tracking table if it doesn't exist.
    """
    db = get_db_manager()
    
    query = """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id SERIAL PRIMARY KEY,
            migration_name VARCHAR(255) NOT NULL UNIQUE,
            applied_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
        )
    """
    
    await db.execute(query)
    logger.debug("Ensured schema_migrations table exists")


async def get_applied_migrations() -> List[str]:
    """
    Get list of already applied migrations.
    
    Returns:
        List of migration names that have been applied
    """
    db = get_db_manager()
    
    try:
        rows = await db.fetch("SELECT migration_name FROM schema_migrations ORDER BY id")
        return [row['migration_name'] for row in rows]
    except asyncpg.UndefinedTableError:
        # Migrations table doesn't exist yet
        return []


async def mark_migration_applied(migration_name: str) -> None:
    """
    Mark a migration as applied.
    
    Args:
        migration_name: Name of the migration file
    """
    db = get_db_manager()
    
    query = """
        INSERT INTO schema_migrations (migration_name)
        VALUES ($1)
        ON CONFLICT (migration_name) DO NOTHING
    """
    
    await db.execute(query, migration_name)
    logger.info(f"Marked migration {migration_name} as applied")


async def get_pending_migrations(migrations_dir: str) -> List[Tuple[str, str]]:
    """
    Get list of migrations that need to be applied.
    
    Args:
        migrations_dir: Directory containing migration files
        
    Returns:
        List of tuples (migration_name, file_path)
    """
    # Ensure migrations table exists
    await create_migrations_table()
    
    # Get applied migrations
    applied_migrations = await get_applied_migrations()
    
    # Find all migration files
    migrations_path = Path(migrations_dir)
    if not migrations_path.exists():
        logger.warning(f"Migrations directory {migrations_dir} does not exist")
        return []
    
    migration_files = []
    for file_path in migrations_path.glob("*.sql"):
        migration_name = file_path.name
        if migration_name not in applied_migrations:
            migration_files.append((migration_name, str(file_path)))
    
    # Sort by filename to ensure proper order
    migration_files.sort(key=lambda x: x[0])
    
    return migration_files


async def apply_migration(migration_name: str, file_path: str) -> None:
    """
    Apply a single migration.
    
    Args:
        migration_name: Name of the migration
        file_path: Path to the migration SQL file
    """
    db = get_db_manager()
    
    logger.info(f"Applying migration: {migration_name}")
    
    try:
        # Read migration file
        with open(file_path, 'r') as f:
            migration_sql = f.read()
        
        # Execute migration in a transaction
        async with db.pool.acquire() as conn:
            async with conn.transaction():
                # Execute the migration SQL
                await conn.execute(migration_sql)
                
                # Mark as applied
                await conn.execute(
                    "INSERT INTO schema_migrations (migration_name) VALUES ($1)",
                    migration_name
                )
        
        logger.info(f"Successfully applied migration: {migration_name}")
        
    except Exception as e:
        logger.error(f"Failed to apply migration {migration_name}: {e}")
        raise


async def run_migrations(migrations_dir: str = "db/migrations") -> int:
    """
    Run all pending database migrations.
    
    Args:
        migrations_dir: Directory containing migration files
        
    Returns:
        Number of migrations applied
        
    Raises:
        Exception: If any migration fails
    """
    logger.info("Starting database migrations")
    
    try:
        # Get pending migrations
        pending_migrations = await get_pending_migrations(migrations_dir)
        
        if not pending_migrations:
            logger.info("No pending migrations")
            return 0
        
        logger.info(f"Found {len(pending_migrations)} pending migrations")
        
        # Apply each migration
        for migration_name, file_path in pending_migrations:
            await apply_migration(migration_name, file_path)
        
        logger.info(f"Successfully applied {len(pending_migrations)} migrations")
        return len(pending_migrations)
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise


async def rollback_migration(migration_name: str) -> None:
    """
    Rollback a specific migration (remove from applied list).
    
    Note: This only removes the migration from the tracking table.
    Manual SQL commands may be needed to undo schema changes.
    
    Args:
        migration_name: Name of the migration to rollback
    """
    db = get_db_manager()
    
    query = "DELETE FROM schema_migrations WHERE migration_name = $1"
    result = await db.execute(query, migration_name)
    
    if "DELETE 1" in result:
        logger.info(f"Rolled back migration: {migration_name}")
    else:
        logger.warning(f"Migration {migration_name} was not found in applied migrations")


async def get_migration_status() -> List[dict]:
    """
    Get status of all migrations.
    
    Returns:
        List of dictionaries with migration status information
    """
    applied_migrations = await get_applied_migrations()
    
    # Find all migration files
    migrations_path = Path("db/migrations")
    all_files = []
    if migrations_path.exists():
        all_files = [f.name for f in migrations_path.glob("*.sql")]
    
    status = []
    for file_name in sorted(all_files):
        status.append({
            'migration': file_name,
            'applied': file_name in applied_migrations,
            'applied_at': None  # Could be enhanced to include timestamp
        })
    
    return status