"""Simplified Task Manager for external loop management of trading tasks.

Provides centralized orchestration of trading tasks with automatic lifecycle management.
"""

import asyncio
import time
from collections import defaultdict
from typing import Dict, List, Optional
from infrastructure.logging import HFTLoggerInterface
from trading.tasks.base_task import BaseTradingTask, TaskExecutionResult
from trading.struct import TradingStrategyState
from exchanges.structs import Symbol


class TaskManager:
    """Simple external loop manager for trading tasks.
    
    Manages task lifecycle and provides centralized control over all trading tasks.
    Tasks on the same symbol are executed sequentially to prevent conflicts.
    """
    
    def __init__(self, logger: HFTLoggerInterface):
        """Initialize TaskManager.
        
        Args:
            logger: HFT logger for task management events
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
    
    async def start(self):
        """Start the task manager execution loop."""
        if self._running:
            self.logger.warning("TaskManager already running")
            return
        
        self._running = True
        self._start_time = time.time()
        self._executor_task = asyncio.create_task(self._execution_loop())
        self.logger.info("TaskManager started")
    
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
        
        self.logger.info(f"TaskManager stopped",
                        total_executions=self._total_executions,
                        runtime_seconds=time.time() - self._start_time)
    
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
                    
                    # Remove completed tasks
                    for result in results:
                        if isinstance(result, TaskExecutionResult) and not result.should_continue:
                            await self.remove_task(result.task_id)
                            self.logger.info(f"Task {result.task_id} completed, removed from manager")
                
                # Minimal sleep for cooperative multitasking
                await asyncio.sleep(0.001)
                
            except Exception as e:
                self.logger.error(f"TaskManager execution loop error", error=str(e))
                await asyncio.sleep(1.0)  # Back off on error
        
        self.logger.info("TaskManager execution loop stopped")
    
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
            "tasks": tasks_info
        }