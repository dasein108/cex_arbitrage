"""
Centralized Orderbook Management System

High-performance orderbook state management with HFT-optimized diff processing.
Coordinates between HFTOrderBook instances and OrderbookDiffProcessor implementations
to provide unified orderbook state management across multiple exchanges.

Key Features:
- Centralized orderbook state per symbol
- Exchange-agnostic diff processing
- Thread-safe concurrent access with copy-on-read semantics
- Performance monitoring and health checks
- Automatic stale data detection and cleanup
- Memory-efficient symbol lifecycle management

Performance Targets:
- <100μs per diff application
- <10μs per orderbook access (copy-on-read)
- O(1) symbol lookup
- <1MB memory overhead per active symbol
"""

import time
import asyncio
import logging
from typing import Dict, List, Optional, Set, Callable, Awaitable, Any
from dataclasses import dataclass

from core.structs.common import Symbol, OrderBook
from common.hft_orderbook import HFTOrderBook
from common.orderbook_diff_processor import (
    OrderbookDiffProcessor, 
    ParsedOrderbookUpdate,
    MexcOrderbookDiffProcessor,
    GateioOrderbookDiffProcessor
)


@dataclass
class OrderbookStats:
    """Statistics for orderbook monitoring and health checks."""
    symbol: Symbol
    last_update_time: float
    total_updates: int = 0
    diff_updates: int = 0
    snapshot_updates: int = 0
    parse_errors: int = 0
    processing_time_avg: float = 0.0
    processing_time_max: float = 0.0
    bid_levels: int = 0
    ask_levels: int = 0
    spread: Optional[float] = None
    mid_price: Optional[float] = None
    is_healthy: bool = True
    
    def update_processing_time(self, processing_time: float):
        """Update processing time statistics with exponential moving average."""
        if self.processing_time_avg == 0:
            self.processing_time_avg = processing_time
        else:
            # 10% weight for new measurement
            alpha = 0.1
            self.processing_time_avg = (
                alpha * processing_time + (1 - alpha) * self.processing_time_avg
            )
        
        if processing_time > self.processing_time_max:
            self.processing_time_max = processing_time


class OrderbookManager:
    """
    Centralized orderbook state management with HFT performance.
    
    Provides thread-safe, high-performance orderbook state management
    with support for multiple exchanges and concurrent access patterns.
    
    Architecture:
    - HFTOrderBook instances per symbol for efficient diff processing
    - Exchange-specific diff processors for message parsing
    - Copy-on-read semantics for thread safety
    - Performance monitoring and health checks
    - Automatic cleanup of inactive symbols
    """
    
    def __init__(
        self,
        stale_threshold_seconds: float = 30.0,
        max_processing_time_us: float = 100.0,
        enable_monitoring: bool = True
    ):
        """
        Initialize OrderbookManager.
        
        Args:
            stale_threshold_seconds: Time after which orderbook is considered stale
            max_processing_time_us: Maximum acceptable processing time in microseconds
            enable_monitoring: Enable performance monitoring and health checks
        """
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Configuration
        self.stale_threshold_seconds = stale_threshold_seconds
        self.max_processing_time_us = max_processing_time_us
        self.enable_monitoring = enable_monitoring
        
        # State management - O(1) symbol lookup
        self._orderbooks: Dict[Symbol, HFTOrderBook] = {}
        self._stats: Dict[Symbol, OrderbookStats] = {}
        self._active_symbols: Set[Symbol] = set()
        
        # Exchange-specific diff processors
        self._diff_processors: Dict[str, OrderbookDiffProcessor] = {
            'MEXC': MexcOrderbookDiffProcessor(),
            'Gate.io': GateioOrderbookDiffProcessor()
        }
        
        # Event handlers for orderbook updates
        self._update_handlers: List[Callable[[Symbol, OrderBook], Awaitable[None]]] = []
        
        # Performance tracking
        self._global_stats = {
            'total_symbols': 0,
            'active_symbols': 0,
            'total_updates': 0,
            'processing_errors': 0,
            'avg_processing_time_us': 0.0,
            'max_processing_time_us': 0.0,
            'stale_orderbooks': 0
        }
        
        # Cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        
        self.logger.info(
            f"OrderbookManager initialized with "
            f"stale_threshold={stale_threshold_seconds}s, "
            f"max_processing_time={max_processing_time_us}μs"
        )
    
    async def start(self) -> None:
        """Start the orderbook manager and background cleanup task."""
        if self._running:
            return
        
        self._running = True
        
        # Start background cleanup task
        if self.enable_monitoring:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        self.logger.info("OrderbookManager started")
    
    async def stop(self) -> None:
        """Stop the orderbook manager and cleanup resources."""
        if not self._running:
            return
        
        self._running = False
        
        # Stop cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Clear all state
        self._orderbooks.clear()
        self._stats.clear()
        self._active_symbols.clear()
        
        self.logger.info("OrderbookManager stopped")
    
    def add_symbol(self, symbol: Symbol) -> None:
        """
        Add symbol for orderbook tracking.
        
        Args:
            symbol: Symbol to track
        """
        if symbol not in self._orderbooks:
            # Create new HFTOrderbook instance
            self._orderbooks[symbol] = HFTOrderBook(symbol)
            
            # Initialize statistics
            self._stats[symbol] = OrderbookStats(
                symbol=symbol,
                last_update_time=time.perf_counter()
            )
            
            self.logger.info(f"Added symbol {symbol} to orderbook manager")
        
        self._active_symbols.add(symbol)
        self._global_stats['active_symbols'] = len(self._active_symbols)
        self._global_stats['total_symbols'] = len(self._orderbooks)
    
    def remove_symbol(self, symbol: Symbol) -> None:
        """
        Remove symbol from active tracking.
        
        Args:
            symbol: Symbol to remove from active tracking
        """
        self._active_symbols.discard(symbol)
        self._global_stats['active_symbols'] = len(self._active_symbols)
        
        self.logger.info(f"Removed symbol {symbol} from active tracking")
    
    async def process_diff_update(
        self,
        raw_message: Any,
        symbol: Symbol,
        exchange_name: str
    ) -> bool:
        """
        Process orderbook diff update with HFT performance.
        
        Args:
            raw_message: Raw message from exchange WebSocket
            symbol: Symbol for the update
            exchange_name: Name of the exchange (for processor selection)
            
        Returns:
            True if update was processed successfully, False otherwise
            
        Performance: Target <100μs including diff parsing and application
        """
        start_time = time.perf_counter()
        
        try:
            # Get exchange-specific diff processor
            diff_processor = self._diff_processors.get(exchange_name)
            if not diff_processor:
                self.logger.error(f"No diff processor for exchange: {exchange_name}")
                return False
            
            # Parse exchange-specific message format
            parsed_update = diff_processor.parse_diff_message(raw_message, symbol)
            if not parsed_update:
                return False
            
            # Ensure symbol is being tracked
            if symbol not in self._orderbooks:
                self.add_symbol(symbol)
            
            # Get orderbook instance
            orderbook = self._orderbooks[symbol]
            stats = self._stats[symbol]
            
            # Apply diff or snapshot
            if parsed_update.is_snapshot:
                # Full snapshot - convert to separate bid/ask lists
                await self._apply_snapshot(orderbook, parsed_update)
                stats.snapshot_updates += 1
            else:
                # Incremental diff
                orderbook.apply_diff(
                    bid_updates=parsed_update.bid_updates,
                    ask_updates=parsed_update.ask_updates,
                    timestamp=parsed_update.timestamp,
                    sequence=parsed_update.sequence
                )
                stats.diff_updates += 1
            
            # Update statistics
            processing_time = (time.perf_counter() - start_time) * 1_000_000  # μs
            self._update_stats(symbol, processing_time)
            
            # Trigger update handlers
            if self._update_handlers:
                # Create standard OrderBook for handlers
                standard_orderbook = orderbook.to_orderbook()
                await self._notify_handlers(symbol, standard_orderbook)
            
            # Performance validation
            if processing_time > self.max_processing_time_us:
                self.logger.warning(
                    f"Processing time {processing_time:.1f}μs exceeds "
                    f"HFT threshold {self.max_processing_time_us}μs for {symbol}"
                )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error processing diff update for {symbol}: {e}")
            
            # Update error statistics
            if symbol in self._stats:
                self._stats[symbol].parse_errors += 1
            self._global_stats['processing_errors'] += 1
            
            return False
    
    async def _apply_snapshot(
        self,
        orderbook: HFTOrderBook,
        parsed_update: ParsedOrderbookUpdate
    ) -> None:
        """Apply full snapshot to orderbook."""
        orderbook.apply_snapshot(
            bids=parsed_update.bid_updates,
            asks=parsed_update.ask_updates,
            timestamp=parsed_update.timestamp,
            sequence=parsed_update.sequence
        )
    
    def get_orderbook(self, symbol: Symbol, levels: int = 10) -> Optional[OrderBook]:
        """
        Get orderbook snapshot with copy-on-read semantics.
        
        Args:
            symbol: Symbol to get orderbook for
            levels: Number of price levels to include
            
        Returns:
            OrderBook snapshot or None if symbol not tracked
            
        Performance: Target <10μs (copy-on-read)
        Thread Safety: Copy-on-read ensures thread safety without locks
        """
        orderbook = self._orderbooks.get(symbol)
        if not orderbook:
            return None
        
        return orderbook.to_orderbook(levels)
    
    def get_all_orderbooks(self, levels: int = 10) -> Dict[Symbol, OrderBook]:
        """
        Get all tracked orderbooks with copy-on-read semantics.
        
        Args:
            levels: Number of price levels to include
            
        Returns:
            Dictionary of symbol -> OrderBook mappings
        """
        result = {}
        for symbol, orderbook in self._orderbooks.items():
            result[symbol] = orderbook.to_orderbook(levels)
        return result
    
    def add_update_handler(
        self, 
        handler: Callable[[Symbol, OrderBook], Awaitable[None]]
    ) -> None:
        """
        Add handler for orderbook update events.
        
        Args:
            handler: Async function to call on orderbook updates
        """
        self._update_handlers.append(handler)
    
    def remove_update_handler(
        self, 
        handler: Callable[[Symbol, OrderBook], Awaitable[None]]
    ) -> None:
        """
        Remove orderbook update handler.
        
        Args:
            handler: Handler to remove
        """
        if handler in self._update_handlers:
            self._update_handlers.remove(handler)
    
    def _update_stats(self, symbol: Symbol, processing_time_us: float) -> None:
        """Update performance statistics."""
        stats = self._stats[symbol]
        
        # Update symbol-specific stats
        stats.total_updates += 1
        stats.last_update_time = time.perf_counter()
        stats.update_processing_time(processing_time_us)
        
        # Update orderbook health info
        orderbook = self._orderbooks[symbol]
        stats.bid_levels = len(orderbook._bids)
        stats.ask_levels = len(orderbook._asks)
        stats.spread = orderbook.get_spread()
        stats.mid_price = orderbook.get_mid_price()
        stats.is_healthy = orderbook.is_valid()
        
        # Update global stats
        self._global_stats['total_updates'] += 1
        
        # Update global processing time averages
        if self._global_stats['avg_processing_time_us'] == 0:
            self._global_stats['avg_processing_time_us'] = processing_time_us
        else:
            alpha = 0.01  # 1% weight for new measurement
            self._global_stats['avg_processing_time_us'] = (
                alpha * processing_time_us + 
                (1 - alpha) * self._global_stats['avg_processing_time_us']
            )
        
        if processing_time_us > self._global_stats['max_processing_time_us']:
            self._global_stats['max_processing_time_us'] = processing_time_us
    
    async def _notify_handlers(self, symbol: Symbol, orderbook: OrderBook) -> None:
        """Notify all registered update handlers."""
        if not self._update_handlers:
            return
        
        # Execute all handlers concurrently
        tasks = [
            handler(symbol, orderbook) 
            for handler in self._update_handlers
        ]
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _cleanup_loop(self) -> None:
        """Background cleanup task for stale orderbooks."""
        while self._running:
            try:
                await asyncio.sleep(60)  # Run cleanup every minute
                await self._cleanup_stale_orderbooks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in cleanup loop: {e}")
    
    async def _cleanup_stale_orderbooks(self) -> None:
        """Clean up stale orderbooks that haven't been updated recently."""
        current_time = time.perf_counter()
        stale_symbols = []
        
        for symbol, stats in self._stats.items():
            age_seconds = current_time - stats.last_update_time
            if age_seconds > self.stale_threshold_seconds:
                stale_symbols.append(symbol)
        
        # Remove stale orderbooks
        for symbol in stale_symbols:
            if symbol not in self._active_symbols:  # Only remove inactive symbols
                self._orderbooks.pop(symbol, None)
                self._stats.pop(symbol, None)
                self.logger.info(f"Cleaned up stale orderbook for {symbol}")
        
        self._global_stats['stale_orderbooks'] = len(stale_symbols)
        self._global_stats['total_symbols'] = len(self._orderbooks)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics."""
        symbol_stats = {}
        for symbol, stats in self._stats.items():
            symbol_stats[str(symbol)] = {
                'total_updates': stats.total_updates,
                'diff_updates': stats.diff_updates,
                'snapshot_updates': stats.snapshot_updates,
                'parse_errors': stats.parse_errors,
                'processing_time_avg': stats.processing_time_avg,
                'processing_time_max': stats.processing_time_max,
                'bid_levels': stats.bid_levels,
                'ask_levels': stats.ask_levels,
                'spread': stats.spread,
                'mid_price': stats.mid_price,
                'is_healthy': stats.is_healthy,
                'last_update_age': time.perf_counter() - stats.last_update_time
            }
        
        return {
            'global': self._global_stats,
            'symbols': symbol_stats,
            'processors': {
                name: processor.get_processing_stats()
                for name, processor in self._diff_processors.items()
            }
        }
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get health summary for monitoring."""
        healthy_symbols = sum(1 for stats in self._stats.values() if stats.is_healthy)
        total_symbols = len(self._stats)
        
        return {
            'healthy_symbols': healthy_symbols,
            'total_symbols': total_symbols,
            'health_percentage': (healthy_symbols / total_symbols * 100) if total_symbols > 0 else 0,
            'avg_processing_time_us': self._global_stats['avg_processing_time_us'],
            'max_processing_time_us': self._global_stats['max_processing_time_us'],
            'hft_compliant': self._global_stats['avg_processing_time_us'] < self.max_processing_time_us,
            'total_updates': self._global_stats['total_updates'],
            'processing_errors': self._global_stats['processing_errors']
        }

    async def _apply_parsed_update(self, parsed_update: ParsedOrderbookUpdate) -> bool:
        """
        Apply a pre-parsed orderbook update directly with HFT performance.
        
        Args:
            parsed_update: Pre-parsed orderbook diff update
            
        Returns:
            True if update was processed successfully
            
        Performance: Target <50μs (bypass parsing overhead)
        """
        start_time = time.perf_counter()
        
        try:
            symbol = parsed_update.symbol
            
            # Ensure symbol is being tracked
            if symbol not in self._orderbooks:
                self.add_symbol(symbol)
            
            # Get orderbook instance
            orderbook = self._orderbooks[symbol]
            stats = self._stats[symbol]
            
            # Apply diff or snapshot
            if parsed_update.is_snapshot:
                # Full snapshot - convert to separate bid/ask lists
                orderbook.apply_snapshot(
                    bids=parsed_update.bid_updates,
                    asks=parsed_update.ask_updates,
                    timestamp=parsed_update.timestamp,
                    sequence=parsed_update.sequence
                )
                stats.snapshot_updates += 1
            else:
                # Incremental diff
                orderbook.apply_diff(
                    bid_updates=parsed_update.bid_updates,
                    ask_updates=parsed_update.ask_updates,
                    timestamp=parsed_update.timestamp,
                    sequence=parsed_update.sequence
                )
                stats.diff_updates += 1
            
            # Update statistics
            processing_time = (time.perf_counter() - start_time) * 1_000_000  # μs
            self._update_stats(symbol, processing_time)
            
            # Trigger update handlers
            if self._update_handlers:
                # Create standard OrderBook for handlers
                standard_orderbook = orderbook.to_orderbook()
                await self._notify_handlers(symbol, standard_orderbook)
            
            # Performance validation
            if processing_time > self.max_processing_time_us:
                self.logger.warning(
                    f"Direct processing time {processing_time:.1f}μs exceeds "
                    f"HFT threshold {self.max_processing_time_us}μs for {symbol}"
                )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error applying parsed update for {parsed_update.symbol}: {e}")
            
            # Update error statistics
            if parsed_update.symbol in self._stats:
                self._stats[parsed_update.symbol].parse_errors += 1
            self._global_stats['processing_errors'] += 1
            
            return False