"""
Database Module - Simplified Architecture

This module provides access to the simplified DatabaseManager following PROJECT_GUIDES.md requirements.
All database functionality is consolidated into a single DatabaseManager class with simple lookup table.

Key Features:
- Float-Only Data Policy: NEVER use Decimal, ALWAYS use float
- Struct-First Data Policy: msgspec.Struct over dict for ALL data modeling  
- HFT Performance Requirements: Sub-millisecond targets, minimal LOC
- Configuration Management: Use HftConfig with get_database_config()
- Simple lookup table: (ExchangeEnum, Symbol) -> symbol_id
- Auto-resolution: create missing exchanges/symbols automatically

SIMPLIFIED API:
    from db import get_database_manager, initialize_database_manager
    from exchanges.structs.enums import ExchangeEnum
    from exchanges.structs.common import Symbol
    
    # Initialize the database manager
    await initialize_database_manager()
    
    # Get the global manager instance
    db = get_database_manager()
    
    # Auto-resolving methods (create if missing)
    await db.insert_book_ticker_snapshot(ExchangeEnum.MEXC_SPOT, symbol, snapshot)
    await db.insert_balance_snapshots_batch(ExchangeEnum.MEXC_SPOT, balance_snapshots)
    
    # Get database statistics
    db_stats = await db.get_database_stats()
    lookup_stats = db.get_lookup_table_stats()

LEGACY COMPATIBILITY:
Basic operations continue to work for backward compatibility.
"""

# NEW SIMPLIFIED API (PROJECT_GUIDES.md compliant)
from .database_manager import (
    DatabaseManager as SimplifiedDatabaseManager,
    get_database_manager,
    initialize_database_manager,
    close_database_manager
)

# LEGACY API (backward compatibility)
from .database_manager import DatabaseManager, get_db_manager, initialize_database, close_database
from .models import BookTickerSnapshot, TradeSnapshot, Exchange, Symbol as DBSymbol
from .migrations import run_all_pending_migrations as run_pending_migrations

# Basic operations (still available from operations.py)
try:
    from .operations import (
        get_book_ticker_snapshots,
        get_latest_book_ticker_snapshots,
        get_book_ticker_history,
        get_exchange_by_id,
        get_exchange_by_enum,
        get_all_active_exchanges,
        get_symbol_by_id,
        get_symbol_by_exchange_and_pair,
        get_symbols_by_exchange,
        get_all_active_symbols
    )
except ImportError:
    # Operations may depend on removed cache modules
    pass

# Symbol manager (if still exists)
try:
    from .symbol_manager import get_symbol_id, get_symbol_details, clear_symbol_cache
except ImportError:
    # Symbol manager may depend on removed cache modules
    pass

from config.structs import DatabaseConfig

__all__ = [
    # NEW SIMPLIFIED API (PROJECT_GUIDES.md compliant)
    'SimplifiedDatabaseManager',
    'get_database_manager', 
    'initialize_database_manager',
    'close_database_manager',
    
    # LEGACY Connection management (backward compatibility)
    'DatabaseManager',
    'get_db_manager',
    'initialize_database',
    'close_database',
    'DatabaseConfig',
    
    # Models
    'BookTickerSnapshot',
    'TradeSnapshot', 
    'Exchange',
    'DBSymbol',
    
    # Basic operations (if available)
    'get_book_ticker_snapshots',
    'get_latest_book_ticker_snapshots',
    'get_book_ticker_history',
    'get_exchange_by_id',
    'get_exchange_by_enum',
    'get_all_active_exchanges',
    'get_symbol_by_id',
    'get_symbol_by_exchange_and_pair',
    'get_symbols_by_exchange',
    'get_all_active_symbols',
    
    # Migrations
    'run_pending_migrations',
    
    # Symbol manager (if available)
    'get_symbol_id',
    'get_symbol_details',
    'clear_symbol_cache'
]