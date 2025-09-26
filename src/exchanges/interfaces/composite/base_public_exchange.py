"""
Public exchange interface for market data operations.

This interface handles orderbook streaming, symbol management, and market data
without requiring authentication credentials.
"""

import asyncio
import time
from abc import abstractmethod
from typing import Dict, List, Optional, Callable, Awaitable, Set

from exchanges.structs.common import (Symbol, SymbolsInfo, OrderBook, OrderBookEntry, Side, BookTicker, Ticker)
from exchanges.structs.enums import OrderbookUpdateType
from .base_exchange import BaseCompositeExchange
from infrastructure.exceptions.exchange import BaseExchangeError
from infrastructure.logging import LoggingTimer
from infrastructure.networking.websocket.handlers import PublicWebsocketHandlers
from exchanges.interfaces.rest.spot.rest_spot_public import PublicSpotRest
from exchanges.interfaces.ws.spot.base_ws_public import PublicSpotWebsocket
from exchanges.interfaces.base_events import (
    OrderbookUpdateEvent, TickerUpdateEvent, TradeUpdateEvent, BookTickerUpdateEvent,
    ConnectionStatusEvent, ErrorEvent
)


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
    # Abstract Factory Methods (COPIED FROM UnifiedCompositeExchange)
    # ========================================

    @abstractmethod
    async def _create_public_rest(self) -> PublicSpotRest:
        """
        Create exchange-specific public REST client.
        PATTERN: Copied from UnifiedCompositeExchange line 120
        
        Subclasses must implement this factory method to return
        their specific REST client that extends PublicSpotRest.
        """
        pass

    @abstractmethod
    async def _create_public_ws_with_handlers(self, handlers: PublicWebsocketHandlers) -> Optional[PublicSpotWebsocket]:
        """
        Create exchange-specific public WebSocket client with handler objects.
        PATTERN: Copied from UnifiedCompositeExchange line 130
        
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
    @abstractmethod
    def orderbooks(self) -> Dict[Symbol, OrderBook]:
        """Get current orderbooks for all active symbols."""
        pass

    async def _load_symbols_info(self) -> None:
        """Load symbol information from REST API with error handling."""
        if not self._public_rest:
            self.logger.warning("No public REST client available for symbols info loading")
            return
            
        try:
            with LoggingTimer(self.logger, "load_symbols_info") as timer:
                self._symbols_info = await self._public_rest.get_symbols_info(list(self._active_symbols))
                
            self.logger.info("Symbols info loaded successfully",
                            symbol_count=len(self._symbols_info.symbols) if self._symbols_info else 0,
                            load_time_ms=timer.elapsed_ms)
                            
        except Exception as e:
            self.logger.error("Failed to load symbols info", error=str(e))
            raise BaseExchangeError(f"Symbols info loading failed: {e}") from e

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
        if not self._public_rest:
            raise BaseExchangeError("No public REST client available")
            
        try:
            with LoggingTimer(self.logger, "get_orderbook_snapshot") as timer:
                orderbook = await self._public_rest.get_orderbook(symbol)
                
            # Track performance for HFT compliance
            if timer.elapsed_ms > 50:
                self.logger.warning("Orderbook snapshot slow", 
                                  symbol=symbol, 
                                  time_ms=timer.elapsed_ms)
                                  
            return orderbook
            
        except Exception as e:
            self.logger.error("Failed to get orderbook snapshot", 
                             symbol=symbol, error=str(e))
            raise BaseExchangeError(f"Orderbook snapshot failed for {symbol}: {e}") from e

    async def _start_real_time_streaming_with_book_ticker(self, symbols: List[Symbol]) -> None:
        """Start real-time WebSocket streaming with book ticker support for HFT."""
        if not self._public_ws:
            self.logger.warning("No public WebSocket client available for streaming")
            return
            
        try:
            self.logger.info("Starting real-time streaming with book ticker", symbol_count=len(symbols))
            
            # Subscribe to ALL data streams concurrently (HFT CRITICAL)
            subscription_tasks = []
            for symbol in symbols:
                subscription_tasks.append(self._public_ws.subscribe_orderbook(symbol))
                subscription_tasks.append(self._public_ws.subscribe_ticker(symbol))
                subscription_tasks.append(self._public_ws.subscribe_book_ticker(symbol))  # NEW: HFT Critical
                
            # Execute subscriptions concurrently with error handling
            results = await asyncio.gather(*subscription_tasks, return_exceptions=True)
            
            # Log subscription results
            successful_subs = sum(1 for r in results if not isinstance(r, Exception))
            failed_subs = len(results) - successful_subs
            
            self.logger.info("Real-time streaming started",
                            successful_subscriptions=successful_subs,
                            failed_subscriptions=failed_subs,
                            symbols=len(symbols),
                            has_book_ticker=True)
                            
        except Exception as e:
            self.logger.error("Failed to start real-time streaming", error=str(e))
            raise BaseExchangeError(f"Streaming startup failed: {e}") from e

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
        PATTERN: Copied from UnifiedCompositeExchange line 45-120
        
        ELIMINATES DUPLICATION: This orchestration logic was previously 
        duplicated across ALL exchange implementations (70%+ code reduction).
        
        Initialization sequence (UnifiedCompositeExchange pattern):
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
            
            # Step 3: Create WebSocket client with handler injection (line 80)
            if self.config.enable_websocket:
                self.logger.info(f"{self._tag} Creating public WebSocket client...")
                await self._initialize_public_websocket()
            
            # Step 4: Start real-time streaming including book ticker (line 90)
            if self._public_ws:
                self.logger.info(f"{self._tag} Starting real-time streaming...")
                await self._start_real_time_streaming_with_book_ticker(list(self._active_symbols))
            
            # Mark as initialized (line 100)
            self._initialized = True
            self._connection_healthy = self._validate_public_connections()
            
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
            raise BaseExchangeError(f"Public initialization failed: {e}") from e

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
                    bid_quantity=orderbook.bids[0].quantity,
                    ask_price=orderbook.asks[0].price,
                    ask_quantity=orderbook.asks[0].quantity,
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

    async def _initialize_public_websocket(self) -> None:
        """Initialize public WebSocket with constructor injection pattern including book ticker handler."""
        try:
            self.logger.debug("Initializing public WebSocket client")
            
            # Create handler objects for constructor injection (INCLUDING book_ticker_handler)
            public_handlers = PublicWebsocketHandlers(
                orderbook_handler=self._handle_orderbook_event,
                ticker_handler=self._handle_ticker_event,
                trades_handler=self._handle_trade_event,
                book_ticker_handler=self._handle_book_ticker_event,  # NEW: Critical for HFT
                connection_handler=self._handle_public_connection_event,
                error_handler=self._handle_error_event
            )
            
            # Use abstract factory method to create client
            self._public_ws = await self._create_public_ws_with_handlers(public_handlers)
            
            if self._public_ws:
                await self._public_ws.connect()
                self._public_ws_connected = self._public_ws.is_connected
                
            self.logger.info("Public WebSocket client initialized",
                            connected=self._public_ws_connected,
                            has_book_ticker_handler=True)
                            
        except Exception as e:
            self.logger.error("Public WebSocket initialization failed", error=str(e))
            raise BaseExchangeError(f"Public WebSocket initialization failed: {e}") from e

    def _validate_public_connections(self) -> bool:
        """Validate that required public connections are established."""
        return self._public_rest_connected and self._public_ws_connected

    # ========================================
    # Event Handler Methods with Book Ticker Support (NEW)
    # ========================================

    async def _handle_orderbook_event(self, event: OrderbookUpdateEvent) -> None:
        """
        Handle orderbook update events from public WebSocket.
        
        HFT CRITICAL: <1ms processing time for orderbook updates.
        """
        try:
            # Validate event freshness for HFT compliance
            if not self._validate_event_timestamp(event, max_age_seconds=5.0):
                self.logger.warning("Stale orderbook event ignored", 
                                  symbol=event.symbol)
                return
            
            # Update internal orderbook state
            self._update_orderbook(event.symbol, event.orderbook, event.update_type)
            
            # Track operation for performance monitoring
            self._track_operation("orderbook_update")
            
        except Exception as e:
            self.logger.error("Error handling orderbook event", 
                             symbol=event.symbol, error=str(e))

    async def _handle_book_ticker_event(self, book_ticker: BookTicker) -> None:
        """
        Handle book ticker events from public WebSocket.
        
        HFT CRITICAL: <500μs processing time for best bid/ask updates.
        This is ESSENTIAL for arbitrage opportunity detection.
        """
        try:
            start_time = time.perf_counter()
            
            # Validate event freshness for HFT compliance
            if book_ticker.timestamp:
                event_age = (time.time() * 1000) - book_ticker.timestamp
                if event_age > 5000:  # 5 seconds max age
                    self.logger.warning("Stale book ticker event ignored", 
                                      symbol=book_ticker.symbol, 
                                      age_ms=event_age)
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

    async def _handle_ticker_event(self, event: TickerUpdateEvent) -> None:
        """Handle ticker update events from public WebSocket."""
        try:
            # Update internal ticker state
            self._tickers[event.symbol] = event.ticker
            self._last_update_time = time.perf_counter()
            
            self._track_operation("ticker_update")
            
        except Exception as e:
            self.logger.error("Error handling ticker event", 
                             symbol=event.symbol, error=str(e))

    async def _handle_trade_event(self, event: TradeUpdateEvent) -> None:
        """Handle trade update events from public WebSocket."""
        try:
            # Trade events are typically forwarded to arbitrage layer
            # No internal state update needed
            
            self._track_operation("trade_update")
            
            self.logger.debug("Trade event processed", symbol=event.symbol)
            
        except Exception as e:
            self.logger.error("Error handling trade event", 
                             symbol=event.symbol, error=str(e))

    async def _handle_public_connection_event(self, event: ConnectionStatusEvent) -> None:
        """Handle public WebSocket connection status changes."""
        try:
            self._public_ws_connected = event.is_connected
            self._connection_healthy = self._validate_public_connections()
            
            self.logger.info("Public WebSocket connection status changed",
                            connected=event.is_connected,
                            error=event.error_message)
                            
            # If reconnected, refresh market data
            if event.is_connected:
                await self._refresh_market_data_after_reconnection()
                
        except Exception as e:
            self.logger.error("Error handling public connection event", error=str(e))

    async def _handle_error_event(self, event: ErrorEvent) -> None:
        """Handle error events from public WebSocket."""
        self.logger.error("Public WebSocket error event",
                         error_type=event.error_type,
                         error_code=event.error_code,
                         error_message=event.error_message,
                         is_recoverable=event.is_recoverable)

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

    def _validate_event_timestamp(self, event, max_age_seconds: float) -> bool:
        """Validate event timestamp for HFT compliance."""
        if not hasattr(event, 'timestamp'):
            return True  # Accept events without timestamps
            
        event_age = time.time() - event.timestamp
        return event_age <= max_age_seconds