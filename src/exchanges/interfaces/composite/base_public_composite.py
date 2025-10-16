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
from functools import lru_cache
from typing import Dict, List, Optional, Callable, Awaitable, Set, Any, Union

from exchanges.structs.common import (Symbol, SymbolsInfo, OrderBook, BookTicker, Ticker, Trade, FuturesTicker)
from exchanges.structs.enums import OrderbookUpdateType
from infrastructure.exceptions.system import InitializationError
from exchanges.interfaces.composite.base_composite import BaseCompositeExchange
from exchanges.interfaces.composite.types import PublicRestType, PublicWebsocketType
from infrastructure.logging import LoggingTimer, HFTLoggerInterface
from exchanges.interfaces.common.binding import BoundHandlerInterface
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, WebsocketChannelType
import cachetools.func

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

        # Bind WebSocket handlers to websocket client events for data processing
        websocket_client.bind(PublicWebsocketChannelType.BOOK_TICKER, self._handle_book_ticker)
        websocket_client.bind(PublicWebsocketChannelType.ORDERBOOK, self._handle_orderbook)
        websocket_client.bind(PublicWebsocketChannelType.TICKER, self._handle_ticker)
        websocket_client.bind(PublicWebsocketChannelType.PUB_TRADE, self._handle_trade)

        self._orderbooks: Dict[Symbol, OrderBook] = {}
        self._tickers: Dict[Symbol, Union[Ticker, FuturesTicker]] = {}

        # NEW: Enhanced best bid/ask state management (HFT CRITICAL)
        self.book_ticker: Dict[Symbol, BookTicker] = {}
        self._book_ticker_update: Dict[Symbol, float] = {}  # Performance tracking

        self._active_symbols: Set[Symbol] = set()

        # Client instances now injected via constructor - no need for duplicates

        # Performance tracking for HFT compliance (NEW)
        self._book_ticker_update_count = 0
        self._book_ticker_latency_sum = 0.0
        
        # Background ticker syncing (NEW)
        self._ticker_sync_task: Optional[asyncio.Task] = None
        self._ticker_sync_interval = 2 * 60 * 60  # 2 hours in seconds

    # Factory methods ELIMINATED - clients injected via constructor
    
    # ========================================
    # Type-Safe Channel Publishing (Phase 1)
    # ========================================
    
    def publish(self, channel: PublicWebsocketChannelType, data: Any) -> None:
        """
        Type-safe publish method for public channels using enum types.
        
        Args:
            channel: Public channel enum type
                   - PublicWebsocketChannelType.ORDERBOOK: Orderbook updates
                   - PublicWebsocketChannelType.PUB_TRADE: Trade updates  
                   - PublicWebsocketChannelType.BOOK_TICKER: Best bid/ask updates
                   - PublicWebsocketChannelType.TICKER: 24hr ticker statistics
            data: Event data to publish
        """
        # Convert enum to string for internal publishing
        if hasattr(self, '_exec_bound_handler'):
            try:
                import asyncio
                if asyncio.iscoroutinefunction(self._exec_bound_handler):
                    asyncio.create_task(self._exec_bound_handler(channel, data))
                else:
                    self._exec_bound_handler(channel, data)
            except Exception as e:
                if hasattr(self, 'logger'):
                    self.logger.error("Error publishing event",
                                    channel=channel,
                                    error_type=type(e).__name__,
                                    error_message=str(e))

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

    @cachetools.func.ttl_cache(ttl=60)
    def get_min_order_quote(self, symbol: Symbol) -> Optional[float]:
        """Get minimum order quote size for all active symbols."""
        # *** Hack to match min quote size ~ precise
        symbol_info = self._symbols_info.get(symbol)
        if symbol_info.min_quote_quantity:
            return symbol_info.min_quote_quantity

        return symbol_info.min_base_quantity * self.book_ticker[symbol].ask_price * 1.002

    @cachetools.func.ttl_cache(ttl=60)
    def get_min_base_quantity(self, symbol: Symbol) -> Optional[float]:
        """Get minimum order base size for all active symbols."""
        symbol_info = self._symbols_info.get(symbol)
        if symbol_info.min_base_quantity:
            return symbol_info.min_base_quantity

        return (symbol_info.min_quote_quantity / self.book_ticker[symbol].ask_price) * 1.002

    async def get_book_ticker(self, symbol: Symbol, force=False) -> Optional[BookTicker]:
        """Get current best bid/ask (book ticker) for a symbol."""

        if symbol in self.book_ticker and not force:
            return self.book_ticker.get(symbol)

        ob = await self._rest.get_orderbook(symbol, 1)

        return BookTicker(
            symbol=symbol,
            bid_price=ob.bids[0].price if ob.bids else 0.0,
            bid_quantity=ob.bids[0].size if ob.bids else 0.0,
            ask_price=ob.asks[0].price if ob.asks else 0.0,
            ask_quantity=ob.asks[0].size if ob.asks else 0.0,
            timestamp=int(time.time() * 1000),
        )


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

    # Initialization and lifecycle

    async def initialize(self, symbols: List[Symbol] = None,
                         channels: List[WebsocketChannelType]=None ) -> None:
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

        new_symbols = set()

        if symbols:
            new_symbols = set(symbols) - self._active_symbols
            self._active_symbols.update(symbols)

        if channels is None:
            channels = [WebsocketChannelType.BOOK_TICKER]

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

            if new_symbols:
                await self._ws.subscribe(symbol=list(self.active_symbols), channel=channels)

            # Start background ticker sync task
            if not self._ticker_sync_task or self._ticker_sync_task.done():
                self._ticker_sync_task = asyncio.create_task(self._background_ticker_sync())
                self.logger.info("Started background ticker sync task")

            init_time = (time.perf_counter() - init_start) * 1000

            self.logger.info(f"{self._tag} public initialization completed",
                             symbols=len(self._active_symbols),
                             init_time_ms=round(init_time, 2),
                             hft_compliant=init_time < 100.0,
                             has_rest=self._rest is not None,
                             has_ws=self._ws is not None,
                             orderbook_count=len(self._orderbooks),
                             ticker_count=len(self._tickers),
                             ticker_sync_active=self._ticker_sync_task is not None and not self._ticker_sync_task.done())

        except Exception as e:
            self.logger.error(f"Public exchange initialization failed: {e}")
            await self.close()  # Cleanup on failure
            raise InitializationError(f"Public initialization failed: {e}")

    # Orderbook update handlers for arbitrage layer

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

                self.book_ticker[symbol] = book_ticker
                self._book_ticker_update[symbol] = time.perf_counter()
                self.publish(PublicWebsocketChannelType.BOOK_TICKER, book_ticker)  # Publish to streams

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

    # Direct data handlers (match PublicWebsocketHandlers signatures)
    async def _handle_orderbook(self, orderbook: OrderBook) -> None:
        """Handle orderbook updates from WebSocket (direct data object)."""
        try:
            self._update_orderbook(orderbook.symbol, orderbook, OrderbookUpdateType.DIFF)
            self._track_operation("orderbook_update")


        except Exception as e:
            self.logger.error("Error handling direct orderbook", error=str(e))

    async def _handle_ticker(self, ticker: Union[Ticker, FuturesTicker]) -> None:
        """Handle ticker updates from WebSocket (direct data object)."""
        try:
            # hack for futures ticker
            if isinstance(ticker, FuturesTicker) and ticker.symbol in self._tickers:
                # Preserve funding time for futures tickers
                funding_time = self._tickers[ticker.symbol].funding_time
                self._tickers[ticker.symbol] = ticker
                self._tickers[ticker.symbol].funding_time = funding_time
            else:
                self._tickers[ticker.symbol] = ticker

            self._last_update_time = time.perf_counter()
            self._track_operation("ticker_update")

            self.publish(PublicWebsocketChannelType.TICKER, ticker)  # Publish to streams


        except Exception as e:
            self.logger.error("Error handling direct ticker", error=str(e))

    async def _handle_trade(self, trade: Trade) -> None:
        """Handle trade updates from WebSocket (direct data object)."""
        try:
            # Trade events are typically forwarded to arbitrage layer
            self._track_operation("trade_update")
            self.logger.debug(f"Trade event processed", symbol=trade.symbol, exchange=self._exchange_name)

            self.publish(PublicWebsocketChannelType.PUB_TRADE, trade)  # Publish to streams


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
                self.logger.debug("Stale book ticker data ignored",
                                    symbol=book_ticker.symbol)
                return

            # Update internal best bid/ask state (HFT CRITICAL PATH)
            self.book_ticker[book_ticker.symbol] = book_ticker
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

            self.publish(PublicWebsocketChannelType.BOOK_TICKER, book_ticker)  # Publish to streams


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
        return self.book_ticker.get(symbol)

    async def _sync_tickers(self) -> None:
        """Sync ticker data for all active symbols."""
        if not self._rest:
            return
            
        try:
            with LoggingTimer(self.logger, "ticker_sync") as timer:
                # Sync tickers for all active symbols
                # For futures exchanges that support FuturesTicker
                tickers = await self._rest.get_ticker_info()
                for symbol, ticker in tickers.items():
                    if symbol in self._active_symbols:
                        self._tickers[symbol] = ticker
                        self.publish("tickers", ticker)
                else:
                    self.logger.warning("REST client has no ticker methods available")
                            
            self.logger.info("Ticker sync completed",
                           symbols_synced=len([s for s in self._active_symbols if s in self._tickers]),
                           sync_time_ms=timer.elapsed_ms)
                           
        except Exception as e:
            self.logger.error("Failed to sync tickers", error=str(e))

    async def _background_ticker_sync(self) -> None:
        """Background task to sync tickers every 2 hours."""
        while True:
            try:
                await asyncio.sleep(self._ticker_sync_interval)
                await self._sync_tickers()
            except asyncio.CancelledError:
                self.logger.info("Background ticker sync task cancelled")
                break
            except Exception as e:
                self.logger.error("Error in background ticker sync", error=str(e))
                # Continue running even if sync fails

    async def _refresh_exchange_data(self) -> None:
        """Refresh market data including best bid/ask after WebSocket reconnection."""
        try:
            self.logger.info(f"Initializing {len(self.active_symbols)} orderbooks from REST API")

            # Reload orderbook snapshots (includes best bid/ask initialization)
            refresh_tasks = []
            for symbol in self._active_symbols:
                refresh_tasks.append(self._load_orderbook_snapshot(symbol))

            # Ticker refresh not required - real-time updates via WebSocket

            results = await asyncio.gather(*refresh_tasks, return_exceptions=True)

            successful_loads = 0
            for result in results:
                if isinstance(result, Exception):
                    self.logger.error(f"Failed to load snapshot:  {result}")
                else:
                    successful_loads += 1

            self.logger.info(
                f"Successfully initialized {successful_loads}/{len(self.active_symbols)} operations")

            self.logger.info("Market data refreshed",
                             symbols=len(self._active_symbols),
                             includes_best_bid_ask=True,
                             includes_tickers=True)

        except Exception as e:
            self.logger.error("Failed to refresh market data after reconnection", error=str(e))

    async def close(self) -> None:
        """Close public exchange connections."""
        try:
            close_tasks = []

            # Cancel background ticker sync task
            if self._ticker_sync_task and not self._ticker_sync_task.done():
                self._ticker_sync_task.cancel()
                try:
                    await self._ticker_sync_task
                except asyncio.CancelledError:
                    pass
                self.logger.info("Background ticker sync task cancelled")

            if self._ws:
                close_tasks.append(self._ws.close())
            if self._rest:
                close_tasks.append(self._rest.close())

            if close_tasks:
                await asyncio.gather(*close_tasks, return_exceptions=True)

            # Clear bound handlers
            self.clear_handlers()

            # Call parent cleanup
            await super().close()

            # Reset connection status
            self._rest_connected = False
            self._ws_connected = False

            # Clear cached market data including best bid/ask
            self._orderbooks.clear()
            self._tickers.clear()
            self.book_ticker.clear()  # NEW: Clear best bid/ask state
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