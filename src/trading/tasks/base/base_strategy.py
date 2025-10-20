import asyncio
import uuid
from abc import ABC, abstractmethod
from typing import Optional, TypeVar, Generic, Type, Dict, Any, List, Union, Callable, Awaitable, Literal
import msgspec
from infrastructure.logging import HFTLoggerInterface, get_strategy_logger

# Base state literals that all task state types should include
StrategyTaskStus = Literal[
    'idle',
    'paused', 
    'error',
    'completed',
    'cancelled',
    'active',
    'inactive'
]

class TaskResult(msgspec.Struct):
    """Result of a task execution step."""
    status: StrategyTaskStus
    task_id: str

# Type alias for cleaner signatures
StateHandler = Callable[[], Awaitable[None]]


class StrategyError(msgspec.Struct):
    """Structured error information for strategy tasks."""
    message: str
    code: Optional[int] = None
    details: Optional[Dict[str, Any]] = None

class BaseStrategyContext(msgspec.Struct, frozen=False, kw_only=True):
    """Base context for all trading tasks.
    
    Contains only universal fields that apply to all task types.
    Task-specific fields should be added in subclasses.
    """
    task_type: str = "base"
    task_id: str = str(uuid.uuid4())
    status: StrategyTaskStus = 'idle'
    error: Optional[StrategyError] = None
    metadata: Dict[str, Any] = msgspec.field(default_factory=dict)
    should_save_flag: bool = True  # Whether to persist this task

    @property
    def tag(self) -> str:
        """Generate logging tag based on task_id."""
        return f"{self.task_type}.{self.task_id}"

    def save(self):
        self.should_save_flag = True

    @staticmethod
    def from_json(self, json_bytes: str) -> 'BaseStrategyContext':
        """Deserialize context from dict data."""
        return msgspec.json.decode(json_bytes, type='BaseStrategyContext')

    def to_json(self) -> str:
        """Serialize context to JSON string."""
        return msgspec.json.encode(self).decode('utf-8')


T = TypeVar('T', bound=BaseStrategyContext)


class BaseStrategyTask(Generic[T], ABC):
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
        if not isinstance(context, BaseStrategyContext):
            raise TypeError(f"Context must be a BaseStrategyContext, got {type(context)}")
        
        self.logger = logger or get_strategy_logger(f"task.{self.context.tag}")
        self.delay = delay
        self.context: T = context

    @property
    def status(self) -> StrategyTaskStus:
        """Get current state from context."""
        return self.context.status

    @property
    def tag(self):
        return self.context.tag
    
    @property
    def task_id(self) -> str:
        """Get task_id from context."""
        return self.context.task_id
    

    async def pause(self):
        self.logger.info(f"Pausing task from state {self.context.status}")
        self.context.status = 'paused'
        self.context.should_save_flag = True

    async def update(self, **context_updates):
        """Update the task with new context data.
        
        Args:
            **context_updates: Partial context updates to apply to existing context
        """

        if context_updates:
            self.context = order = msgspec.structs.replace(self.context, **context_updates)
            # Partial updates - evolve existing context
            self.logger.debug(f"Updated context fields: {list(context_updates.keys())}")

    @abstractmethod
    async def step(self):
        pass

    async def process(self):
        """Execute one cycle of the task state machine.
        
        Returns:
            TaskExecutionResult containing execution metadata and continuation info
        """

        try:
            await self.step()
            await asyncio.sleep(self.delay)

        except asyncio.CancelledError:
            self.logger.info(f"Task cancelled during execution")
            self.context.status = 'cancelled'

        except Exception as e:
            self.logger.error(f"Task execution failed", error=str(e))
            import traceback
            traceback.print_exc()
            self.context.status = 'error'
            self.context.error = StrategyError(message=str(e))

    async def start(self):
        """Stop the task gracefully."""
        self.logger.info(f"Starting task...")
        self.context.status = 'active'

    async def stop(self):
        """Stop the task gracefully."""
        self.logger.info(f"Stopping task")
        self.context.status = 'inactive'
    
    async def cancel(self):
        """Cancel the task immediately."""
        self.logger.info(f"Cancelling task")
        self.context.status = 'cancelled'

    @abstractmethod
    async def cleanup(self):
        """Perform any necessary cleanup before task is removed."""
        self.logger.info(f"Cleaning up task resources")
