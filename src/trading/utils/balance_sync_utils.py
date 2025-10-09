"""
Balance Sync Utilities

Helper functions for setting up and managing balance synchronization
across multiple exchanges in HFT trading systems.
"""

from typing import Dict, List, Optional
from datetime import datetime

from infrastructure.logging import HFTLoggerInterface
from trading.tasks.balance_sync_task import BalanceSyncTask, BalanceSyncTaskContext
from trading.task_manager.task_manager import TaskManager
from exchanges.structs import ExchangeEnum
from exchanges.interfaces.composite.base_private_composite import BasePrivateComposite


async def create_balance_sync_task(
    logger: HFTLoggerInterface,
    exchange_enums: List[ExchangeEnum],
    sync_interval_seconds: float = 60.0,
    task_manager: Optional[TaskManager] = None
) -> BalanceSyncTask:
    """Create a balance sync task with specified configuration.
    
    Args:
        logger: HFT logger instance
        exchange_enums: List of exchanges to monitor
        sync_interval_seconds: Sync interval in seconds (default 1 minute)
        task_manager: Optional task manager to register with
        
    Returns:
        Configured BalanceSyncTask instance
    """
    # Create task context
    context = BalanceSyncTaskContext(
        exchange_enums=exchange_enums,
        sync_interval_seconds=sync_interval_seconds,
        task_id=f"balance_sync_{int(datetime.now().timestamp())}"
    )
    
    # Create task
    balance_sync_task = BalanceSyncTask(
        logger=logger,
        context=context
    )
    
    # Register with task manager if provided
    if task_manager:
        await task_manager.add_task(balance_sync_task)
        logger.info(f"Registered balance sync task with TaskManager: {balance_sync_task.task_id}")
    
    return balance_sync_task


async def setup_balance_sync_for_exchanges(
    logger: HFTLoggerInterface,
    private_exchanges: Dict[ExchangeEnum, BasePrivateComposite],
    sync_interval_seconds: float = 60.0,
    task_manager: Optional[TaskManager] = None
) -> BalanceSyncTask:
    """Set up balance synchronization for a collection of private exchanges.
    
    Args:
        logger: HFT logger instance
        private_exchanges: Dict mapping exchange enums to private exchange instances
        sync_interval_seconds: Sync interval in seconds (default 1 minute)
        task_manager: Optional task manager to register with
        
    Returns:
        Configured and connected BalanceSyncTask instance
    """
    exchange_enums = list(private_exchanges.keys())
    
    # Create balance sync task
    balance_sync_task = await create_balance_sync_task(
        logger=logger,
        exchange_enums=exchange_enums,
        sync_interval_seconds=sync_interval_seconds,
        task_manager=task_manager
    )
    
    # Register all private exchanges
    for exchange_enum, private_exchange in private_exchanges.items():
        balance_sync_task.add_private_exchange(exchange_enum, private_exchange)
        
        # If the exchange supports balance sync mixin, register it
        if hasattr(private_exchange, 'register_balance_sync'):
            private_exchange.register_balance_sync(balance_sync_task, exchange_enum)
    
    logger.info(
        f"Set up balance sync for {len(private_exchanges)} exchanges: "
        f"{[e.name for e in exchange_enums]}"
    )
    
    return balance_sync_task


def get_balance_sync_stats_summary(balance_sync_task: BalanceSyncTask) -> str:
    """Get a formatted summary of balance sync statistics.
    
    Args:
        balance_sync_task: Balance sync task instance
        
    Returns:
        Formatted statistics string
    """
    stats = balance_sync_task.get_sync_stats()
    
    summary_lines = [
        f"Balance Sync Statistics:",
        f"  Successful syncs: {stats['successful_syncs']}",
        f"  Failed syncs: {stats['failed_syncs']}",
        f"  Last sync: {stats['last_sync_timestamp']}",
        f"  Last duration: {stats['last_sync_duration_ms']:.1f}ms",
        f"  Last balances count: {stats['last_sync_balances_count']}",
        f"  Sync interval: {stats['sync_interval_seconds']}s",
        f"  Configured exchanges: {stats['configured_exchanges']}",
        f"  Active exchanges: {stats['active_exchanges']}"
    ]
    
    if stats['last_error']:
        summary_lines.append(f"  Last error: {stats['last_error']}")
    
    return "\n".join(summary_lines)


async def stop_balance_sync_task(
    balance_sync_task: BalanceSyncTask,
    task_manager: Optional[TaskManager] = None
) -> None:
    """Gracefully stop a balance sync task.
    
    Args:
        balance_sync_task: Balance sync task to stop
        task_manager: Optional task manager to unregister from
    """
    # Stop the task
    await balance_sync_task.stop()
    
    # Remove from task manager if provided
    if task_manager:
        await task_manager.remove_task(balance_sync_task.task_id)
    
    balance_sync_task.logger.info(f"Stopped balance sync task: {balance_sync_task.task_id}")


class BalanceSyncManager:
    """High-level manager for balance synchronization across multiple exchange systems.
    
    Provides a convenient interface for managing balance sync tasks across
    different trading strategies and exchange configurations.
    """
    
    def __init__(self, logger: HFTLoggerInterface, task_manager: Optional[TaskManager] = None):
        """Initialize balance sync manager.
        
        Args:
            logger: HFT logger instance
            task_manager: Optional task manager for automatic lifecycle management
        """
        self.logger = logger
        self.task_manager = task_manager
        self._balance_sync_tasks: Dict[str, BalanceSyncTask] = {}
    
    async def create_sync_group(self,
                              group_name: str,
                              private_exchanges: Dict[ExchangeEnum, BasePrivateComposite],
                              sync_interval_seconds: float = 60.0) -> str:
        """Create a new balance sync group.
        
        Args:
            group_name: Unique name for this sync group
            private_exchanges: Dict of private exchanges to sync
            sync_interval_seconds: Sync interval in seconds
            
        Returns:
            Task ID of the created balance sync task
        """
        if group_name in self._balance_sync_tasks:
            raise ValueError(f"Balance sync group '{group_name}' already exists")
        
        balance_sync_task = await setup_balance_sync_for_exchanges(
            logger=self.logger,
            private_exchanges=private_exchanges,
            sync_interval_seconds=sync_interval_seconds,
            task_manager=self.task_manager
        )
        
        self._balance_sync_tasks[group_name] = balance_sync_task
        
        self.logger.info(f"Created balance sync group '{group_name}' with {len(private_exchanges)} exchanges")
        
        return balance_sync_task.task_id
    
    async def remove_sync_group(self, group_name: str) -> bool:
        """Remove a balance sync group.
        
        Args:
            group_name: Name of the sync group to remove
            
        Returns:
            True if group was removed, False if not found
        """
        if group_name not in self._balance_sync_tasks:
            return False
        
        balance_sync_task = self._balance_sync_tasks[group_name]
        await stop_balance_sync_task(balance_sync_task, self.task_manager)
        
        del self._balance_sync_tasks[group_name]
        
        self.logger.info(f"Removed balance sync group '{group_name}'")
        
        return True
    
    def get_sync_group(self, group_name: str) -> Optional[BalanceSyncTask]:
        """Get a balance sync task by group name.
        
        Args:
            group_name: Name of the sync group
            
        Returns:
            BalanceSyncTask instance if found, None otherwise
        """
        return self._balance_sync_tasks.get(group_name)
    
    def get_all_groups(self) -> Dict[str, BalanceSyncTask]:
        """Get all balance sync groups.
        
        Returns:
            Dict mapping group names to BalanceSyncTask instances
        """
        return self._balance_sync_tasks.copy()
    
    def get_summary(self) -> str:
        """Get a summary of all balance sync groups.
        
        Returns:
            Formatted summary string
        """
        if not self._balance_sync_tasks:
            return "No balance sync groups configured"
        
        summary_lines = [f"Balance Sync Groups ({len(self._balance_sync_tasks)} groups):"]
        
        for group_name, task in self._balance_sync_tasks.items():
            stats = task.get_sync_stats()
            summary_lines.append(
                f"  {group_name}: {len(stats['active_exchanges'])} exchanges, "
                f"{stats['successful_syncs']} syncs, "
                f"{stats['sync_interval_seconds']}s interval"
            )
        
        return "\n".join(summary_lines)