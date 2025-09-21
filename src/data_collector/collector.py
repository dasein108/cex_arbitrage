"""
Data Collector - Unified WebSocket Manager and Main Orchestrator

Manages real-time data collection from multiple exchanges using WebSocket connections.
Provides unified interface for MEXC and Gate.io book ticker data collection.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Set, Callable, Awaitable
from dataclasses import dataclass

from core.config import get_exchange_config
from structs.common import Symbol, BookTicker
from core.transport.websocket.structs import PublicWebsocketChannelType
from exchanges.mexc.ws.mexc_ws_public import MexcWebsocketPublic
from exchanges.gateio.ws.gateio_ws_public import GateioWebsocketPublic
from db import BookTickerSnapshot
from exchanges.consts import ExchangeEnum
from .analytics import RealTimeAnalytics

@dataclass
class BookTickerCache:
    """In-memory cache for book ticker data."""
    ticker: BookTicker
    last_updated: datetime
    exchange: str

WEBSOCKET_CHANNELS=[PublicWebsocketChannelType.BOOK_TICKER]

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
        exchanges: List[str],
        book_ticker_handler: Optional[Callable[[str, Symbol, BookTicker], Awaitable[None]]] = None
    ):
        """
        Initialize unified WebSocket manager.
        
        Args:
            exchanges: List of exchange names to connect to
            book_ticker_handler: Handler for book ticker updates
        """
        self.exchanges = exchanges
        self.book_ticker_handler = book_ticker_handler
        
        # Logging
        self.logger = logging.getLogger(__name__)
        
        # Exchange WebSocket clients
        self._exchange_clients: Dict[str, any] = {}
        
        # Book ticker cache: {exchange_symbol: BookTickerCache}
        self._book_ticker_cache: Dict[str, BookTickerCache] = {}
        
        # Active symbols per exchange
        self._active_symbols: Dict[str, Set[Symbol]] = {}
        
        # Connection status
        self._connected: Dict[str, bool] = {}
        
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
    
    async def _initialize_exchange_client(self, exchange: str, symbols: List[Symbol]) -> None:
        """
        Initialize WebSocket client for a specific exchange.
        
        Args:
            exchange: Exchange name (mexc, gateio)
            symbols: Symbols to subscribe to
        """
        try:
            # Create exchange configuration
            config = get_exchange_config(exchange)
            
            # Create WebSocket client based on exchange
            # Optional[Callable[[Symbol, BookTicker], Awaitable[None]]]
            if exchange == "mexc":
                client = MexcWebsocketPublic(
                    config=config,
                    book_ticker_handler=lambda symbol, ticker: self._handle_book_ticker_update(ExchangeEnum.MEXC.value, symbol, ticker)
                )
            elif exchange == "gateio":
                client = GateioWebsocketPublic(
                    config=config,
                    book_ticker_handler=lambda symbol, ticker: self._handle_book_ticker_update(ExchangeEnum.GATEIO.value, symbol, ticker)
                )
            else:
                raise ValueError(f"Unsupported exchange: {exchange}")
            
            # Store client and initialize
            self._exchange_clients[exchange] = client
            self._active_symbols[exchange] = set()
            self._connected[exchange] = False
            
            # Initialize connection and subscribe to symbols
            await client.initialize(symbols, WEBSOCKET_CHANNELS)
            self._active_symbols[exchange].update(symbols)
            self._connected[exchange] = True
            
            self.logger.info(f"Initialized {exchange} WebSocket with {len(symbols)} symbols")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize {exchange} WebSocket: {e}")
            self._connected[exchange.lower()] = False
            raise
    
    async def _handle_book_ticker_update(self, exchange: str, symbol: Symbol, book_ticker: BookTicker) -> None:
        """
        Handle book ticker updates from any exchange.
        
        Args:
            symbol: Symbol that was updated
            book_ticker: Updated book ticker data
        """
        try:
            # Update cache
            cache_key = f"{exchange}_{symbol}"
            self._book_ticker_cache[cache_key] = BookTickerCache(
                ticker=book_ticker,
                last_updated=datetime.now(),
                exchange=exchange
            )
            
            # Call registered handler if available
            if self.book_ticker_handler:
                await self.book_ticker_handler(exchange, symbol, book_ticker)
            
        except Exception as e:
            self.logger.error(f"Error handling book ticker update for {symbol}: {e}")
    
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
                    cache_key = f"{exchange.lower()}_{symbol}"
                    self._book_ticker_cache.pop(cache_key, None)
            
            self.logger.info(f"Removed {len(symbols)} symbols from all exchanges")
            
        except Exception as e:
            self.logger.error(f"Failed to remove symbols: {e}")
    
    def get_latest_book_ticker(self, exchange: str, symbol: Symbol) -> Optional[BookTicker]:
        """
        Get latest book ticker for a specific exchange and symbol.
        
        Args:
            exchange: Exchange name
            symbol: Symbol to get ticker for
            
        Returns:
            BookTicker if available, None otherwise
        """
        cache_key = f"{exchange.lower()}_{symbol}"
        cache_entry = self._book_ticker_cache.get(cache_key)
        
        if cache_entry:
            return cache_entry.ticker
        return None
    
    def get_all_cached_tickers(self) -> List[BookTickerSnapshot]:
        """
        Get all cached book tickers as BookTickerSnapshot objects.
        
        Returns:
            List of BookTickerSnapshot objects
        """
        snapshots = []
        
        for cache_key, cache_entry in self._book_ticker_cache.items():
            # Parse exchange and symbol from cache key
            exchange, symbol_str = cache_key.split("_", 1)
            
            # Find the original Symbol object
            symbol = None
            for active_symbols in self._active_symbols.values():
                for sym in active_symbols:
                    if str(sym) == symbol_str:
                        symbol = sym
                        break
                if symbol:
                    break
            
            if symbol:
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
        
        return snapshots
    
    def get_connection_status(self) -> Dict[str, bool]:
        """
        Get connection status for all exchanges.
        
        Returns:
            Dictionary mapping exchange names to connection status
        """
        return self._connected.copy()
    
    def get_active_symbols_count(self) -> Dict[str, int]:
        """
        Get count of active symbols per exchange.
        
        Returns:
            Dictionary mapping exchange names to symbol counts
        """
        return {
            exchange: len(symbols) 
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
            exchange = cache_key.split("_", 1)[0]
            by_exchange[exchange] = by_exchange.get(exchange, 0) + 1
        
        return {
            "total_cached_tickers": total_cached,
            "tickers_by_exchange": by_exchange,
            "connected_exchanges": sum(1 for connected in self._connected.values() if connected),
            "total_exchanges": len(self._connected)
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
        snapshot_handler: Optional[Callable[[List[BookTickerSnapshot]], Awaitable[None]]] = None
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
        
        self.logger = logging.getLogger(__name__)
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
        """Take a snapshot of all cached book ticker data."""
        try:
            # Get all cached tickers
            snapshots = self.ws_manager.get_all_cached_tickers()
            
            if not snapshots:
                self.logger.debug("No cached tickers available for snapshot")
                return
            
            self._snapshot_count += 1
            
            # Call snapshot handler if available
            if self.snapshot_handler:
                await self.snapshot_handler(snapshots)
            
            # Log snapshot statistics
            cache_stats = self.ws_manager.get_cache_statistics()
            self.logger.debug(
                f"Snapshot #{self._snapshot_count:03d}: "
                f"Captured {len(snapshots)} tickers from "
                f"{cache_stats['connected_exchanges']}/{cache_stats['total_exchanges']} exchanges"
            )
            
        except Exception as e:
            self.logger.error(f"Error taking snapshot: {e}")
    
    def get_statistics(self) -> Dict[str, any]:
        """Get scheduler statistics."""
        return {
            "running": self._running,
            "snapshot_count": self._snapshot_count,
            "interval_seconds": self.interval_seconds
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
        from data_collector.config import load_data_collector_config
        self.config = load_data_collector_config(config_path)
        
        # Logging
        self.logger = logging.getLogger(__name__)
        
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
            
            # Initialize database manager
            from db import DatabaseManager
            
            # Use the centralized database config directly
            db_manager = DatabaseManager()
            await db_manager.initialize(self.config.database)
            self.logger.info("Database connection pool initialized")
            
            # Initialize analytics engine
            from data_collector.analytics import RealTimeAnalytics
            self.analytics = RealTimeAnalytics(self.config.analytics)
            
            # Initialize WebSocket manager with analytics handler
            self.ws_manager = UnifiedWebSocketManager(
                exchanges=self.config.exchanges,
                book_ticker_handler=self._handle_book_ticker_update
            )
            
            # Initialize WebSocket connections
            await self.ws_manager.initialize(self.config.symbols)
            
            # Initialize snapshot scheduler with database handler
            self.scheduler = SnapshotScheduler(
                ws_manager=self.ws_manager,
                interval_seconds=self.config.snapshot_interval,
                snapshot_handler=self._handle_snapshot_storage
            )
            
            self.logger.info("All data collector components initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize data collector: {e}")
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
    
    async def _handle_book_ticker_update(self, exchange: str, symbol: Symbol, book_ticker: BookTicker) -> None:
        """
        Handle book ticker updates from WebSocket manager.
        
        Routes updates to analytics engine.
        """
        try:
            if self.analytics:
                await self.analytics.on_book_ticker_update(exchange, symbol, book_ticker)
        except Exception as e:
            self.logger.error(f"Error handling book ticker update: {e}")
    
    async def _handle_snapshot_storage(self, snapshots: List[BookTickerSnapshot]) -> None:
        """
        Handle snapshot storage to database.
        
        Args:
            snapshots: List of snapshots to store
        """
        try:
            if not snapshots:
                return
            
            # Store snapshots in database using batch insert
            from db.operations import insert_book_ticker_snapshots_batch
            
            start_time = datetime.now()
            count = await insert_book_ticker_snapshots_batch(snapshots)
            storage_duration = (datetime.now() - start_time).total_seconds() * 1000
            
            self.logger.debug(
                f"Stored {count} snapshots in {storage_duration:.1f}ms"
            )
            
        except Exception as e:
            self.logger.error(f"Error storing snapshots: {e}")
    
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
                "symbols_count": len(self.config.symbols)
            }
        }
        
        if self._start_time:
            status["uptime_seconds"] = (datetime.now() - self._start_time).total_seconds()
        
        # WebSocket manager status
        if self.ws_manager:
            status["websocket"] = {
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