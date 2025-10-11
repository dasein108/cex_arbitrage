"""
DEPRECATED: connection.py has been merged into database_manager.py

This module has been consolidated into database_manager.py to eliminate duplication.
All functionality from connection.py is now available in DatabaseManager.

Migration Guide:
OLD: from db.connection import DatabaseManager, get_db_manager, initialize_database
NEW: from db.database_manager import DatabaseManager, get_db_manager, initialize_database

Or use the simplified imports:
from db import get_db_manager, initialize_database

The consolidated DatabaseManager now provides:
- All low-level database operations (execute, fetch, fetchrow, fetchval, etc.)
- High-level cached operations (symbol/exchange lookups)
- Built-in caching with HFT performance optimization
- Float-only data policy throughout
- Struct-first data modeling

For backward compatibility, all imports still work via db/__init__.py
"""

import warnings

warnings.warn(
    "db.connection is deprecated. Use db.database_manager.DatabaseManager instead. "
    "All functionality has been consolidated into a single DatabaseManager class.",
    DeprecationWarning,
    stacklevel=2
)

# Import consolidated functionality for backward compatibility
from .database_manager import (
    DatabaseManager,
    get_db_manager,
    initialize_database,
    close_database,
    get_database_manager,
    initialize_database_manager,
    close_database_manager
)

__all__ = [
    'DatabaseManager',
    'get_db_manager', 
    'initialize_database',
    'close_database',
    'get_database_manager',
    'initialize_database_manager', 
    'close_database_manager'
]