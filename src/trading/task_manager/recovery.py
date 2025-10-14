"""Task recovery utilities for restoring tasks from persistence.

Provides centralized task recovery logic to reduce complexity in TaskManager.
"""

from typing import Dict, List, Tuple, Optional
import json

from infrastructure.logging import HFTLoggerInterface
from trading.task_manager.persistence import TaskPersistenceManager
from trading.task_manager.serialization import TaskSerializer
from trading.tasks.base_task import BaseTradingTask


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
                return task_parts[0]
            
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
            task.restore_from_json(json_data)
            
            return task
            
        except Exception as e:
            self.logger.error(f"Failed to recover IcebergTask {task_id}", error=str(e))
            return None
    
    async def recover_delta_neutral_task(self, task_id: str, json_data: str) -> Optional['DeltaNeutralTask']:
        """Recover a DeltaNeutralTask from JSON data.
        
        Args:
            task_id: Task identifier
            json_data: JSON string containing task context
            
        Returns:
            Optional[DeltaNeutralTask]: Recovered task or None if failed
        """
        try:
            from trading.tasks.delta_neutral_task import DeltaNeutralTask, DeltaNeutralTaskContext, Direction
            from exchanges.structs import Symbol, ExchangeEnum, Side
            
            # Parse JSON data to extract required fields
            context_data = json.loads(json_data)
            symbol_data = context_data.get('symbol', {})
            exchange_names_data = context_data.get('exchange_names', {})
            
            # Reconstruct required fields for minimal context
            symbol = Symbol(
                base=symbol_data['base'],
                quote=symbol_data['quote']
            )
            
            # Reconstruct exchange_names dict with Side enum keys
            exchange_names = {}
            for side_value, exchange_value in exchange_names_data.items():
                try:
                    # Handle both string names and numeric values
                    if isinstance(side_value, str):
                        # Try enum name first (e.g., "BUY")
                        try:
                            side_key = Side[side_value]  # e.g., "BUY" -> Side.BUY
                        except KeyError:
                            # Try converting string numeric to int (e.g., "1" -> 1)
                            if side_value.isdigit():
                                side_key = Side(int(side_value))  # e.g., "1" -> 1 -> Side.BUY
                            else:
                                raise ValueError(f"Cannot convert '{side_value}' to Side enum")
                    else:
                        side_key = Side(side_value)  # numeric value
                    exchange_names[side_key] = ExchangeEnum(exchange_value) if exchange_value else None
                except (ValueError, KeyError) as e:
                    self.logger.warning(f"Invalid side value {side_value} in exchange_names for task {task_id}: {e}")
                    continue
            
            # Handle legacy data - default to MEXC for both sides if missing
            if not exchange_names:
                exchange_names = {Side.BUY: ExchangeEnum.MEXC, Side.SELL: ExchangeEnum.MEXC}
                self.logger.warning(f"Missing exchange_names in persisted task {task_id}, defaulting to MEXC for both sides")
            
            # Reconstruct other dict fields with defaults
            filled_quantity = {}
            avg_price = {}
            offset_ticks = {}
            tick_tolerance = {}
            order_id = {}
            
            # Helper function to get value from dict with Side keys that may be serialized as strings
            def get_side_value(data_dict: dict, side: Side, default):
                """Get value from dict where Side keys may be serialized as strings."""
                # Try enum name first (e.g., "BUY")
                if side.name in data_dict:
                    return data_dict[side.name]
                # Try string representation of enum value (e.g., "1")
                if str(side.value) in data_dict:
                    return data_dict[str(side.value)]
                # Try direct enum value (e.g., 1)
                if side.value in data_dict:
                    return data_dict[side.value]
                # Try the enum itself as key
                if side in data_dict:
                    return data_dict[side]
                return default

            for side in [Side.BUY, Side.SELL]:
                filled_quantity[side] = get_side_value(context_data.get('filled_quantity', {}), side, 0.0)
                avg_price[side] = get_side_value(context_data.get('avg_price', {}), side, 0.0)
                offset_ticks[side] = get_side_value(context_data.get('offset_ticks', {}), side, 0)
                tick_tolerance[side] = get_side_value(context_data.get('tick_tolerance', {}), side, 1)
                order_id[side] = get_side_value(context_data.get('order_id', {}), side, None)
            
            # Handle direction enum
            direction_value = context_data.get('direction', Direction.NONE.value)
            if isinstance(direction_value, int):
                direction = Direction(direction_value)
            else:
                direction = Direction.NONE
            
            # Create minimal context for task initialization
            context = DeltaNeutralTaskContext(
                symbol=symbol,
                exchange_names=exchange_names,
                total_quantity=context_data.get('total_quantity', 0.0),
                order_quantity=context_data.get('order_quantity', 0.0),
                filled_quantity=filled_quantity,
                avg_price=avg_price,
                direction=direction,
                offset_ticks=offset_ticks,
                tick_tolerance=tick_tolerance,
                order_id=order_id
            )
            
            task = DeltaNeutralTask(self.logger, context)
            
            # Restore full state from JSON
            task.restore_from_json(json_data)
            
            return task
            
        except Exception as e:
            self.logger.error(f"Failed to recover DeltaNeutralTask {task_id}", error=str(e))
            return None
    
    async def recover_spot_futures_arbitrage_task(self, task_id: str, json_data: str) -> Optional['SpotFuturesArbitrageTask']:
        """Recover a SpotFuturesArbitrageTask from JSON data.
        
        Args:
            task_id: Task identifier
            json_data: JSON string containing task context
            
        Returns:
            Optional[SpotFuturesArbitrageTask]: Recovered task or None if failed
        """
        try:
            from trading.tasks.spot_futures_arbitrage_task import SpotFuturesArbitrageTask
            from trading.tasks.arbitrage_task_context import ArbitrageTaskContext
            from exchanges.structs import ExchangeEnum
            
            # Use TaskSerializer to properly deserialize the full context
            context = TaskSerializer.deserialize_context(json_data, ArbitrageTaskContext)
            
            # Extract exchange enums from context (with fallback values)
            spot_exchange = context.spot_exchange if context.spot_exchange else ExchangeEnum.MEXC
            futures_exchange = context.futures_exchange if context.futures_exchange else ExchangeEnum.GATEIO_FUTURES
            
            # Create task with properly deserialized context
            task = SpotFuturesArbitrageTask(self.logger, context, spot_exchange, futures_exchange)
            
            # No need to call restore_from_json since context is already fully deserialized
            
            return task
            
        except Exception as e:
            self.logger.error(f"Failed to recover SpotFuturesArbitrageTask {task_id}", error=str(e))
            import traceback
            traceback.print_exc()
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
        elif task_type == "DeltaNeutralTask":
            return await self.recover_delta_neutral_task(task_id, json_data)
        elif task_type == "SpotFuturesArbitrageTask":
            return await self.recover_spot_futures_arbitrage_task(task_id, json_data)
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