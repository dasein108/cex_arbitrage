# TradingTaskContext Hierarchy Refactoring

## Overview

Refactored the `TradingTaskContext` class hierarchy to support both single-exchange and multi-exchange trading tasks by creating a flexible, extensible inheritance structure.

## Problem Statement

The original `TradingTaskContext` was too specific for single-exchange, single-symbol tasks:
- Required fields: `exchange_name`, `symbol` 
- Assumed single order tracking with `order_id`
- Made it impossible to create multi-exchange or multi-symbol tasks

## Solution: Hierarchical Context Design

### 1. Base Context - `TradingTaskContext`

Generic base for ALL trading tasks with only universal fields:
```python
class TradingTaskContext(msgspec.Struct):
    task_id: str = ""                    # Universal task identifier
    state: TradingStrategyState           # Task lifecycle state
    error: Optional[Exception] = None     # Error tracking
    metadata: Dict[str, Any]              # Flexible metadata
```

### 2. Single Exchange Context - `SingleExchangeTaskContext`

Intermediate context for single-exchange operations:
```python
class SingleExchangeTaskContext(TradingTaskContext):
    exchange_name: ExchangeEnum           # Exchange identifier
    symbol: Symbol                        # Trading pair
    side: Optional[Side] = None           # Trading direction  
    order_id: Optional[str] = None        # Current order tracking
```

### 3. Task-Specific Contexts

Tasks extend the appropriate parent based on their needs:

**Single Exchange Tasks** (extend `SingleExchangeTaskContext`):
- `IcebergTaskContext` - Adds iceberg-specific fields
- `DeltaNeutralTaskContext` - Adds delta-neutral tracking

**Multi-Exchange Tasks** (extend `TradingTaskContext` directly):
- `ArbitrageTaskContext` - Multiple exchanges, spread tracking
- `HedgeTaskContext` - Multiple symbols and exchanges

## Key Changes

### Modified Files

1. **`src/trading/tasks/base_task.py`**
   - Split `TradingTaskContext` into base and `SingleExchangeTaskContext`
   - Made `BaseTradingTask` flexible to handle any context type
   - Updated validation to be context-aware
   - Modified tag generation to handle missing fields gracefully

2. **`src/trading/tasks/iceberg_task.py`**
   - Changed parent from `TradingTaskContext` to `SingleExchangeTaskContext`
   - No other changes needed - fully backward compatible

3. **`src/trading/tasks/delta_neutral_task.py`**
   - Changed parent from `TradingTaskContext` to `SingleExchangeTaskContext`
   - Updated docstring to reflect actual purpose

### Backward Compatibility

✅ **Fully Backward Compatible**
- Existing tasks (`IcebergTask`, `DeltaNeutralTask`) work unchanged
- Serialization/deserialization remains compatible
- Persistence module works without modifications

### Benefits of New Design

1. **Flexibility**: Support for multi-exchange and multi-symbol tasks
2. **Clean Separation**: Clear boundaries between universal and domain-specific fields
3. **Type Safety**: Proper inheritance hierarchy with type hints
4. **Extensibility**: Easy to add new context types for different task patterns
5. **Minimal Code**: Only essential fields at each level

## Usage Examples

### Single Exchange Task
```python
from trading.tasks.base_task import SingleExchangeTaskContext

context = SingleExchangeTaskContext(
    exchange_name=ExchangeEnum.MEXC,
    symbol=Symbol(base="BTC", quote="USDT"),
    side=Side.BUY,
    task_id="single_123"
)
```

### Multi-Exchange Arbitrage Task
```python
from trading.tasks.base_task import TradingTaskContext

class ArbitrageTaskContext(TradingTaskContext):
    exchanges: List[ExchangeEnum]
    symbol: Symbol
    spreads: Dict[str, float]

context = ArbitrageTaskContext(
    exchanges=[ExchangeEnum.MEXC, ExchangeEnum.GATEIO],
    symbol=Symbol(base="BTC", quote="USDT"),
    spreads={},
    task_id="arb_456"
)
```

### Iceberg Task (Unchanged)
```python
from trading.tasks.iceberg_task import IcebergTaskContext

context = IcebergTaskContext(
    exchange_name=ExchangeEnum.MEXC,
    symbol=Symbol(base="ETH", quote="USDT"),
    side=Side.SELL,
    total_quantity=100.0,
    order_quantity=10.0
)
```

## Serialization Support

All contexts support JSON serialization through inheritance:

- Base fields handled by `TradingTaskContext.to_json()`
- Exchange fields handled by `SingleExchangeTaskContext.to_json()`
- Task-specific fields automatically included via `msgspec.structs.asdict()`

## Testing

Comprehensive test suite created in `tests/test_task_context_hierarchy.py`:
- Base context minimal fields
- Single exchange context fields
- Inheritance chain validation
- Multi-exchange context examples
- Serialization/deserialization
- Context evolution (immutable updates)

All tests pass ✅

## Migration Guide

For existing code:
1. No changes needed for `IcebergTask` or `DeltaNeutralTask`
2. New multi-exchange tasks should extend `TradingTaskContext` directly
3. New single-exchange tasks should extend `SingleExchangeTaskContext`

## Future Considerations

The new hierarchy supports future patterns:
- Portfolio management tasks (multiple symbols, multiple exchanges)
- Cross-exchange hedging strategies
- Market making across venues
- Statistical arbitrage with basket trading

## Summary

This refactoring creates a clean, extensible hierarchy that:
- Removes single-exchange assumptions from the base
- Maintains full backward compatibility
- Enables new multi-exchange task patterns
- Keeps code minimal and maintainable