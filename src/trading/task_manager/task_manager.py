"""Simplified Task Manager for external loop management of trading tasks.

Provides centralized orchestration of trading tasks with automatic lifecycle management.
"""

import asyncio
import time
from collections import defaultdict
from typing import Dict, List, Optional
from infrastructure.logging import HFTLoggerInterface
from trading.tasks.base_task import BaseTradingTask, TaskExecutionResult
from trading.task_manager.persistence import TaskPersistenceManager
from trading.task_manager.recovery import TaskRecovery
from trading.struct import TradingStrategyState
from exchanges.structs import Symbol


class TaskManager:
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
        self._tasks: Dict[str, BaseTradingTask] = {}
        self._symbol_locks: Dict[Symbol, asyncio.Lock] = {}
        self._running = False
        self._executor_task: Optional[asyncio.Task] = None
        
        # Track next execution time for each task
        self._next_execution: Dict[str, float] = {}
        
        # Performance metrics
        self._total_executions = 0
        self._start_time = time.time()
        
        # Initialize persistence manager and recovery helper
        self._persistence = TaskPersistenceManager(logger, base_path)
        self._recovery = TaskRecovery(logger, self._persistence)

    @property
    def task_count(self):
        return len(self._tasks)

    async def add_task(self, task: BaseTradingTask) -> str:
        """Add a task for managed execution.
        
        Args:
            task: Trading task to manage
            
        Returns:
            Task ID for reference
        """
        task_id = task.task_id
        
        if task_id in self._tasks:
            raise ValueError(f"Task {task_id} already registered")
        
        self._tasks[task_id] = task
        self._next_execution[task_id] = time.time()  # Ready immediately
        
        self.logger.info(f"Added task {task_id}",
                        symbol=str(task.context.symbol),
                        state=task.state.name)
        
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
            del self._next_execution[task_id]
            
            self.logger.info(f"Removed task {task_id}")
            return True
        
        return False
    
    def get_task(self, task_id: str) -> Optional[BaseTradingTask]:
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
        self._start_time = time.time()
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
        
        self.logger.info(f"TaskManager stopped",
                        total_executions=self._total_executions,
                        runtime_seconds=time.time() - self._start_time)
    
    async def _cleanup_task_resources(self):
        """Clean up all task resources including exchange connections."""
        cleanup_tasks = []
        for task in self._tasks.values():
            if hasattr(task, 'cleanup'):
                cleanup_tasks.append(task.cleanup())
        
        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        
        # Clear tasks
        self._tasks.clear()
        self._next_execution.clear()
    
    def _get_ready_tasks(self) -> List[BaseTradingTask]:
        """Get tasks ready for execution.
        
        Returns:
            List of tasks whose next_execution time has passed
        """
        current_time = time.time()
        ready = []
        
        for task_id, task in self._tasks.items():
            # Skip completed/cancelled tasks
            if task.state in [TradingStrategyState.COMPLETED, TradingStrategyState.CANCELLED]:
                continue
            
            # Check if ready to execute
            if current_time >= self._next_execution.get(task_id, 0):
                ready.append(task)
        
        return ready
    
    async def _execute_task(self, task: BaseTradingTask) -> TaskExecutionResult:
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
                result = await task.execute_once()

                # Save task context to persistence
                if result.context and result.context.should_save_flag:
                    saved = self._persistence.save_context(task.task_id, result.context)
                    if not saved:
                        self.logger.warning(f"Failed to save context for task {task.task_id}")
                
                # Calculate next execution time
                self._next_execution[task.task_id] = time.time() + max(0.001, result.next_delay)
                
                # Update metrics
                self._total_executions += 1
                
                return result
                
            except Exception as e:
                self.logger.error(f"Task {task.task_id} execution failed", error=str(e))
                
                # Create error result and apply backoff
                result = TaskExecutionResult(
                    task_id=task.task_id,
                    context=task.context,
                    should_continue=False,
                    error=e,
                    state=task.state
                )
                
                # Backoff on error
                self._next_execution[task.task_id] = time.time() + 1.0
                
                return result
    
    async def _execution_loop(self):
        """Main loop orchestrating all task executions."""
        self.logger.info("TaskManager execution loop started")
        
        while self._running:
            try:
                # Get tasks ready for execution
                ready_tasks = self._get_ready_tasks()
                
                if not ready_tasks:
                    # No tasks ready, small sleep
                    await asyncio.sleep(0.01)
                    continue
                
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
                        if isinstance(result, TaskExecutionResult) and not result.should_continue:
                            # Remove completed/cancelled tasks from persistence (keep errored)
                            if result.state in [TradingStrategyState.COMPLETED, TradingStrategyState.CANCELLED]:
                                # Save final state first, then it will be auto-cleaned by persistence manager
                                if result.context:
                                    self._persistence.save_context(result.task_id, result.context)
                            
                            await self.remove_task(result.task_id)
                            self.logger.info(f"Task {result.task_id} completed, removed from manager", state=result.state.name)
                
                # Minimal sleep for cooperative multitasking
                await asyncio.sleep(0.001)
                
            except Exception as e:
                self.logger.error(f"TaskManager execution loop error", error=str(e))
                await asyncio.sleep(1.0)  # Back off on error
        
        self.logger.info("TaskManager execution loop stopped")
    
    async def _recover_tasks(self):
        """Recover tasks from persistence storage using TaskRecovery helper."""
        try:
            # Load all active tasks
            active_tasks = await self._recovery.recover_all_tasks()
            recovery_results = []
            
            for task_id, json_data in active_tasks:
                try:
                    # Extract task type
                    task_type = self._recovery.extract_task_type(task_id, json_data)
                    if not task_type:
                        self.logger.warning(f"Could not determine task type for {task_id}")
                        recovery_results.append((task_id, None))
                        continue
                    
                    # Recover task by type
                    task = await self._recovery.recover_task_by_type(task_id, json_data, task_type)
                    recovery_results.append((task_id, task))
                    
                    if task:
                        # Add to manager
                        self._tasks[task_id] = task
                        self._next_execution[task_id] = time.time()  # Ready immediately
                        await task.start()
                        
                        self.logger.info(f"✅ Recovered task {task_id}", 
                                       task_type=task_type,
                                       symbol=str(task.context.symbol) if task.context.symbol else "N/A",
                                       state=task.state.name)
                        
                except Exception as e:
                    self.logger.error(f"Failed to recover task {task_id}", error=str(e))
                    recovery_results.append((task_id, None))
            
            # Log recovery statistics
            stats = self._recovery.get_recovery_stats(recovery_results)
            self.logger.info(f"Task recovery completed", **stats)
            
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
    
    def get_persistence_stats(self) -> Dict[str, int]:
        """Get persistence statistics.
        
        Returns:
            Dictionary with persistence statistics
        """
        return self._persistence.get_statistics()
    
    def get_status(self) -> Dict[str, any]:
        """Get current status of the task manager.
        
        Returns:
            Dictionary with status information
        """
        tasks_info = []
        for task_id, task in self._tasks.items():
            tasks_info.append({
                "task_id": task_id,
                "symbol": str(task.context.symbol),
                "state": task.state.name,
                "next_execution": self._next_execution.get(task_id, 0) - time.time()
            })
        
        return {
            "running": self._running,
            "active_tasks": len(self._tasks),
            "total_executions": self._total_executions,
            "runtime_seconds": time.time() - self._start_time,
            "persistence_stats": self._persistence.get_statistics(),
            "tasks": tasks_info
        }