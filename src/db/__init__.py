"""
Database Module

High-performance PostgreSQL integration for the CEX Arbitrage Engine.
Provides asyncpg-based connection management and operations optimized for HFT requirements.

Key Features:
- Ultra-fast asyncpg connection pooling
- HFT-optimized BookTicker storage
- Sub-microsecond symbol resolution cache
- Normalized exchange and symbol management
- Automatic schema migrations
- Sub-millisecond insert/query performance
- Prepared statement caching
"""

from .connection import DatabaseManager, get_db_manager, initialize_database, close_database
from .operations import (
    insert_book_ticker_snapshot,
    get_book_ticker_snapshots,
    get_latest_book_ticker_snapshots,
    get_book_ticker_history,
    # Exchange operations
    get_exchange_by_id,
    get_exchange_by_enum,
    get_all_active_exchanges,
    insert_exchange,
    update_exchange,
    get_exchange_stats,
    # Symbol operations
    get_symbol_by_id,
    get_symbol_by_exchange_and_pair,
    get_symbols_by_exchange,
    get_all_active_symbols,
    get_symbols_by_market_type,
    insert_symbol,
    update_symbol,
    get_symbol_stats
)
from .models import BookTickerSnapshot, TradeSnapshot, Exchange, Symbol as DBSymbol
from .migrations import run_migrations
from .symbol_manager import get_symbol_id, get_symbol_details, clear_symbol_cache
from .cache import SymbolCache, initialize_symbol_cache, close_symbol_cache, get_symbol_cache
from .cache_operations import (
    # Cached symbol lookups
    cached_get_symbol_by_id,
    cached_get_symbol_by_exchange_and_pair,
    cached_get_symbol_by_exchange_and_string,
    cached_get_symbols_by_exchange,
    cached_get_all_symbols,
    # Cached exchange lookups
    cached_get_exchange_by_id,
    cached_get_exchange_by_enum,
    cached_get_exchange_by_enum_value,
    # High-level convenience functions
    cached_resolve_symbol_for_exchange,
    cached_resolve_symbol_by_exchange_string,
    cached_get_symbols_for_exchange_enum,
    # Cache management
    get_cache_stats,
    reset_cache_stats,
    refresh_symbol_cache,
    is_cache_initialized,
    validate_cache_performance,
    log_cache_performance_summary
)
from .cache_warming import (
    WarmingStrategy,
    WarmingConfig,
    WarmingResults,
    CacheWarmingService,
    get_cache_warming_service,
    warm_symbol_cache,
    warm_cache_for_exchange,
    warm_cache_for_priority_symbols,
    is_cache_warming_needed
)
from .cache_monitor import (
    AlertLevel,
    PerformanceThresholds,
    PerformanceAlert,
    PerformanceSnapshot,
    CachePerformanceMonitor,
    get_cache_performance_monitor,
    start_cache_monitoring,
    stop_cache_monitoring,
    get_cache_performance_summary,
    get_cache_recent_alerts
)
from .cache_validation import (
    PerformanceTarget,
    ValidationResult,
    CacheValidationReport,
    CacheValidator,
    validate_cache_hft_performance,
    print_validation_report
)
from config.structs import DatabaseConfig

__all__ = [
    # Connection management
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
    
    # BookTicker operations
    'insert_book_ticker_snapshot',
    'insert_book_ticker_snapshots_batch',
    'get_book_ticker_snapshots',
    'get_latest_book_ticker_snapshots',
    'get_book_ticker_history',
    
    # Exchange operations
    'get_exchange_by_id',
    'get_exchange_by_enum',
    'get_all_active_exchanges',
    'insert_exchange',
    'update_exchange',
    'get_exchange_stats',
    
    # Symbol operations
    'get_symbol_by_id',
    'get_symbol_by_exchange_and_pair',
    'get_symbols_by_exchange',
    'get_all_active_symbols',
    'get_symbols_by_market_type',
    'insert_symbol',
    'update_symbol',
    'get_symbol_stats',
    
    # Migrations
    'run_migrations',
    
    # Symbol manager (legacy compatibility)
    'get_symbol_id',
    'get_symbol_details',
    'clear_symbol_cache',
    
    # Cache infrastructure
    'SymbolCache',
    'initialize_symbol_cache',
    'close_symbol_cache',
    'get_symbol_cache',
    
    # Cached symbol lookups
    'cached_get_symbol_by_id',
    'cached_get_symbol_by_exchange_and_pair',
    'cached_get_symbol_by_exchange_and_string',
    'cached_get_symbols_by_exchange',
    'cached_get_all_symbols',
    
    # Cached exchange lookups
    'cached_get_exchange_by_id',
    'cached_get_exchange_by_enum',
    'cached_get_exchange_by_enum_value',
    
    # High-level convenience functions
    'cached_resolve_symbol_for_exchange',
    'cached_resolve_symbol_by_exchange_string',
    'cached_get_symbols_for_exchange_enum',
    
    # Cache management
    'get_cache_stats',
    'reset_cache_stats',
    'refresh_symbol_cache',
    'is_cache_initialized',
    'validate_cache_performance',
    'log_cache_performance_summary',
    
    # Cache warming
    'WarmingStrategy',
    'WarmingConfig',
    'WarmingResults',
    'CacheWarmingService',
    'get_cache_warming_service',
    'warm_symbol_cache',
    'warm_cache_for_exchange',
    'warm_cache_for_priority_symbols',
    'is_cache_warming_needed',
    
    # Cache monitoring
    'AlertLevel',
    'PerformanceThresholds',
    'PerformanceAlert',
    'PerformanceSnapshot',
    'CachePerformanceMonitor',
    'get_cache_performance_monitor',
    'start_cache_monitoring',
    'stop_cache_monitoring',
    'get_cache_performance_summary',
    'get_cache_recent_alerts',
    
    # Cache validation
    'PerformanceTarget',
    'ValidationResult',
    'CacheValidationReport',
    'CacheValidator',
    'validate_cache_hft_performance',
    'print_validation_report'
]