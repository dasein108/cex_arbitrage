"""
Balance Sync Task for HFT Trading System

Periodically collects account balances from all private exchange interfaces
and stores them in the balance_snapshots table for analytics and monitoring.
"""

import asyncio
from typing import Optional, Type, Dict, List
from datetime import datetime
import msgspec

from infrastructure.logging import HFTLoggerInterface
from trading.tasks.base_task import TaskContext, BaseTradingTask, TaskExecutionResult
from exchanges.interfaces.composite.base_private_composite import BasePrivateComposite
from exchanges.structs import ExchangeEnum, AssetName, AssetBalance
from db.models import BalanceSnapshot
from db import get_database_manager


class BalanceSyncTaskContext(TaskContext):
    """Context for balance synchronization task.
    
    Extends TaskContext with balance sync specific configuration.
    """
    # Exchange configuration
    exchange_enums: List[ExchangeEnum] = msgspec.field(default_factory=list)
    
    # Sync configuration
    sync_interval_seconds: float = 60.0  # Default 1 minute
    last_sync_timestamp: Optional[datetime] = None
    
    # Performance tracking
    last_sync_duration_ms: float = 0.0
    successful_syncs: int = 0
    failed_syncs: int = 0
    
    # Metadata for monitoring
    last_sync_balances_count: int = 0
    last_error: Optional[str] = None


class BalanceSyncTask(BaseTradingTask[BalanceSyncTaskContext, str]):
    """Periodic task to sync account balances from private exchanges.
    
    Collects balance data from all configured private exchange interfaces
    and stores snapshots in the database for analytics and monitoring.
    
    Features:
    - Configurable sync intervals (default 1 minute)
    - Batch database operations for HFT performance
    - Error handling with automatic recovery
    - Performance monitoring and metrics
    - Supports all composite (non-futures) exchanges
    """
    
    name: str = "BalanceSyncTask"
    
    @property
    def context_class(self) -> Type[BalanceSyncTaskContext]:
        """Return the balance sync context class."""
        return BalanceSyncTaskContext
    
    def __init__(self,
                 logger: HFTLoggerInterface,
                 context: BalanceSyncTaskContext,
                 private_exchanges: Optional[Dict[ExchangeEnum, BasePrivateComposite]] = None,
                 **kwargs):
        """Initialize balance sync task.
        
        Args:
            logger: HFT logger instance
            context: Balance sync task context
            private_exchanges: Optional dict of private exchange instances
            **kwargs: Additional arguments passed to base class
        """
        super().__init__(logger, context, **kwargs)
        
        # Private exchange instances for balance collection
        self._private_exchanges: Dict[ExchangeEnum, BasePrivateComposite] = private_exchanges or {}
        
        # Timing control
        self._last_execution_time: Optional[datetime] = None
        
    def _build_tag(self) -> None:
        """Build logging tag with exchange information."""
        exchange_names = [enum.name for enum in self.context.exchange_enums]
        exchanges_str = ",".join(exchange_names) if exchange_names else "NO_EXCHANGES"
        self._tag = f"{self.name}_{exchanges_str}_INTERVAL:{self.context.sync_interval_seconds}s"
    
    async def _handle_executing(self):
        """Execute balance synchronization cycle.
        
        Collects balances from all configured exchanges and stores them
        in the database. Implements timing control to respect sync intervals.
        """
        current_time = datetime.now()
        
        # Check if enough time has passed since last sync
        if self._should_skip_sync(current_time):
            await asyncio.sleep(0.1)  # Short sleep to prevent busy waiting
            return
        
        self.logger.debug(f"Starting balance sync for {len(self.context.exchange_enums)} exchanges")
        
        try:
            sync_start_time = datetime.now()
            
            # Collect balances from all exchanges
            all_balance_snapshots = await self._collect_all_balances(current_time)
            
            # Store in database if we have data
            if all_balance_snapshots:
                await self._store_balance_snapshots(all_balance_snapshots)
                
                # Update context with success metrics
                sync_duration = (datetime.now() - sync_start_time).total_seconds() * 1000
                self.evolve_context(
                    last_sync_timestamp=current_time,
                    last_sync_duration_ms=sync_duration,
                    successful_syncs=self.context.successful_syncs + 1,
                    last_sync_balances_count=len(all_balance_snapshots),
                    last_error=None
                )
                
                self.logger.info(
                    f"Balance sync completed: {len(all_balance_snapshots)} balances "
                    f"from {len(self.context.exchange_enums)} exchanges in {sync_duration:.1f}ms"
                )
            else:
                self.logger.warning("No balance data collected from any exchange")
                
            # Update last execution time
            self._last_execution_time = current_time
            
        except Exception as e:
            # Handle errors gracefully - don't crash the task
            error_msg = f"Balance sync failed: {str(e)}"
            self.logger.error(error_msg, error=str(e))
            
            self.evolve_context(
                failed_syncs=self.context.failed_syncs + 1,
                last_error=error_msg
            )
            
            # Continue running despite errors
            self._last_execution_time = current_time
    
    def _should_skip_sync(self, current_time: datetime) -> bool:
        """Check if sync should be skipped based on interval timing.
        
        Args:
            current_time: Current timestamp
            
        Returns:
            True if sync should be skipped, False otherwise
        """
        if self._last_execution_time is None:
            return False  # Never executed, should run
            
        time_since_last = (current_time - self._last_execution_time).total_seconds()
        return time_since_last < self.context.sync_interval_seconds
    
    async def _collect_all_balances(self, timestamp: datetime) -> List[BalanceSnapshot]:
        """Collect balance data from all configured exchanges.
        
        Args:
            timestamp: Timestamp to use for all balance snapshots
            
        Returns:
            List of BalanceSnapshot objects
        """
        all_snapshots = []
        
        for exchange_enum in self.context.exchange_enums:
            try:
                snapshots = await self._collect_exchange_balances(exchange_enum, timestamp)
                all_snapshots.extend(snapshots)
                
                self.logger.debug(
                    f"Collected {len(snapshots)} balance entries from {exchange_enum.name}"
                )
                
            except Exception as e:
                self.logger.error(
                    f"Failed to collect balances from {exchange_enum.name}", 
                    error=str(e)
                )
                # Continue with other exchanges
                continue
        
        return all_snapshots
    
    async def _collect_exchange_balances(self, 
                                       exchange_enum: ExchangeEnum, 
                                       timestamp: datetime) -> List[BalanceSnapshot]:
        """Collect balance data from a specific exchange.
        
        Args:
            exchange_enum: Exchange to collect from
            timestamp: Timestamp for the snapshots
            
        Returns:
            List of BalanceSnapshot objects for this exchange
        """
        # Get private exchange instance
        private_exchange = self._private_exchanges.get(exchange_enum)
        if private_exchange is None:
            self.logger.warning(f"No private exchange instance for {exchange_enum.name}")
            return []
        
        # Get exchange database ID using simplified DatabaseManager (PROJECT_GUIDES.md compliant)
        db = get_database_manager()
        exchange_db = db.get_exchange_by_enum(exchange_enum)
        if exchange_db is None:
            self.logger.error(f"Exchange {exchange_enum.name} not found in database")
            return []
        
        # Get current balances from exchange
        try:
            balances_dict = private_exchange.balances
            if not balances_dict:
                self.logger.debug(f"No balances returned from {exchange_enum.name}")
                return []
                
        except Exception as e:
            self.logger.error(
                f"Failed to get balances from {exchange_enum.name}", 
                error=str(e)
            )
            return []
        
        # Convert to BalanceSnapshot objects
        snapshots = []
        for asset_name, asset_balance in balances_dict.items():
            # Skip zero balances to reduce database storage
            if asset_balance.available == 0.0 and asset_balance.locked == 0.0:
                continue
                
            snapshot = BalanceSnapshot(
                exchange_id=exchange_db.id,
                asset_name=str(asset_name),
                available_balance=float(asset_balance.available),
                locked_balance=float(asset_balance.locked),
                timestamp=timestamp
            )
            snapshots.append(snapshot)
        
        return snapshots
    
    async def _store_balance_snapshots(self, snapshots: List[BalanceSnapshot]):
        """Store balance snapshots in database using batch operation.
        
        Args:
            snapshots: List of balance snapshots to store
        """
        if not snapshots:
            return
            
        try:
            db = get_database_manager()
            stored_count = await db.insert_balance_snapshots_batch(snapshots)
            
            self.logger.debug(
                f"Stored {stored_count} balance snapshots in database "
                f"(attempted: {len(snapshots)})"
            )
            
        except Exception as e:
            self.logger.error(
                f"Failed to store {len(snapshots)} balance snapshots", 
                error=str(e)
            )
            raise  # Re-raise to trigger error handling in caller
    
    def add_private_exchange(self, exchange_enum: ExchangeEnum, private_exchange: BasePrivateComposite):
        """Add a private exchange instance for balance collection.
        
        Args:
            exchange_enum: Exchange identifier
            private_exchange: Private exchange instance
        """
        self._private_exchanges[exchange_enum] = private_exchange
        
        # Update context with new exchange if not already present
        if exchange_enum not in self.context.exchange_enums:
            current_enums = list(self.context.exchange_enums)
            current_enums.append(exchange_enum)
            self.evolve_context(exchange_enums=current_enums)
            
            # Rebuild tag with updated exchange list
            self._build_tag()
            
        self.logger.info(f"Added private exchange {exchange_enum.name} for balance sync")
    
    def remove_private_exchange(self, exchange_enum: ExchangeEnum):
        """Remove a private exchange from balance collection.
        
        Args:
            exchange_enum: Exchange identifier to remove
        """
        if exchange_enum in self._private_exchanges:
            del self._private_exchanges[exchange_enum]
            
            # Update context to remove exchange
            current_enums = [e for e in self.context.exchange_enums if e != exchange_enum]
            self.evolve_context(exchange_enums=current_enums)
            
            # Rebuild tag with updated exchange list
            self._build_tag()
            
            self.logger.info(f"Removed private exchange {exchange_enum.name} from balance sync")
    
    def update_sync_interval(self, interval_seconds: float):
        """Update the sync interval.
        
        Args:
            interval_seconds: New sync interval in seconds
        """
        if interval_seconds <= 0:
            raise ValueError("Sync interval must be positive")
            
        self.evolve_context(sync_interval_seconds=interval_seconds)
        self._build_tag()  # Rebuild tag with new interval
        
        self.logger.info(f"Updated balance sync interval to {interval_seconds} seconds")
    
    def get_sync_stats(self) -> Dict[str, any]:
        """Get balance sync performance statistics.
        
        Returns:
            Dictionary with sync performance metrics
        """
        return {
            "successful_syncs": self.context.successful_syncs,
            "failed_syncs": self.context.failed_syncs,
            "last_sync_timestamp": self.context.last_sync_timestamp,
            "last_sync_duration_ms": self.context.last_sync_duration_ms,
            "last_sync_balances_count": self.context.last_sync_balances_count,
            "sync_interval_seconds": self.context.sync_interval_seconds,
            "configured_exchanges": [e.name for e in self.context.exchange_enums],
            "active_exchanges": [e.name for e in self._private_exchanges.keys()],
            "last_error": self.context.last_error
        }