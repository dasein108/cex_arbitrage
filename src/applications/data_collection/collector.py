"""
Simplified Data Collector - Minimal Working Version

Collects and saves:
1. Book ticker snapshots
2. Funding rates  
3. Trades

Simple architecture with minimal dependencies.
"""

import asyncio
import logging
from typing import List

from applications.data_collection.collector_ws_manager import CollectorWebSocketManager
from applications.data_collection.snapshot_scheduler import SnapshotScheduler
from exchanges.structs import Symbol, ExchangeEnum
from db import close_database_manager, initialize_database_manager, get_database_manager


class DataCollector:
    """Simple data collector for funding rates, book tickers, and trades."""
    
    def __init__(self, exchanges: List[ExchangeEnum], symbols: List[Symbol]):
        self.exchanges = exchanges
        self.symbols = symbols
        self.logger = logging.getLogger('data_collector')
        self.ws_manager = None
        self.scheduler = None
        self.db = None
        self._running = False
        
    async def initialize(self) -> None:
        """Initialize database and WebSocket connections."""
        try:
            # Initialize database
            await initialize_database_manager()
            self.db = await get_database_manager()
            self.logger.info("Database initialized")
            
            # Initialize WebSocket manager
            self.ws_manager = CollectorWebSocketManager(self.exchanges, self.db)
            await self.ws_manager.initialize(self.symbols)
            self.logger.info("WebSocket manager initialized")
            
            # Initialize scheduler
            self.scheduler = SnapshotScheduler(self.ws_manager, interval_seconds=5)
            self.logger.info("Scheduler initialized")
            
        except Exception as e:
            self.logger.error(f"Initialization failed: {e}")
            raise
            
    async def start(self) -> None:
        """Start data collection."""
        if self._running:
            return
            
        self._running = True
        self.logger.info("Starting data collection")
        
        try:
            await self.scheduler.start()
        except Exception as e:
            self.logger.error(f"Data collection error: {e}")
            self._running = False
            raise
        finally:
            self._running = False
            
    async def stop(self) -> None:
        """Stop data collection."""
        self.logger.info("Stopping data collection")
        
        if self.scheduler:
            await self.scheduler.stop()
            
        if self.ws_manager:
            await self.ws_manager.close()
            
        if self.db:
            await close_database_manager()
            
        self._running = False

