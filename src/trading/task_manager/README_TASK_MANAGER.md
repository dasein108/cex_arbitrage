# Task Manager System Documentation

## Overview

The Task Manager system is a centralized orchestration platform for managing high-frequency trading tasks in the CEX Arbitrage Engine. It provides automated lifecycle management, persistence, recovery, and concurrent execution of trading strategies while maintaining state consistency and performance requirements.

### Key Features

- **Centralized Task Orchestration** - Single point of control for all trading tasks
- **Symbol-Based Sequential Execution** - Tasks operating on the same symbol execute sequentially to prevent conflicts
- **Automatic State Persistence** - Context preservation across system restarts
- **Task Recovery** - Restoration of active tasks from persistent storage
- **Performance Monitoring** - Execution metrics and task health tracking
- **Resource Management** - Automatic cleanup and lifecycle management

## System Architecture

### Component Overview

```
TaskManager (Core Orchestrator)
├── TaskPersistenceManager (State Storage)
├── TaskRecovery (Recovery Logic)  
├── TaskSerializer (JSON Serialization)
└── BaseTradingTask (Abstract Task Foundation)
    ├── IcebergTask (Iceberg Order Execution)
    ├── DeltaNeutralTask (Cross-Exchange Arbitrage)
    └── CustomTask (User-Defined Tasks)
```

### Base Task Architecture

The system is built on a robust foundation defined in `base_task.py`:

#### Core Components

**1. TaskContext (Base Context)**
```python
class TaskContext(msgspec.Struct, frozen=False, kw_only=True):
    task_id: str = ""
    state: TradingStrategyState = TradingStrategyState.NOT_STARTED
    error: Optional[Exception] = None
    metadata: Dict[str, Any] = msgspec.field(default_factory=dict)
    should_save_flag: bool = True  # Whether to persist this task
```

**2. TaskExecutionResult (Execution Metadata)**
```python
class TaskExecutionResult(msgspec.Struct, frozen=False, kw_only=True):
    task_id: str  # Unique task identifier
    context: 'TaskContext'  # Snapshot of task context after execution
    should_continue: bool = True  # True if task needs more cycles
    next_delay: float = 0.1  # Suggested delay before next execution
    state: TradingStrategyState = TradingStrategyState.IDLE
    error: Optional[Exception] = None
    execution_time_ms: float = 0.0
    metadata: Dict[str, Any] = msgspec.field(default_factory=dict)
```

**3. BaseTradingTask (Generic Task Foundation)**
```python
class BaseTradingTask(Generic[T, StateT], ABC):
    """Generic base class for all trading tasks with type-safe context handling."""
```

#### Generic Type System

The task architecture uses advanced Python generics to provide type safety:

- `T` - Bound to `TaskContext` (specific context type for each task)
- `StateT` - Bound to `IntEnum` (custom states beyond base TradingStrategyState)

This enables:
- **Type-safe context access** - IDE autocomplete and type checking
- **Extensible state machines** - Custom states per task type
- **Compile-time validation** - Catch type errors before runtime

### State Machine Pattern

#### Base States (All Tasks)
```python
class TradingStrategyState(IntEnum):
    IDLE = 1           # Waiting for execution
    EXECUTING = 2      # Active execution
    MONITORING = 3     # Observing market conditions
    ADJUSTING = 4      # Parameter updates
    COMPLETED = 100    # Successfully finished
    NOT_STARTED = -1   # Initial state
    CANCELLED = -2     # User cancelled
    PAUSED = 0         # Temporarily suspended
    ERROR = -100       # Error state
```

#### Extended States (Task-Specific)
Tasks can define custom states by implementing `get_extended_state_handlers()`:

```python
# Example: DeltaNeutralTask custom states
class DeltaNeutralState(IntEnum):
    SYNCING = 1          # Sync order status from exchanges
    ANALYZING = 2        # Analyze imbalances and completion
    REBALANCING = 3      # Handle imbalances with market orders
    MANAGING_ORDERS = 4  # Cancel/place limit orders
    COMPLETING = 5       # Finalize task
    ADJUSTING = 6        # External adjustments
```

#### State Handler Registration
```python
def get_extended_state_handlers(self) -> Dict[DeltaNeutralState, str]:
    return {
        DeltaNeutralState.SYNCING: '_handle_syncing',
        DeltaNeutralState.ANALYZING: '_handle_analyzing',
        DeltaNeutralState.REBALANCING: '_handle_rebalancing',
        DeltaNeutralState.MANAGING_ORDERS: '_handle_managing_orders',
        DeltaNeutralState.COMPLETING: '_handle_completing',
    }
```

### Context Evolution Pattern

The system uses an immutable context evolution pattern for thread-safe state updates:

```python
# Django-like field updates
self.evolve_context(
    state=TradingStrategyState.EXECUTING,
    total_quantity=1000.0
)

# Dict field updates with double-underscore syntax
self.evolve_context(
    order_id__buy="12345",           # Sets order_id[Side.BUY] = "12345"
    filled_quantity__sell=500.0      # Sets filled_quantity[Side.SELL] = 500.0
)

# Mixed updates
self.evolve_context(
    state=TradingStrategyState.EXECUTING,
    order_id__buy="12345",
    avg_price__sell=0.001234
)
```

## Task Manager Features

### 1. TaskManager (Core Orchestrator)

**Primary Responsibilities:**
- Task lifecycle management (add, remove, execute, cleanup)
- Symbol-based sequential execution to prevent trading conflicts
- Performance monitoring and metrics collection
- Resource cleanup and memory management

**Key Methods:**
```python
async def add_task(task: BaseTradingTask) -> str
async def remove_task(task_id: str) -> bool
async def start(recover_tasks: bool = False)
async def stop()
def get_status() -> Dict[str, any]
```

**Performance Features:**
- **Concurrent Execution**: Tasks on different symbols run in parallel
- **Symbol Locking**: Sequential execution per symbol prevents conflicts
- **Adaptive Scheduling**: Dynamic delay adjustment based on task performance
- **Resource Optimization**: Automatic cleanup of completed tasks

### 2. TaskPersistenceManager (State Storage)

**State-Based Organization:**
```
task_data/
├── active/     # Currently running tasks
├── completed/  # Successfully finished tasks
├── errored/    # Failed or cancelled tasks
└── metadata.json
```

**Features:**
- **Atomic Writes** - Temporary file + rename for consistency
- **Automatic Cleanup** - Old completed tasks removed periodically  
- **State Migration** - Tasks move between directories based on state
- **Statistics Tracking** - Persistence metrics and health monitoring

**Key Methods:**
```python
def save_context(task_id: str, context: TaskContext) -> bool
def load_context(task_id: str, context_class: Type[T]) -> Optional[T]
def load_active_tasks() -> List[Tuple[str, str]]
def cleanup_completed(max_age_hours: int = 24)
```

### 3. TaskSerializer (JSON Serialization)

**Advanced Serialization Features:**
- **Complex Type Handling** - Symbol, ExchangeEnum, Exception objects
- **Dict Field Support** - Side enum keys serialized correctly
- **Metadata Injection** - Timestamps and schema versioning
- **Backward Compatibility** - Legacy data format support

**Serialization Process:**
```python
# Serialize context to JSON
data = TaskSerializer.serialize_context(context)

# Deserialize with type safety
context = TaskSerializer.deserialize_context(data, IcebergTaskContext)

# Extract metadata without full deserialization
metadata = TaskSerializer.extract_task_metadata(json_data)
```

### 4. TaskRecovery (Recovery Logic)

**Intelligent Task Recovery:**
- **Type Detection** - Automatic task type identification from task_id or metadata
- **Minimal Context Creation** - Reconstruct required fields for task initialization
- **Full State Restoration** - Complete context recovery from JSON
- **Error Handling** - Graceful degradation for corrupted data

**Recovery Process:**
1. **Load Active Tasks** - Find all tasks in `active/` directory
2. **Extract Task Type** - Parse task_id or metadata for type identification
3. **Create Minimal Context** - Build required fields for task construction
4. **Initialize Task** - Create task instance with minimal context
5. **Restore Full State** - Deserialize complete context from JSON
6. **Register with Manager** - Add recovered task to task manager

## Integration Guide

### Creating a New Task Type

Follow these steps to create a custom trading task:

#### Step 1: Define Task Context
```python
from trading.tasks.base_task import TaskContext
from exchanges.structs import Symbol, Side, ExchangeEnum
from typing import Optional, Dict
import msgspec

class MyTaskContext(TaskContext):
    """Context for my custom trading task."""
    # Required fields
    symbol: Symbol
    exchange_name: ExchangeEnum
    
    # Task-specific fields
    target_price: float
    quantity: float
    filled_quantity: float = 0.0
    average_price: float = 0.0
    
    # Optional advanced fields
    order_ids: Dict[str, Optional[str]] = msgspec.field(default_factory=dict)
    metadata_custom: Dict[str, float] = msgspec.field(default_factory=dict)
```

#### Step 2: Define Custom States (Optional)
```python
from enum import IntEnum

class MyTaskState(IntEnum):
    """Custom states for my task."""
    ANALYZING_MARKET = 1
    PLACING_ORDERS = 2  
    MONITORING_FILLS = 3
    ADJUSTING_PRICE = 4
```

#### Step 3: Implement Task Class
```python
from trading.tasks.base_task import BaseTradingTask
from typing import Type, Dict

class MyTask(BaseTradingTask[MyTaskContext, MyTaskState]):
    """Custom trading task implementation."""
    name: str = "MyTask"
    
    @property
    def context_class(self) -> Type[MyTaskContext]:
        return MyTaskContext
    
    def __init__(self, logger: HFTLoggerInterface, context: MyTaskContext, **kwargs):
        super().__init__(logger, context, **kwargs)
        # Initialize task-specific resources
        self._exchange = None
        
    async def start(self, **kwargs):
        await super().start(**kwargs)
        # Initialize exchanges, load symbol info, etc.
        self._exchange = self._load_exchange(self.context.exchange_name)
        await self._exchange.initialize([self.context.symbol])
    
    def _build_tag(self) -> None:
        """Build logging tag with task-specific fields."""
        self._tag = f'{self.name}_{self.context.exchange_name.name}_{self.context.symbol}'
    
    def get_extended_state_handlers(self) -> Dict[MyTaskState, str]:
        """Register custom state handlers."""
        return {
            MyTaskState.ANALYZING_MARKET: '_handle_analyzing_market',
            MyTaskState.PLACING_ORDERS: '_handle_placing_orders',
            MyTaskState.MONITORING_FILLS: '_handle_monitoring_fills',
            MyTaskState.ADJUSTING_PRICE: '_handle_adjusting_price',
        }
    
    # Implement required abstract method
    async def _handle_executing(self):
        """Main execution logic - transition to custom states."""
        self._transition(MyTaskState.ANALYZING_MARKET)
    
    # Implement custom state handlers
    async def _handle_analyzing_market(self):
        # Analyze market conditions
        # Transition to next state based on analysis
        pass
    
    async def _handle_placing_orders(self):
        # Place trading orders
        pass
    
    async def _handle_monitoring_fills(self):
        # Monitor order fills and update context
        pass
    
    async def _handle_adjusting_price(self):
        # Adjust order prices based on market movement
        pass
    
    async def cleanup(self):
        """Clean up task resources."""
        if self._exchange:
            await self._exchange.close()
```

#### Step 4: Add Recovery Support
```python
# Add to TaskRecovery.recover_task_by_type()
async def recover_task_by_type(self, task_id: str, json_data: str, task_type: str):
    if task_type == "MyTask":
        return await self.recover_my_task(task_id, json_data)
    # ... existing task types

async def recover_my_task(self, task_id: str, json_data: str) -> Optional['MyTask']:
    """Recover MyTask from JSON data."""
    try:
        # Parse context data and reconstruct required fields
        context_data = json.loads(json_data)
        
        # Create minimal context
        context = MyTaskContext(
            symbol=Symbol(...),
            exchange_name=ExchangeEnum(...),
            # ... other required fields
        )
        
        task = MyTask(self.logger, context)
        task.restore_from_json(json_data)  # Restore full state
        return task
        
    except Exception as e:
        self.logger.error(f"Failed to recover MyTask {task_id}", error=str(e))
        return None
```

### Example Implementations

#### Iceberg Task (Simple Example)

**Use Case**: Break large orders into smaller chunks to minimize market impact

**Key Features:**
- Single exchange execution
- Order size management with exchange minimums
- Price tolerance monitoring
- Weighted average price calculation

**Context Structure:**
```python
class IcebergTaskContext(TaskContext):
    # Exchange and symbol
    exchange_name: ExchangeEnum
    symbol: Symbol
    side: Side
    
    # Iceberg parameters
    total_quantity: Optional[float] = None      # Total amount to execute
    order_quantity: Optional[float] = None     # Size per order
    filled_quantity: float = 0.0               # Amount filled so far
    offset_ticks: int = 0                      # Price offset from top
    tick_tolerance: int = 1                    # Price movement tolerance
    avg_price: float = 0.0                     # Weighted average price
    
    # Current order
    order_id: Optional[str] = None
```

**Execution Flow:**
1. **IDLE** → **EXECUTING**: Start iceberg execution
2. **Place Order**: Create limit order at top ± offset_ticks
3. **Monitor Order**: Sync order status and check for fills
4. **Price Check**: Cancel if price moved beyond tick_tolerance
5. **Partial Fill**: Update avg_price and filled_quantity
6. **Continue/Complete**: Place next order or complete when total_quantity filled

#### Delta Neutral Task (Complex Example)

**Use Case**: Execute simultaneous buy/sell orders across different exchanges for arbitrage

**Key Features:**
- Multi-exchange coordination
- Cross-exchange balance management
- Imbalance detection and rebalancing
- Enhanced state machine with parallel execution

**Context Structure:**
```python
class DeltaNeutralTaskContext(TaskContext):
    symbol: Symbol
    total_quantity: Optional[float] = None
    
    # Side-specific mappings
    filled_quantity: Dict[Side, float]         # Filled per side
    avg_price: Dict[Side, float]               # Average price per side  
    exchange_names: Dict[Side, ExchangeEnum]   # Exchange per side
    offset_ticks: Dict[Side, int]              # Price offset per side
    tick_tolerance: Dict[Side, int]            # Tolerance per side
    order_id: Dict[Side, Optional[str]]        # Order ID per side
    
    direction: Direction = Direction.NONE
    order_quantity: Optional[float] = None
```

**Enhanced State Machine:**
1. **IDLE** → **SYNCING**: Sync order status from both exchanges
2. **SYNCING** → **ANALYZING**: Analyze imbalances and completion status
3. **ANALYZING** → **REBALANCING**: Handle imbalances with market orders
4. **ANALYZING** → **MANAGING_ORDERS**: Cancel/place limit orders
5. **MANAGING_ORDERS** → **SYNCING**: Return to monitoring
6. **ANALYZING** → **COMPLETING**: Finalize when both sides complete

## Usage Examples

### Basic Task Manager Usage

```python
from infrastructure.logging import get_hft_logger
from trading.task_manager.task_manager import TaskManager
from trading.tasks.iceberg_task import IcebergTask, IcebergTaskContext

# Initialize logger and task manager
logger = get_hft_logger("task_manager_demo")
manager = TaskManager(logger, base_path="demo_tasks")

# Create task context
context = IcebergTaskContext(
    symbol=Symbol(base="BTC", quote="USDT"),
    exchange_name=ExchangeEnum.MEXC,
    side=Side.SELL,
    total_quantity=100.0,
    order_quantity=10.0,
    offset_ticks=2,
    tick_tolerance=3
)

# Create and add task
task = IcebergTask(logger, context)
await task.start()
task_id = await manager.add_task(task)

# Start manager with recovery
await manager.start(recover_tasks=True)

# Monitor status
while manager.task_count > 0:
    status = manager.get_status()
    logger.info("Manager status", **status)
    await asyncio.sleep(5)

# Clean shutdown
await manager.stop()
```

### Advanced Multi-Task Management

```python
async def run_arbitrage_strategy():
    """Example: Run multiple arbitrage tasks concurrently."""
    
    logger = get_hft_logger("arbitrage_manager")
    manager = TaskManager(logger)
    
    # Define symbols for arbitrage
    symbols = [
        Symbol(base="BTC", quote="USDT"),
        Symbol(base="ETH", quote="USDT"), 
        Symbol(base="BNB", quote="USDT")
    ]
    
    # Create delta neutral tasks for each symbol
    for symbol in symbols:
        context = DeltaNeutralTaskContext(
            symbol=symbol,
            exchange_names={
                Side.BUY: ExchangeEnum.MEXC,      # Buy on MEXC
                Side.SELL: ExchangeEnum.GATEIO    # Sell on Gate.io
            },
            total_quantity=50.0,
            order_quantity=5.0,
            offset_ticks={Side.BUY: 1, Side.SELL: 1},
            tick_tolerance={Side.BUY: 2, Side.SELL: 2}
        )
        
        task = DeltaNeutralTask(logger, context)
        await task.start()
        await manager.add_task(task)
    
    # Start with recovery
    await manager.start(recover_tasks=True)
    
    # Monitor and adjust
    try:
        while manager.task_count > 0:
            status = manager.get_status()
            logger.info("Arbitrage strategy status", 
                       active_tasks=status['active_tasks'],
                       total_executions=status['total_executions'])
            
            # Adjust parameters based on market conditions
            for task_info in status['tasks']:
                if task_info['state'] == 'EXECUTING':
                    task = manager.get_task(task_info['task_id'])
                    # Dynamic parameter adjustment logic here
            
            await asyncio.sleep(10)
    
    finally:
        await manager.stop()
```

### Task Recovery and Persistence

```python
async def recovery_demo():
    """Demonstrate task recovery capabilities."""
    
    logger = get_hft_logger("recovery_demo")
    manager = TaskManager(logger, base_path="recovery_tasks")
    
    # Start with recovery enabled
    await manager.start(recover_tasks=True)
    
    # Check recovery statistics
    status = manager.get_status()
    persistence_stats = status['persistence_stats']
    
    logger.info("Recovery completed",
               active_tasks=persistence_stats['active'],
               completed_tasks=persistence_stats['completed'], 
               errored_tasks=persistence_stats['errored'])
    
    # Manual cleanup of old completed tasks (>12 hours old)
    manager.cleanup_persistence(max_age_hours=12)
    
    await manager.stop()
```

## Best Practices

### Task Design Guidelines

**1. Context Design**
- Use msgspec.Struct for all context classes
- Include all persistent state in context, not instance variables
- Use appropriate default values and factory functions
- Organize fields logically (required first, optional second)

**2. State Machine Design**
- Keep states focused and single-purpose
- Use meaningful state names that describe the action
- Implement proper error handling and state transitions
- Document state flow and transition conditions

**3. Resource Management**
- Always implement cleanup() method for exchange connections
- Use async context managers where appropriate
- Handle exchange disconnections gracefully
- Implement proper error recovery

**4. Performance Considerations**
- Minimize context updates (use should_save_flag strategically)
- Batch operations where possible
- Use symbol locking appropriately for conflict prevention
- Consider execution delays for system stability

### Error Handling Patterns

```python
async def _handle_executing(self):
    """Example: Robust error handling in state handlers."""
    try:
        # Main execution logic
        await self._sync_orders()
        await self._analyze_market()
        await self._execute_strategy()
        
    except ExchangeConnectionError as e:
        # Handle connection issues
        self.logger.error("Exchange connection lost", error=str(e))
        self._transition(TradingStrategyState.ERROR)
        
    except InsufficientBalanceError as e:
        # Handle balance issues
        self.logger.warning("Insufficient balance", error=str(e))
        self._transition(TradingStrategyState.PAUSED)
        
    except Exception as e:
        # Handle unexpected errors
        self.logger.error("Unexpected error in execution", error=str(e))
        self.evolve_context(error=e)
        self._transition(TradingStrategyState.ERROR)
```

### Monitoring and Debugging

**1. Logging Best Practices**
- Use structured logging with meaningful tags
- Include context information (symbol, exchange, quantities)
- Log state transitions and important events
- Use appropriate log levels (debug, info, warning, error)

**2. Performance Monitoring**
- Track execution times and identify bottlenecks
- Monitor task lifecycle and completion rates
- Alert on error states and recovery failures
- Track persistence and recovery statistics

**3. Testing Strategies**
- Unit test individual state handlers
- Integration test with mock exchanges
- Test recovery scenarios with corrupted data
- Load test with multiple concurrent tasks

### Security Considerations

**1. Credential Management**
- Never store credentials in task context
- Use environment variables or secure configuration
- Implement proper API key rotation
- Monitor for credential exposure in logs

**2. Data Protection**
- Validate all input parameters
- Sanitize data before persistence
- Implement proper error messages (avoid sensitive data leaks)
- Use secure file permissions for persistence storage

## Troubleshooting

### Common Issues

**1. Task Not Recovering**
- Check task_id format matches expected pattern
- Verify context class is properly imported
- Check for serialization errors in logs
- Ensure all required fields are present in persisted data

**2. State Machine Deadlock** 
- Review state transition logic
- Check for missing state handlers
- Verify error handling doesn't cause loops
- Use logging to trace state transitions

**3. Memory/Resource Leaks**
- Implement proper cleanup() methods
- Check for unclosed exchange connections
- Monitor task manager memory usage
- Review symbol lock cleanup

**4. Performance Issues**
- Check execution delays and scheduling
- Monitor symbol lock contention
- Review persistence frequency (should_save_flag usage)
- Profile task execution times

### Debugging Tools

```python
# Get detailed task status
status = manager.get_status()
for task_info in status['tasks']:
    print(f"Task: {task_info['task_id']}")
    print(f"  State: {task_info['state']}")
    print(f"  Next execution in: {task_info['next_execution']:.2f}s")

# Check persistence statistics
persistence_stats = manager.get_persistence_stats()
print(f"Active tasks: {persistence_stats['active']}")
print(f"Completed tasks: {persistence_stats['completed']}")
print(f"Errored tasks: {persistence_stats['errored']}")

# Manual task recovery for debugging
recovery = TaskRecovery(logger, persistence_manager)
active_tasks = await recovery.recover_all_tasks()
for task_id, json_data in active_tasks:
    metadata = TaskSerializer.extract_task_metadata(json_data)
    print(f"Task {task_id}: {metadata}")
```

---

*This documentation covers the complete Task Manager system. For specific implementation details, refer to the source code and inline documentation. For questions or issues, consult the development team or create an issue in the project repository.*