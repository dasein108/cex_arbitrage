"""
Public exchange interface for market data operations.

This interface handles orderbook streaming, symbol management, and market data
without requiring authentication credentials.
"""

import asyncio
import time
from abc import abstractmethod
from typing import Dict, List, Optional, Callable, Awaitable, Set

from exchanges.structs.common import (Symbol, SymbolsInfo, OrderBook)
from ...structs.enums import OrderbookUpdateType
from .base_exchange import BaseCompositeExchange


class CompositePublicExchange(BaseCompositeExchange):
    """
    Base interface for public exchange operations (market data only).
    
    Handles:
    - Orderbook streaming and management
    - Symbol information loading
    - Real-time market data via WebSocket
    - Orderbook update broadcasting to arbitrage layer
    - Connection state management for market data streams
    
    This interface does not require authentication and focuses solely on
    public market data operations.
    """

    def __init__(self, config):
        """
        Initialize public exchange interface.
        
        Args:
            config: Exchange configuration (credentials not required)
        """
        super().__init__(config, is_private=False)
        
        # Market data state
        self._orderbooks: Dict[Symbol, OrderBook] = {}
        self._active_symbols: Set[Symbol] = []

        # Update handlers for arbitrage layer
        self._orderbook_update_handlers: List[
            Callable[[Symbol, OrderBook, OrderbookUpdateType], Awaitable[None]]
        ] = []

    # Abstract properties and methods

    @property
    def active_symbols(self) -> List[Symbol]:
        """Get list of actively tracked symbols."""
        return self._active_symbols.copy()

    @property
    def symbols_info(self) -> Optional[SymbolsInfo]:
        """Get symbol information."""
        return self._symbols_info

    @property
    @abstractmethod
    def orderbooks(self) -> Dict[Symbol, OrderBook]:
        """Get current orderbooks for all active symbols."""
        pass

    @abstractmethod
    async def _load_symbols_info(self) -> None:
        """Load symbol information from REST API."""
        pass

    async def add_symbol(self, symbol: Symbol) -> None:
        """
        Start streaming data for a new symbol.
        
        Args:
            symbol: Symbol to start tracking
        """
        self._active_symbols.add(symbol)

    async def remove_symbol(self, symbol: Symbol) -> None:
        """
        Stop streaming data for a symbol.
        
        Args:
            symbol: Symbol to stop tracking
        """
        self.active_symbols.remove(symbol)

    @abstractmethod
    async def _get_orderbook_snapshot(self, symbol: Symbol) -> OrderBook:
        """
        Get orderbook snapshot from REST API.
        
        Args:
            symbol: Symbol to get orderbook for
            
        Returns:
            Current orderbook snapshot
        """
        pass

    @abstractmethod
    async def _start_real_time_streaming(self, symbols: List[Symbol]) -> None:
        """
        Start real-time WebSocket streaming for symbols.
        
        Args:
            symbols: List of symbols to stream
        """
        pass

    @abstractmethod
    async def _stop_real_time_streaming(self) -> None:
        """Stop real-time WebSocket streaming."""
        pass

    # Initialization and lifecycle

    async def initialize(self, symbols: List[Symbol] = None) -> None:
        """
        Initialize public exchange with symbols.
        
        Args:
            symbols: Optional list of symbols to immediately start tracking
        """
        await super().initialize()

        try:
            # Common initialization sequence
            await self._load_symbols_info()

            if symbols:
                await self._initialize_orderbooks_from_rest(symbols)
                self._active_symbols.update(symbols)

            await self._start_real_time_streaming(symbols or [])

            self._initialized = True
            self._connection_healthy = True
            self.logger.info(f"{self._tag} initialized with {len(self._active_symbols)} symbols")

        except Exception as e:
            self.logger.error(f"Failed to initialize {self._tag}: {e}")
            raise

    # Orderbook update handlers for arbitrage layer

    def add_orderbook_update_handler(
            self,
            handler: Callable[[Symbol, OrderBook, OrderbookUpdateType], Awaitable[None]]
    ) -> None:
        """
        Add handler for orderbook updates (for arbitrage layer).
        
        Args:
            handler: Async function to call on orderbook updates
        """
        self._orderbook_update_handlers.append(handler)

    def remove_orderbook_update_handler(
            self,
            handler: Callable[[Symbol, OrderBook, OrderbookUpdateType], Awaitable[None]]
    ) -> None:
        """
        Remove orderbook update handler.
        
        Args:
            handler: Handler function to remove
        """
        if handler in self._orderbook_update_handlers:
            self._orderbook_update_handlers.remove(handler)

    # Orderbook management implementation

    async def _initialize_orderbooks_from_rest(self, symbols: List[Symbol]) -> None:
        """
        Initialize orderbooks with REST snapshots before starting streaming.
        
        Args:
            symbols: Symbols to initialize orderbooks for
        """
        self.logger.info(f"Initializing {len(symbols)} orderbooks from REST API")

        # Load snapshots concurrently for better performance
        tasks = []
        for symbol in symbols:
            task = self._load_orderbook_snapshot(symbol)
            tasks.append(task)

        # Wait for all snapshots to load
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successful_loads = 0
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error(f"Failed to load snapshot for {symbols[i]}: {result}")
            else:
                successful_loads += 1

        self.logger.info(f"Successfully initialized {successful_loads}/{len(symbols)} orderbook snapshots")

    async def _load_orderbook_snapshot(self, symbol: Symbol) -> None:
        """
        Load and store orderbook snapshot for a symbol.
        
        Args:
            symbol: Symbol to load snapshot for
        """
        try:
            orderbook = await self._get_orderbook_snapshot(symbol)
            self._orderbooks[symbol] = orderbook
            self._last_update_time = time.perf_counter()

            # Notify arbitrage layer of initial snapshot
            await self._notify_orderbook_update(symbol, orderbook, OrderbookUpdateType.SNAPSHOT)

        except Exception as e:
            self.logger.error(f"Failed to load orderbook snapshot for {symbol}: {e}")
            raise

    def _update_orderbook(
            self,
            symbol: Symbol,
            orderbook: OrderBook,
            update_type: OrderbookUpdateType = OrderbookUpdateType.DIFF
    ) -> None:
        """
        Update internal orderbook state and notify arbitrage layer.

        Called by exchange-specific implementations when they receive updates.
        
        Args:
            symbol: Symbol that was updated
            orderbook: New orderbook state
            update_type: Type of update (snapshot or diff)
        """
        # Update internal state
        self._orderbooks[symbol] = orderbook
        self._last_update_time = time.perf_counter()
        self._connection_healthy = True

        # Notify arbitrage layer asynchronously
        asyncio.create_task(self._notify_orderbook_update(symbol, orderbook, update_type))

    async def _notify_orderbook_update(
            self,
            symbol: Symbol,
            orderbook: OrderBook,
            update_type: OrderbookUpdateType
    ) -> None:
        """
        Notify all registered handlers of orderbook updates.
        
        Args:
            symbol: Symbol that was updated
            orderbook: Updated orderbook
            update_type: Type of update
        """
        if not self._orderbook_update_handlers:
            return

        # Execute all handlers concurrently
        tasks = [
            handler(symbol, orderbook, update_type)
            for handler in self._orderbook_update_handlers
        ]

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # Monitoring and diagnostics

    def get_orderbook_stats(self) -> Dict[str, any]:
        """
        Get orderbook statistics for monitoring.
        
        Returns:
            Dictionary with orderbook and connection statistics
        """
        return {
            'exchange': self._config.name,
            'active_symbols': len(self._active_symbols),
            'cached_orderbooks': len(self._orderbooks),
            'connection_healthy': self.is_connected,
            'connection_state': self.connection_state.name,
            'last_update_time': self._last_update_time,
        }