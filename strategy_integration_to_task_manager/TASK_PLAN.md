# Strategy Integration to TaskManager - Implementation Plan

## Overview

This plan integrates the MexcGateioFuturesStrategy with the TaskManager system to enable centralized task management, persistence, recovery, and lifecycle control while maintaining all existing arbitrage functionality.

## Analysis Summary

### Current Components
- **TaskManager**: External loop manager with symbol-based locking, persistence, and recovery
- **BaseTradingTask**: Generic task interface with context snapshots and state machine
- **MexcGateioFuturesStrategy**: Complex arbitrage strategy with market monitoring and position tracking

### Integration Requirements
1. Make strategy compatible with BaseTradingTask interface
2. Implement context snapshotting with active order preservation
3. Add persistence/recovery for strategy state and positions
4. Maintain existing arbitrage logic and performance
5. Follow PROJECT_GUIDES.md (float-only policy, separated domains, struct-first)

## Task Implementation Plan

### Phase 1: Context Architecture Design

**Task 1.1: Create ArbitrageTaskContext**
- Location: `src/trading/tasks/arbitrage_task_context.py`
- Extend TaskContext with arbitrage-specific fields
- Include active order tracking, position state, and strategy parameters
- Preserve all critical strategy state for recovery
- Use msgspec.Struct with float-only policy

**Task 1.2: Create Context Serialization**
- Extend TaskSerializer to handle ArbitrageTaskContext
- Ensure order_ids and complex structs are properly serialized
- Support recovery of Symbol, Side, and nested structures
- Test serialization roundtrip with real strategy data

### Phase 2: Task-Compatible Strategy Implementation

**Task 2.1: Create ArbitrageTask Base Class**
- Location: `src/trading/tasks/arbitrage_task.py`
- Inherit from BaseTradingTask[ArbitrageTaskContext, ArbitrageState]
- Map ArbitrageState to BaseTradingTask state handlers
- Implement abstract methods and context management
- Maintain strategy lifecycle compatibility

**Task 2.2: Refactor MexcGateioFuturesStrategy**
- Location: `src/applications/hedged_arbitrage/strategy/mexc_gateio_futures_task.py`
- Inherit from ArbitrageTask instead of standalone class
- Convert run() loop to execute_once() pattern
- Integrate context evolution with task context system
- Preserve all existing arbitrage logic and performance

### Phase 3: State Management Integration

**Task 3.1: Map Strategy States to Task States**
- Map ArbitrageState enum to TradingStrategyState where possible
- Create custom state handlers for arbitrage-specific states
- Ensure smooth state transitions and error handling
- Maintain strategy performance with minimal overhead

**Task 3.2: Implement Context Evolution**
- Replace msgspec.structs.replace with task context evolution
- Update position tracking to use context snapshots
- Preserve order tracking across context updates
- Ensure all state changes trigger context saves

### Phase 4: Persistence and Recovery

**Task 4.1: Implement Strategy Recovery**
- Add recovery logic for exchange connections and orders
- Restore position tracking and active orders
- Validate recovered state against current market conditions
- Handle partial recovery scenarios gracefully

**Task 4.2: Add Order Preservation**
- Ensure active order_ids are preserved in context snapshots
- Implement order status validation on recovery
- Handle order reconnection after restart
- Maintain delta neutrality validation

### Phase 5: TaskManager Integration

**Task 5.1: Create Strategy Factory**
- Location: `src/applications/hedged_arbitrage/strategy/strategy_factory.py`
- Factory function to create task-compatible strategies
- Handle initialization and configuration
- Support both direct and TaskManager execution modes

**Task 5.2: Integration Testing**
- Create demo showing TaskManager execution
- Test persistence and recovery scenarios
- Validate performance maintains HFT requirements
- Ensure clean shutdown and resource management

## Implementation Details

### ArbitrageTaskContext Structure
```python
class ArbitrageTaskContext(TaskContext):
    """Context for arbitrage trading tasks with order preservation."""
    
    # Core strategy configuration
    symbol: Symbol
    base_position_size_usdt: float = 20.0
    futures_leverage: float = 1.0
    
    # Trading parameters
    params: TradingParameters = msgspec.field(default_factory=TradingParameters)
    
    # Position tracking
    positions: PositionState = msgspec.field(default_factory=PositionState)
    
    # Active orders (preserved across restarts)
    active_orders: Dict[str, Dict[str, Order]] = msgspec.field(default_factory=dict)
    
    # Strategy state and performance
    arbitrage_state: ArbitrageState = ArbitrageState.IDLE
    current_opportunity: Optional[ArbitrageOpportunity] = None
    position_start_time: Optional[float] = None
    arbitrage_cycles: int = 0
    total_volume_usdt: float = 0.0
```

### State Mapping Strategy
```python
# Map ArbitrageState to TradingStrategyState handlers
ARBITRAGE_STATE_HANDLERS = {
    ArbitrageState.IDLE: TradingStrategyState.IDLE,
    ArbitrageState.INITIALIZING: TradingStrategyState.IDLE,  # Custom handler
    ArbitrageState.MONITORING: TradingStrategyState.EXECUTING,  # Main logic
    ArbitrageState.ANALYZING: TradingStrategyState.EXECUTING,
    ArbitrageState.EXECUTING: TradingStrategyState.EXECUTING,
    ArbitrageState.ERROR_RECOVERY: TradingStrategyState.ERROR
}
```

### Execute Once Pattern
```python
async def execute_once(self) -> TaskExecutionResult:
    """Execute one arbitrage cycle."""
    start_time = time.time()
    
    # Check order updates
    await self._check_order_updates()
    
    # Handle current arbitrage state
    if self.context.arbitrage_state == ArbitrageState.MONITORING:
        await self._check_arbitrage_opportunity()
    elif self.context.arbitrage_state == ArbitrageState.ANALYZING:
        await self._handle_analyzing()
    elif self.context.arbitrage_state == ArbitrageState.EXECUTING:
        await self._handle_executing()
    
    # Return execution result
    return TaskExecutionResult(
        task_id=self.context.task_id,
        context=self.context,
        should_continue=self._should_continue(),
        next_delay=0.01,  # 10ms for HFT performance
        execution_time_ms=(time.time() - start_time) * 1000
    )
```

## Success Criteria

### Functional Requirements
1. ✅ Strategy works with TaskManager lifecycle management
2. ✅ All arbitrage logic and performance preserved
3. ✅ Context snapshots preserve active orders and positions
4. ✅ Recovery restores full strategy state correctly
5. ✅ Symbol-based locking prevents conflicts

### Performance Requirements
1. ✅ Maintains <50ms order execution targets
2. ✅ Context evolution overhead <1ms per cycle
3. ✅ Serialization/deserialization <5ms per snapshot
4. ✅ Recovery time <10s for full state restoration
5. ✅ Memory usage increase <10% vs standalone strategy

### Code Quality Requirements
1. ✅ Follows PROJECT_GUIDES.md (float-only, struct-first)
2. ✅ Maintains separated domain architecture
3. ✅ Minimal code changes to existing strategy logic
4. ✅ Full test coverage for integration points
5. ✅ Clean shutdown and resource management

## File Structure

```
strategy_integration_to_task_manager/
├── TASK_PLAN.md                              # This plan
├── implementation/
│   ├── arbitrage_task_context.py             # Task 1.1
│   ├── arbitrage_task.py                     # Task 2.1  
│   ├── mexc_gateio_futures_task.py           # Task 2.2
│   └── strategy_factory.py                   # Task 5.1
├── tests/
│   ├── test_context_serialization.py         # Task 1.2
│   ├── test_arbitrage_task.py                # Task 2.1
│   └── test_task_manager_integration.py      # Task 5.2
└── demo/
    └── task_manager_arbitrage_demo.py        # Task 5.2
```

## Risk Mitigation

### Performance Risk
- **Risk**: TaskManager overhead impacts HFT performance
- **Mitigation**: Benchmark each integration step, optimize context evolution

### Recovery Risk
- **Risk**: Order state recovery fails, causing position imbalances
- **Mitigation**: Comprehensive order validation on recovery, delta balance checks

### Complexity Risk
- **Risk**: Integration adds excessive complexity
- **Mitigation**: Minimal changes approach, preserve existing patterns

## Next Steps

1. **Start with Task 1.1**: Create ArbitrageTaskContext with all required fields
2. **Implement Task 1.2**: Add serialization support and test thoroughly
3. **Continue with Task 2.1**: Build ArbitrageTask base class
4. **Follow sequential implementation** through all phases
5. **Test each phase** before proceeding to next

## Implementation Priority

**HIGH PRIORITY (Core Functionality)**
- Tasks 1.1, 1.2: Context architecture and serialization
- Tasks 2.1, 2.2: Task-compatible strategy implementation
- Task 4.1: Basic recovery functionality

**MEDIUM PRIORITY (Integration)**  
- Tasks 3.1, 3.2: State management integration
- Task 5.1: Strategy factory
- Task 4.2: Advanced order preservation

**LOW PRIORITY (Polish)**
- Task 5.2: Integration testing and demos
- Performance optimization
- Advanced recovery scenarios

This plan ensures the arbitrage strategy becomes fully compatible with TaskManager while preserving all existing functionality and performance characteristics.