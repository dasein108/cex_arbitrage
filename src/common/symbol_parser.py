"""
Simple symbol parsing for multi-exchange cryptocurrency pairs.

This module provides straightforward symbol parsing that works across multiple exchanges
without pre-computed assumptions. Optimized for simplicity and multi-exchange compatibility.

Performance characteristics:
- Simple suffix matching algorithm
- No pre-computed exchange-specific symbols
- Works with any exchange symbol format
- Initialization-time performance (not critical path)
"""

from typing import Dict, Optional, Tuple, Set
from functools import lru_cache
from structs.exchange import Symbol

# Common quote assets in priority order (longest first to avoid conflicts)
# This list works across most major exchanges
COMMON_QUOTE_ASSETS = [
    'USDT', 'USDC', 'BUSD', 'TUSD',  # 4-char stablecoins
    # 'BTC', 'ETH', 'BNB', 'USD', 'EUR', 'GBP', 'AUD',  # 3-char assets
]


@lru_cache(maxsize=1000)
def parse_symbol_simple(symbol_str: str) -> Symbol:
    """
    Simple symbol parsing for multi-exchange compatibility.
    
    Uses LRU cache for performance but keeps logic simple and exchange-agnostic.
    This approach works across multiple exchanges without pre-computed assumptions.
    
    Args:
        symbol_str: Trading pair string (e.g., "BTCUSDT")
        
    Returns:
        Parsed Symbol object
        
    Performance:
        - Simple suffix matching algorithm
        - LRU cache for repeated symbols
        - Works with any exchange format
        - No complex pre-computations
    """
    # Normalize to uppercase
    symbol_upper = symbol_str.upper().strip()
    
    if len(symbol_upper) < 3:
        # Too short to be valid, default to USDT quote
        return Symbol(base=symbol_upper, quote='USDT', is_futures=False)
    
    # Simple suffix matching - try common quote assets
    for quote_asset in COMMON_QUOTE_ASSETS:
        if symbol_upper.endswith(quote_asset):
            base = symbol_upper[:-len(quote_asset)]
            if base:  # Ensure non-empty base
                return Symbol(base=base, quote=quote_asset, is_futures=False)
    
    # Fallback: Split roughly in middle if no quote match found
    mid = len(symbol_upper) // 2
    base = symbol_upper[:mid] if mid > 0 else symbol_upper
    quote = symbol_upper[mid:] if mid < len(symbol_upper) else 'USDT'
    
    return Symbol(base=base, quote=quote, is_futures=False)


def parse_symbol_fast(symbol_str: str) -> Symbol:
    """
    Fast symbol parsing with LRU caching for multi-exchange compatibility.
    
    Args:
        symbol_str: Trading pair string (e.g., "BTCUSDT")
        
    Returns:
        Parsed Symbol object
        
    Performance:
        - Simple algorithm with LRU caching
        - Works across multiple exchanges
        - No pre-computed exchange-specific data
        - Initialization-time performance (not critical)
    """
    return parse_symbol_simple(symbol_str)


def get_parser_cache_info():
    """Get LRU cache statistics for symbol parser."""
    return parse_symbol_simple.cache_info()


def clear_parser_cache() -> None:
    """Clear the symbol parser LRU cache."""
    parse_symbol_simple.cache_clear()