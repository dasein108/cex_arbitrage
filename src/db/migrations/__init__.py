"""
Database Migrations Module

Manages database schema migrations for the HFT arbitrage system.
Each migration is a separate module with up/down migration functions.
"""

import logging
from typing import Dict, Any, List
from pathlib import Path
import importlib.util

from db.connection import get_db_manager

logger = logging.getLogger(__name__)


async def get_available_migrations() -> List[Dict[str, Any]]:
    """
    Get list of available migration modules.
    
    Returns:
        List of migration info dictionaries
    """
    migrations_dir = Path(__file__).parent
    migration_files = sorted([f for f in migrations_dir.glob("*.py") if f.name != "__init__.py"])
    
    migrations = []
    for migration_file in migration_files:
        try:
            # Import migration module
            spec = importlib.util.spec_from_file_location(migration_file.stem, migration_file)
            migration_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration_module)
            
            # Get migration info
            if hasattr(migration_module, 'get_migration_info'):
                migration_info = await migration_module.get_migration_info()
                migration_info['module'] = migration_module
                migration_info['file'] = str(migration_file)
                migrations.append(migration_info)
                
        except Exception as e:
            logger.error(f"Failed to load migration {migration_file}: {e}")
    
    return migrations


async def run_migration(migration_id: str) -> Dict[str, Any]:
    """
    Run a specific migration by ID.
    
    Args:
        migration_id: Migration ID (e.g., "001")
        
    Returns:
        Dictionary with migration results
    """
    migrations = await get_available_migrations()
    
    for migration in migrations:
        if migration['id'] == migration_id:
            logger.info(f"Running migration {migration_id}: {migration['name']}")
            
            try:
                result = await migration['module'].migrate_up()
                logger.info(f"Migration {migration_id} completed successfully")
                return result
            except Exception as e:
                logger.error(f"Migration {migration_id} failed: {e}")
                raise
    
    raise ValueError(f"Migration {migration_id} not found")


async def rollback_migration(migration_id: str) -> Dict[str, Any]:
    """
    Rollback a specific migration by ID.
    
    Args:
        migration_id: Migration ID (e.g., "001")
        
    Returns:
        Dictionary with rollback results
    """
    migrations = await get_available_migrations()
    
    for migration in migrations:
        if migration['id'] == migration_id:
            logger.info(f"Rolling back migration {migration_id}: {migration['name']}")
            
            try:
                result = await migration['module'].migrate_down()
                logger.info(f"Migration {migration_id} rollback completed")
                return result
            except Exception as e:
                logger.error(f"Migration {migration_id} rollback failed: {e}")
                raise
    
    raise ValueError(f"Migration {migration_id} not found")


async def run_all_pending_migrations() -> Dict[str, Any]:
    """
    Run all pending migrations.
    
    Returns:
        Dictionary with overall results
    """
    migrations = await get_available_migrations()
    
    results = {
        'success': True,
        'migrations_run': [],
        'migrations_failed': [],
        'total_migrations': len(migrations)
    }
    
    for migration in migrations:
        try:
            # Check if migration is needed
            if await _is_migration_needed(migration):
                result = await migration['module'].migrate_up()
                results['migrations_run'].append({
                    'id': migration['id'],
                    'name': migration['name'],
                    'result': result
                })
                logger.info(f"Migration {migration['id']} completed successfully")
            else:
                logger.info(f"Migration {migration['id']} already applied")
                
        except Exception as e:
            error_info = {
                'id': migration['id'],
                'name': migration['name'],
                'error': str(e)
            }
            results['migrations_failed'].append(error_info)
            results['success'] = False
            logger.error(f"Migration {migration['id']} failed: {e}")
    
    return results


async def _is_migration_needed(migration: Dict[str, Any]) -> bool:
    """
    Check if a migration needs to be run.
    
    Args:
        migration: Migration info dictionary
        
    Returns:
        True if migration is needed
    """
    db = get_db_manager()
    
    # Check if the tables created by this migration exist
    if 'tables_created' in migration:
        for table_name in migration['tables_created']:
            exists = await db.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = $1
                )
            """, table_name)
            
            if not exists:
                return True  # At least one table is missing
    
    return False  # All tables exist