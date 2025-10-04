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


class TaskExecutionResult(msgspec.Struct, frozen=False, kw_only=True):
    """Result from single task execution cycle."""
    task_id: str  # Unique task identifier
    context: 'TradingTaskContext'  # Snapshot of task context after execution
    should_continue: bool = True  # True if task needs more cycles
    next_delay: float = 0.1  # Suggested delay before next execution
    state: TradingStrategyState = TradingStrategyState.IDLE
    error: Optional[Exception] = None
    execution_time_ms: float = 0.0
    metadata: Dict[str, Any] = msgspec.field(default_factory=dict)

class TaskContext(msgspec.Struct, frozen=False, kw_only=True):
    """Unified flexible context for all trading tasks.
    
    Supports both single-exchange and multi-exchange scenarios with optional fields.
    Use exchange_name + symbol for single-exchange tasks, or exchange_names + symbols
    for multi-exchange tasks.
    """
    task_id: str = ""
    state: TradingStrategyState = TradingStrategyState.NOT_STARTED
    error: Optional[Exception] = None
    metadata: Dict[str, Any] = msgspec.field(default_factory=dict)
    
    # Single-exchange fields (use these for single-exchange tasks)
    exchange_name: Optional[ExchangeEnum] = None
    symbol: Optional[Symbol] = None
    side: Optional[Side] = None
    order_id: Optional[str] = None
    
    # Multi-exchange fields (use these for multi-exchange tasks)
    exchange_names: List[ExchangeEnum] = msgspec.field(default_factory=list)
    symbols: List[Symbol] = msgspec.field(default_factory=list)
    should_save: bool = False  # True if context should be persisted

    def reset_save_flag(self) -> None:
        """Reset the should_save flag after saving."""
        self.should_save = False

    def evolve(self, **updates) -> 'TaskContext':
        """Create a new context with updated fields."""

        self.should_save = True  # Mark context for saving on any update

        return msgspec.structs.replace(self, **updates)


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

        self._should_save = False  # Flag to indicate if context should be persisted


        # Generate task_id if not already set
        if not self.context.task_id:
            timestamp = int(time.time() * 1000)  # milliseconds
            # Build task_id based on available context fields
            task_id_parts = [str(timestamp), self.name]
            
            # Add symbol if available
            if self.context.symbol:
                task_id_parts.append(f"{self.context.symbol.base}_{self.context.symbol.quote}")
            
            # Add side if available
            if self.context.side:
                task_id_parts.append(self.context.side.name)
            
            self.evolve_context(task_id="_".join(task_id_parts))
        
        # Build tag for logging (flexible based on context type)
        self._build_tag()
        
        # State handlers mapping
        self._state_handlers = {
            TradingStrategyState.IDLE: self._handle_idle,
            TradingStrategyState.PAUSED: self._handle_paused,
            TradingStrategyState.ERROR: self._handle_error,
            TradingStrategyState.COMPLETED: self._handle_complete,
            TradingStrategyState.EXECUTING: self._handle_executing,
        }

    @abstractmethod
    def _build_tag(self) -> None:
        """Build logging tag based on available context fields."""
        tag_parts = []
        
        # Add exchange name if available
        if self.config:
            tag_parts.append(self.config.name)
        
        tag_parts.append(self.name)
        
        # Add symbol if available
        if self.context.symbol:
            tag_parts.append(str(self.context.symbol))
        
        # Add side if available
        if self.context.side:
            tag_parts.append(self.context.side.name)
        
        self._tag = "_".join(tag_parts)

    def _load_exchange_config(self, exchange_name: ExchangeEnum) -> ExchangeConfig:
        """Load exchange configuration from ExchangeEnum.
        
        Args:
            exchange_name: Exchange identifier enum
            
        Returns:
            ExchangeConfig: Loaded exchange configuration
            
        Raises:
            ValueError: If config loading fails
        """
        try:
            from config.config_manager import get_exchange_config
            # Convert enum to string format expected by config manager
            # ExchangeEnum.MEXC has value ExchangeName("MEXC_SPOT"), so convert to lowercase
            if hasattr(exchange_name.value, 'value'):
                # Handle ExchangeName wrapper
                config_name = exchange_name.value.value.lower()
            else:
                # Handle direct string value
                config_name = exchange_name.value.lower()
            return get_exchange_config(config_name)
        except Exception as e:
            raise ValueError(f"Failed to load config for {exchange_name}: {e}")

    @property
    def state(self) -> TradingStrategyState:
        """Get current state from context."""
        return self.context.state
    
    @property
    def task_id(self) -> str:
        """Get task_id from context."""
        return self.context.task_id
    
    @property
    def order_id(self) -> Optional[str]:
        """Get current order_id from context."""
        return self.context.order_id

    def evolve_context(self, **updates) -> None:
        """Update context with new fields.
        
        Args:
            **updates: Fields to update in the context
        """
        self.context = self.context.evolve(**updates)
        
        # Rebuild tag if relevant fields changed
        if any(field in updates for field in ['symbol', 'side', 'exchange_name']):
            self._build_tag()
    
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
        # Use centralized serialization
        self.context = TaskSerializer.deserialize_context(json_data, self.context_class)

        # Rebuild tag after restoration
        self._build_tag()
    
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

        self.context.reset_save_flag() # Reset save flag at start, set only if changes in task

        result = TaskExecutionResult(
            task_id=self.context.task_id,
            context=self.context,
            state=self.context.state,
            next_delay=self.delay,
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