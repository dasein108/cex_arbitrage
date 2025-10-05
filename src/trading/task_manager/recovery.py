"""Task recovery utilities for restoring tasks from persistence.

Provides centralized task recovery logic to reduce complexity in TaskManager.
"""

from typing import Dict, List, Tuple, Optional
import json

from infrastructure.logging import HFTLoggerInterface
from trading.task_manager.persistence import TaskPersistenceManager
from trading.task_manager.serialization import TaskSerializer


class TaskRecovery:
    """Handles task recovery from persistence storage."""
    
    def __init__(self, logger: HFTLoggerInterface, persistence: TaskPersistenceManager):
        self.logger = logger
        self.persistence = persistence
    
    async def recover_all_tasks(self) -> List[Tuple[str, str]]:
        """Load all active tasks for recovery.
        
        Returns:
            List[Tuple[str, str]]: List of (task_id, json_data) tuples
        """
        try:
            active_tasks = self.persistence.load_active_tasks()
            self.logger.info(f"Found {len(active_tasks)} tasks to recover")
            return active_tasks
            
        except Exception as e:
            self.logger.error("Failed to load active tasks for recovery", error=str(e))
            return []
    
    def extract_task_type(self, task_id: str, json_data: str) -> Optional[str]:
        """Extract task type from task data.
        
        Args:
            task_id: Task identifier
            json_data: JSON string containing task data
            
        Returns:
            Optional[str]: Task type name or None if cannot determine
        """
        try:
            # First try to extract from task_id format: {timestamp}_{task_name}_{symbol}_{side}
            task_parts = task_id.split('_')
            if len(task_parts) >= 2:
                return task_parts[1]
            
            # Fallback: extract from metadata if available
            metadata = TaskSerializer.extract_task_metadata(json_data)
            return metadata.get('task_type')
            
        except Exception as e:
            self.logger.warning(f"Failed to extract task type from {task_id}", error=str(e))
            return None
    
    async def recover_iceberg_task(self, task_id: str, json_data: str) -> Optional['IcebergTask']:
        """Recover an IcebergTask from JSON data.
        
        Args:
            task_id: Task identifier
            json_data: JSON string containing task context
            
        Returns:
            Optional[IcebergTask]: Recovered task or None if failed
        """
        try:
            from trading.tasks.iceberg_task import IcebergTask, IcebergTaskContext
            from exchanges.structs import Symbol, ExchangeEnum
            
            # Parse JSON data to extract required fields
            context_data = json.loads(json_data)
            symbol_data = context_data.get('symbol', {})
            exchange_name_value = context_data.get('exchange_name')
            
            # Reconstruct required fields for minimal context
            symbol = Symbol(
                base=symbol_data['base'],
                quote=symbol_data['quote']
            )
            
            # Handle legacy data without exchange_name
            if exchange_name_value:
                exchange_name = ExchangeEnum(exchange_name_value)
            else:
                # Default to MEXC for legacy data (adjust as needed)
                exchange_name = ExchangeEnum.MEXC
                self.logger.warning(f"Missing exchange_name in persisted task {task_id}, defaulting to MEXC")
            
            # Create minimal context for task initialization
            context = IcebergTaskContext(
                symbol=symbol, 
                exchange_name=exchange_name,
                total_quantity=context_data.get('total_quantity', 0.0),
                order_quantity=context_data.get('order_quantity', 0.0),
                filled_quantity=context_data.get('filled_quantity', 0.0),
                offset_ticks=context_data.get('offset_ticks', 0),
                tick_tolerance=context_data.get('tick_tolerance', 1),
                avg_price=context_data.get('avg_price', 0.0)
            )
            task = IcebergTask(self.logger, context)
            
            # Restore full state from JSON
            await task.restore_from_json(json_data)
            
            return task
            
        except Exception as e:
            self.logger.error(f"Failed to recover IcebergTask {task_id}", error=str(e))
            return None
    
    async def recover_task_by_type(self, task_id: str, json_data: str, task_type: str) -> Optional['BaseTradingTask']:
        """Recover a task based on its type.
        
        Args:
            task_id: Task identifier
            json_data: JSON string containing task data
            task_type: Type of task to recover
            
        Returns:
            Optional[BaseTradingTask]: Recovered task or None if failed
        """
        if task_type == "IcebergTask":
            return await self.recover_iceberg_task(task_id, json_data)
        else:
            self.logger.warning(f"Unknown task type {task_type} for task {task_id}")
            return None
    
    def get_recovery_stats(self, recovered_tasks: List[Tuple[str, Optional['BaseTradingTask']]]) -> Dict[str, int]:
        """Generate recovery statistics.
        
        Args:
            recovered_tasks: List of (task_id, task) tuples
            
        Returns:
            Dict[str, int]: Recovery statistics
        """
        total_found = len(recovered_tasks)
        successful = sum(1 for _, task in recovered_tasks if task is not None)
        failed = total_found - successful
        
        return {
            'total_found': total_found,
            'successful': successful,
            'failed': failed
        }