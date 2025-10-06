import asyncio
from abc import ABC, abstractmethod
from typing import Optional, TypeVar, Generic, Type, Dict, Any, List
import msgspec
import time

from config.structs import ExchangeConfig
from exchanges.structs import Symbol, Side, ExchangeEnum
from infrastructure.logging import HFTLoggerInterface
from trading.struct import TradingStrategyState
from trading.task_manager.serialization import TaskSerializer
from exchanges.dual_exchange import DualExchange
from config.config_manager import get_exchange_config


class TaskExecutionResult(msgspec.Struct, frozen=False, kw_only=True):
    """Result from single task execution cycle."""
    task_id: str  # Unique task identifier
    context: 'TaskContext'  # Snapshot of task context after execution
    should_continue: bool = True  # True if task needs more cycles
    next_delay: float = 0.1  # Suggested delay before next execution
    state: TradingStrategyState = TradingStrategyState.IDLE
    error: Optional[Exception] = None
    execution_time_ms: float = 0.0
    metadata: Dict[str, Any] = msgspec.field(default_factory=dict)

class TaskContext(msgspec.Struct, frozen=False, kw_only=True):
    """Base context for all trading tasks.
    
    Contains only universal fields that apply to all task types.
    Task-specific fields should be added in subclasses.
    """
    task_id: str = ""
    state: TradingStrategyState = TradingStrategyState.NOT_STARTED
    error: Optional[Exception] = None
    metadata: Dict[str, Any] = msgspec.field(default_factory=dict)
    should_save_flag: bool = True  # Whether to persist this task

    def evolve(self, **updates) -> 'TaskContext':
        """Create a new context with updated fields.
        
        Supports Django-like syntax for dict field updates:
        - field__key=value for dict field updates
        - Regular field=value for normal updates
        
        Examples:
            # Update dict fields
            ctx.evolve(order_id__buy=None, filled_quantity__sell=100.0)
            
            # Mix regular and dict updates
            ctx.evolve(state=EXECUTING, filled_quantity__buy=50.0)
        """
        dict_updates = {}
        regular_updates = {}
        self.should_save_flag = True  # Mark for saving on any evolve
        for key, value in updates.items():
            if '__' in key:
                # Parse dict field update: field_name__dict_key
                field_name, dict_key_str = key.split('__', 1)
                
                # Get current dict or create new one
                if field_name not in dict_updates:
                    current_dict = getattr(self, field_name, None)
                    if current_dict is None:
                        dict_updates[field_name] = {}
                    else:
                        dict_updates[field_name] = current_dict.copy()
                
                # Convert string keys to proper types
                dict_key = self._convert_dict_key(field_name, dict_key_str)
                
                # Update the dict
                dict_updates[field_name][dict_key] = value
            else:
                regular_updates[key] = value
        
        # Combine all updates
        all_updates = {**regular_updates, **dict_updates}
        return msgspec.structs.replace(self, **all_updates)
    
    def _convert_dict_key(self, field_name: str, key_str: str):
        """Convert string key to appropriate type based on field conventions.
        
        Override in subclasses to handle specific enum conversions.
        """
        # Handle common Side enum conversion
        if key_str.upper() in ['BUY', 'SELL']:
            try:
                from exchanges.structs.common import Side
                return Side.BUY if key_str.upper() == 'BUY' else Side.SELL
            except ImportError:
                pass
        
        # Handle numeric keys
        if key_str.isdigit():
            return int(key_str)
        
        # Handle boolean strings
        if key_str.lower() in ['true', 'false']:
            return key_str.lower() == 'true'
        
        # Default to string
        return key_str
    


T = TypeVar('T', bound=TaskContext)


class BaseTradingTask(Generic[T], ABC):
    """Simplified base class for trading tasks.
    
    Subclasses should:
    1. Define their own context class extending TaskContext
    2. Override context_class property to return their context type
    3. Implement _handle_executing() method
    4. Call evolve_context() to update context during lifecycle
    """
    name: str = "BaseTradingTask"
    
    @property
    @abstractmethod
    def context_class(self) -> Type[T]:
        """Return the context class for this task.

        Subclasses must override this to specify their context type.
        Example:
            @property
            def context_class(self) -> Type[MyTaskContext]:
                return MyTaskContext
        """
        pass

    def __init__(self,
                 logger: HFTLoggerInterface,
                 context: T,
                 delay: float = 0.1):
        """Initialize task with context.
        
        Args:
            logger: HFT logger instance
            context: Trading task context (type depends on task requirements)
            delay: Delay between state cycles
        """
        # Validate provided context type
        if not isinstance(context, TaskContext):
            raise TypeError(f"Context must be a TaskContext, got {type(context)}")
        
        self.logger = logger
        self.delay = delay
        self.context: T = context
        self._tag = "not-set"

        # Generate task_id if not already set
        if not self.context.task_id:
            timestamp = int(time.time() * 1000)  # milliseconds
            # Build basic task_id - subclasses can override to add specific fields
            task_id_parts = [str(timestamp), self.name]
            self.evolve_context(task_id="_".join(task_id_parts))
        
        # State handlers mapping
        self._state_handlers = {
            TradingStrategyState.IDLE: self._handle_idle,
            TradingStrategyState.PAUSED: self._handle_paused,
            TradingStrategyState.ERROR: self._handle_error,
            TradingStrategyState.COMPLETED: self._handle_complete,
            TradingStrategyState.EXECUTING: self._handle_executing,
            TradingStrategyState.ADJUSTING: self._handle_adjusting,
        }

        self._build_tag()

    def _build_tag(self) -> None:
        """Build logging tag based on available context fields.

        Base implementation uses task name. Subclasses can override
        to add task-specific fields to the tag.
        """
        self._tag = self.name


    @property
    def state(self) -> TradingStrategyState:
        """Get current state from context."""
        return self.context.state
    
    @property
    def task_id(self) -> str:
        """Get task_id from context."""
        return self.context.task_id
    
    def evolve_context(self, **updates) -> None:
        """Update context with new fields.
        
        Supports Django-like syntax for dict field updates:
        - field__key=value for dict field updates  
        - Regular field=value for normal updates
        
        Examples:
            # Update dict fields
            self.evolve_context(order_id__buy=None, filled_quantity__sell=100.0)
            
            # Mix regular and dict updates
            self.evolve_context(state=EXECUTING, avg_price__buy=50.5)
            
            # Dynamic key construction
            side_key = 'buy' if order.side == Side.BUY else 'sell'
            self.evolve_context(**{f'filled_quantity__{side_key}': new_quantity})
        
        Args:
            **updates: Fields to update, supporting Django-like dict notation
        """
        self.context = self.context.evolve(**updates)
    


    def save_context(self) -> str:
        """Serialize current context to JSON string for persistence."""
        return TaskSerializer.serialize_context(self.context)
    
    def restore_context(self, data: str) -> None:
        """Restore context from serialized JSON string."""
        self.context = TaskSerializer.deserialize_context(data, self.context_class)
    
    def restore_from_json(self, json_data: str) -> None:
        """Restore task from JSON string data.
        
        Base implementation for task recovery. Subclasses can override
        to add exchange-specific recovery logic (e.g., order fetching).
        
        Args:
            json_data: JSON string containing task context
        """
        try:
            # Use centralized serialization
            self.context = TaskSerializer.deserialize_context(json_data, self.context_class)

            # Rebuild tag after restoration
            self._build_tag()
        except Exception as e:
            # Log the error but don't crash - let the recovery method handle the failure
            if hasattr(self, 'logger'):
                self.logger.error(f"Failed to restore context from JSON", error=str(e))
            # Re-raise the exception so the recovery method knows it failed
            raise

    def _transition(self, new_state: TradingStrategyState) -> None:
        """Transition to a new state.
        
        Args:
            new_state: Target state to transition to
        """
        old_state = self.context.state
        self.logger.info(f"Transitioning from {old_state.name} to {new_state.name}")
        self.evolve_context(state=new_state)

    async def _handle_idle(self):
        """Default idle state handler."""
        self.logger.debug(f"IDLE state for {self._tag}")

    async def _handle_paused(self):
        """Default paused state handler."""
        self.logger.debug(f"PAUSED state for {self._tag}")

    async def _handle_complete(self):
        """Default complete state handler."""
        self.logger.debug(f"COMPLETED state for {self._tag}")

    @abstractmethod
    async def _handle_executing(self):
        """Abstract executing state handler.

        Subclasses must implement this to define execution logic.
        """
        pass

    async def _handle_adjusting(self):
        """Default adjusting state handler."""
        # Actual for arbitrage/delta neutral tasks
        self.logger.debug(f"ADJUSTING state for {self._tag}")

    async def _handle_error(self):
        """Default error state handler."""
        self.logger.error(f"ERROR state for {self._tag}", error=str(self.context.error))

    async def start(self, **context_updates):
        """Initialize the task with optional context updates.
        
        Args:
            **context_updates: Partial context updates to apply before starting
            
        Note: This no longer starts an internal loop. Use execute_once() or TaskManager.
        """
        if context_updates:
            self.evolve_context(**context_updates)
        
        self._transition(TradingStrategyState.IDLE)
    
    async def pause(self):
        self.logger.info(f"Pausing task from state {self.context.state.name}")
        self._transition(TradingStrategyState.PAUSED)

    async def update(self, **context_updates):
        """Update the task with new context data.
        
        Args:
            **context_updates: Partial context updates to apply to existing context
            
        Important:
            - Updates are applied to the existing context
            - Required fields are preserved from current context
            - Pass field_name=value to update specific fields
        """
        self.logger.info(f"Updating task in state {self.context.state.name}")
        
        if context_updates:
            # Partial updates - evolve existing context
            self.evolve_context(**context_updates)
            self.logger.debug(f"Updated context fields: {list(context_updates.keys())}")
        else:
            self.logger.debug("No updates provided to update() method")

    async def execute_once(self) -> TaskExecutionResult:
        """Execute one cycle of the task state machine.
        
        Returns:
            TaskExecutionResult containing execution metadata and continuation info
        """
        start_time = time.time()

        self.context.should_save_flag = False # reset save flag

        result = TaskExecutionResult(
            task_id=self.context.task_id,
            context=self.context,
            state=self.context.state,
            next_delay=self.delay
        )
        
        try:
            # Check if task should continue
            if self.context.state in [TradingStrategyState.COMPLETED, TradingStrategyState.CANCELLED]:
                result.should_continue = False
                return result
            
            # Get handler for current state
            handler = self._state_handlers.get(self.context.state)
            if handler:
                await handler()
            else:
                # No handler for this state
                await self._handle_unhandled_state()
            
            # Update result with current state
            result.state = self.context.state
            
            # Determine if should continue
            result.should_continue = self.context.state not in [
                TradingStrategyState.COMPLETED,
                TradingStrategyState.CANCELLED,
                TradingStrategyState.ERROR
            ]
            
            # Calculate execution time
            result.execution_time_ms = (time.time() - start_time) * 1000
            result.context = self.context
            
        except asyncio.CancelledError:
            self.logger.info(f"Task cancelled during execution: {self._tag}")
            self._transition(TradingStrategyState.CANCELLED)
            result.should_continue = False
            result.state = self.context.state
            result.context = self.context
            raise
            
        except Exception as e:
            self.logger.error(f"Task execution failed {self._tag}", error=str(e))
            traceback.print_exc()
            self.evolve_context(error=e)
            self._transition(TradingStrategyState.ERROR)
            result.error = e
            result.should_continue = False
            result.state = self.context.state
        
        return result
    
    async def _handle_unhandled_state(self):
        """Handle states without explicit handlers.
        
        Subclasses can override to provide custom behavior.
        """
        self.logger.warning(f"No handler for state {self.context.state}, transitioning to ERROR")
        self._transition(TradingStrategyState.ERROR)
    
    async def stop(self):
        """Stop the task gracefully."""
        self.logger.info(f"Stopping task {self._tag}")
        self._transition(TradingStrategyState.COMPLETED)
    
    async def cancel(self):
        """Cancel the task immediately."""
        self.logger.info(f"Cancelling task {self._tag}")
        self._transition(TradingStrategyState.CANCELLED)

    async def complete(self):
        """Mark the task as completed."""
        self.logger.info(f"Completing task {self._tag}")
        self._transition(TradingStrategyState.COMPLETED)

    def _load_exchange(self, exchange_name: ExchangeEnum) -> DualExchange:
        """Load exchange configuration from ExchangeEnum.

        Args:
            exchange_name: Exchange identifier enum

        Returns:
            ExchangeConfig: Loaded exchange configuration

        Raises:
            ValueError: If config loading fails
        """
        try:
            config = get_exchange_config(exchange_name.value)
            return DualExchange(config, self.logger)
        except Exception as e:
            raise ValueError(f"Failed to load config for {exchange_name}: {e}")
