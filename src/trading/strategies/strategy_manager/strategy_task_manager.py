"""Simplified Task Manager for external loop management of trading tasks.

Provides centralized orchestration of trading tasks with automatic lifecycle management.
"""

import asyncio
import traceback
from collections import defaultdict
from typing import Dict, Optional
from infrastructure.logging import HFTLoggerInterface
from .task_persistence_manager import TaskPersistenceManager
from exchanges.structs import Symbol
from trading.strategies.implementations.base_strategy.base_strategy import BaseStrategyTask, TaskResult
from trading.strategies.implementations.cross_exchange_arbitrage_strategy.cross_exchange_arbitrage_task import CrossExchangeArbitrageTaskContext, CrossExchangeArbitrageTask

TASK_TYPE_MAP = {
    CrossExchangeArbitrageTaskContext.task_type: (CrossExchangeArbitrageTaskContext, CrossExchangeArbitrageTask),
}

class StrategyTaskManager:
    """Simple external loop manager for trading tasks.
    
    Manages task lifecycle and provides centralized control over all trading tasks.
    Tasks on the same symbol are executed sequentially to prevent conflicts.
    """
    
    def __init__(self, logger: HFTLoggerInterface, base_path: str = "task_data"):
        """Initialize TaskManager.
        
        Args:
            logger: HFT logger for task management events
            base_path: Base path for task persistence storage
        """
        self.logger = logger
        self._tasks: Dict[str, BaseStrategyTask] = {}

        # lock avoid task concurrency on same symbol
        self._symbol_locks: Dict[Symbol, asyncio.Lock] = {}
        self._running = False
        self._executor_task: Optional[asyncio.Task] = None
        
        # Initialize persistence manager and recovery helper
        self._persistence = TaskPersistenceManager(logger, base_path)

    @property
    def task_count(self):
        return len(self._tasks)

    async def add_task(self, task: BaseStrategyTask) -> str:
        """Add a task for managed execution.
        
        For strategy tasks with deterministic IDs, duplicate tasks are handled gracefully.
        For non-strategy tasks, duplicates raise an error.
        
        Args:
            task: Trading task to manage
            
        Returns:
            Task ID for reference
        """
        task_id = task.task_id
        
        self._tasks[task_id] = task
        self.logger.info(f"Added {task.tag} task {task_id}",
                         symbol=str(task.context.symbol),
                         state=task.status)
        
        return task_id
    
    async def remove_task(self, task_id: str) -> bool:
        """Remove task from management.
        
        Args:
            task_id: ID of task to remove
            
        Returns:
            True if task was removed, False if not found
        """
        if task_id in self._tasks:
            del self._tasks[task_id]

            self.logger.info(f"Removed task {task_id}")
            return True
        
        return False
    
    def get_task(self, task_id: str) -> Optional[BaseStrategyTask]:
        """Get task by ID.
        
        Args:
            task_id: Task identifier
            
        Returns:
            Task if found, None otherwise
        """
        return self._tasks.get(task_id)
    

    async def start(self, recover_tasks: bool = False):
        """Start the task manager execution loop.
        
        Args:
            recover_tasks: If True, recover tasks from persistence storage
        """
        if self._running:
            self.logger.warning("TaskManager already running")
            return
        
        # Recover tasks if requested
        if recover_tasks:
            await self._recover_tasks()
        
        self._running = True
        self._executor_task = asyncio.create_task(self._execution_loop())
        self.logger.info("TaskManager started", recover_tasks=recover_tasks)
    
    async def stop(self):
        """Stop the task manager gracefully."""
        if not self._running:
            return
        
        self.logger.info("Stopping TaskManager...")
        self._running = False
        
        if self._executor_task:
            try:
                await asyncio.wait_for(self._executor_task, timeout=5.0)
            except asyncio.TimeoutError:
                self.logger.warning("TaskManager stop timeout, cancelling...")
                self._executor_task.cancel()
                try:
                    await self._executor_task
                except asyncio.CancelledError:
                    pass
        
        # Clean up all task resources
        await self._cleanup_task_resources()

    
    async def _cleanup_task_resources(self):
        """Clean up all task resources including exchange connections."""
        cleanup_tasks = []
        for task in self._tasks.values():
            cleanup_tasks.append(task.cleanup())
        
        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        
        # Clear tasks
        self._tasks.clear()

    
    async def _execute_task(self, task: BaseStrategyTask) -> TaskResult:
        """Execute a single task.
        
        Args:
            task: Task to execute
            
        Returns:
            Execution result from the task
        """
        symbol = task.context.symbol
        
        # Get or create lock for symbol (sequential execution per symbol)
        if symbol not in self._symbol_locks:
            self._symbol_locks[symbol] = asyncio.Lock()
        
        # Execute with symbol lock to prevent conflicts
        async with self._symbol_locks[symbol]:
            try:
                await task.process()

                # Save task context to persistence
                if task.context.should_save_flag:
                    saved = self._persistence.save_context(task.context.to_json())
                    if not saved:
                        self.logger.warning(f"Failed to save context for task {task.task_id}")
                    # reset save flag
                    task.context.should_save_flag = False
                
            except Exception as e:
                self.logger.error(f"Task {task.task_id} execution failed", error=str(e))

        return TaskResult(task_id=task.task_id, status=task.status)

    async def _execution_loop(self):
        """Main loop orchestrating all task executions."""
        self.logger.info("TaskManager execution loop started")
        
        while self._running:
            try:
                # Get tasks ready for execution
                ready_tasks = self._tasks.values()
                

                # Group tasks by symbol
                by_symbol = defaultdict(list)
                for task in ready_tasks:
                    by_symbol[task.context.symbol].append(task)
                
                # Execute tasks - parallel across symbols, sequential within symbol
                coroutines = []
                for symbol, symbol_tasks in by_symbol.items():
                    # Tasks on same symbol execute sequentially via lock
                    for task in symbol_tasks:
                        coroutines.append(self._execute_task(task))
                
                if coroutines:
                    # Execute all tasks (symbol locks handle sequencing)
                    results = await asyncio.gather(*coroutines, return_exceptions=True)
                    
                    # Remove completed tasks and cleanup persistence
                    for result in results:
                        if isinstance(result, TaskResult):
                            # Remove completed/cancelled/error tasks from persistence
                            if result in ['completed', 'cancelled', 'error']:
                                self._persistence.save_context(self._tasks[result.task_id].context.to_json())
                            
                                await self.remove_task(result.task_id)
                                self.logger.info(f"Task {result.task_id} ', removed from manager", state=result.status)
                
                # Minimal sleep for cooperative multitasking
                await asyncio.sleep(0.001)
                
            except Exception as e:
                self.logger.error(f"TaskManager execution loop error", error=str(e))
                traceback.print_exc()
                await asyncio.sleep(1.0)  # Back off on error
        
        self.logger.info("TaskManager execution loop stopped")

    async def _recover_tasks(self):
        """Recover tasks from persistence storage using TaskRecovery helper."""
        try:
            # Load all active tasks
            raw_contexts = self._persistence.load_active_task_raw_context()

            for task_id, json_data in raw_contexts:
                try:
                    # Extract task type
                    task_type = task_id.split(".")[0]
                    if task_type not in TASK_TYPE_MAP:
                        self.logger.warning(f"Unknown task type for {task_id}")
                        continue

                    context_cls, task_cls = TASK_TYPE_MAP[task_type]
                    task = task_cls(context_cls.from_json(json_data))
                    # Recover task by type

                    if task:
                        # Add to manager
                        self._tasks[task_id] = task
                        await task.start()
                        
                        self.logger.info(f"✅ Recovered task {task_id}",
                                         task_type=task_type,
                                         symbol=str(task.context.symbol) if task.context.symbol else "N/A",
                                         state=task.status)

                except Exception as e:
                    self.logger.error(f"Failed to recover task {task_id}", error=str(e))
                    traceback.print_exc()

            # Run cleanup of old completed tasks
            self._persistence.cleanup_completed()
            
        except Exception as e:
            self.logger.error("Failed to recover tasks", error=str(e))
    
    def cleanup_persistence(self, max_age_hours: int = 24):
        """Cleanup old completed tasks from persistence.
        
        Args:
            max_age_hours: Maximum age in hours before cleanup
        """
        self._persistence.cleanup_completed(max_age_hours)
