import asyncio
import time
from abc import abstractmethod
from typing import Dict, List, Set, Optional, Callable, Awaitable

from structs.exchange import (Symbol, SymbolsInfo,
                     OrderBook, OrderbookUpdateType)

from core.cex.base.base_exchange import BaseExchangeInterface
from core.cex.rest import PublicExchangeSpotRestInterface
from core.cex.websocket.ws_base import BaseExchangeWebsocketInterface

class BasePublicExchangeInterface(BaseExchangeInterface):
    """Base cex containing common methods for both public and private exchange operations"""
    @property
    @abstractmethod
    def orderbooks(self) -> Dict[Symbol, OrderBook]:
        """Abstract property to get the current orderbook"""
        pass

    @property
    def active_symbols(self) -> List[Symbol]:
        """Get list of actively tracked symbols."""
        return self._active_symbols

    @property
    def symbols_info(self) -> Optional[SymbolsInfo]:
        """Get symbol information."""
        return self._symbols_info

    @abstractmethod
    async def _load_symbols_info(self) -> None:
        """Load symbol information from REST API."""
        pass

    def __init__(self, config):
        super().__init__(f'{config.name}_public', config)
        self._orderbooks: Dict[Symbol, OrderBook] = {}
        self._symbols_info: SymbolsInfo = {}
        self._active_symbols: List[Symbol] = []

        # Update handlers for arbitrage layer
        self._orderbook_update_handlers: List[
            Callable[[Symbol, OrderBook, OrderbookUpdateType], Awaitable[None]]
        ] = []

        self._public_rest = MexcPublicSpotRest(config)
        self._websocket_client = MexcWebsocketPublic(
            config=self._config,
            orderbook_diff_handler=self._handle_raw_orderbook_message,
            state_change_handler=self._handle_connection_state_change
        )


    # Public interface methods

    async def initialize(self, symbols: List[Symbol] = None) -> None:
        """Initialize exchange with symbols"""
        await super().initialize()

        try:
            # Common initialization sequence
            await self._load_symbols_info()

            if symbols:
                await self._initialize_orderbooks_from_rest(symbols)
                self._active_symbols+=symbols

            await self._start_real_time_streaming(symbols or [])

            self._initialized = True
            self._connection_healthy = True
            self.logger.info(f"{self._tag} initialized with {len(self._active_symbols)} symbols")

        except Exception as e:
            self.logger.error(f"Failed to initialize {self._tag}: {e}")
            raise

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

    @abstractmethod
    async def add_symbol(self, symbol: Symbol) -> None:
        """Start symbol data streaming"""
        pass

    @abstractmethod
    async def remove_symbol(self, symbol: Symbol) -> None:
        """Stop symbol data streaming"""
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

    # Connection state change handlers (called by WebSocket client)


    def get_orderbook_stats(self) -> Dict[str, any]:
        """Get orderbook statistics for monitoring."""
        return {
            'exchange': self._config.name,
            'active_symbols': len(self._active_symbols),
            'cached_orderbooks': len(self._orderbooks),
            'connection_healthy': self.is_connected,
            'connection_state': self.connection_state.name,
            'last_update_time': self._last_update_time,
        }