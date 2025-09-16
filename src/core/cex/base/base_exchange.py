import time
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Set, Optional, Callable, Awaitable
from enum import Enum

from structs.exchange import ExchangeName, Symbol, OrderBook, SymbolsInfo
from core.config.structs import ExchangeConfig


class OrderbookUpdateType(Enum):
    """Type of orderbook update for downstream processing."""
    SNAPSHOT = "snapshot"
    DIFF = "diff"
    RECONNECT = "reconnect"


class BaseExchangeInterface(ABC):
    """
    Base exchange interface with common orderbook management logic.
    
    Handles:
    - Initial orderbook loading from REST API
    - Reconnection and state recovery
    - Orderbook state management
    - Update broadcasting to arbitrage layer
    """
    exchange_name: ExchangeName = "abstract"

    def __init__(self, config: ExchangeConfig):
        self._config = config
        self._initialized = False
        self.logger = logging.getLogger(f"{__name__}.{self.exchange_name}")
        
        # Common orderbook state management
        self._orderbooks: Dict[Symbol, OrderBook] = {}
        self._active_symbols: Set[Symbol] = set()
        self._symbols_info: Optional[SymbolsInfo] = None
        self._connection_healthy = False
        self._last_update_time = 0.0
        
        # Update handlers for arbitrage layer
        self._orderbook_update_handlers: List[
            Callable[[Symbol, OrderBook, OrderbookUpdateType], Awaitable[None]]
        ] = []
        
        # Reconnection management
        self._reconnect_task: Optional[asyncio.Task] = None
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10

    @abstractmethod
    async def close(self):
        """Close exchange connections and cleanup."""
        pass

    @abstractmethod
    async def initialize(self, symbols: List[Symbol] = None) -> None:
        """Initialize exchange with symbols."""
        if self._initialized:
            self.logger.warning("Exchange already initialized")
            return
        
        try:
            # Common initialization sequence
            await self._load_symbols_info()
            
            if symbols:
                await self._initialize_orderbooks_from_rest(symbols)
                self._active_symbols.update(symbols)
                
            await self._start_real_time_streaming(symbols or [])
            
            self._initialized = True
            self._connection_healthy = True
            self.logger.info(f"{self.exchange_name} initialized with {len(self._active_symbols)} symbols")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize {self.exchange_name}: {e}")
            raise

    # Abstract methods for exchange-specific implementation
    
    @abstractmethod
    async def _load_symbols_info(self) -> None:
        """Load symbol information from REST API."""
        pass
    
    @abstractmethod
    async def _get_orderbook_snapshot(self, symbol: Symbol) -> OrderBook:
        """Get orderbook snapshot from REST API."""
        pass
    
    @abstractmethod
    async def _start_real_time_streaming(self, symbols: List[Symbol]) -> None:
        """Start real-time WebSocket streaming for symbols."""
        pass
    
    @abstractmethod
    async def _stop_real_time_streaming(self) -> None:
        """Stop real-time WebSocket streaming."""
        pass

    # Common orderbook management methods
    
    async def _initialize_orderbooks_from_rest(self, symbols: List[Symbol]) -> None:
        """Initialize orderbooks with REST snapshots before starting streaming."""
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
        """Load and store orderbook snapshot for a symbol."""
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
        """Notify all registered handlers of orderbook updates."""
        if not self._orderbook_update_handlers:
            return
        
        # Execute all handlers concurrently
        tasks = [
            handler(symbol, orderbook, update_type)
            for handler in self._orderbook_update_handlers
        ]
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _handle_connection_lost(self) -> None:
        """Handle connection loss and attempt reconnection."""
        if not self._connection_healthy:
            return  # Already handling reconnection
        
        self._connection_healthy = False
        self.logger.warning(f"{self.exchange_name} connection lost, starting reconnection")
        
        # Cancel any existing reconnection task
        if self._reconnect_task:
            self._reconnect_task.cancel()
        
        # Start reconnection task
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        """Reconnection loop with exponential backoff."""
        self._reconnect_attempts = 0
        
        while self._reconnect_attempts < self._max_reconnect_attempts and not self._connection_healthy:
            try:
                self._reconnect_attempts += 1
                delay = min(2 ** self._reconnect_attempts, 60)  # Max 60 seconds
                
                self.logger.info(
                    f"Reconnection attempt {self._reconnect_attempts}/{self._max_reconnect_attempts} "
                    f"in {delay} seconds"
                )
                
                await asyncio.sleep(delay)
                
                # Stop existing streaming
                await self._stop_real_time_streaming()
                
                # Reload orderbook snapshots to ensure consistency
                if self._active_symbols:
                    await self._initialize_orderbooks_from_rest(list(self._active_symbols))
                
                # Restart streaming
                await self._start_real_time_streaming(list(self._active_symbols))
                
                # Notify arbitrage layer of reconnection
                for symbol, orderbook in self._orderbooks.items():
                    await self._notify_orderbook_update(symbol, orderbook, OrderbookUpdateType.RECONNECT)
                
                self._connection_healthy = True
                self._reconnect_attempts = 0
                self.logger.info(f"{self.exchange_name} reconnected successfully")
                break
                
            except Exception as e:
                self.logger.error(f"Reconnection attempt {self._reconnect_attempts} failed: {e}")
                continue
        
        if not self._connection_healthy:
            self.logger.error(f"{self.exchange_name} failed to reconnect after {self._max_reconnect_attempts} attempts")

    # Public interface methods
    
    def add_orderbook_update_handler(
        self, 
        handler: Callable[[Symbol, OrderBook, OrderbookUpdateType], Awaitable[None]]
    ) -> None:
        """Add handler for orderbook updates (for arbitrage layer)."""
        self._orderbook_update_handlers.append(handler)
    
    def remove_orderbook_update_handler(
        self, 
        handler: Callable[[Symbol, OrderBook, OrderbookUpdateType], Awaitable[None]]
    ) -> None:
        """Remove orderbook update handler."""
        if handler in self._orderbook_update_handlers:
            self._orderbook_update_handlers.remove(handler)

    @property
    def orderbooks(self) -> Dict[Symbol, OrderBook]:
        """Get current orderbook snapshots."""
        return self._orderbooks.copy()  # Copy for thread safety

    @property 
    def active_symbols(self) -> List[Symbol]:
        """Get list of actively tracked symbols."""
        return list(self._active_symbols)

    @property
    def symbols_info(self) -> Optional[SymbolsInfo]:
        """Get symbol information."""
        return self._symbols_info

    @property
    def is_connected(self) -> bool:
        """Check if exchange is connected and healthy."""
        return self._connection_healthy

    def get_orderbook_stats(self) -> Dict[str, any]:
        """Get orderbook statistics for monitoring."""
        return {
            'exchange': self.exchange_name,
            'active_symbols': len(self._active_symbols),
            'cached_orderbooks': len(self._orderbooks),
            'connection_healthy': self._connection_healthy,
            'last_update_time': self._last_update_time,
            'reconnect_attempts': self._reconnect_attempts
        }
