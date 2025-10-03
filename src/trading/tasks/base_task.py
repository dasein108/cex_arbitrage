import asyncio
from abc import ABC, abstractmethod
from typing import Optional, TypeVar, Generic, Type, Dict, Any
import msgspec
import time

from config.structs import ExchangeConfig
from exchanges.structs import Symbol, Side
from infrastructure.logging import HFTLoggerInterface
from trading.struct import TradingStrategyState


class TaskExecutionResult(msgspec.Struct, frozen=False):
    """Result from single task execution cycle."""
    task_id: str  # Unique task identifier
    should_continue: bool = True  # True if task needs more cycles
    next_delay: float = 0.1  # Suggested delay before next execution
    state: TradingStrategyState = TradingStrategyState.IDLE
    error: Optional[Exception] = None
    execution_time_ms: float = 0.0
    metadata: Dict[str, Any] = msgspec.field(default_factory=dict)


class TradingTaskContext(msgspec.Struct, frozen=False, kw_only=True):
    """Base context for trading tasks with partial update support.
    
    Supports evolution pattern where fields can be added incrementally
    through the task lifecycle.
    
    Note: symbol is REQUIRED and must be provided at initialization.
    Other fields can be added later via evolve().
    """
    symbol: Symbol  # Required field - no default
    side: Optional[Side] = None
    error: Optional[Exception] = None
    metadata: Dict[str, Any] = msgspec.field(default_factory=dict)
    
    def evolve(self, **updates) -> 'TradingTaskContext':
        """Create a new context with updated fields.
        
        Note: This creates a new context with updates applied.
        Required fields from the original context are preserved.
        """
        return msgspec.structs.replace(self, **updates)
    
    def to_json(self) -> bytes:
        """Serialize context to JSON bytes."""
        # Convert non-serializable fields for JSON
        data = msgspec.structs.asdict(self)
        if data.get('error'):
            data['error'] = str(data['error'])
        return msgspec.json.encode(data)
    
    @classmethod
    def from_json(cls, data: bytes) -> 'TradingTaskContext':
        """Deserialize context from JSON bytes."""
        obj_data = msgspec.json.decode(data)
        # Reconstruct error if present
        if obj_data.get('error'):
            obj_data['error'] = Exception(obj_data['error'])
        return cls(**obj_data)

T = TypeVar('T', bound=TradingTaskContext)


class BaseTradingTask(Generic[T], ABC):
    """Base class for trading tasks with state management and context evolution.
    
    Subclasses should:
    1. Define their own context class extending TradingTaskContext
    2. Override context_class property to return their context type
    3. Implement state handlers and transitions
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
                 config: ExchangeConfig, 
                 logger: HFTLoggerInterface,
                 context: Optional[T] = None,
                 delay: float = 0.1,
                 task_id: Optional[str] = None,
                 **context_kwargs):
        """Initialize task with either a context or context parameters.
        
        Args:
            config: Exchange configuration
            logger: HFT logger instance
            context: Pre-built context (if provided, symbol/side/context_kwargs ignored)
            symbol: Trading symbol (used if context not provided)
            side: Trading side (used if context not provided)
            delay: Delay between state cycles
            **context_kwargs: Additional context fields
        """
        self.config = config
        self.state = TradingStrategyState.NOT_STARTED
        self.logger = logger
        self.delay = delay
        self.task_id = task_id if task_id else f"{self.name}_{id(self)}"
        
        # Initialize context either from provided or create new
            # Validate provided context
        if not isinstance(context, TradingTaskContext):
            raise TypeError(f"Context must be a TradingTaskContext, got {type(context)}")
        self.context: T = context


        # try:
        #     self.context = self.context_class(**context_kwargs)
        # except TypeError as e:
        #     raise ValueError(f"Failed to create context: {e}")
        #
        # Build tag from available context fields
        tag_parts = [self.config.name, self.name]
        if hasattr(self.context, 'symbol') and self.context.symbol:
            tag_parts.append(str(self.context.symbol))
        if hasattr(self.context, 'side') and self.context.side:
            tag_parts.append(self.context.side.name)
        self._tag = "_".join(tag_parts)
        
        # State handlers mapping
        self._state_handlers = {
            TradingStrategyState.IDLE: self._handle_idle,
            TradingStrategyState.PAUSED: self._handle_paused,
            TradingStrategyState.ERROR: self._handle_error,
            TradingStrategyState.COMPLETED: self._handle_complete,
            TradingStrategyState.EXECUTING: self._handle_executing,
        }

    def evolve_context(self, **updates) -> None:
        """Update context with new fields.
        
        Args:
            **updates: Fields to update in the context
        """
        self.context = self.context.evolve(**updates)
        
        # Update tag if symbol or side changed
        if 'symbol' in updates or 'side' in updates:
            tag_parts = [self.config.name, self.name]
            if self.context.symbol:
                tag_parts.append(str(self.context.symbol))
            if self.context.side:
                tag_parts.append(self.context.side.name)
            self._tag = "_".join(tag_parts)
    
    def save_context(self) -> bytes:
        """Serialize current context to JSON bytes for persistence."""
        return self.context.to_json()
    
    def restore_context(self, data: bytes) -> None:
        """Restore context from serialized JSON bytes."""
        self.context = self.context_class.from_json(data)
    
    def _transition(self, new_state: TradingStrategyState) -> None:
        """Transition to a new state.
        
        Args:
            new_state: Target state to transition to
        """
        self.logger.info(f"Transitioning from {self.state} to {new_state}")
        self.state = new_state

    async def _handle_idle(self):
        """Default idle state handler."""
        self.logger.debug(f"IDLE state for {self._tag}")

    async def _handle_paused(self):
        """Default paused state handler."""
        self.logger.debug(f"PAUSED state for {self._tag}")

    async def _handle_complete(self):
        """Default paused state handler."""
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
        self.logger.info(f"Pausing task from state {self.state.name}")
        self._transition(TradingStrategyState.PAUSED)

    async def update(self, **context_updates):
        """Update the task with new context data.
        
        Args:
            **context_updates: Partial context updates to apply to existing context
            
        Important:
            - Updates are applied to the existing context
            - Required fields (like 'symbol') are preserved from current context
            - Pass field_name=value to update specific fields
        """
        self.logger.info(f"Updating task in state {self.state.name}")
        
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
        result = TaskExecutionResult(
            task_id=self.task_id,
            state=self.state,
            next_delay=self.delay
        )
        
        try:
            # Check if task should continue
            if self.state in [TradingStrategyState.COMPLETED, TradingStrategyState.CANCELLED]:
                result.should_continue = False
                return result
            
            # Get handler for current state
            handler = self._state_handlers.get(self.state)
            if handler:
                await handler()
            else:
                # No handler for this state
                await self._handle_unhandled_state()
            
            # Update result with current state
            result.state = self.state
            
            # Determine if should continue
            result.should_continue = self.state not in [
                TradingStrategyState.COMPLETED,
                TradingStrategyState.CANCELLED,
                TradingStrategyState.ERROR
            ]
            
            # Calculate execution time
            result.execution_time_ms = (time.time() - start_time) * 1000
            
        except asyncio.CancelledError:
            self.logger.info(f"Task cancelled during execution: {self._tag}")
            self.state = TradingStrategyState.CANCELLED
            result.should_continue = False
            result.state = self.state
            raise
            
        except Exception as e:
            self.logger.error(f"Task execution failed {self._tag}", error=str(e))
            self.evolve_context(error=e)
            self._transition(TradingStrategyState.ERROR)
            result.error = e
            result.should_continue = False
            result.state = self.state
        
        return result
    
    async def _handle_unhandled_state(self):
        """Handle states without explicit handlers.
        
        Subclasses can override to provide custom behavior.
        """
        self.logger.warning(f"No handler for state {self.state}, transitioning to ERROR")
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
    

