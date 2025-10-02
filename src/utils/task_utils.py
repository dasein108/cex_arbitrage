import asyncio
from typing import List, Optional, Union
import time


async def safe_cancel_task(task: asyncio.Task):
    """Cancel a single task safely, handling CancelledError."""
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    return None


async def cancel_tasks_with_timeout(
    tasks: List[Optional[asyncio.Task]], 
    timeout: float = 2.0,
    logger=None
) -> bool:
    """
    Cancel multiple tasks with timeout protection.
    
    Args:
        tasks: List of asyncio tasks (None entries are ignored)
        timeout: Maximum time to wait for cancellation
        logger: Optional logger for timeout warnings
    
    Returns:
        bool: True if all tasks cancelled within timeout, False if timeout occurred
    """
    if not tasks:
        return True
    
    # Filter out None tasks and already done tasks
    active_tasks = [task for task in tasks if task and not task.done()]
    if not active_tasks:
        return True
    
    # Cancel all tasks
    for task in active_tasks:
        task.cancel()
    
    # Wait for cancellation with timeout
    try:
        await asyncio.wait_for(
            asyncio.gather(*active_tasks, return_exceptions=True),
            timeout=timeout
        )
        return True
    except asyncio.TimeoutError:
        if logger:
            remaining = [task for task in active_tasks if not task.done()]
            logger.warning(f"Task cancellation timed out after {timeout}s. {len(remaining)} tasks still running")
        return False


async def safe_close_connection(
    connection, 
    timeout: float = 1.0,
    logger=None
) -> bool:
    """
    Safely close a connection with timeout protection.
    
    Args:
        connection: Connection object with close() method
        timeout: Maximum time to wait for close
        logger: Optional logger for timeout warnings
    
    Returns:
        bool: True if closed within timeout, False if timeout occurred
    """
    if not connection:
        return True
    
    try:
        await asyncio.wait_for(
            connection.close(),
            timeout=timeout
        )
        return True
    except asyncio.TimeoutError:
        if logger:
            logger.warning(f"Connection close timed out after {timeout}s")
        return False
    except Exception as e:
        if logger:
            logger.error(f"Error closing connection: {e}")
        return False


class TaskManager:
    """
    Centralized task management with automatic cleanup.
    """
    
    def __init__(self, name: str = "task_manager"):
        self.name = name
        self._tasks: List[asyncio.Task] = []
        self._should_stop = False
    
    def create_task(self, coro, name: str = None) -> asyncio.Task:
        """Create and track a task."""
        if self._should_stop:
            raise RuntimeError(f"Cannot create task '{name}' - manager is stopping")
        
        task_name = f"{self.name}.{name}" if name else f"{self.name}.task_{len(self._tasks)}"
        task = asyncio.create_task(coro, name=task_name)
        self._tasks.append(task)
        
        # Auto-remove completed tasks
        def cleanup_task(completed_task):
            try:
                self._tasks.remove(completed_task)
            except ValueError:
                pass  # Task already removed
        
        task.add_done_callback(cleanup_task)
        return task
    
    async def shutdown(self, timeout: float = 2.0, logger=None) -> bool:
        """Shutdown all managed tasks."""
        self._should_stop = True
        
        if not self._tasks:
            return True
        
        # Get tasks that are still running
        active_tasks = [task for task in self._tasks if not task.done()]
        
        success = await cancel_tasks_with_timeout(active_tasks, timeout, logger)
        
        # Clear task list
        self._tasks.clear()
        
        return success
    
    @property
    def active_task_count(self) -> int:
        """Get count of active tasks."""
        return len([task for task in self._tasks if not task.done()])
    
    @property
    def is_stopping(self) -> bool:
        """Check if manager is in shutdown mode."""
        return self._should_stop


def check_should_continue(flag_name: str, flag_value: bool, check_interval: float = 1.0) -> bool:
    """
    Helper to reduce redundant flag checking patterns.
    
    Args:
        flag_name: Name of the flag for logging
        flag_value: Current value of the flag
        check_interval: How often this check happens (for optimization)
    
    Returns:
        bool: Whether operation should continue
    """
    return flag_value


async def drain_message_queue(
    queue: asyncio.Queue, 
    logger=None,
    max_drain_count: int = 1000
) -> int:
    """
    Drain remaining messages from a queue during shutdown.
    
    Args:
        queue: AsyncIO queue to drain
        logger: Optional logger for drain metrics
        max_drain_count: Maximum messages to drain (safety limit)
    
    Returns:
        int: Number of messages drained
    """
    if not queue:
        return 0
    
    drained_count = 0
    
    while not queue.empty() and drained_count < max_drain_count:
        try:
            queue.get_nowait()
            queue.task_done()
            drained_count += 1
        except asyncio.QueueEmpty:
            break
        except Exception as e:
            if logger:
                logger.error(f"Error draining queue: {e}")
            break
    
    if logger and drained_count > 0:
        logger.info(f"Drained {drained_count} pending messages during shutdown")
    
    return drained_count
