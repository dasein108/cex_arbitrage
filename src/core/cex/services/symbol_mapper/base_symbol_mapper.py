"""
Base Symbol Mapper Interface

Provides abstract cex for exchange-specific symbol format conversion.
Eliminates singleton pattern in favor of factory-based instance management.

HFT Performance Requirements:
- Symbol conversion: <0.5μs per operation
- Cache hit rate: >98% for common trading pairs
- Memory bounded: <50MB for 10,000+ symbols
- Thread safe: Lock-free read operations

Architecture:
- Factory pattern for exchange-specific mapper creation
- Unified caching layer with O(1) lookup performance
- Interface segregation for clean exchange integration
"""

from abc import ABC, abstractmethod
from typing import Tuple, Dict
from structs.exchange import Symbol


class BaseSymbolMapper(ABC):
    """
    Abstract cex for exchange-specific symbol mapping.
    
    Provides contract for converting between unified Symbol structs
    and exchange-specific string formats with HFT-optimized performance.
    """
    
    def __init__(self, quote_assets: Tuple[str, ...]):
        """
        Initialize symbol mapper with exchange-specific quote assets.
        
        Args:
            quote_assets: Tuple of supported quote assets for this exchange
        """
        self._quote_assets = quote_assets
        self._symbol_to_pair_cache: Dict[Symbol, str] = {}
        self._pair_to_symbol_cache: Dict[str, Symbol] = {}
    
    @property
    def quote_assets(self) -> Tuple[str, ...]:
        """Get supported quote assets for this exchange."""
        return self._quote_assets
    
    @abstractmethod
    def _symbol_to_string(self, symbol: Symbol) -> str:
        """
        Convert Symbol to exchange-specific string format.
        
        Args:
            symbol: Unified Symbol struct
            
        Returns:
            Exchange-specific string format
            
        Note: This method defines exchange-specific formatting rules
        """
        pass
    
    @abstractmethod
    def _string_to_symbol(self, pair: str) -> Symbol:
        """
        Parse exchange-specific string to Symbol struct.
        
        Args:
            pair: Exchange-specific trading pair string
            
        Returns:
            Unified Symbol struct
            
        Note: This method implements exchange-specific parsing logic
        """
        pass
    
    def symbol_to_pair(self, symbol: Symbol) -> str:
        """
        Convert Symbol to exchange-specific pair string with caching.
        
        Args:
            symbol: Unified Symbol struct
            
        Returns:
            Exchange-specific pair string
            
        Performance: O(1) with cache hit, sub-microsecond target
        """
        if symbol in self._symbol_to_pair_cache:
            return self._symbol_to_pair_cache[symbol]
        
        # Cache miss - compute and store
        pair = self._symbol_to_string(symbol)
        self._cache_mapping(symbol, pair)
        
        return pair
    
    def pair_to_symbol(self, pair: str) -> Symbol:
        """
        Convert exchange-specific pair string to Symbol with caching.
        
        Args:
            pair: Exchange-specific trading pair string
            
        Returns:
            Unified Symbol struct
            
        Performance: O(1) with cache hit, sub-microsecond target
        """
        if pair in self._pair_to_symbol_cache:
            return self._pair_to_symbol_cache[pair]
        
        # Cache miss - parse and store
        symbol = self._string_to_symbol(pair)
        self._cache_mapping(symbol, pair)
        
        return symbol
    
    def _cache_mapping(self, symbol: Symbol, pair: str) -> None:
        """
        Cache bidirectional mapping between Symbol and pair string.
        
        Args:
            symbol: Unified Symbol struct
            pair: Exchange-specific pair string
        """
        self._symbol_to_pair_cache[symbol] = pair.upper()
        self._pair_to_symbol_cache[pair.upper()] = symbol
    
    def validate_symbol(self, symbol: Symbol) -> bool:
        """
        Validate if symbol is supported by this exchange.
        
        Args:
            symbol: Symbol to validate
            
        Returns:
            True if symbol is supported, False otherwise
        """
        return str(symbol.quote) in self._quote_assets
    
    def get_cache_stats(self) -> Dict[str, int]:
        """
        Get cache statistics for performance monitoring.
        
        Returns:
            Dictionary with cache size information
        """
        return {
            'symbol_to_pair_cache_size': len(self._symbol_to_pair_cache),
            'pair_to_symbol_cache_size': len(self._pair_to_symbol_cache),
            'supported_quote_assets': len(self._quote_assets)
        }
    
    def clear_cache(self) -> None:
        """Clear all cached mappings (for testing/memory management)."""
        self._symbol_to_pair_cache.clear()
        self._pair_to_symbol_cache.clear()