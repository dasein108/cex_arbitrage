"""
Cache Operations

Convenience functions for cached symbol and exchange lookups.
Provides HFT-optimized access patterns for frontend operations.
"""

import logging
from typing import Optional, List
from exchanges.structs.enums import ExchangeEnum

from .cache import get_symbol_cache, CacheStats
from .models import Symbol as DBSymbol, Exchange


logger = logging.getLogger(__name__)


# ================================================================================================
# Cached Symbol Lookups
# High-performance symbol resolution for HFT operations
# ================================================================================================

def cached_get_symbol_by_id(symbol_id: int) -> Optional[DBSymbol]:
    """
    Get symbol by database ID using cache.
    
    Args:
        symbol_id: Symbol database ID
        
    Returns:
        Symbol instance or None if not found
        
    Performance: Target <1μs lookup time
    """
    cache = get_symbol_cache()
    return cache.get_symbol_by_id(symbol_id)


def cached_get_symbol_by_exchange_and_pair(
    exchange_id: int, 
    symbol_base: str, 
    symbol_quote: str
) -> Optional[DBSymbol]:
    """
    Get symbol by exchange ID and base/quote pair using cache.
    
    Args:
        exchange_id: Exchange database ID
        symbol_base: Base asset (e.g., 'BTC')
        symbol_quote: Quote asset (e.g., 'USDT')
        
    Returns:
        Symbol instance or None if not found
        
    Performance: Target <1μs lookup time
    """
    cache = get_symbol_cache()
    return cache.get_symbol_by_exchange_and_pair(exchange_id, symbol_base, symbol_quote)


def cached_get_symbol_by_exchange_and_string(
    exchange_id: int, 
    exchange_symbol: str
) -> Optional[DBSymbol]:
    """
    Get symbol by exchange ID and exchange-specific symbol string using cache.
    
    Args:
        exchange_id: Exchange database ID
        exchange_symbol: Exchange-specific symbol (e.g., 'BTCUSDT')
        
    Returns:
        Symbol instance or None if not found
        
    Performance: Target <1μs lookup time
    """
    cache = get_symbol_cache()
    return cache.get_symbol_by_exchange_and_string(exchange_id, exchange_symbol)


def cached_get_symbols_by_exchange(exchange_id: int) -> List[DBSymbol]:
    """
    Get all symbols for a specific exchange using cache.
    
    Args:
        exchange_id: Exchange database ID
        
    Returns:
        List of symbols for the exchange
        
    Performance: Target <10μs for typical exchange symbol counts
    """
    cache = get_symbol_cache()
    return cache.get_symbols_by_exchange(exchange_id)


def cached_get_all_symbols() -> List[DBSymbol]:
    """
    Get all cached symbols.
    
    Returns:
        List of all cached symbols
        
    Performance: Target <100μs for full symbol list
    """
    cache = get_symbol_cache()
    return cache.get_all_symbols()


# ================================================================================================
# Cached Exchange Lookups
# High-performance exchange resolution
# ================================================================================================

def cached_get_exchange_by_id(exchange_id: int) -> Optional[Exchange]:
    """
    Get exchange by database ID using cache.
    
    Args:
        exchange_id: Exchange database ID
        
    Returns:
        Exchange instance or None if not found
        
    Performance: Target <1μs lookup time
    """
    cache = get_symbol_cache()
    return cache.get_exchange_by_id(exchange_id)


def cached_get_exchange_by_enum(exchange_enum: ExchangeEnum) -> Optional[Exchange]:
    """
    Get exchange by ExchangeEnum using cache.
    
    Args:
        exchange_enum: ExchangeEnum value
        
    Returns:
        Exchange instance or None if not found
        
    Performance: Target <1μs lookup time
    """
    cache = get_symbol_cache()
    return cache.get_exchange_by_enum(str(exchange_enum.value))


def cached_get_exchange_by_enum_value(enum_value: str) -> Optional[Exchange]:
    """
    Get exchange by enum value string using cache.
    
    Args:
        enum_value: Exchange enum value (e.g., 'MEXC_SPOT')
        
    Returns:
        Exchange instance or None if not found
        
    Performance: Target <1μs lookup time
    """
    cache = get_symbol_cache()
    return cache.get_exchange_by_enum(enum_value)


# ================================================================================================
# High-Level Convenience Functions
# Optimized lookup patterns for common use cases
# ================================================================================================

def cached_resolve_symbol_for_exchange(
    exchange_enum: ExchangeEnum,
    symbol_base: str,
    symbol_quote: str
) -> Optional[DBSymbol]:
    """
    Resolve symbol using exchange enum and base/quote pair.
    
    Args:
        exchange_enum: ExchangeEnum value
        symbol_base: Base asset (e.g., 'BTC')
        symbol_quote: Quote asset (e.g., 'USDT')
        
    Returns:
        Symbol instance or None if not found
        
    Performance: Target <2μs lookup time (exchange + symbol lookup)
    """
    # First get exchange
    exchange = cached_get_exchange_by_enum(exchange_enum)
    if not exchange:
        return None
    
    # Then get symbol
    return cached_get_symbol_by_exchange_and_pair(exchange.id, symbol_base, symbol_quote)


def cached_resolve_symbol_by_exchange_string(
    exchange_enum: ExchangeEnum,
    exchange_symbol: str
) -> Optional[DBSymbol]:
    """
    Resolve symbol using exchange enum and exchange-specific symbol string.
    
    Args:
        exchange_enum: ExchangeEnum value
        exchange_symbol: Exchange-specific symbol (e.g., 'BTCUSDT')
        
    Returns:
        Symbol instance or None if not found
        
    Performance: Target <2μs lookup time (exchange + symbol lookup)
    """
    # First get exchange
    exchange = cached_get_exchange_by_enum(exchange_enum)
    if not exchange:
        return None
    
    # Then get symbol
    return cached_get_symbol_by_exchange_and_string(exchange.id, exchange_symbol)


def cached_get_symbols_for_exchange_enum(exchange_enum: ExchangeEnum) -> List[DBSymbol]:
    """
    Get all symbols for an exchange using ExchangeEnum.
    
    Args:
        exchange_enum: ExchangeEnum value
        
    Returns:
        List of symbols for the exchange, empty list if exchange not found
        
    Performance: Target <15μs for typical exchange symbol counts
    """
    # First get exchange
    exchange = cached_get_exchange_by_enum(exchange_enum)
    if not exchange:
        return []
    
    # Then get symbols
    return cached_get_symbols_by_exchange(exchange.id)


# ================================================================================================
# Cache Management and Monitoring
# ================================================================================================

def get_cache_stats() -> CacheStats:
    """
    Get cache performance statistics.
    
    Returns:
        CacheStats instance with current performance metrics
    """
    cache = get_symbol_cache()
    return cache.get_stats()


def reset_cache_stats() -> None:
    """Reset cache performance statistics."""
    cache = get_symbol_cache()
    cache.reset_stats()


async def refresh_symbol_cache() -> None:
    """
    Manually refresh symbol cache from database.
    
    This updates the cache with any new or modified symbols/exchanges.
    """
    cache = get_symbol_cache()
    await cache.refresh()


def is_cache_initialized() -> bool:
    """
    Check if symbol cache is initialized.
    
    Returns:
        True if cache is initialized and ready
    """
    try:
        get_symbol_cache()
        return True
    except RuntimeError:
        return False


# ================================================================================================
# Performance Validation Functions
# ================================================================================================

def validate_cache_performance() -> dict:
    """
    Validate cache performance against HFT targets.
    
    Returns:
        Dictionary with performance validation results
    """
    stats = get_cache_stats()
    
    # HFT performance targets
    TARGET_LOOKUP_TIME_US = 1.0  # <1μs average lookup time
    TARGET_HIT_RATIO = 0.95      # >95% hit ratio
    
    results = {
        'avg_lookup_time_us': stats.avg_lookup_time_us,
        'lookup_time_target': TARGET_LOOKUP_TIME_US,
        'lookup_time_meets_target': stats.avg_lookup_time_us <= TARGET_LOOKUP_TIME_US,
        
        'hit_ratio': stats.hit_ratio,
        'hit_ratio_target': TARGET_HIT_RATIO,
        'hit_ratio_meets_target': stats.hit_ratio >= TARGET_HIT_RATIO,
        
        'total_requests': stats.total_requests,
        'cache_size': stats.cache_size,
        'last_refresh': stats.last_refresh,
        
        'overall_performance_acceptable': (
            stats.avg_lookup_time_us <= TARGET_LOOKUP_TIME_US and
            stats.hit_ratio >= TARGET_HIT_RATIO
        )
    }
    
    return results


def log_cache_performance_summary() -> None:
    """Log a summary of cache performance for monitoring."""
    stats = get_cache_stats()
    validation = validate_cache_performance()
    
    logger.info("=== Symbol Cache Performance Summary ===")
    logger.info(f"Average lookup time: {stats.avg_lookup_time_us:.3f}μs (target: ≤{validation['lookup_time_target']}μs)")
    logger.info(f"Hit ratio: {stats.hit_ratio:.1%} (target: ≥{validation['hit_ratio_target']:.0%})")
    logger.info(f"Total requests: {stats.total_requests:,}")
    logger.info(f"Cache size: {stats.cache_size:,} symbols")
    logger.info(f"Last refresh: {stats.last_refresh}")
    logger.info(f"Performance target met: {validation['overall_performance_acceptable']}")
    logger.info("=" * 45)