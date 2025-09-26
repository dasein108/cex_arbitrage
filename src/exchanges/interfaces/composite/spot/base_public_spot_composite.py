"""
Public exchange interface for market data operations.

This interface handles orderbook streaming, symbol management, and market data
without requiring authentication credentials.
"""

import asyncio
import time
from abc import abstractmethod
from typing import Dict, List, Optional, Callable, Awaitable, Set, Union

from exchanges.structs.common import (Symbol, SymbolsInfo, OrderBook, BookTicker, Ticker, Trade)
from exchanges.structs.enums import OrderbookUpdateType
from infrastructure.exceptions.system import InitializationError
from exchanges.interfaces.composite.base_composite import BaseCompositeExchange
from infrastructure.exceptions.exchange import ExchangeRestError
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType
from infrastructure.logging import LoggingTimer, HFTLoggerInterface
from infrastructure.networking.websocket.handlers import PublicWebsocketHandlers, PrivateWebsocketHandlers
from exchanges.interfaces.rest.spot.rest_spot_public import PublicSpotRest
from exchanges.interfaces.ws.spot.ws_spot_public import PublicSpotWebsocket


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

    def __init__(self, config, logger: Optional[HFTLoggerInterface] = None):
        """
        Initialize public exchange interface.
        
        Args:
            config: Exchange configuration (credentials not required)
            logger: Optional injected HFT logger (auto-created if not provided)
        """
        super().__init__(config, is_private=False, logger=logger)
        
        # Market data state (existing + enhanced)
        self._orderbooks: Dict[Symbol, OrderBook] = {}
        self._tickers: Dict[Symbol, Ticker] = {}
        
        # NEW: Enhanced best bid/ask state management (HFT CRITICAL)
        self._best_bid_ask: Dict[Symbol, BookTicker] = {}
        self._best_bid_ask_last_update: Dict[Symbol, float] = {}  # Performance tracking
        
        self._active_symbols: Set[Symbol] = set()
        
        # Client instances (NEW - managed by factory methods)
        self._public_rest: Optional[PublicSpotRest] = None
        self._public_ws: Optional[PublicSpotWebsocket] = None
        
        # Connection status tracking (NEW)
        self._public_rest_connected = False
        self._public_ws_connected = False
        
        # Performance tracking for HFT compliance (NEW)
        self._book_ticker_update_count = 0
        self._book_ticker_latency_sum = 0.0

        # Update handlers for arbitrage layer (existing)
        self._orderbook_update_handlers: List[
            Callable[[Symbol, OrderBook, OrderbookUpdateType], Awaitable[None]]
        ] = []

    # ========================================
    # Abstract Factory Methods (COPIED FROM composite exchange)
    # ========================================

    @abstractmethod
    async def _create_public_rest(self) -> PublicSpotRest:
        """
        Create exchange-specific public REST client.
        PATTERN: Copied from composite exchange line 120
        
        Subclasses must implement this factory method to return
        their specific REST client that extends PublicSpotRest.
        """
        pass

    @abstractmethod
    async def _create_public_ws_with_handlers(self, handlers: PublicWebsocketHandlers) -> Optional[PublicSpotWebsocket]:
        """
        Create exchange-specific public WebSocket client with handler objects.
        PATTERN: Copied from composite exchange line 130
        
        KEY INSIGHT: Handler injection eliminates manual setup in each exchange.
        
        Args:
            handlers: PublicWebsocketHandlers object with event handlers
            
        Returns:
            Optional[PublicSpotWebsocket]: WebSocket client or None if disabled
        """
        pass

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

    async def _load_symbols_info(self) -> None:
        """Load symbol information from REST API with error handling."""
        if not self._public_rest:
            self.logger.warning("No public REST client available for symbols info loading")
            return
            
        try:
            with LoggingTimer(self.logger, "load_symbols_info") as timer:
                self._symbols_info = await self._public_rest.get_symbols_info()

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
            orderbook = await self._public_rest.get_orderbook(symbol)

        # Track performance for HFT compliance
        if timer.elapsed_ms > 50:
            self.logger.warning("Orderbook snapshot slow",
                              symbol=symbol,
                              time_ms=timer.elapsed_ms)

        return orderbook
            

    async def _stop_real_time_streaming(self) -> None:
        """Stop real-time WebSocket streaming."""
        if self._public_ws:
            try:
                await self._public_ws.close()
                self._public_ws_connected = False
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
            self._public_rest = await self._create_public_rest()
            
            # Step 2: Load initial market data via REST (parallel loading, line 70)
            self.logger.info(f"{self._tag} Loading initial market data...")
            await asyncio.gather(
                self._load_symbols_info(),
                self._load_initial_orderbooks(),
                self._initialize_best_bid_ask_from_rest(),  # NEW: Initialize from REST before WebSocket
                return_exceptions=True
            )
            
            self.logger.info(f"{self._tag} Creating public WebSocket client...")

            await self._initialize_public_websocket()

            self._initialized = True

            init_time = (time.perf_counter() - init_start) * 1000
            
            self.logger.info(f"{self._tag} public initialization completed",
                            symbols=len(self._active_symbols),
                            init_time_ms=round(init_time, 2),
                            hft_compliant=init_time < 100.0,
                            has_rest=self._public_rest is not None,
                            has_ws=self._public_ws is not None,
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
            'best_bid_ask_count': len(self._best_bid_ask),  # NEW
        }

    # ========================================
    # Template Method Support Methods (NEW)
    # ========================================

    async def _load_initial_orderbooks(self) -> None:
        """Load initial orderbooks from REST API for all active symbols."""
        if self._active_symbols:
            await self._initialize_orderbooks_from_rest(list(self._active_symbols))

    async def _initialize_best_bid_ask_from_rest(self) -> None:
        """
        Initialize best bid/ask state from REST orderbook snapshots.
        
        HFT STRATEGY: Load initial state via REST, then maintain via WebSocket book ticker.
        This ensures arbitrage strategies have immediate access to pricing data.
        """
        if not self._public_rest:
            self.logger.warning("No public REST client available for best bid/ask initialization")
            return
            
        try:
            self.logger.info("Initializing best bid/ask from REST orderbook snapshots", 
                            symbol_count=len(self._active_symbols))
            
            initialization_tasks = []
            for symbol in self._active_symbols:
                initialization_tasks.append(self._initialize_symbol_best_bid_ask(symbol))
                
            # Process all symbols concurrently for speed
            results = await asyncio.gather(*initialization_tasks, return_exceptions=True)
            
            successful_inits = sum(1 for r in results if not isinstance(r, Exception))
            failed_inits = len(results) - successful_inits
            
            self.logger.info("Best bid/ask initialization completed",
                            successful=successful_inits,
                            failed=failed_inits,
                            total_symbols=len(self._active_symbols))
            
        except Exception as e:
            self.logger.error("Failed to initialize best bid/ask from REST", error=str(e))
            # Not critical - WebSocket will populate this data

    async def _initialize_symbol_best_bid_ask(self, symbol: Symbol) -> None:
        """Initialize best bid/ask for a single symbol from REST orderbook."""
        try:
            # Get orderbook snapshot from REST
            orderbook = await self._public_rest.get_orderbook(symbol, limit=1)  # Only need top level
            
            if orderbook and orderbook.bids and orderbook.asks:
                # Create BookTicker from orderbook top level
                book_ticker = BookTicker(
                    symbol=symbol,
                    bid_price=orderbook.bids[0].price,
                    bid_quantity=orderbook.bids[0].size,
                    ask_price=orderbook.asks[0].price,
                    ask_quantity=orderbook.asks[0].size,
                    timestamp=int(time.time() * 1000),
                    update_id=getattr(orderbook, 'update_id', None)
                )
                
                # Initialize state
                self._best_bid_ask[symbol] = book_ticker
                self._best_bid_ask_last_update[symbol] = time.perf_counter()
                
                self.logger.debug("Initialized best bid/ask from REST",
                                 symbol=symbol,
                                 bid_price=book_ticker.bid_price,
                                 ask_price=book_ticker.ask_price)
                                 
        except Exception as e:
            self.logger.warning("Failed to initialize best bid/ask for symbol",
                               symbol=symbol, error=str(e))
            # Continue with other symbols - not critical

    async def _get_websocket_handlers(self) -> PublicWebsocketHandlers:
        return PublicWebsocketHandlers(
                orderbook_handler=self._handle_orderbook,
                ticker_handler=self._handle_ticker,
                trades_handler=self._handle_trade,
                book_ticker_handler=self._handle_book_ticker,  # This one already matches signature
            )

    async def _initialize_public_websocket(self) -> None:
        """Initialize public WebSocket with constructor injection pattern including book ticker handler."""
        try:
            self.logger.debug("Initializing public WebSocket client")
            
            # Create handler objects for constructor injection using actual handler signatures
            # NOTE: Handler signatures expect direct data objects (OrderBook, BookTicker, etc.), not events
            # TODO: This will be refactored in websocket_refactoring.md to align properly
            public_handlers = self._get_websocket_handlers()
            
            # Use abstract factory method to create client
            self._public_ws = await self._create_public_ws_with_handlers(public_handlers)
            
            self._public_ws_connected = self._public_ws.is_connected

            await self._public_ws.initialize(symbols=list(self.active_symbols),
                                             channels=[PublicWebsocketChannelType.BOOK_TICKER])

            self.logger.info("Public WebSocket client initialized",
                            connected=self._public_ws_connected,
                            has_book_ticker_handler=True)
                            
        except Exception as e:
            self.logger.error("Public WebSocket initialization failed", error=str(e))
            raise InitializationError(f"Public WebSocket initialization failed: {e}")

    # ========================================
    # Event Handler Methods with Book Ticker Support (NEW)
    # ========================================
    
    # Direct data handlers (match PublicWebsocketHandlers signatures)
    async def _handle_orderbook(self, orderbook: OrderBook) -> None:
        """Handle orderbook updates from WebSocket (direct data object)."""
        try:
            self._update_orderbook(orderbook.symbol, orderbook, OrderbookUpdateType.DIFF)
            self._track_operation("orderbook_update")
        except Exception as e:
            self.logger.error("Error handling direct orderbook", error=str(e))

    async def _handle_ticker(self, ticker: Ticker) -> None:
        """Handle ticker updates from WebSocket (direct data object).""" 
        try:
            # Update internal ticker state
            self._tickers[ticker.symbol] = ticker
            self._last_update_time = time.perf_counter()
            self._track_operation("ticker_update")
        except Exception as e:
            self.logger.error("Error handling direct ticker", error=str(e))

    async def _handle_trade(self, trade: Trade) -> None:
        """Handle trade updates from WebSocket (direct data object)."""
        try:
            # Trade events are typically forwarded to arbitrage layer
            self._track_operation("trade_update")
            self.logger.debug(f"Trade event processed", symbol=trade.symbol, exchange=self._exchange_name)
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
            self._best_bid_ask[book_ticker.symbol] = book_ticker
            self._best_bid_ask_last_update[book_ticker.symbol] = start_time
            
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
        return self._best_bid_ask.get(symbol)

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

    # ========================================
    # Connection Management and Recovery (NEW)
    # ========================================

    async def _refresh_market_data_after_reconnection(self) -> None:
        """Refresh market data including best bid/ask after WebSocket reconnection."""
        try:
            # Reload both orderbook snapshots AND best bid/ask state
            refresh_tasks = []
            for symbol in self._active_symbols:
                refresh_tasks.append(self._load_orderbook_snapshot(symbol))
                refresh_tasks.append(self._initialize_symbol_best_bid_ask(symbol))  # NEW: Refresh best bid/ask
                
            await asyncio.gather(*refresh_tasks, return_exceptions=True)
            
            self.logger.info("Market data refreshed after reconnection",
                            symbols=len(self._active_symbols),
                            includes_best_bid_ask=True)
            
        except Exception as e:
            self.logger.error("Failed to refresh market data after reconnection", error=str(e))

    async def close(self) -> None:
        """Close public exchange connections."""
        try:
            close_tasks = []
            
            if self._public_ws:
                close_tasks.append(self._public_ws.close())
            if self._public_rest:
                close_tasks.append(self._public_rest.close())
                
            if close_tasks:
                await asyncio.gather(*close_tasks, return_exceptions=True)
                
            # Call parent cleanup
            await super().close()
            
            # Reset connection status
            self._public_rest_connected = False
            self._public_ws_connected = False
            
            # Clear cached market data including best bid/ask
            self._orderbooks.clear()
            self._tickers.clear()
            self._best_bid_ask.clear()  # NEW: Clear best bid/ask state
            self._best_bid_ask_last_update.clear()  # NEW: Clear performance tracking
            
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