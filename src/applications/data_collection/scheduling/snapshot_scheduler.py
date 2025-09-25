"""
Snapshot Scheduler - Simplified Implementation

Manages periodic tasks with focus on snapshot operations.
Simplified design with essential scheduling capabilities.
"""

import asyncio
from datetime import datetime
from typing import Optional, Callable, Awaitable, Any, Dict

from infrastructure.logging import get_logger


class SnapshotScheduler:
    """
    Simplified scheduler for periodic snapshot operations.
    
    Responsibilities:
    - Execute periodic snapshots at configured intervals
    - Handle snapshot and trade data processing
    - Provide basic scheduling statistics
    """

    def __init__(self, 
                 interval_seconds: float = 1.0,
                 snapshot_handler: Optional[Callable[..., Awaitable[None]]] = None,
                 trade_handler: Optional[Callable[..., Awaitable[None]]] = None):
        """Initialize snapshot scheduler."""
        self.interval_seconds = interval_seconds
        self.snapshot_handler = snapshot_handler
        self.trade_handler = trade_handler
        
        self.logger = get_logger('data_collection.scheduler')
        self._running = False
        self._snapshot_count = 0
        self._error_count = 0
        self._start_time: Optional[datetime] = None

        self.logger.info("SnapshotScheduler initialized", 
                        interval_seconds=interval_seconds)

    async def start(self, data_source: Any) -> None:
        """Start the snapshot scheduler."""
        if self._running:
            self.logger.warning("Scheduler already running")
            return

        self._running = True
        self._start_time = datetime.now()
        self.logger.info(f"Starting scheduler with {self.interval_seconds}s interval")

        try:
            while self._running:
                await self._take_snapshot(data_source)
                await asyncio.sleep(self.interval_seconds)
        except Exception as e:
            self.logger.error(f"Scheduler error: {e}")
            raise
        finally:
            self._running = False

    async def stop(self) -> None:
        """Stop the scheduler."""
        self.logger.info("Stopping scheduler")
        self._running = False

    async def _take_snapshot(self, data_source: Any) -> None:
        """Take a snapshot using the data source."""
        try:
            # Get ticker snapshots
            ticker_snapshots = []
            if hasattr(data_source, 'get_all_cached_tickers'):
                ticker_snapshots = data_source.get_all_cached_tickers()

            # Get trade snapshots  
            trade_snapshots = []
            if hasattr(data_source, 'get_all_cached_trades'):
                trade_snapshots = data_source.get_all_cached_trades()

            # Process ticker snapshots
            if self.snapshot_handler and ticker_snapshots:
                await self.snapshot_handler(ticker_snapshots)

            # Process trade snapshots
            if self.trade_handler and trade_snapshots:
                await self.trade_handler(trade_snapshots)

            self._snapshot_count += 1

            # Log periodic status
            if self._snapshot_count % 60 == 0:  # Every minute at 1s intervals
                self.logger.info(f"Snapshot #{self._snapshot_count}: "
                               f"Processed {len(ticker_snapshots)} tickers, "
                               f"{len(trade_snapshots)} trades")

        except Exception as e:
            self._error_count += 1
            self.logger.error(f"Error taking snapshot #{self._snapshot_count + 1}: {e}")

    def get_statistics(self) -> Dict[str, Any]:
        """Get scheduler statistics."""
        uptime = 0
        if self._start_time:
            uptime = (datetime.now() - self._start_time).total_seconds()

        return {
            "running": self._running,
            "snapshot_count": self._snapshot_count,
            "error_count": self._error_count,
            "interval_seconds": self.interval_seconds,
            "uptime_seconds": uptime,
            "snapshots_per_minute": (self._snapshot_count / (uptime / 60)) if uptime > 0 else 0,
            "error_rate": (self._error_count / max(self._snapshot_count, 1)) * 100
        }