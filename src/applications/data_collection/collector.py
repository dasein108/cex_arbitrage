"""
Data Collector - Modern Separated Domain Architecture

Manages real-time data collection from multiple exchanges using the modern separated domain
architecture with BindedEventHandlersAdapter pattern for flexible event handling.

Architecture (Oct 2025):
- Separated Domain Pattern: Public exchanges for market data only
- BindedEventHandlersAdapter: Modern event binding with .bind() method
- Constructor Injection: REST/WebSocket clients injected via constructors
- HFT Compliance: Sub-millisecond latency targets, no real-time data caching
- msgspec.Struct: All data modeling uses structured types
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Set, Callable, Awaitable
from dataclasses import dataclass

from exchanges.structs import Symbol, BookTicker, Trade, ExchangeEnum
from exchanges.exchange_factory import get_composite_implementation
from exchanges.adapters import BindedEventHandlersAdapter
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType
from db import BookTickerSnapshot
from db.models import TradeSnapshot, NormalizedBookTickerSnapshot, NormalizedTradeSnapshot
from .analytics import RealTimeAnalytics, ArbitrageOpportunity
from config.config_manager import get_exchange_config
from infrastructure.logging import get_logger, LoggingTimer


@dataclass
class BookTickerCache:
    """In-memory cache for book ticker data."""
    ticker: BookTicker
    last_updated: datetime
    exchange: str


@dataclass
class TradeCache:
    """In-memory cache for trade data."""
    trade: Trade
    last_updated: datetime
    exchange: str


class UnifiedWebSocketManager:
    """
    Unified WebSocket manager using modern separated domain architecture.
    
    Architecture (Oct 2025):
    - Separated Domain Pattern: Uses CompositePublicExchange for market data only
    - BindedEventHandlersAdapter: Modern event binding with .bind() method
    - Constructor Injection: Dependencies injected via constructors
    - HFT Optimized: Sub-millisecond latency targets
    
    Features:
    - Manages connections to multiple exchanges via composite pattern
    - Uses BindedEventHandlersAdapter for flexible event handling
    - Maintains in-memory cache following HFT caching policy
    - Provides unified interface for symbol subscription
    """

    def __init__(
            self,
            exchanges: List[ExchangeEnum],
            book_ticker_handler: Optional[Callable[[ExchangeEnum, Symbol, BookTicker], Awaitable[None]]] = None,
            trade_handler: Optional[Callable[[ExchangeEnum, Symbol, Trade], Awaitable[None]]] = None
    ):
        """
        Initialize unified WebSocket manager with modern architecture.
        
        Args:
            exchanges: List of exchange enums to connect to
            book_ticker_handler: Callback for book ticker updates
            trade_handler: Callback for trade updates
        """
        self.exchanges = exchanges
        self.book_ticker_handler = book_ticker_handler
        self.trade_handler = trade_handler

        # HFT Logging
        self.logger = get_logger('data_collector.websocket_manager')

        # Exchange composite clients (separated domain architecture)
        self._exchange_composites: Dict[ExchangeEnum, any] = {}
        
        # Event handler adapters for each exchange
        self._event_adapters: Dict[ExchangeEnum, BindedEventHandlersAdapter] = {}

        # Book ticker cache: {exchange_symbol: BookTickerCache}
        self._book_ticker_cache: Dict[str, BookTickerCache] = {}

        # Performance tracking
        self._total_messages_received = 0
        self._total_data_processed = 0

        # Log initialization
        self.logger.info("UnifiedWebSocketManager initialized with modern architecture",
                         exchanges=[e.value for e in exchanges],
                         has_book_ticker_handler=book_ticker_handler is not None,
                         has_trade_handler=trade_handler is not None)

        # Trade cache: {exchange_symbol: List[TradeCache]} (keep recent trades)
        self._trade_cache: Dict[str, List[TradeCache]] = {}

        # Active symbols per exchange
        self._active_symbols: Dict[ExchangeEnum, Set[Symbol]] = {}

        # Connection status
        self._connected: Dict[ExchangeEnum, bool] = {}

        self.logger.info(f"Initialized unified WebSocket manager for exchanges: {exchanges}")

    async def initialize(self, symbols: List[Symbol]) -> None:
        """
        Initialize WebSocket connections for all configured exchanges.
        
        Args:
            symbols: List of symbols to subscribe to across all exchanges
        """
        try:
            self.logger.info(f"Initializing WebSocket connections for {len(symbols)} symbols")

            # Initialize exchange clients
            for exchange in self.exchanges:
                await self._initialize_exchange_client(exchange, symbols)

            self.logger.info("All WebSocket connections initialized successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize WebSocket connections: {e}")
            raise

    async def _initialize_exchange_client(self, exchange: ExchangeEnum, symbols: List[Symbol]) -> None:
        """
        Initialize composite exchange client using modern separated domain architecture.
        
        Modern Pattern (Oct 2025):
        1. Create CompositePublicExchange via factory (constructor injection)
        2. Create BindedEventHandlersAdapter and bind to exchange
        3. Bind event handlers using .bind() method
        4. Initialize and subscribe to symbols
        
        Args:
            exchange: Exchange enum (ExchangeEnum.MEXC, ExchangeEnum.GATEIO, etc.)
            symbols: Symbols to subscribe to
        """
        try:
            # Create exchange configuration
            config = get_exchange_config(exchange.value)
            
            # Create composite public exchange (separated domain architecture)
            composite = get_composite_implementation(
                exchange_config=config,
                is_private=False  # Pure market data domain
            )

            # Create event handler adapter
            adapter = BindedEventHandlersAdapter(self.logger).bind_to_exchange(composite)
            
            # Bind event handlers using modern .bind() pattern
            if self.book_ticker_handler:
                adapter.bind(PublicWebsocketChannelType.BOOK_TICKER, 
                           lambda book_ticker: self._handle_book_ticker_update(exchange, book_ticker.symbol, book_ticker))
            
            if self.trade_handler:
                adapter.bind(PublicWebsocketChannelType.PUB_TRADE, 
                           lambda trade: self._handle_trades_update(exchange, trade.symbol, [trade]))

            # Store composite and adapter
            self._exchange_composites[exchange] = composite
            self._event_adapters[exchange] = adapter
            self._active_symbols[exchange] = set()
            self._connected[exchange] = False

            # Initialize composite with symbols and channels
            with LoggingTimer(self.logger, "composite_initialization") as timer:
                channels = [PublicWebsocketChannelType.BOOK_TICKER, PublicWebsocketChannelType.PUB_TRADE]
                
                # Filter tradable symbols before subscription
                tradable_symbols = []
                non_tradable_symbols = []
                
                for symbol in symbols:
                    try:
                        if await composite.is_tradable(symbol):
                            tradable_symbols.append(symbol)
                        else:
                            non_tradable_symbols.append(symbol)
                            self.logger.warning(f"Symbol {symbol.base}/{symbol.quote} not tradable on {exchange.value}, excluding from subscription")
                    except Exception as e:
                        non_tradable_symbols.append(symbol)
                        self.logger.error(f"Error checking tradability for {symbol.base}/{symbol.quote} on {exchange.value}: {e}")
                
                # Send Telegram notification for non-tradable symbols
                if non_tradable_symbols:
                    await self._notify_non_tradable_symbols(exchange, non_tradable_symbols)
                
                # Initialize with only tradable symbols
                await composite.initialize(tradable_symbols, channels)
                self._active_symbols[exchange].update(tradable_symbols)
                self._connected[exchange] = True

            self.logger.info("Composite exchange initialized successfully",
                             exchange=exchange.value,
                             symbols_count=len(symbols),
                             initialization_time_ms=timer.elapsed_ms)

            # Track successful initialization metrics
            self.logger.metric("composite_initializations", 1,
                               tags={"exchange": exchange.value, "status": "success"})

            self.logger.metric("symbols_subscribed", len(tradable_symbols),
                               tags={"exchange": exchange.value})

        except Exception as e:
            self.logger.error("Failed to initialize composite exchange",
                              exchange=exchange.value,
                              error_type=type(e).__name__,
                              error_message=str(e),
                              symbols_count=len(symbols))

            # Track initialization failures
            self.logger.metric("composite_initializations", 1,
                               tags={"exchange": exchange.value, "status": "error"})

            self._connected[exchange] = False
            raise

    async def _notify_non_tradable_symbols(self, exchange: ExchangeEnum, symbols: List[Symbol]) -> None:
        """Send Telegram notification for non-tradable symbols."""
        try:
            from infrastructure.networking.telegram import send_to_telegram
            
            symbol_list = ", ".join([f"{s.base}/{s.quote}" for s in symbols])
            message = f"🚫 Non-tradable symbols excluded from {exchange.value}:\n{symbol_list}"
            
            await send_to_telegram(message)
            self.logger.info(f"Sent Telegram notification for {len(symbols)} non-tradable symbols on {exchange.value}")
        except Exception as e:
            self.logger.error(f"Failed to send Telegram notification: {e}")

    async def _handle_book_ticker_update(self, exchange: ExchangeEnum, symbol: Symbol, book_ticker: BookTicker) -> None:
        """
        Handle book ticker updates from any exchange.
        
        Args:
            exchange: Exchange that was updated
            symbol: Symbol that was updated
            book_ticker: Updated book ticker data
        """
        try:
            # Track message reception
            self._total_messages_received += 1

            # Update cache - use symbol directly without prefixes
            cache_key = f"{exchange.value}_{symbol}"
            with LoggingTimer(self.logger, "book_ticker_cache_update") as timer:
                self._book_ticker_cache[cache_key] = BookTickerCache(
                    ticker=book_ticker,
                    last_updated=datetime.now(),
                    exchange=exchange.value
                )

            # Log update with performance context
            self.logger.debug("Book ticker cached",
                              exchange=exchange.value,
                              symbol=str(symbol),
                              bid_price=book_ticker.bid_price,
                              ask_price=book_ticker.ask_price,
                              cache_time_us=timer.elapsed_ms * 1000)

            # Track performance metrics
            self.logger.metric("book_ticker_updates", 1,
                               tags={"exchange": exchange.value, "symbol": str(symbol)})

            self.logger.metric("cache_update_time_us", timer.elapsed_ms * 1000,
                               tags={"exchange": exchange.value, "operation": "book_ticker"})

            # Call registered handler if available
            if self.book_ticker_handler:
                with LoggingTimer(self.logger, "book_ticker_handler") as handler_timer:
                    await self.book_ticker_handler(exchange, symbol, book_ticker)

                self.logger.metric("handler_processing_time_us", handler_timer.elapsed_ms * 1000,
                                   tags={"exchange": exchange.value, "handler": "book_ticker"})

            self._total_data_processed += 1

            # Log periodic performance stats
            if self._total_messages_received % 1000 == 0:
                self.logger.info("Performance checkpoint",
                                 messages_received=self._total_messages_received,
                                 data_processed=self._total_data_processed,
                                 cache_size=len(self._book_ticker_cache))

                self.logger.metric("messages_received_total", self._total_messages_received)
                self.logger.metric("data_processed_total", self._total_data_processed)
                self.logger.metric("cache_size", len(self._book_ticker_cache))

        except Exception as e:
            self.logger.error("Error handling book ticker update",
                              exchange=exchange.value,
                              symbol=str(symbol),
                              error_type=type(e).__name__,
                              error_message=str(e))

            # Track error metrics
            self.logger.metric("book_ticker_processing_errors", 1,
                               tags={"exchange": exchange.value, "symbol": str(symbol)})

            import traceback
            self.logger.debug("Full traceback", traceback=traceback.format_exc())



    async def _handle_trades_update(self, exchange: ExchangeEnum, symbol: Symbol, trades: List[Trade]) -> None:
        """
        Handle trade updates from any exchange.
        
        Args:
            exchange: Exchange enum
            symbol: Symbol that was traded
            trades: List of trade data
        """
        try:
            # Update cache (keep recent trades, limit to 100 per symbol)
            cache_key = f"{exchange.value}_{symbol}"
            if cache_key not in self._trade_cache:
                self._trade_cache[cache_key] = []

            # Process each trade in the list
            for trade in trades:
                trade_cache_entry = TradeCache(
                    trade=trade,
                    last_updated=datetime.now(),
                    exchange=exchange.value
                )

                self._trade_cache[cache_key].append(trade_cache_entry)

            # Keep only recent trades (limit to 100 to prevent memory bloat)
            if len(self._trade_cache[cache_key]) > 100:
                self._trade_cache[cache_key] = self._trade_cache[cache_key][-100:]

            # Call registered handler for each trade if available
            if self.trade_handler:
                for trade in trades:
                    await self.trade_handler(exchange, symbol, trade)
        except Exception as e:
            self.logger.error(f"Error handling trades update for {symbol}: {e}")

    async def add_symbols(self, symbols: List[Symbol]) -> None:
        """
        Add symbols to all active exchanges.
        
        Args:
            symbols: Symbols to add
        """
        if not symbols:
            return

        try:
            for exchange, composite in self._exchange_composites.items():
                if self._connected[exchange]:
                    # Use channel types for subscription
                    channels = [PublicWebsocketChannelType.BOOK_TICKER, PublicWebsocketChannelType.PUB_TRADE]
                    await composite.subscribe_symbols(symbols)
                    self._active_symbols[exchange].update(symbols)

            self.logger.info(f"Added {len(symbols)} symbols to all exchanges")

        except Exception as e:
            self.logger.error(f"Failed to add symbols: {e}")
            raise

    async def remove_symbols(self, symbols: List[Symbol]) -> None:
        """
        Remove symbols from all active exchanges.
        
        Args:
            symbols: Symbols to remove
        """
        if not symbols:
            return

        try:
            for exchange, composite in self._exchange_composites.items():
                if self._connected[exchange]:
                    # Use composite pattern for unsubscription
                    await composite.unsubscribe_symbols(symbols)
                    self._active_symbols[exchange].difference_update(symbols)

            # Remove from cache
            for symbol in symbols:
                for exchange in self.exchanges:
                    cache_key = f"{exchange.value}_{symbol}"
                    self._book_ticker_cache.pop(cache_key, None)

            self.logger.info(f"Removed {len(symbols)} symbols from all exchanges")

        except Exception as e:
            self.logger.error(f"Failed to remove symbols: {e}")

    def get_latest_book_ticker(self, exchange: ExchangeEnum, symbol: Symbol) -> Optional[BookTicker]:
        """
        Get latest book ticker for a specific exchange and symbol.
        
        Args:
            exchange: Exchange enum
            symbol: Symbol to get ticker for
            
        Returns:
            BookTicker if available, None otherwise
        """
        cache_key = f"{exchange.value}_{symbol}"
        cache_entry = self._book_ticker_cache.get(cache_key)

        if cache_entry:
            return cache_entry.ticker
        return None

    def _parse_cache_key(self, cache_key: str) -> tuple[str, str]:
        """
        Parse cache key into exchange and symbol components.
        
        Cache keys follow the format: {exchange}_{symbol}
        where exchange may contain underscores (e.g., "MEXC_SPOT").
        
        Args:
            cache_key: Cache key in format "exchange_symbol"
            
        Returns:
            Tuple of (exchange, symbol_str)
            
        Raises:
            ValueError: If cache key format is invalid
        """
        parts = cache_key.rsplit("_", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid cache key format: {cache_key}")

        return parts[0], parts[1]

    def get_all_cached_tickers(self) -> List[BookTickerSnapshot]:
        """
        Get all cached book tickers as normalized BookTickerSnapshot objects.
        
        Returns:
            List of BookTickerSnapshot objects with symbol_id (normalized approach)
        """
        snapshots = []

        for cache_key, cache_entry in self._book_ticker_cache.items():
            try:
                # Parse exchange and symbol from cache key
                exchange, symbol_str = self._parse_cache_key(cache_key)

                # Resolve symbol_id directly using database cache (normalized approach)
                symbol_id = self._resolve_symbol_id_from_cache(exchange, symbol_str)
                if symbol_id is None:
                    self.logger.warning(f"Cannot resolve symbol_id from cache: {symbol_str} on {exchange}")
                    continue

                # Create normalized snapshot directly with symbol_id
                snapshot = BookTickerSnapshot.from_symbol_id_and_data(
                    symbol_id=symbol_id,
                    bid_price=cache_entry.ticker.bid_price,
                    bid_qty=cache_entry.ticker.bid_quantity,
                    ask_price=cache_entry.ticker.ask_price,
                    ask_qty=cache_entry.ticker.ask_quantity,
                    timestamp=cache_entry.last_updated
                )
                snapshots.append(snapshot)

            except Exception as e:
                self.logger.error(f"Error processing cached ticker {cache_key}: {e}")
                continue

        return snapshots

    def _resolve_symbol_id_from_cache(self, exchange: str, symbol_str: str) -> Optional[int]:
        """
        Resolve symbol_id from database cache using exchange and symbol string.
        
        Handles both slash format (BTC/USDT) and exchange format (BTCUSDT).
        
        Args:
            exchange: Exchange identifier (e.g., 'MEXC_SPOT')
            symbol_str: Symbol string (e.g., 'BTCUSDT' or 'BTC/USDT')
            
        Returns:
            symbol_id if found, None otherwise
        """
        try:
            from exchanges.structs.enums import ExchangeEnum
            from db.cache_operations import cached_resolve_symbol_by_exchange_string
            
            # Parse exchange enum
            exchange_enum = ExchangeEnum(exchange)
            
            # Try direct resolution first (for exchange format like 'BTCUSDT')
            db_symbol = cached_resolve_symbol_by_exchange_string(exchange_enum, symbol_str)
            if db_symbol:
                self.logger.debug(f"Resolved symbol_id {db_symbol.id} for {symbol_str} on {exchange}")
                return db_symbol.id
            
            # If slash format (e.g., 'BTC/USDT'), convert to exchange format
            if '/' in symbol_str:
                parts = symbol_str.split('/')
                if len(parts) == 2:
                    exchange_symbol = f"{parts[0]}{parts[1]}"  # BTC/USDT -> BTCUSDT
                    db_symbol = cached_resolve_symbol_by_exchange_string(exchange_enum, exchange_symbol)
                    if db_symbol:
                        self.logger.debug(f"Resolved symbol_id {db_symbol.id} for {symbol_str} (converted to {exchange_symbol}) on {exchange}")
                        return db_symbol.id
            
            return None
            
        except Exception as e:
            self.logger.warning(f"Error resolving symbol_id for {symbol_str} on {exchange}: {e}")
            return None

    def get_all_cached_trades(self) -> List[TradeSnapshot]:
        """
        Get all cached trades as normalized TradeSnapshot objects.
        
        Returns:
            List of TradeSnapshot objects with symbol_id (normalized approach)
        """
        snapshots = []

        for cache_key, trade_cache_list in self._trade_cache.items():
            try:
                # Parse exchange and symbol from cache key
                exchange, symbol_str = self._parse_cache_key(cache_key)

                # Resolve symbol_id directly using database cache (normalized approach)
                symbol_id = self._resolve_symbol_id_from_cache(exchange, symbol_str)
                if symbol_id is None:
                    self.logger.warning(f"Cannot resolve symbol_id from cache for trades: {symbol_str} on {exchange}")
                    continue

                # Convert each cached trade to normalized TradeSnapshot
                for trade_cache in trade_cache_list:
                    snapshot = TradeSnapshot.from_symbol_id_and_trade(
                        symbol_id=symbol_id,
                        trade=trade_cache.trade
                    )
                    snapshots.append(snapshot)
            except Exception as e:
                self.logger.error(f"Error processing cached trades {cache_key}: {e}")
                continue

        return snapshots

    def get_connection_status(self) -> Dict[str, bool]:
        """
        Get connection status for all exchanges.
        
        Returns:
            Dictionary mapping exchange names to connection status
        """
        return {exchange.value: status for exchange, status in self._connected.items()}

    def get_active_symbols_count(self) -> Dict[str, int]:
        """
        Get count of active symbols per exchange.
        
        Returns:
            Dictionary mapping exchange names to symbol counts
        """
        return {
            exchange.value: len(symbols)
            for exchange, symbols in self._active_symbols.items()
        }

    def get_cache_statistics(self) -> Dict[str, any]:
        """
        Get cache statistics for monitoring.
        
        Returns:
            Dictionary with cache statistics
        """
        total_cached = len(self._book_ticker_cache)

        # Count by exchange
        by_exchange = {}
        for cache_key in self._book_ticker_cache.keys():
            try:
                exchange, _ = self._parse_cache_key(cache_key)
                by_exchange[exchange] = by_exchange.get(exchange, 0) + 1
            except Exception as e:
                self.logger.warning(f"Error parsing cache key {cache_key}: {e}")

        # Count cached trades by exchange
        trades_by_exchange = {}
        total_cached_trades = 0
        for cache_key, trade_list in self._trade_cache.items():
            try:
                exchange, _ = self._parse_cache_key(cache_key)
                trade_count = len(trade_list)
                trades_by_exchange[exchange] = trades_by_exchange.get(exchange, 0) + trade_count
                total_cached_trades += trade_count
            except Exception as e:
                self.logger.warning(f"Error parsing trade cache key {cache_key}: {e}")

        # Add detailed cache keys for debugging
        cache_keys = list(self._book_ticker_cache.keys())

        return {
            "total_cached_tickers": total_cached,
            "tickers_by_exchange": by_exchange,
            "total_cached_trades": total_cached_trades,
            "trades_by_exchange": trades_by_exchange,
            "connected_exchanges": sum(1 for connected in self._connected.values() if connected),
            "total_exchanges": len(self._connected),
            "sample_cache_keys": cache_keys[:5],  # Show first 5 cache keys for debugging
            "connection_status": dict(self._connected)  # Show individual connection status
        }

    async def close(self) -> None:
        """Close all composite exchange connections."""
        try:
            self.logger.info("Closing all composite exchange connections")

            # Dispose event adapters first
            for exchange, adapter in self._event_adapters.items():
                try:
                    await adapter.dispose()
                except Exception as e:
                    self.logger.error(f"Error disposing adapter for {exchange}: {e}")

            # Close all composite exchanges
            for exchange, composite in self._exchange_composites.items():
                try:
                    await composite.close()
                    self._connected[exchange] = False
                except Exception as e:
                    self.logger.error(f"Error closing {exchange} composite: {e}")

            # Clear caches and state
            self._book_ticker_cache.clear()
            self._trade_cache.clear()
            self._active_symbols.clear()
            self._exchange_composites.clear()
            self._event_adapters.clear()

            self.logger.info("All composite exchange connections closed")

        except Exception as e:
            self.logger.error(f"Error during composite exchange cleanup: {e}")


class SnapshotScheduler:
    """
    Scheduler for taking periodic snapshots of book ticker data.
    
    Captures data every N seconds and triggers storage operations.
    """

    def __init__(
            self,
            ws_manager: UnifiedWebSocketManager,
            interval_seconds: float = 1,
            snapshot_handler: Optional[Callable[[List[BookTickerSnapshot]], Awaitable[None]]] = None,
            trade_handler: Optional[Callable[[List[TradeSnapshot]], Awaitable[None]]] = None
    ):
        """
        Initialize snapshot scheduler.
        
        Args:
            ws_manager: WebSocket manager to get data from
            interval_seconds: Snapshot interval in seconds
            snapshot_handler: Handler for snapshot data
        """
        self.ws_manager = ws_manager
        self.interval_seconds = interval_seconds
        self.snapshot_handler = snapshot_handler
        self.trade_handler = trade_handler

        self.logger = get_logger('data_collector.snapshot_scheduler')
        self._running = False
        self._snapshot_count = 0

    async def start(self) -> None:
        """Start the snapshot scheduler."""
        if self._running:
            self.logger.warning("Snapshot scheduler is already running")
            return

        self._running = True
        self.logger.info(f"Starting snapshot scheduler with {self.interval_seconds}s interval")

        try:
            while self._running:
                await self._take_snapshot()
                await asyncio.sleep(self.interval_seconds)
        except Exception as e:
            self.logger.error(f"Snapshot scheduler error: {e}")
            raise
        finally:
            self._running = False

    async def stop(self) -> None:
        """Stop the snapshot scheduler."""
        self.logger.info("Stopping snapshot scheduler")
        self._running = False

    async def _take_snapshot(self) -> None:
        """Take a snapshot of all cached book ticker and trade data."""
        try:
            # Get all cached tickers
            ticker_snapshots = self.ws_manager.get_all_cached_tickers()

            # Get all cached trades
            trade_snapshots = self.ws_manager.get_all_cached_trades()

            # Enhanced debugging
            cache_stats = self.ws_manager.get_cache_statistics()
            self.logger.debug(
                f"Snapshot #{self._snapshot_count + 1:03d}: Cache stats - "
                f"Connected: {cache_stats['connected_exchanges']}/{cache_stats['total_exchanges']}, "
                f"Cached tickers: {cache_stats['total_cached_tickers']}, "
                f"Retrieved tickers: {len(ticker_snapshots)}, "
                f"Retrieved trades: {len(trade_snapshots)}"
            )

            if not ticker_snapshots and not trade_snapshots:
                # Log more details about why no data
                if cache_stats['total_cached_tickers'] > 0:
                    self.logger.warning(
                        f"Cache has {cache_stats['total_cached_tickers']} tickers but get_all_cached_tickers returned none!"
                    )
                else:
                    self.logger.debug("No cached data available for snapshot")
                return

            self._snapshot_count += 1

            # Call snapshot handlers if available
            if self.snapshot_handler and ticker_snapshots:
                self.logger.debug(f"Calling snapshot_handler with {len(ticker_snapshots)} tickers")
                await self.snapshot_handler(ticker_snapshots)
                self.logger.debug("Snapshot_handler completed successfully")
            elif ticker_snapshots:
                self.logger.warning(f"Have {len(ticker_snapshots)} tickers but no snapshot_handler configured!")

            if self.trade_handler and trade_snapshots:
                self.logger.debug(f"Calling trade_handler with {len(trade_snapshots)} trades")
                await self.trade_handler(trade_snapshots)
                self.logger.debug("Trade_handler completed successfully")

            # Log snapshot statistics
            self.logger.info(
                f"Snapshot #{self._snapshot_count:03d}: "
                f"Processed {len(ticker_snapshots)} tickers, {len(trade_snapshots)} trades from "
                f"{cache_stats['connected_exchanges']}/{cache_stats['total_exchanges']} exchanges"
            )

        except Exception as e:
            self.logger.error(f"Error taking snapshot: {e}")
            import traceback
            self.logger.error(traceback.format_exc())

    def get_statistics(self) -> Dict[str, any]:
        """Get scheduler statistics."""
        return {
            "running": self._running,
            "snapshot_count": self._snapshot_count,
            "interval_seconds": self.interval_seconds,
            "has_ticker_handler": self.snapshot_handler is not None,
            "has_trade_handler": self.trade_handler is not None
        }


class DataCollector:
    """
    Main orchestrator for the data collection system.
    
    Coordinates WebSocket manager, analytics engine, snapshot scheduler,
    and database operations to provide a complete data collection solution.
    """

    def __init__(self):
        """
        Initialize data collector.
        """
        # Load configuration
        from config.config_manager import get_data_collector_config
        self.config = get_data_collector_config()

        # HFT Logging
        from infrastructure.logging import get_logger
        self.logger = get_logger('data_collector.collector')

        # Components
        self.ws_manager: Optional[UnifiedWebSocketManager] = None
        self.analytics: Optional[RealTimeAnalytics] = None
        self.scheduler: Optional[SnapshotScheduler] = None

        # State
        self._running = False
        self._start_time: Optional[datetime] = None

        self.logger.info(f"Data collector initialized with {len(self.config.symbols)} symbols")

    async def _perform_symbol_synchronization(self) -> None:
        """
        Perform symbol synchronization on startup.
        
        Synchronizes exchanges and symbols with the database:
        1. Ensures all configured exchanges exist in database
        2. Fetches symbol information from exchange APIs
        3. Adds new symbols, updates existing ones, marks delisted as inactive
        """
        try:
            self.logger.info("Starting symbol synchronization process")
            
            # Import synchronization services
            from db.symbol_sync import get_symbol_sync_service
            from db.exchange_sync import get_exchange_sync_service
            
            # Get configured exchanges from config
            exchanges_to_sync = self.config.exchanges
            self.logger.info(f"Synchronizing {len(exchanges_to_sync)} exchanges: {[e.value for e in exchanges_to_sync]}")
            
            # Sync exchanges first (ensure they exist in database)
            exchange_sync = get_exchange_sync_service()
            exchanges = await exchange_sync.sync_exchanges(exchanges_to_sync)
            self.logger.info(f"Exchange synchronization completed: {len(exchanges)} exchanges synchronized")
            
            # Sync symbols for all exchanges
            symbol_sync = get_symbol_sync_service()
            symbol_stats = await symbol_sync.sync_all_exchanges(exchanges_to_sync)
            
            # Log detailed synchronization results
            total_stats = symbol_stats.get('_totals', {})
            self.logger.info(
                f"Symbol synchronization completed: "
                f"Added={total_stats.get('added', 0)}, "
                f"Updated={total_stats.get('updated', 0)}, "
                f"Deactivated={total_stats.get('deactivated', 0)}, "
                f"Errors={total_stats.get('errors', 0)}"
            )
            
            # Log per-exchange statistics
            for exchange_name, stats in symbol_stats.items():
                if exchange_name != '_totals':
                    self.logger.info(
                        f"Exchange {exchange_name}: Added={stats.get('added', 0)}, "
                        f"Updated={stats.get('updated', 0)}, Deactivated={stats.get('deactivated', 0)}, "
                        f"Errors={stats.get('errors', 0)}"
                    )
            
            # Send notification for significant changes
            if total_stats.get('added', 0) > 0 or total_stats.get('deactivated', 0) > 0:
                await self._notify_symbol_changes(total_stats)
                
        except Exception as e:
            self.logger.error(f"Symbol synchronization failed: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            # Don't re-raise - allow data collector to start even if sync fails
            
    async def _notify_symbol_changes(self, stats: dict) -> None:
        """Send notification for significant symbol changes."""
        try:
            from infrastructure.networking.telegram import send_to_telegram
            
            added = stats.get('added', 0)
            deactivated = stats.get('deactivated', 0)
            
            message = "📈 Symbol synchronization completed:\n"
            if added > 0:
                message += f"➕ {added} new symbols added\n"
            if deactivated > 0:
                message += f"❌ {deactivated} symbols deactivated\n"
            
            await send_to_telegram(message)
            self.logger.info("Sent Telegram notification for symbol changes")
        except Exception as e:
            self.logger.error(f"Failed to send symbol change notification: {e}")

    async def initialize(self) -> None:
        """Initialize all components."""
        try:
            if not self.config.enabled:
                self.logger.warning("Data collector is disabled in configuration")
                return

            self.logger.info("Initializing data collector components")

            # Ensure exchange modules are imported to trigger registrations
            self.logger.debug("Importing exchange modules for factory registration...")
            import exchanges.integrations.mexc
            import exchanges.integrations.gateio
            self.logger.debug("Exchange modules imported successfully")

            # Initialize database manager
            from db import DatabaseManager

            # Use the centralized database config directly
            db_manager = DatabaseManager()
            await db_manager.initialize(self.config.database)
            self.logger.info("Database connection pool initialized")
            
            # Perform symbol synchronization on startup
            await self._perform_symbol_synchronization()
            
            # Initialize symbol cache for normalized schema operations
            from db.cache_warming import warm_symbol_cache
            await warm_symbol_cache()
            self.logger.info("Symbol cache warmed for normalized schema operations")

            # Initialize analytics engine
            from .analytics import RealTimeAnalytics
            self.analytics = RealTimeAnalytics(self.config.analytics)
            self.logger.info("Analytics engine initialized")

            # Initialize WebSocket manager using modern architecture
            self.ws_manager = UnifiedWebSocketManager(
                exchanges=self.config.exchanges,
                book_ticker_handler=self._handle_external_book_ticker,
                trade_handler=self._handle_external_trade
            )
            self.logger.info(f"WebSocket manager created for {len(self.config.exchanges)} exchanges")

            # Initialize WebSocket connections
            self.logger.info(f"Initializing WebSocket connections for {len(self.config.symbols)} symbols...")
            await self.ws_manager.initialize(self.config.symbols)
            self.logger.info("WebSocket connections initialized")

            # Verify connections
            connection_status = self.ws_manager.get_connection_status()
            self.logger.info(f"Connection status: {connection_status}")

            # Initialize snapshot scheduler with database handler
            self.scheduler = SnapshotScheduler(
                ws_manager=self.ws_manager,
                interval_seconds=self.config.snapshot_interval,
                snapshot_handler=self._handle_snapshot_storage,
                trade_handler=self._handle_trade_storage
            )
            self.logger.info(f"Snapshot scheduler initialized with {self.config.snapshot_interval}s interval")

            self.logger.info("All data collector components initialized successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize data collector: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            raise

    async def start(self) -> None:
        """Start the data collection process."""
        if self._running:
            self.logger.warning("Data collector is already running")
            return

        if not self.config.enabled:
            self.logger.warning("Data collector is disabled in configuration")
            return

        try:
            self.logger.info("Starting data collector")
            self._running = True
            self._start_time = datetime.now()

            # Start snapshot scheduler (this will run the main loop)
            if self.scheduler:
                await self.scheduler.start()

        except Exception as e:
            self.logger.error(f"Error during data collection: {e}")
            self._running = False
            raise
        finally:
            self._running = False

    async def stop(self) -> None:
        """Stop the data collection process."""
        self.logger.info("Stopping data collector")

        try:
            # Stop scheduler
            if self.scheduler:
                await self.scheduler.stop()

            # Close WebSocket connections
            if self.ws_manager:
                await self.ws_manager.close()

            # Close database connection pool
            from db import DatabaseManager
            db_manager = DatabaseManager()
            await db_manager.close()
            self.logger.info("Database connection pool closed")

            self._running = False
            self.logger.info("Data collector stopped successfully")

        except Exception as e:
            self.logger.error(f"Error stopping data collector: {e}")

    async def _handle_book_ticker_update(self, exchange: ExchangeEnum, symbol: Symbol, book_ticker: BookTicker) -> None:
        """
        Handle book ticker updates from WebSocket manager (legacy compatibility).
        
        Routes updates to analytics engine.
        """
        try:
            if self.analytics:
                await self.analytics.on_book_ticker_update(exchange.value, symbol, book_ticker)
        except Exception as e:
            self.logger.error(f"Error handling book ticker update: {e}")

    async def _handle_trades_update(self, exchange: ExchangeEnum, symbol: Symbol, trades: List[Trade]) -> None:
        """
        Handle trade updates from WebSocket manager (legacy compatibility).

        Routes updates to analytics engine.
        """
        try:
            if self.analytics:
                # Analytics trade handling would go here when implemented
                for trade in trades:
                    # Future: add analytics.on_trade_update when available
                    pass

        except Exception as e:
            self.logger.error(f"Error handling trades update: {e}")

    async def _handle_external_book_ticker(self, exchange: ExchangeEnum, symbol: Symbol, book_ticker: BookTicker) -> None:
        """
        External handler for book ticker updates using modern architecture.
        
        This method receives book ticker data with exchange and symbol context
        from the BindedEventHandlersAdapter pattern.
        """
        try:
            if self.analytics:
                await self.analytics.on_book_ticker_update(exchange.value, symbol, book_ticker)
        except Exception as e:
            self.logger.error(f"Error handling external book ticker update: {e}")

    async def _handle_external_trade(self, exchange: ExchangeEnum, symbol: Symbol, trade: Trade) -> None:
        """
        External handler for trade updates using modern architecture.
        
        This method receives trade data with exchange and symbol context
        from the BindedEventHandlersAdapter pattern.
        """
        try:
            # Process individual trade if analytics supports it
            if self.analytics:
                # Analytics trade handling would go here when implemented
                pass
        except Exception as e:
            self.logger.error(f"Error handling external trade update: {e}")

    async def _handle_snapshot_storage(self, snapshots: List[BookTickerSnapshot]) -> None:
        """
        Handle snapshot storage to database using normalized schema.

        The snapshots are already normalized with symbol_id, so we can store them directly.

        Args:
            snapshots: List of normalized BookTickerSnapshot objects with symbol_id
        """
        try:
            if not snapshots:
                self.logger.debug("No snapshots to store")
                return

            self.logger.debug(f"Storing {len(snapshots)} normalized snapshots to database...")

            # Store snapshots using normalized batch insert (snapshots have symbol_id)
            from db.operations import insert_book_ticker_snapshot

            start_time = datetime.now()
            count = 0
            
            # Use individual inserts for normalized snapshots
            for snapshot in snapshots:
                try:
                    await insert_book_ticker_snapshot(snapshot)
                    count += 1
                except Exception as e:
                    self.logger.warning(f"Failed to insert snapshot for symbol_id {snapshot.symbol_id}: {e}")
                    
            storage_duration = (datetime.now() - start_time).total_seconds() * 1000

            self.logger.debug(
                f"Successfully stored {count} snapshots in {storage_duration:.1f}ms"
            )

            # Log sample of what was stored for verification
            if snapshots:
                sample = snapshots[0]
                self.logger.debug(
                    f"Sample snapshot stored: symbol_id={sample.symbol_id} @ {sample.timestamp} - "
                    f"bid={sample.bid_price} ask={sample.ask_price}"
                )

        except Exception as e:
            self.logger.error(f"Error storing normalized snapshots: {e}")
            import traceback
            self.logger.error(traceback.format_exc())

    async def _handle_trade_storage(self, trade_snapshots: List[TradeSnapshot]) -> None:
        """
        Handle trade snapshot storage to database using normalized schema.

        The trade snapshots are already normalized with symbol_id, so we can store them directly.

        Args:
            trade_snapshots: List of normalized TradeSnapshot objects with symbol_id
        """
        try:
            if not trade_snapshots:
                return

            self.logger.debug(f"Storing {len(trade_snapshots)} normalized trade snapshots to database...")

            # Store trade snapshots using normalized individual inserts (they have symbol_id)
            from db.operations import insert_trade_snapshot

            start_time = datetime.now()
            count = 0
            
            # Use individual inserts for normalized trade snapshots
            for trade_snapshot in trade_snapshots:
                try:
                    await insert_trade_snapshot(trade_snapshot)
                    count += 1
                except Exception as e:
                    self.logger.warning(f"Failed to insert trade snapshot for symbol_id {trade_snapshot.symbol_id}: {e}")
                    
            storage_duration = (datetime.now() - start_time).total_seconds() * 1000

            self.logger.debug(
                f"Successfully stored {count} trade snapshots in {storage_duration:.1f}ms"
            )

        except Exception as e:
            self.logger.error(f"Error storing trade snapshots: {e}")

    def get_status(self) -> Dict[str, any]:
        """
        Get comprehensive status of the data collector.
        
        Returns:
            Dictionary with status information
        """
        status = {
            "running": self._running,
            "config": {
                "enabled": self.config.enabled,
                "snapshot_interval": self.config.snapshot_interval,
                "analytics_interval": self.config.analytics_interval,
                "exchanges": self.config.exchanges,
                "symbols_count": len(self.config.symbols),
                "trade_collection_enabled": getattr(self.config, 'collect_trades', True)
            }
        }

        if self._start_time:
            status["uptime_seconds"] = (datetime.now() - self._start_time).total_seconds()

        # WebSocket manager status
        if self.ws_manager:
            status["ws"] = {
                "connections": self.ws_manager.get_connection_status(),
                "active_symbols": self.ws_manager.get_active_symbols_count(),
                "cache_stats": self.ws_manager.get_cache_statistics()
            }

        # Analytics status
        if self.analytics:
            status["analytics"] = self.analytics.get_statistics()

        # Scheduler status
        if self.scheduler:
            status["scheduler"] = self.scheduler.get_statistics()

        return status

    async def add_symbols(self, symbols: List[Symbol]) -> None:
        """
        Add symbols to data collection.
        
        Args:
            symbols: Symbols to add
        """
        if self.ws_manager:
            await self.ws_manager.add_symbols(symbols)
            self.config.symbols.extend(symbols)
            self.logger.info(f"Added {len(symbols)} symbols to data collection")

    async def remove_symbols(self, symbols: List[Symbol]) -> None:
        """
        Remove symbols from data collection.
        
        Args:
            symbols: Symbols to remove
        """
        if self.ws_manager:
            await self.ws_manager.remove_symbols(symbols)
            for symbol in symbols:
                if symbol in self.config.symbols:
                    self.config.symbols.remove(symbol)
            self.logger.info(f"Removed {len(symbols)} symbols from data collection")

    async def get_recent_opportunities(self, minutes: int = 5) -> List[ArbitrageOpportunity]:
        """
        Get recent arbitrage opportunities.
        
        Args:
            minutes: Number of minutes to look back
            
        Returns:
            List of recent opportunities
        """
        if self.analytics:
            return self.analytics.get_recent_opportunities(minutes)
        return []
