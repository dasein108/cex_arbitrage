"""
Cache Warming Service

Provides intelligent cache warming strategies for optimal HFT performance.
Ensures cache is pre-populated with frequently accessed symbols and exchanges.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from .cache import get_symbol_cache, initialize_symbol_cache
from .cache_operations import is_cache_initialized
from .operations import get_all_active_exchanges, get_all_active_symbols


logger = logging.getLogger(__name__)


class WarmingStrategy(Enum):
    """Cache warming strategies."""
    FULL = "full"                    # Warm entire cache
    PRIORITY_SYMBOLS = "priority"    # Warm high-priority symbols only
    EXCHANGE_SPECIFIC = "exchange"   # Warm specific exchanges
    INCREMENTAL = "incremental"      # Warm in stages


@dataclass
class WarmingConfig:
    """Configuration for cache warming."""
    strategy: WarmingStrategy = WarmingStrategy.FULL
    priority_exchanges: List[str] = None  # Exchange enum values
    priority_symbols: List[tuple] = None  # (exchange_id, base, quote) tuples
    batch_size: int = 100
    batch_delay_ms: int = 10
    max_warming_time_ms: int = 5000
    validate_after_warming: bool = True
    
    def __post_init__(self):
        if self.priority_exchanges is None:
            self.priority_exchanges = []
        if self.priority_symbols is None:
            self.priority_symbols = []


@dataclass
class WarmingResults:
    """Results from cache warming operation."""
    strategy_used: WarmingStrategy
    total_time_ms: float
    exchanges_loaded: int
    symbols_loaded: int
    batches_processed: int
    validation_passed: bool
    error_message: Optional[str] = None
    
    @property
    def success(self) -> bool:
        """Check if warming was successful."""
        return self.error_message is None and self.exchanges_loaded > 0


class CacheWarmingService:
    """
    Cache warming service for HFT symbol resolution.
    
    Provides intelligent warming strategies to ensure optimal cache performance
    from the first lookup operation.
    """
    
    def __init__(self):
        self._logger = logging.getLogger(f"{__name__}.CacheWarmingService")
        self._warming_in_progress = False
        self._last_warming_time: Optional[datetime] = None
    
    async def warm_cache(self, config: WarmingConfig = None) -> WarmingResults:
        """
        Warm the symbol cache using specified strategy.
        
        Args:
            config: Warming configuration, defaults to full warming
            
        Returns:
            WarmingResults with warming operation details
        """
        if config is None:
            config = WarmingConfig()
        
        if self._warming_in_progress:
            return WarmingResults(
                strategy_used=config.strategy,
                total_time_ms=0,
                exchanges_loaded=0,
                symbols_loaded=0,
                batches_processed=0,
                validation_passed=False,
                error_message="Warming already in progress"
            )
        
        self._warming_in_progress = True
        start_time = time.perf_counter()
        
        try:
            self._logger.info(f"Starting cache warming with strategy: {config.strategy.value}")
            
            # Initialize cache if not already done
            if not is_cache_initialized():
                await initialize_symbol_cache(auto_refresh_interval=300)
                
                # Cache initialization already loads everything, so we're done
                end_time = time.perf_counter()
                total_time_ms = (end_time - start_time) * 1000
                
                cache = get_symbol_cache()
                cache_stats = cache.get_stats()
                
                results = WarmingResults(
                    strategy_used=config.strategy,
                    total_time_ms=total_time_ms,
                    exchanges_loaded=len(cache._exchange_cache),
                    symbols_loaded=cache_stats.cache_size,
                    batches_processed=1,
                    validation_passed=True
                )
                
                self._last_warming_time = datetime.utcnow()
                self._logger.info(f"Cache warming completed in {total_time_ms:.2f}ms")
                return results
            
            # Cache is already initialized, apply specific warming strategy
            results = await self._apply_warming_strategy(config)
            
            # Validation if requested
            if config.validate_after_warming and results.success:
                results.validation_passed = await self._validate_cache_warming()
            
            end_time = time.perf_counter()
            results.total_time_ms = (end_time - start_time) * 1000
            
            self._last_warming_time = datetime.utcnow()
            self._logger.info(f"Cache warming completed in {results.total_time_ms:.2f}ms")
            
            return results
            
        except Exception as e:
            end_time = time.perf_counter()
            total_time_ms = (end_time - start_time) * 1000
            
            error_msg = f"Cache warming failed: {e}"
            self._logger.error(error_msg)
            
            return WarmingResults(
                strategy_used=config.strategy,
                total_time_ms=total_time_ms,
                exchanges_loaded=0,
                symbols_loaded=0,
                batches_processed=0,
                validation_passed=False,
                error_message=error_msg
            )
        
        finally:
            self._warming_in_progress = False
    
    async def _apply_warming_strategy(self, config: WarmingConfig) -> WarmingResults:
        """Apply specific warming strategy."""
        cache = get_symbol_cache()
        
        if config.strategy == WarmingStrategy.FULL:
            # Full cache refresh
            await cache.refresh()
            cache_stats = cache.get_stats()
            
            return WarmingResults(
                strategy_used=config.strategy,
                total_time_ms=0,  # Will be set by caller
                exchanges_loaded=len(cache._exchange_cache),
                symbols_loaded=cache_stats.cache_size,
                batches_processed=1,
                validation_passed=False  # Will be set by caller
            )
        
        elif config.strategy == WarmingStrategy.PRIORITY_SYMBOLS:
            return await self._warm_priority_symbols(config)
        
        elif config.strategy == WarmingStrategy.EXCHANGE_SPECIFIC:
            return await self._warm_exchange_specific(config)
        
        elif config.strategy == WarmingStrategy.INCREMENTAL:
            return await self._warm_incremental(config)
        
        else:
            raise ValueError(f"Unknown warming strategy: {config.strategy}")
    
    async def _warm_priority_symbols(self, config: WarmingConfig) -> WarmingResults:
        """Warm cache with priority symbols only."""
        cache = get_symbol_cache()
        
        # Access priority symbols to warm specific cache entries
        symbols_warmed = 0
        batches = 0
        
        for exchange_id, base, quote in config.priority_symbols:
            symbol = cache.get_symbol_by_exchange_and_pair(exchange_id, base, quote)
            if symbol:
                symbols_warmed += 1
            
            # Batch delay
            if symbols_warmed % config.batch_size == 0:
                batches += 1
                await asyncio.sleep(config.batch_delay_ms / 1000)
        
        return WarmingResults(
            strategy_used=config.strategy,
            total_time_ms=0,
            exchanges_loaded=len(cache._exchange_cache),
            symbols_loaded=symbols_warmed,
            batches_processed=batches,
            validation_passed=False
        )
    
    async def _warm_exchange_specific(self, config: WarmingConfig) -> WarmingResults:
        """Warm cache for specific exchanges only."""
        cache = get_symbol_cache()
        
        symbols_warmed = 0
        batches = 0
        exchanges_loaded = 0
        
        for exchange_enum in config.priority_exchanges:
            exchange = cache.get_exchange_by_enum(exchange_enum)
            if exchange:
                exchanges_loaded += 1
                
                # Warm all symbols for this exchange
                symbols = cache.get_symbols_by_exchange(exchange.id)
                symbols_warmed += len(symbols)
                
                # Batch delay
                if len(symbols) > 0:
                    batches += 1
                    await asyncio.sleep(config.batch_delay_ms / 1000)
        
        return WarmingResults(
            strategy_used=config.strategy,
            total_time_ms=0,
            exchanges_loaded=exchanges_loaded,
            symbols_loaded=symbols_warmed,
            batches_processed=batches,
            validation_passed=False
        )
    
    async def _warm_incremental(self, config: WarmingConfig) -> WarmingResults:
        """Warm cache incrementally in batches."""
        cache = get_symbol_cache()
        
        # Get all symbols and warm in batches
        all_symbols = cache.get_all_symbols()
        
        symbols_warmed = 0
        batches = 0
        
        for i in range(0, len(all_symbols), config.batch_size):
            batch = all_symbols[i:i + config.batch_size]
            
            # Access each symbol to warm cache
            for symbol in batch:
                cache.get_symbol_by_id(symbol.id)
                symbols_warmed += 1
            
            batches += 1
            await asyncio.sleep(config.batch_delay_ms / 1000)
            
            # Check time limit
            elapsed_ms = batches * config.batch_delay_ms
            if elapsed_ms >= config.max_warming_time_ms:
                self._logger.warning(f"Incremental warming stopped at time limit: {elapsed_ms}ms")
                break
        
        return WarmingResults(
            strategy_used=config.strategy,
            total_time_ms=0,
            exchanges_loaded=len(cache._exchange_cache),
            symbols_loaded=symbols_warmed,
            batches_processed=batches,
            validation_passed=False
        )
    
    async def _validate_cache_warming(self) -> bool:
        """Validate that cache warming was effective."""
        try:
            cache = get_symbol_cache()
            
            # Test basic functionality
            all_symbols = cache.get_all_symbols()
            if len(all_symbols) == 0:
                self._logger.error("Cache validation failed: no symbols loaded")
                return False
            
            # Test lookup performance with sample operations
            test_symbol = all_symbols[0]
            
            # Test different lookup patterns
            by_id = cache.get_symbol_by_id(test_symbol.id)
            by_pair = cache.get_symbol_by_exchange_and_pair(
                test_symbol.exchange_id,
                test_symbol.symbol_base,
                test_symbol.symbol_quote
            )
            by_string = cache.get_symbol_by_exchange_and_string(
                test_symbol.exchange_id,
                test_symbol.exchange_symbol
            )
            
            if not (by_id and by_pair and by_string):
                self._logger.error("Cache validation failed: lookup operations failed")
                return False
            
            # Check performance stats
            stats = cache.get_stats()
            if stats.total_requests == 0:
                self._logger.error("Cache validation failed: no requests recorded")
                return False
            
            self._logger.debug(f"Cache validation passed: {stats.total_requests} requests, {stats.hit_ratio:.1%} hit ratio")
            return True
            
        except Exception as e:
            self._logger.error(f"Cache validation failed: {e}")
            return False
    
    async def warm_for_exchange(self, exchange_enum: str) -> WarmingResults:
        """
        Warm cache for a specific exchange.
        
        Args:
            exchange_enum: Exchange enum value (e.g., 'MEXC_SPOT')
            
        Returns:
            WarmingResults for the exchange-specific warming
        """
        config = WarmingConfig(
            strategy=WarmingStrategy.EXCHANGE_SPECIFIC,
            priority_exchanges=[exchange_enum]
        )
        
        return await self.warm_cache(config)
    
    async def warm_priority_symbols(self, symbol_specs: List[tuple]) -> WarmingResults:
        """
        Warm cache for specific priority symbols.
        
        Args:
            symbol_specs: List of (exchange_id, base, quote) tuples
            
        Returns:
            WarmingResults for priority symbol warming
        """
        config = WarmingConfig(
            strategy=WarmingStrategy.PRIORITY_SYMBOLS,
            priority_symbols=symbol_specs
        )
        
        return await self.warm_cache(config)
    
    def is_warming_needed(self, max_age_minutes: int = 60) -> bool:
        """
        Check if cache warming is needed.
        
        Args:
            max_age_minutes: Maximum age before warming is needed
            
        Returns:
            True if warming is recommended
        """
        if not is_cache_initialized():
            return True
        
        if self._last_warming_time is None:
            return True
        
        age = datetime.utcnow() - self._last_warming_time
        return age > timedelta(minutes=max_age_minutes)
    
    @property
    def last_warming_time(self) -> Optional[datetime]:
        """Get the last warming time."""
        return self._last_warming_time
    
    @property
    def is_warming_in_progress(self) -> bool:
        """Check if warming is currently in progress."""
        return self._warming_in_progress


# Global cache warming service instance
_warming_service: Optional[CacheWarmingService] = None


def get_cache_warming_service() -> CacheWarmingService:
    """
    Get global cache warming service instance.
    
    Returns:
        CacheWarmingService singleton instance
    """
    global _warming_service
    if _warming_service is None:
        _warming_service = CacheWarmingService()
    return _warming_service


# Convenience functions
async def warm_symbol_cache(config: WarmingConfig = None) -> WarmingResults:
    """Warm symbol cache using specified configuration."""
    service = get_cache_warming_service()
    return await service.warm_cache(config)


async def warm_cache_for_exchange(exchange_enum: str) -> WarmingResults:
    """Warm cache for specific exchange."""
    service = get_cache_warming_service()
    return await service.warm_for_exchange(exchange_enum)


async def warm_cache_for_priority_symbols(symbol_specs: List[tuple]) -> WarmingResults:
    """Warm cache for specific priority symbols."""
    service = get_cache_warming_service()
    return await service.warm_priority_symbols(symbol_specs)


def is_cache_warming_needed(max_age_minutes: int = 60) -> bool:
    """Check if cache warming is needed."""
    service = get_cache_warming_service()
    return service.is_warming_needed(max_age_minutes)