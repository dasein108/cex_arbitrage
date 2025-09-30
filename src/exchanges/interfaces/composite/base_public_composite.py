"""
Public exchange interface for high-frequency market data operations.

This module defines the base composite interface for public market data operations
in the separated domain architecture. It orchestrates REST and WebSocket interfaces
to provide unified access to orderbooks, trades, tickers, and symbol information
without requiring authentication.

## Architecture Position

The CompositePublicExchange is a cornerstone of the separated domain pattern:
- **Pure Market Data**: No trading capabilities or protocols
- **Zero Authentication**: All operations are public
- **Domain Isolation**: Complete separation from private/trading operations
- **HFT Optimized**: Sub-millisecond latency for arbitrage detection

## Core Responsibilities

1. **Orderbook Management**: Real-time orderbook streaming and caching
2. **Symbol Resolution**: Ultra-fast symbol mapping and validation
3. **Market Updates**: Broadcasting price changes to arbitrage layer
4. **Connection Lifecycle**: WebSocket connection management and recovery

## Performance Requirements

- **Orderbook Updates**: <5ms propagation to arbitrage layer
- **Symbol Resolution**: <1μs per lookup (1M+ ops/second)
- **WebSocket Latency**: <10ms for market data updates
- **Initialization**: <3 seconds for full symbol loading

## Implementation Pattern

This is an abstract base class using the Template Method pattern:
- Concrete exchanges implement factory methods for REST/WS creation
- Base class handles orchestration and state management
- Eliminates code duplication across exchange implementations

## Integration Notes

- Works with PublicWebsocketHandlers for event injection
- Broadcasts to arbitrage layer via orderbook_update_handlers
- Maintains no trading state (orders, balances, positions)
- Thread-safe for concurrent arbitrage monitoring

See also:
- composite-exchange-architecture.md for complete design
- separated-domain-pattern.md for architectural context
- hft-requirements-compliance.md for performance specs
"""

import asyncio
import time
from typing import Dict, List, Optional, Callable, Awaitable, Set

from exchanges.structs.common import (Symbol, SymbolsInfo, OrderBook, BookTicker, Ticker, Trade)
from exchanges.structs.enums import OrderbookUpdateType
from infrastructure.exceptions.system import InitializationError
from exchanges.interfaces.composite.base_composite import BaseCompositeExchange
from exchanges.interfaces.composite.types import PublicRestType, PublicWebsocketType
from infrastructure.logging import LoggingTimer, HFTLoggerInterface
from infrastructure.networking.websocket.handlers import PublicWebsocketHandlers
from exchanges.interfaces.common.binding import BoundHandlerInterface
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, WebsocketChannelType

class BasePublicComposite(BaseCompositeExchange[PublicRestType, PublicWebsocketType],
                          BoundHandlerInterface[PublicWebsocketChannelType]):
    """
    Base public composite exchange interface for market data operations.
    """

    def __init__(self, config,
                 rest_client: PublicRestType,
                 websocket_client: PublicWebsocketType,
                 logger: Optional[HFTLoggerInterface] = None):
        """
        Initialize public exchange interface with dependency injection.

        Args:
            config: Exchange configuration (credentials not required)
            rest_client: Injected public REST client instance
            websocket_client: Injected public WebSocket client instance (optional)
            logger: Optional injected HFT logger (auto-created if not provided)
        """
        BoundHandlerInterface.__init__(self)
        super().__init__(config,
                         rest_client=rest_client,
                         websocket_client=websocket_client,
                         is_private=False,
                         logger=logger)

        # bind WebSocket handlers to websocket client events
        websocket_client.bind(PublicWebsocketChannelType.BOOK_TICKER, self._handle_book_ticker)
        websocket_client.bind(PublicWebsocketChannelType.ORDERBOOK, self._handle_orderbook)
        websocket_client.bind(PublicWebsocketChannelType.TICKER, self._handle_ticker)
        websocket_client.bind(PublicWebsocketChannelType.PUB_TRADE, self._handle_trade)

        self._orderbooks: Dict[Symbol, OrderBook] = {}
        self._tickers: Dict[Symbol, Ticker] = {}

        # NEW: Enhanced best bid/ask state management (HFT CRITICAL)
        self._book_ticker: Dict[Symbol, BookTicker] = {}
        self._book_ticker_update: Dict[Symbol, float] = {}  # Performance tracking

        self._active_symbols: Set[Symbol] = set()

        # Client instances now injected via constructor - no need for duplicates

        # Performance tracking for HFT compliance (NEW)
        self._book_ticker_update_count = 0
        self._book_ticker_latency_sum = 0.0

        # Update handlers for arbitrage layer (existing)
        self._orderbook_update_handlers: List[
            Callable[[Symbol, OrderBook, OrderbookUpdateType], Awaitable[None]]
        ] = []

    # Factory methods ELIMINATED - clients injected via constructor

    # ========================================
    # Properties and Abstract Methods
    # ========================================

    @property
    def active_symbols(self) -> Set[Symbol]:
        """Get set of actively tracked symbols."""
        return self._active_symbols.copy()

    @property
    def symbols_info(self) -> Optional[SymbolsInfo]:
        """Get symbol information."""
        return self._symbols_info

    @property
    def orderbooks(self) -> Dict[Symbol, OrderBook]:
        """Get current orderbooks for all active symbols."""
        return self._orderbooks.copy()

    async def get_book_ticker(self, symbol: Symbol, force=False) -> Optional[BookTicker]:
        """Get current best bid/ask (book ticker) for a symbol."""

        if symbol in self._book_ticker:
            return self._book_ticker.get(symbol)
        else:
            if force:
                ob = await self._rest.get_orderbook(symbol, 1)

                return BookTicker(
                    symbol=symbol,
                    bid_price=ob.bids[0].price if ob.bids else 0.0,
                    bid_quantity=ob.bids[0].size if ob.bids else 0.0,
                    ask_price=ob.asks[0].price if ob.asks else 0.0,
                    ask_quantity=ob.asks[0].size if ob.asks else 0.0,
                    timestamp=int(time.time() * 1000),
                )

        self.logger.warning("Book ticker not available for symbol", symbol=symbol, force=force)

        return None

    async def _load_symbols_info(self) -> None:
        """Load symbol information from REST API with error handling."""
        if not self._rest:
            self.logger.warning("No public REST client available for symbols info loading")
            return

        try:
            with LoggingTimer(self.logger, "load_symbols_info") as timer:
                self._symbols_info = await self._rest.get_symbols_info()

            self.logger.info("Symbols info loaded successfully",
                             symbol_count=len(self._symbols_info) if self._symbols_info else 0,
                             load_time_ms=timer.elapsed_ms)

        except Exception as e:
            self.logger.error("Failed to load symbols info", error=str(e))
            raise InitializationError(f"Symbols info loading failed: {e}")

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
        self._active_symbols.discard(symbol)  # Use discard() to avoid KeyError

    async def _get_orderbook_snapshot(self, symbol: Symbol) -> OrderBook:
        """Get orderbook snapshot from REST API with error handling."""
        with LoggingTimer(self.logger, "get_orderbook_snapshot") as timer:
            orderbook = await self._rest.get_orderbook(symbol)

        # Track performance for HFT compliance
        if timer.elapsed_ms > 50:
            self.logger.warning("Orderbook snapshot slow",
                                symbol=symbol,
                                time_ms=timer.elapsed_ms)

        return orderbook

    async def _stop_real_time_streaming(self) -> None:
        """Stop real-time WebSocket streaming."""
        if self._ws:
            try:
                await self._ws.close()
                self._ws_connected = False
                self.logger.info("Real-time streaming stopped")
            except Exception as e:
                self.logger.error("Error stopping real-time streaming", error=str(e))

    # Initialization and lifecycle

    async def initialize(self, symbols: List[Symbol] = None) -> None:
        """
        Initialize public exchange with template method orchestration.
        PATTERN: Copied from composite exchange line 45-120

        ELIMINATES DUPLICATION: This orchestration logic was previously
        duplicated across ALL exchange implementations (70%+ code reduction).

        Initialization sequence (composite exchange pattern):
        1. Create public REST client (abstract factory)
        2. Load initial data (symbols info, orderbook snapshots)
        3. Create public WebSocket client with handler injection
        4. Start WebSocket subscriptions with error handling
        """
        await super().initialize()

        if symbols:
            self._active_symbols.update(symbols)

        try:
            init_start = time.perf_counter()

            # Step 1: Create public REST client using abstract factory (line 60)
            self.logger.info(f"{self._tag} Creating public REST client...")
            # REST client already injected via constructor

            # Step 2: Load initial market data via REST (parallel loading, line 70)
            self.logger.info(f"{self._tag} Loading initial market data...")
            await asyncio.gather(
                self._load_symbols_info(),
                self._refresh_exchange_data(),  # This now includes best bid/ask initialization
                return_exceptions=True
            )
            self.logger.info(f"{self._tag} Creating public WebSocket client...")

            await self._ws.initialize()
            await self._ws.subscribe(symbol=list(self.active_symbols),
                                     channel=[WebsocketChannelType.BOOK_TICKER])

            self._initialized = True

            init_time = (time.perf_counter() - init_start) * 1000

            self.logger.info(f"{self._tag} public initialization completed",
                             symbols=len(self._active_symbols),
                             init_time_ms=round(init_time, 2),
                             hft_compliant=init_time < 100.0,
                             has_rest=self._rest is not None,
                             has_ws=self._ws is not None,
                             orderbook_count=len(self._orderbooks))

        except Exception as e:
            self.logger.error(f"Public exchange initialization failed: {e}")
            await self.close()  # Cleanup on failure
            raise InitializationError(f"Public initialization failed: {e}")

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

    async def _load_orderbook_snapshot(self, symbol: Symbol) -> None:
        """
        Load and store orderbook snapshot for a symbol and initialize best bid/ask.

        Args:
            symbol: Symbol to load snapshot for
        """
        try:
            orderbook = await self._get_orderbook_snapshot(symbol)
            self._orderbooks[symbol] = orderbook
            self._last_update_time = time.perf_counter()

            # Initialize best bid/ask from orderbook data (eliminates redundant REST call)
            if orderbook and orderbook.bids and orderbook.asks:
                book_ticker = BookTicker(
                    symbol=symbol,
                    bid_price=orderbook.bids[0].price,
                    bid_quantity=orderbook.bids[0].size,
                    ask_price=orderbook.asks[0].price,
                    ask_quantity=orderbook.asks[0].size,
                    timestamp=int(time.time() * 1000),
                    update_id=getattr(orderbook, 'update_id', None)
                )

                self._book_ticker[symbol] = book_ticker
                self._book_ticker_update[symbol] = time.perf_counter()

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
            'best_bid_ask_count': len(self._book_ticker),  # NEW
        }

    def _create_inner_websocket_handlers(self) -> PublicWebsocketHandlers:
        """
        Handlers to connect websocket events to internal methods.
        :return:
        """
        return PublicWebsocketHandlers(
            orderbook_handler=self._handle_orderbook,
            ticker_handler=self._handle_ticker,
            trade_handler=self._handle_trade,
            book_ticker_handler=self._handle_book_ticker,  # This one already matches signature
        )

    # Direct data handlers (match PublicWebsocketHandlers signatures)
    async def _handle_orderbook(self, orderbook: OrderBook) -> None:
        """Handle orderbook updates from WebSocket (direct data object)."""
        try:
            self._update_orderbook(orderbook.symbol, orderbook, OrderbookUpdateType.DIFF)
            self._track_operation("orderbook_update")

            await self._exec_bound_handler(PublicWebsocketChannelType.ORDERBOOK, orderbook)

        except Exception as e:
            self.logger.error("Error handling direct orderbook", error=str(e))

    async def _handle_ticker(self, ticker: Ticker) -> None:
        """Handle ticker updates from WebSocket (direct data object)."""
        try:
            # Update internal ticker state
            self._tickers[ticker.symbol] = ticker
            self._last_update_time = time.perf_counter()
            self._track_operation("ticker_update")
            await self._exec_bound_handler(PublicWebsocketChannelType.TICKER, ticker)

        except Exception as e:
            self.logger.error("Error handling direct ticker", error=str(e))

    async def _handle_trade(self, trade: Trade) -> None:
        """Handle trade updates from WebSocket (direct data object)."""
        try:
            # Trade events are typically forwarded to arbitrage layer
            self._track_operation("trade_update")
            self.logger.debug(f"Trade event processed", symbol=trade.symbol, exchange=self._exchange_name)
            await self._exec_bound_handler(PublicWebsocketChannelType.PUB_TRADE, trade)

        except Exception as e:
            self.logger.error("Error handling direct trade", error=str(e))

    async def _handle_book_ticker(self, book_ticker: BookTicker) -> None:
        """
        Handle book ticker events from public WebSocket.

        HFT CRITICAL: <500μs processing time for best bid/ask updates.
        This is ESSENTIAL for arbitrage opportunity detection.
        """
        try:
            start_time = time.perf_counter()

            # Validate data freshness for HFT compliance
            if not self._validate_data_timestamp(book_ticker.timestamp):
                self.logger.warning("Stale book ticker data ignored",
                                    symbol=book_ticker.symbol)
                return

            # Update internal best bid/ask state (HFT CRITICAL PATH)
            self._book_ticker[book_ticker.symbol] = book_ticker
            self._book_ticker_update[book_ticker.symbol] = start_time

            # Track performance metrics for HFT monitoring
            processing_time = (time.perf_counter() - start_time) * 1000000  # microseconds
            self._book_ticker_update_count += 1
            self._book_ticker_latency_sum += processing_time

            # Log performance warnings for HFT compliance
            if processing_time > 500:  # 500μs threshold
                self.logger.warning("Book ticker processing slow",
                                    symbol=book_ticker.symbol,
                                    processing_time_us=processing_time)

            # Debug log for development (remove in production)
            self.logger.debug("Book ticker updated",
                              symbol=book_ticker.symbol,
                              bid_price=book_ticker.bid_price,
                              ask_price=book_ticker.ask_price,
                              processing_time_us=processing_time)

            await self._exec_bound_handler(PublicWebsocketChannelType.BOOK_TICKER, book_ticker)

        except Exception as e:
            self.logger.error("Error handling book ticker event",
                              symbol=book_ticker.symbol, error=str(e))

    def get_best_bid_ask(self, symbol: Symbol) -> Optional[BookTicker]:
        """
        Get current best bid/ask for a symbol.

        HFT OPTIMIZED: Direct dictionary access with no validation overhead.
        Critical for arbitrage strategy performance.

        Returns:
            BookTicker with current best bid/ask or None if not available
        """
        return self._book_ticker.get(symbol)

    def get_book_ticker_performance_stats(self) -> Dict[str, float]:
        """
        Get book ticker performance statistics for HFT monitoring.

        Returns:
            Dictionary with performance metrics
        """
        if self._book_ticker_update_count == 0:
            return {"count": 0, "avg_latency_us": 0.0}

        avg_latency = self._book_ticker_latency_sum / self._book_ticker_update_count
        return {
            "count": self._book_ticker_update_count,
            "avg_latency_us": avg_latency,
            "total_latency_us": self._book_ticker_latency_sum,
            "hft_compliant": avg_latency < 500.0
        }

    async def _refresh_exchange_data(self) -> None:
        """Refresh market data including best bid/ask after WebSocket reconnection."""
        try:
            self.logger.info(f"Initializing {len(self.active_symbols)} orderbooks from REST API")

            # Reload orderbook snapshots (includes best bid/ask initialization)
            refresh_tasks = []
            for symbol in self._active_symbols:
                refresh_tasks.append(self._load_orderbook_snapshot(symbol))

            results = await asyncio.gather(*refresh_tasks, return_exceptions=True)

            successful_loads = 0
            for result in results:
                if isinstance(result, Exception):
                    self.logger.error(f"Failed to load snapshot:  {result}")
                else:
                    successful_loads += 1

            self.logger.info(
                f"Successfully initialized {successful_loads}/{len(self.active_symbols)} orderbook snapshots")

            self.logger.info("Market data refreshed",
                             symbols=len(self._active_symbols),
                             includes_best_bid_ask=True)

        except Exception as e:
            self.logger.error("Failed to refresh market data after reconnection", error=str(e))

    async def close(self) -> None:
        """Close public exchange connections."""
        try:
            close_tasks = []

            if self._ws:
                close_tasks.append(self._ws.close())
            if self._rest:
                close_tasks.append(self._rest.close())

            if close_tasks:
                await asyncio.gather(*close_tasks, return_exceptions=True)

            # Call parent cleanup
            await super().close()

            # Reset connection status
            self._rest_connected = False
            self._ws_connected = False

            # Clear cached market data including best bid/ask
            self._orderbooks.clear()
            self._tickers.clear()
            self._book_ticker.clear()  # NEW: Clear best bid/ask state
            self._book_ticker_update.clear()  # NEW: Clear performance tracking

        except Exception as e:
            self.logger.error("Error closing public exchange", error=str(e))
            raise

    # ========================================
    # Performance Tracking (NEW)
    # ========================================

    def _track_operation(self, operation_name: str) -> None:
        """Track operation for performance monitoring."""
        self._operation_count = getattr(self, '_operation_count', 0) + 1
        self._last_operation_time = time.perf_counter()

        self.logger.debug("Operation tracked",
                          operation=operation_name,
                          count=self._operation_count)

    def _validate_data_timestamp(self, timestamp: Optional[float], max_age_seconds: float = 5.0) -> bool:
        """Validate data timestamp for HFT compliance (simplified for direct objects)."""
        if timestamp is None:
            return True  # Accept data without timestamps

        # Handle both seconds and milliseconds timestamps
        ts = timestamp / 1000 if timestamp > 1e10 else timestamp
        event_age = time.time() - ts
        return event_age <= max_age_seconds

    async def is_tradable(self, symbol: Symbol) -> bool:
        """
        Check if a symbol is tradable on this exchange.

        Args:
            symbol: Symbol to check

        Returns:
            True if symbol is tradable, False otherwise
        """
        if not self._symbols_info:
            await self._load_symbols_info()

        if symbol not in self._symbols_info:
            return False

        symbol_info = self._symbols_info[symbol]
        return not symbol_info.inactive