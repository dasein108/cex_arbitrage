"""
Simplified Data Collector - Main Orchestrator

Coordinates WebSocket manager, cache manager, analytics, and scheduler.
Simplified design focusing on essential functionality.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any

from config.config_manager import get_data_collector_config
from exchanges.structs import Symbol, BookTicker, Trade, ExchangeEnum
from exchanges.factory import PublicWebsocketHandlers
from infrastructure.logging import get_logger

# Import our decomposed components
from applications.data_collection.websocket.unified_manager import UnifiedWebSocketManager
from applications.data_collection.websocket.connection_monitor import ConnectionMonitor
from applications.data_collection.scheduling.snapshot_scheduler import SnapshotScheduler
from applications.data_collection.caching.cache_manager import CacheManager
from applications.data_collection.analytics import RealTimeAnalytics


class SimplifiedDataCollector:
    """
    Simplified Data Collector orchestrator.
    
    Responsibilities:
    - Initialize and coordinate all components
    - Manage component lifecycle (start/stop)
    - Handle data flow between components
    - Provide monitoring and status interfaces
    """

    def __init__(self):
        """Initialize the simplified data collector."""
        # Load configuration
        self.config = get_data_collector_config()
        self.logger = get_logger('data_collector.simplified_collector')

        # Components (initialized later)
        self.cache_manager: Optional[CacheManager] = None
        self.ws_manager: Optional[UnifiedWebSocketManager] = None
        self.connection_monitor: Optional[ConnectionMonitor] = None
        self.analytics: Optional[RealTimeAnalytics] = None
        self.scheduler: Optional[SnapshotScheduler] = None

        # State
        self._running = False
        self._start_time: Optional[datetime] = None

        self.logger.info("SimplifiedDataCollector initialized")

    async def initialize(self) -> None:
        """Initialize all components."""
        try:
            if not self.config.enabled:
                self.logger.warning("Data collector is disabled in configuration")
                return

            self.logger.info("Initializing simplified data collector components")

            # Ensure exchange modules are imported
            import exchanges.integrations.mexc
            import exchanges.integrations.gateio

            # Initialize database
            from db import DatabaseManager
            db_manager = DatabaseManager()
            await db_manager.initialize(self.config.database)
            self.logger.info("Database initialized")

            # Initialize cache manager
            self.cache_manager = CacheManager()

            # Initialize analytics engine
            if self.config.analytics:
                self.analytics = RealTimeAnalytics(self.config.analytics)
                self.logger.info("Analytics engine initialized")

            # Initialize WebSocket manager with handlers
            handlers = PublicWebsocketHandlers(
                book_ticker_handler=self._handle_book_ticker_update,
                trades_handler=self._handle_trade_update
            )
            
            self.ws_manager = UnifiedWebSocketManager(
                exchanges=self.config.exchanges,
                handlers=handlers
            )

            # Initialize WebSocket connections
            await self.ws_manager.initialize(self.config.symbols)
            
            # Initialize connection monitor
            self.connection_monitor = ConnectionMonitor()
            self.connection_monitor.start_monitoring()

            # Initialize scheduler
            self.scheduler = SnapshotScheduler(
                interval_seconds=self.config.snapshot_interval,
                snapshot_handler=self._handle_snapshot_storage,
                trade_handler=self._handle_trade_storage
            )

            self.logger.info("All components initialized successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize: {e}")
            raise

    async def start(self) -> None:
        """Start the data collection process."""
        if self._running:
            self.logger.warning("Data collector already running")
            return

        if not self.config.enabled:
            self.logger.warning("Data collector is disabled")
            return

        try:
            self._running = True
            self._start_time = datetime.now()
            self.logger.info("Starting simplified data collector")

            # Start scheduler (main loop)
            if self.scheduler and self.cache_manager:
                await self.scheduler.start(self.cache_manager)

        except Exception as e:
            self.logger.error(f"Error during data collection: {e}")
            self._running = False
            raise
        finally:
            self._running = False

    async def stop(self) -> None:
        """Stop the data collection process."""
        self.logger.info("Stopping simplified data collector")

        try:
            # Stop scheduler
            if self.scheduler:
                await self.scheduler.stop()

            # Stop connection monitor
            if self.connection_monitor:
                await self.connection_monitor.stop_monitoring()

            # Close WebSocket connections
            if self.ws_manager:
                await self.ws_manager.close()

            # Close database
            from db.connection import DatabaseManager
            db_manager = DatabaseManager()
            await db_manager.close()

            self._running = False
            self.logger.info("Simplified data collector stopped")

        except Exception as e:
            self.logger.error(f"Error stopping collector: {e}")

    async def _handle_book_ticker_update(self, exchange: ExchangeEnum, symbol: Symbol, book_ticker: BookTicker) -> None:
        """Handle book ticker updates from WebSocket manager."""
        try:
            # Update cache
            if self.cache_manager:
                self.cache_manager.update_book_ticker(exchange, symbol, book_ticker)

            # Update analytics
            if self.analytics:
                await self.analytics.on_book_ticker_update(exchange.value, symbol, book_ticker)

            # Update connection monitor
            if self.connection_monitor and self.ws_manager:
                stats = self.ws_manager.get_statistics()
                # Simplified metrics update
                self.connection_monitor.update_metrics(
                    exchange, 
                    stats.get('total_messages', 0),
                    datetime.now().timestamp()
                )

        except Exception as e:
            self.logger.error(f"Error handling book ticker update: {e}")

    async def _handle_trade_update(self, exchange: ExchangeEnum, symbol: Symbol, trade: Trade) -> None:
        """Handle trade updates from WebSocket manager."""
        try:
            # Update cache
            if self.cache_manager:
                self.cache_manager.update_trade(exchange, symbol, trade)

            # Update analytics (if implemented)
            if self.analytics:
                await self.analytics.on_trade_update(exchange.value, symbol, trade)

        except Exception as e:
            self.logger.error(f"Error handling trade update: {e}")

    async def _handle_snapshot_storage(self, snapshots) -> None:
        """Handle storage of book ticker snapshots."""
        try:
            if not snapshots:
                return

            from db.operations import insert_book_ticker_snapshots_batch
            count = await insert_book_ticker_snapshots_batch(snapshots)
            
            self.logger.debug(f"Stored {count} book ticker snapshots")

        except Exception as e:
            self.logger.error(f"Error storing snapshots: {e}")

    async def _handle_trade_storage(self, trade_snapshots) -> None:
        """Handle storage of trade snapshots."""
        try:
            if not trade_snapshots:
                return

            from db.operations import insert_trade_snapshots_batch
            count = await insert_trade_snapshots_batch(trade_snapshots)
            
            self.logger.debug(f"Stored {count} trade snapshots")

        except Exception as e:
            self.logger.error(f"Error storing trade snapshots: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive status of all components."""
        status = {
            "running": self._running,
            "config": {
                "enabled": self.config.enabled,
                "snapshot_interval": self.config.snapshot_interval,
                "exchanges": [e.value for e in self.config.exchanges],
                "symbols_count": len(self.config.symbols)
            }
        }

        if self._start_time:
            status["uptime_seconds"] = (datetime.now() - self._start_time).total_seconds()

        # Component statuses
        if self.ws_manager:
            status["websocket"] = self.ws_manager.get_connection_status()
            status["websocket_stats"] = self.ws_manager.get_statistics()

        if self.cache_manager:
            status["cache"] = self.cache_manager.get_statistics()

        if self.analytics:
            status["analytics"] = self.analytics.get_statistics()

        if self.scheduler:
            status["scheduler"] = self.scheduler.get_statistics()

        return status

    async def add_symbols(self, symbols: List[Symbol]) -> None:
        """Add symbols to data collection."""
        if self.ws_manager:
            await self.ws_manager.add_symbols(symbols)
            self.config.symbols.extend(symbols)
            self.logger.info(f"Added {len(symbols)} symbols")

    async def get_recent_opportunities(self, minutes: int = 5) -> List[Any]:
        """Get recent arbitrage opportunities."""
        if self.analytics:
            return self.analytics.get_recent_opportunities(minutes)
        return []