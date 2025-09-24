"""
Data Collector - Unified WebSocket Manager and Main Orchestrator

Manages real-time data collection from multiple exchanges using WebSocket connections.
Provides unified interface for MEXC and Gate.io book ticker data collection.
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Set, Callable, Awaitable
from dataclasses import dataclass

from infrastructure.config import get_exchange_config
from infrastructure.data_structures.common import Symbol, BookTicker, Trade
from infrastructure.factories.websocket import PublicWebSocketExchangeFactory
from db import BookTickerSnapshot
from db.models import TradeSnapshot
from infrastructure.data_structures.common import ExchangeEnum
from .analytics import RealTimeAnalytics
from .consts import WEBSOCKET_CHANNELS

# HFT Logger Integration
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
    Unified WebSocket manager for collecting book ticker data from multiple exchanges.
    
    Features:
    - Manages connections to MEXC and Gate.io WebSockets
    - Maintains in-memory cache of latest book ticker data
    - Provides unified interface for subscribing to symbols
    - Routes updates to registered handlers
    """
    
    def __init__(
        self,
        exchanges: List[ExchangeEnum],
        book_ticker_handler: Optional[Callable[[ExchangeEnum, Symbol, BookTicker], Awaitable[None]]] = None,
        trade_handler: Optional[Callable[[ExchangeEnum, Symbol, Trade], Awaitable[None]]] = None
    ):
        """
        Initialize unified WebSocket manager.
        
        Args:
            exchanges: List of exchange enums to connect to
            book_ticker_handler: Handler for book ticker updates
        """
        self.exchanges = exchanges
        self.book_ticker_handler = book_ticker_handler
        self.trade_handler = trade_handler
        
        # HFT Logging
        self.logger = get_logger('data_collector.websocket_manager')
        
        # Exchange WebSocket clients
        self._exchange_clients: Dict[ExchangeEnum, any] = {}
        
        # Book ticker cache: {exchange_symbol: BookTickerCache}
        self._book_ticker_cache: Dict[str, BookTickerCache] = {}
        
        # Performance tracking
        self._total_messages_received = 0
        self._total_data_processed = 0
        
        # Log initialization
        self.logger.info("UnifiedWebSocketManager initialized",
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
        Initialize WebSocket client for a specific exchange.
        
        Args:
            exchange: Exchange enum (ExchangeEnum.MEXC, ExchangeEnum.GATEIO, etc.)
            symbols: Symbols to subscribe to
        """
        try:
            # Create exchange configuration
            config = get_exchange_config(exchange.value)
            
            # Create WebSocket client using factory pattern
            client = PublicWebSocketExchangeFactory.inject(
                exchange=exchange,
                config=config,
                book_ticker_handler=lambda symbol, ticker: self._handle_book_ticker_update(exchange, symbol, ticker),
                trades_handler=lambda symbol, trades: self._handle_trades_update(exchange, symbol, trades)
            )
            
            # Store client and initialize
            self._exchange_clients[exchange] = client
            self._active_symbols[exchange] = set()
            self._connected[exchange] = False
            
            # Initialize connection and subscribe to symbols with performance tracking
            with LoggingTimer(self.logger, "websocket_initialization") as timer:
                await client.initialize(symbols, WEBSOCKET_CHANNELS)
                self._active_symbols[exchange].update(symbols)
                self._connected[exchange] = True
            
            self.logger.info("WebSocket initialized successfully",
                            exchange=exchange.value,
                            symbols_count=len(symbols),
                            initialization_time_ms=timer.elapsed_ms)
            
            # Track successful initialization metrics
            self.logger.metric("websocket_initializations", 1,
                              tags={"exchange": exchange.value, "status": "success"})
            
            self.logger.metric("websocket_symbols_subscribed", len(symbols),
                              tags={"exchange": exchange.value})
            
        except Exception as e:
            self.logger.error("Failed to initialize WebSocket",
                             exchange=exchange.value,
                             error_type=type(e).__name__,
                             error_message=str(e),
                             symbols_count=len(symbols))
            
            # Track initialization failures
            self.logger.metric("websocket_initializations", 1,
                              tags={"exchange": exchange.value, "status": "error"})
            
            self._connected[exchange] = False
            raise
    
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
            for exchange, client in self._exchange_clients.items():
                if self._connected[exchange]:
                    await client.add_symbols(symbols)
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
            for exchange, client in self._exchange_clients.items():
                if self._connected[exchange]:
                    await client.remove_symbols(symbols)
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
        Get all cached book tickers as BookTickerSnapshot objects.
        
        Returns:
            List of BookTickerSnapshot objects
        """
        snapshots = []
        
        for cache_key, cache_entry in self._book_ticker_cache.items():
            try:
                # Parse exchange and symbol from cache key
                exchange, symbol_str = self._parse_cache_key(cache_key)
                
                # Find the original Symbol object more efficiently
                symbol = None
                for active_symbols in self._active_symbols.values():
                    for sym in active_symbols:
                        if str(sym) == symbol_str:
                            symbol = sym
                            break
                    if symbol:
                        break
                
                if symbol is None:
                    # Create a fallback symbol by parsing the symbol string
                    self.logger.debug(f"Symbol not found in active symbols: {symbol_str} for exchange {exchange}, creating fallback")
                    
                    # Parse symbol string directly without prefixes
                    # Try to parse symbol string manually as fallback
                    if len(symbol_str) >= 6 and symbol_str.endswith('USDT'):
                        from infrastructure.data_structures.common import Symbol, AssetName, ExchangeEnum
                        base = symbol_str[:-4]  # Remove USDT
                        quote = 'USDT'
                        # Determine if futures based on exchange type
                        exchange_enum = ExchangeEnum(exchange)
                        is_futures = exchange_enum in [ExchangeEnum.GATEIO_FUTURES]
                        symbol = Symbol(base=AssetName(base), quote=AssetName(quote), is_futures=is_futures)
                        self.logger.debug(f"Created fallback symbol: {symbol}")
                    else:
                        # Skip this entry if we can't parse it
                        self.logger.warning(f"Cannot parse symbol: {symbol_str}")
                        continue
                
                snapshot = BookTickerSnapshot.from_symbol_and_data(
                    exchange=exchange.upper(),
                    symbol=symbol,
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
    
    def get_all_cached_trades(self) -> List[TradeSnapshot]:
        """
        Get all cached trades as TradeSnapshot objects.
        
        Returns:
            List of TradeSnapshot objects
        """
        snapshots = []
        
        for cache_key, trade_cache_list in self._trade_cache.items():
            try:
                # Parse exchange and symbol from cache key
                exchange, symbol_str = self._parse_cache_key(cache_key)
                
                # Convert each cached trade to TradeSnapshot
                for trade_cache in trade_cache_list:
                    snapshot = TradeSnapshot.from_trade_struct(
                        exchange=exchange.upper(),
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
        """Close all WebSocket connections."""
        try:
            self.logger.info("Closing all WebSocket connections")
            
            # Close all exchange clients
            for exchange, client in self._exchange_clients.items():
                try:
                    await client.close()
                    self._connected[exchange] = False
                except Exception as e:
                    self.logger.error(f"Error closing {exchange} WebSocket: {e}")
            
            # Clear cache
            self._book_ticker_cache.clear()
            self._trade_cache.clear()
            self._active_symbols.clear()
            
            self.logger.info("All WebSocket connections closed")
            
        except Exception as e:
            self.logger.error(f"Error during WebSocket cleanup: {e}")


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
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize data collector.
        
        Args:
            config_path: Path to configuration file
        """
        # Load configuration
        from applications.data_collection.config import load_data_collector_config
        self.config = load_data_collector_config(config_path)
        
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
    
    async def initialize(self) -> None:
        """Initialize all components."""
        try:
            if not self.config.enabled:
                self.logger.warning("Data collector is disabled in configuration")
                return
            
            self.logger.info("Initializing data collector components")
            
            # Ensure exchange modules are imported to trigger registrations
            self.logger.debug("Importing exchange modules for factory registration...")
            import exchanges.mexc
            import exchanges.gateio
            self.logger.debug("Exchange modules imported successfully")
            
            # Initialize database manager
            from db import DatabaseManager
            
            # Use the centralized database config directly
            db_manager = DatabaseManager()
            await db_manager.initialize(self.config.database)
            self.logger.info("Database connection pool initialized")
            
            # Initialize analytics engine
            from applications.data_collection.analytics import RealTimeAnalytics
            self.analytics = RealTimeAnalytics(self.config.analytics)
            self.logger.info("Analytics engine initialized")
            
            # Initialize WebSocket manager with analytics handler
            self.ws_manager = UnifiedWebSocketManager(
                exchanges=self.config.exchanges,
                book_ticker_handler=self._handle_book_ticker_update,
                trade_handler=self._handle_trades_update
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
            from db.connection import DatabaseManager
            db_manager = DatabaseManager()
            await db_manager.close()
            self.logger.info("Database connection pool closed")
            
            self._running = False
            self.logger.info("Data collector stopped successfully")
            
        except Exception as e:
            self.logger.error(f"Error stopping data collector: {e}")
    
    async def _handle_book_ticker_update(self, exchange: ExchangeEnum, symbol: Symbol, book_ticker: BookTicker) -> None:
        """
        Handle book ticker updates from WebSocket manager.
        
        Routes updates to analytics engine.
        """
        try:
            if self.analytics:
                await self.analytics.on_book_ticker_update(exchange.value, symbol, book_ticker)
        except Exception as e:
            self.logger.error(f"Error handling book ticker update: {e}")
    
    async def _handle_trades_update(self, exchange: ExchangeEnum, symbol: Symbol, trades: List[Trade]) -> None:
        """
        Handle trade updates from WebSocket manager.

        Routes updates to analytics engine.
        """
        try:
            if self.analytics:
                pass
                # Analytics might have a trades handler method
                # Process each trade if analytics supports it
                # for trade in trades:
                #     pass  # Add analytics trade handling if needed

        except Exception as e:
            self.logger.error(f"Error handling trades update: {e}")

    async def _handle_snapshot_storage(self, snapshots: List[BookTickerSnapshot]) -> None:
        """
        Handle snapshot storage to database.
        
        Args:
            snapshots: List of snapshots to store
        """
        try:
            if not snapshots:
                self.logger.debug("No snapshots to store")
                return
            
            self.logger.debug(f"Storing {len(snapshots)} snapshots to database...")
            
            # Store snapshots in database using batch insert
            from db.operations import insert_book_ticker_snapshots_batch
            
            start_time = datetime.now()
            count = await insert_book_ticker_snapshots_batch(snapshots)
            storage_duration = (datetime.now() - start_time).total_seconds() * 1000
            
            self.logger.debug(
                f"Successfully stored {count} snapshots in {storage_duration:.1f}ms"
            )
            
            # Log sample of what was stored for verification
            if snapshots:
                sample = snapshots[0]
                self.logger.debug(
                    f"Sample stored: {sample.exchange} {sample.symbol_base}/{sample.symbol_quote} "
                    f"@ {sample.timestamp} - bid={sample.bid_price} ask={sample.ask_price}"
                )
            
        except Exception as e:
            self.logger.error(f"Error storing snapshots: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    async def _handle_trade_storage(self, trade_snapshots: List[TradeSnapshot]) -> None:
        """
        Handle trade snapshot storage to database.
        
        Args:
            trade_snapshots: List of trade snapshots to store
        """
        try:
            if not trade_snapshots:
                return
            
            # Store trade snapshots in database using batch insert
            from db.operations import insert_trade_snapshots_batch
            
            start_time = datetime.now()
            count = await insert_trade_snapshots_batch(trade_snapshots)
            storage_duration = (datetime.now() - start_time).total_seconds() * 1000
            
            self.logger.debug(
                f"Stored {count} trade snapshots in {storage_duration:.1f}ms"
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
    
    async def get_recent_opportunities(self, minutes: int = 5) -> List['ArbitrageOpportunity']:
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