"""
Database Cache Infrastructure

High-performance caching layer for HFT symbol resolution.
Provides sub-microsecond symbol lookups for frontend operations.
"""

import asyncio
import logging
import time
from typing import Dict, Optional, List, Tuple, Set
from dataclasses import dataclass
from datetime import datetime, timedelta
import threading
import weakref

from .models import Symbol as DBSymbol, Exchange
from .connection import get_db_manager


logger = logging.getLogger(__name__)


@dataclass
class CacheStats:
    """Cache performance statistics."""
    hits: int = 0
    misses: int = 0
    total_requests: int = 0
    avg_lookup_time_ns: float = 0.0
    last_refresh: Optional[datetime] = None
    cache_size: int = 0
    
    @property
    def hit_ratio(self) -> float:
        """Calculate cache hit ratio."""
        if self.total_requests == 0:
            return 0.0
        return self.hits / self.total_requests
    
    @property
    def avg_lookup_time_us(self) -> float:
        """Get average lookup time in microseconds."""
        return self.avg_lookup_time_ns / 1000.0


class SymbolCache:
    """
    High-performance symbol resolution cache.
    
    Optimized for HFT requirements with sub-microsecond lookup targets.
    Uses multiple indexing strategies for different lookup patterns.
    """
    
    def __init__(self):
        """
        Initialize symbol cache.
        
        Static mapping cache that loads symbols once and provides manual refresh
        when new symbols are added to exchanges.
        """
        self._logger = logging.getLogger(f"{__name__}.SymbolCache")
        
        # Primary caches - different indexing strategies for optimal performance
        self._id_cache: Dict[int, DBSymbol] = {}                           # symbol_id -> Symbol
        self._exchange_pair_cache: Dict[Tuple[int, str, str], DBSymbol] = {}  # (exchange_id, base, quote) -> Symbol
        self._exchange_string_cache: Dict[Tuple[int, str], DBSymbol] = {}     # (exchange_id, exchange_symbol) -> Symbol
        self._all_symbols_cache: List[DBSymbol] = []                       # All active symbols
        
        # Exchange cache for fast exchange lookups
        self._exchange_cache: Dict[int, Exchange] = {}                     # exchange_id -> Exchange
        self._exchange_enum_cache: Dict[str, Exchange] = {}                # enum_value -> Exchange
        
        # Performance tracking
        self._stats = CacheStats()
        self._lookup_times: List[float] = []  # Recent lookup times in nanoseconds
        self._max_lookup_samples = 1000
        
        # Thread safety
        self._lock = threading.RLock()
        
        self._last_refresh = datetime.utcnow()
        
        self._logger.info("SymbolCache initialized for static symbol mapping")
    
    async def initialize(self) -> None:
        """
        Initialize cache with data from database.
        
        This loads all symbols and exchanges once. Use manual refresh()
        when new symbols are added to exchanges.
        """
        start_time = time.perf_counter_ns()
        
        try:
            self._logger.info("Initializing symbol cache from database...")
            
            # Load exchanges first
            await self._load_exchanges()
            
            # Load symbols
            await self._load_symbols()
            
            init_time_ms = (time.perf_counter_ns() - start_time) / 1_000_000
            self._logger.info(f"Symbol cache initialized in {init_time_ms:.2f}ms")
            self._logger.info(f"Cached {len(self._all_symbols_cache)} symbols across {len(self._exchange_cache)} exchanges")
            
        except Exception as e:
            self._logger.error(f"Failed to initialize symbol cache: {e}")
            raise
    
    async def _load_exchanges(self) -> None:
        """Load all exchanges into cache."""
        from .operations import get_all_active_exchanges
        
        exchanges = await get_all_active_exchanges()
        
        with self._lock:
            self._exchange_cache.clear()
            self._exchange_enum_cache.clear()
            
            for exchange in exchanges:
                self._exchange_cache[exchange.id] = exchange
                self._exchange_enum_cache[exchange.enum_value] = exchange
        
        self._logger.debug(f"Loaded {len(exchanges)} exchanges into cache")
    
    async def _load_symbols(self) -> None:
        """Load all symbols into cache."""
        from .operations import get_all_active_symbols
        
        symbols = await get_all_active_symbols()
        
        with self._lock:
            # Clear existing caches
            self._id_cache.clear()
            self._exchange_pair_cache.clear()
            self._exchange_string_cache.clear()
            self._all_symbols_cache.clear()
            
            # Populate all cache indexes
            for symbol in symbols:
                # Primary ID cache
                self._id_cache[symbol.id] = symbol
                
                # Exchange + base/quote cache
                pair_key = (symbol.exchange_id, symbol.symbol_base.upper(), symbol.symbol_quote.upper())
                self._exchange_pair_cache[pair_key] = symbol
                
                # Exchange + exchange_symbol cache
                string_key = (symbol.exchange_id, symbol.exchange_symbol.upper())
                self._exchange_string_cache[string_key] = symbol
                
                # All symbols list
                self._all_symbols_cache.append(symbol)
            
            # Update cache stats
            self._stats.cache_size = len(symbols)
            self._stats.last_refresh = datetime.utcnow()
        
        self._logger.debug(f"Loaded {len(symbols)} symbols into cache indexes")
    
    def get_symbol_by_id(self, symbol_id: int) -> Optional[DBSymbol]:
        """
        Get symbol by database ID.
        
        Args:
            symbol_id: Symbol database ID
            
        Returns:
            Symbol instance or None if not found
        """
        start_time = time.perf_counter_ns()
        
        with self._lock:
            symbol = self._id_cache.get(symbol_id)
            
            # Update stats
            self._stats.total_requests += 1
            if symbol:
                self._stats.hits += 1
            else:
                self._stats.misses += 1
            
            self._record_lookup_time(time.perf_counter_ns() - start_time)
            
            return symbol
    
    def get_symbol_by_exchange_and_pair(
        self, 
        exchange_id: int, 
        symbol_base: str, 
        symbol_quote: str
    ) -> Optional[DBSymbol]:
        """
        Get symbol by exchange ID and base/quote pair.
        
        Args:
            exchange_id: Exchange database ID
            symbol_base: Base asset (e.g., 'BTC')
            symbol_quote: Quote asset (e.g., 'USDT')
            
        Returns:
            Symbol instance or None if not found
        """
        start_time = time.perf_counter_ns()
        
        with self._lock:
            pair_key = (exchange_id, symbol_base.upper(), symbol_quote.upper())
            symbol = self._exchange_pair_cache.get(pair_key)
            
            # Update stats
            self._stats.total_requests += 1
            if symbol:
                self._stats.hits += 1
            else:
                self._stats.misses += 1
            
            self._record_lookup_time(time.perf_counter_ns() - start_time)
            
            return symbol
    
    def get_symbol_by_exchange_and_string(
        self, 
        exchange_id: int, 
        exchange_symbol: str
    ) -> Optional[DBSymbol]:
        """
        Get symbol by exchange ID and exchange-specific symbol string.
        
        Args:
            exchange_id: Exchange database ID
            exchange_symbol: Exchange-specific symbol (e.g., 'BTCUSDT')
            
        Returns:
            Symbol instance or None if not found
        """
        start_time = time.perf_counter_ns()
        
        with self._lock:
            string_key = (exchange_id, exchange_symbol.upper())
            symbol = self._exchange_string_cache.get(string_key)
            
            # Update stats
            self._stats.total_requests += 1
            if symbol:
                self._stats.hits += 1
            else:
                self._stats.misses += 1
            
            self._record_lookup_time(time.perf_counter_ns() - start_time)
            
            return symbol
    
    def get_symbols_by_exchange(self, exchange_id: int) -> List[DBSymbol]:
        """
        Get all symbols for a specific exchange.
        
        Args:
            exchange_id: Exchange database ID
            
        Returns:
            List of symbols for the exchange
        """
        start_time = time.perf_counter_ns()
        
        with self._lock:
            symbols = [
                symbol for symbol in self._all_symbols_cache 
                if symbol.exchange_id == exchange_id
            ]
            
            self._stats.total_requests += 1
            self._stats.hits += 1  # Always a hit since we're filtering cached data
            
            self._record_lookup_time(time.perf_counter_ns() - start_time)
            
            return symbols
    
    def get_all_symbols(self) -> List[DBSymbol]:
        """
        Get all cached symbols.
        
        Returns:
            List of all cached symbols
        """
        start_time = time.perf_counter_ns()
        
        with self._lock:
            symbols = self._all_symbols_cache.copy()
            
            self._stats.total_requests += 1
            self._stats.hits += 1
            
            self._record_lookup_time(time.perf_counter_ns() - start_time)
            
            return symbols
    
    def get_exchange_by_id(self, exchange_id: int) -> Optional[Exchange]:
        """
        Get exchange by database ID.
        
        Args:
            exchange_id: Exchange database ID
            
        Returns:
            Exchange instance or None if not found
        """
        with self._lock:
            return self._exchange_cache.get(exchange_id)
    
    def get_exchange_by_enum(self, enum_value: str) -> Optional[Exchange]:
        """
        Get exchange by enum value.
        
        Args:
            enum_value: Exchange enum value (e.g., 'MEXC_SPOT')
            
        Returns:
            Exchange instance or None if not found
        """
        with self._lock:
            return self._exchange_enum_cache.get(enum_value)
    
    def _record_lookup_time(self, lookup_time_ns: float) -> None:
        """Record lookup time for performance tracking."""
        self._lookup_times.append(lookup_time_ns)
        
        # Keep only recent samples
        if len(self._lookup_times) > self._max_lookup_samples:
            self._lookup_times = self._lookup_times[-self._max_lookup_samples:]
        
        # Update average
        if self._lookup_times:
            self._stats.avg_lookup_time_ns = sum(self._lookup_times) / len(self._lookup_times)
    
    async def refresh(self) -> None:
        """
        Manual refresh cache from database.
        
        Call this method when new symbols are added to exchanges.
        This updates the cache with any new or modified symbols/exchanges.
        """
        start_time = time.perf_counter_ns()
        
        try:
            self._logger.info("Manually refreshing symbol cache from database...")
            
            old_symbol_count = len(self._all_symbols_cache)
            old_exchange_count = len(self._exchange_cache)
            
            await self._load_exchanges()
            await self._load_symbols()
            
            new_symbol_count = len(self._all_symbols_cache)
            new_exchange_count = len(self._exchange_cache)
            
            refresh_time_ms = (time.perf_counter_ns() - start_time) / 1_000_000
            self._logger.info(f"Symbol cache refreshed in {refresh_time_ms:.2f}ms")
            self._logger.info(f"Symbols: {old_symbol_count} → {new_symbol_count} (+{new_symbol_count - old_symbol_count})")
            self._logger.info(f"Exchanges: {old_exchange_count} → {new_exchange_count} (+{new_exchange_count - old_exchange_count})")
            
        except Exception as e:
            self._logger.error(f"Failed to refresh symbol cache: {e}")
            raise
    
    
    def get_stats(self) -> CacheStats:
        """
        Get cache performance statistics.
        
        Returns:
            CacheStats instance with current performance metrics
        """
        with self._lock:
            return CacheStats(
                hits=self._stats.hits,
                misses=self._stats.misses,
                total_requests=self._stats.total_requests,
                avg_lookup_time_ns=self._stats.avg_lookup_time_ns,
                last_refresh=self._stats.last_refresh,
                cache_size=self._stats.cache_size
            )
    
    def reset_stats(self) -> None:
        """Reset performance statistics."""
        with self._lock:
            self._stats.hits = 0
            self._stats.misses = 0
            self._stats.total_requests = 0
            self._lookup_times.clear()
            self._stats.avg_lookup_time_ns = 0.0
        
        self._logger.info("Cache statistics reset")
    
    async def close(self) -> None:
        """Clean up cache resources."""
        with self._lock:
            self._id_cache.clear()
            self._exchange_pair_cache.clear()
            self._exchange_string_cache.clear()
            self._all_symbols_cache.clear()
            self._exchange_cache.clear()
            self._exchange_enum_cache.clear()
            self._lookup_times.clear()
        
        self._logger.info("Symbol cache closed")


# Global cache instance
_symbol_cache: Optional[SymbolCache] = None


def get_symbol_cache() -> SymbolCache:
    """
    Get global symbol cache instance.
    
    Returns:
        SymbolCache singleton instance
        
    Raises:
        RuntimeError: If cache not initialized
    """
    global _symbol_cache
    if _symbol_cache is None:
        raise RuntimeError("Symbol cache not initialized. Call initialize_symbol_cache() first.")
    return _symbol_cache


async def initialize_symbol_cache() -> None:
    """
    Initialize global symbol cache.
    
    Static mapping cache for symbols and exchanges. Use refresh()
    method when new symbols are added to exchanges.
    """
    global _symbol_cache
    if _symbol_cache is not None:
        await _symbol_cache.close()
    
    _symbol_cache = SymbolCache()
    await _symbol_cache.initialize()


async def close_symbol_cache() -> None:
    """Close global symbol cache."""
    global _symbol_cache
    if _symbol_cache is not None:
        await _symbol_cache.close()
        _symbol_cache = None