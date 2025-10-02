# Base Architecture - State Machine Foundation

## Abstract Base Classes

### BaseStrategyStateMachine

```python
from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Any, Dict
import asyncio
import time

class StrategyState(Enum):
    """Common states across all strategies."""
    INITIALIZING = "initializing"
    ACTIVE = "active"
    ERROR = "error"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class BaseStrategyStateMachine(ABC):
    """
    Abstract base class for all trading strategy state machines.
    Provides common interface and lifecycle management.
    """
    
    def __init__(self, context: 'BaseStrategyContext'):
        self.context = context
        self._start_time = time.perf_counter()
        
    @abstractmethod
    async def run_cycle(self) -> 'StrategyResult':
        """
        Execute complete strategy cycle.
        
        Returns:
            StrategyResult with execution details and performance metrics
        """
        pass
    
    @abstractmethod
    def get_current_state(self) -> StrategyState:
        """Get current state for monitoring and debugging."""
        pass
    
    @abstractmethod
    async def handle_error(self, error: Exception) -> None:
        """Handle strategy-specific errors and recovery."""
        pass
    
    @abstractmethod
    async def cleanup(self) -> None:
        """Cleanup resources and finalize strategy execution."""
        pass
    
    def get_execution_time(self) -> float:
        """Get current execution time in seconds."""
        return time.perf_counter() - self._start_time
    
    def is_completed(self) -> bool:
        """Check if strategy has completed successfully."""
        return self.get_current_state() == StrategyState.COMPLETED
    
    def is_error(self) -> bool:
        """Check if strategy is in error state."""
        return self.get_current_state() == StrategyState.ERROR
```

### BaseStrategyContext

```python
@dataclass
class BaseStrategyContext:
    """
    Base context for all trading strategies.
    Single source of truth for strategy state and data.
    """
    # Strategy identification
    strategy_id: str
    strategy_type: str
    
    # State management
    current_state: StrategyState = StrategyState.INITIALIZING
    
    # Timing and performance
    start_time: float = 0.0
    end_time: Optional[float] = None
    
    # Error tracking
    error: Optional[Exception] = None
    error_count: int = 0
    
    # Performance metrics
    execution_time_ms: float = 0.0
    state_transition_count: int = 0
    
    # Configuration
    max_execution_time_ms: float = 30000.0  # 30 second timeout
    max_error_count: int = 3
    
    def transition_to(self, new_state: StrategyState) -> None:
        """Transition to new state with logging."""
        old_state = self.current_state
        self.current_state = new_state
        self.state_transition_count += 1
        
        # Update timing for completed strategies
        if new_state in [StrategyState.COMPLETED, StrategyState.ERROR, StrategyState.CANCELLED]:
            self.end_time = time.perf_counter()
            if self.start_time > 0:
                self.execution_time_ms = (self.end_time - self.start_time) * 1000
    
    def record_error(self, error: Exception) -> None:
        """Record error and increment error count."""
        self.error = error
        self.error_count += 1
        
        if self.error_count >= self.max_error_count:
            self.transition_to(StrategyState.ERROR)
    
    def is_timeout(self) -> bool:
        """Check if strategy has exceeded maximum execution time."""
        if self.start_time == 0:
            return False
        
        current_time = time.perf_counter()
        elapsed_ms = (current_time - self.start_time) * 1000
        return elapsed_ms > self.max_execution_time_ms
```

### StrategyResult

```python
@dataclass
class StrategyResult:
    """Result of strategy execution with performance metrics."""
    
    # Execution results
    success: bool
    strategy_id: str
    strategy_type: str
    
    # Performance metrics
    execution_time_ms: float
    state_transition_count: int
    
    # Financial results
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_fees: float = 0.0
    
    # Execution details
    orders_executed: int = 0
    positions_opened: int = 0
    positions_closed: int = 0
    
    # Error information
    error: Optional[Exception] = None
    error_message: Optional[str] = None
    
    # Strategy-specific data
    additional_data: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.additional_data is None:
            self.additional_data = {}
    
    @property
    def net_pnl(self) -> float:
        """Calculate net PnL after fees."""
        return (self.realized_pnl + self.unrealized_pnl) - self.total_fees
    
    @property
    def is_profitable(self) -> bool:
        """Check if strategy was profitable."""
        return self.net_pnl > 0
```

## Common Strategy States

### HedgingState

```python
class HedgingState(Enum):
    """States specific to hedging strategies."""
    ANALYZING_MARKET = "analyzing_market"
    OPENING_PRIMARY_POSITION = "opening_primary_position"
    OPENING_HEDGE_POSITION = "opening_hedge_position"
    MONITORING_POSITIONS = "monitoring_positions"
    REBALANCING = "rebalancing"
    CLOSING_POSITIONS = "closing_positions"
    COMPLETED = "completed"
    ERROR = "error"
```

### ArbitrageState

```python
class ArbitrageState(Enum):
    """States specific to arbitrage strategies."""
    SCANNING_OPPORTUNITIES = "scanning_opportunities"
    OPPORTUNITY_DETECTED = "opportunity_detected"
    VALIDATING_OPPORTUNITY = "validating_opportunity"
    EXECUTING_BUY_SIDE = "executing_buy_side"
    EXECUTING_SELL_SIDE = "executing_sell_side"
    MONITORING_EXECUTION = "monitoring_execution"
    PROFIT_REALIZED = "profit_realized"
    ERROR = "error"
```

### MarketMakingState

```python
class MarketMakingState(Enum):
    """States specific to market making strategies."""
    IDLE = "idle"
    CALCULATING_SPREADS = "calculating_spreads"
    PLACING_ORDERS = "placing_orders"
    MONITORING_ORDERS = "monitoring_orders"
    ADJUSTING_SPREADS = "adjusting_spreads"
    ORDER_FILLED = "order_filled"
    INVENTORY_MANAGEMENT = "inventory_management"
    COMPLETED = "completed"
    ERROR = "error"
```

## Strategy Factory Pattern

```python
class StrategyFactory:
    """Factory for creating strategy state machines."""
    
    _strategy_registry: Dict[str, type] = {}
    
    @classmethod
    def register_strategy(cls, strategy_name: str, strategy_class: type):
        """Register a strategy class."""
        cls._strategy_registry[strategy_name] = strategy_class
    
    @classmethod
    def create_strategy(cls, strategy_name: str, context: BaseStrategyContext) -> BaseStrategyStateMachine:
        """Create strategy instance by name."""
        if strategy_name not in cls._strategy_registry:
            raise ValueError(f"Unknown strategy: {strategy_name}")
        
        strategy_class = cls._strategy_registry[strategy_name]
        return strategy_class(context)
    
    @classmethod
    def list_strategies(cls) -> list[str]:
        """List all registered strategies."""
        return list(cls._strategy_registry.keys())
```

## Common Utilities

### StateTransitionLogger

```python
class StateTransitionLogger:
    """Logger for state transitions with performance tracking."""
    
    def __init__(self, logger):
        self.logger = logger
        self.transition_history = []
    
    def log_transition(self, strategy_id: str, old_state: str, new_state: str, 
                      transition_time_ms: float):
        """Log state transition with timing."""
        transition = {
            'strategy_id': strategy_id,
            'old_state': old_state,
            'new_state': new_state,
            'transition_time_ms': transition_time_ms,
            'timestamp': time.time()
        }
        
        self.transition_history.append(transition)
        
        self.logger.info(
            "State transition",
            strategy_id=strategy_id,
            old_state=old_state,
            new_state=new_state,
            transition_time_ms=transition_time_ms
        )
    
    def get_transition_stats(self, strategy_id: str) -> Dict[str, float]:
        """Get transition statistics for a strategy."""
        strategy_transitions = [
            t for t in self.transition_history 
            if t['strategy_id'] == strategy_id
        ]
        
        if not strategy_transitions:
            return {}
        
        transition_times = [t['transition_time_ms'] for t in strategy_transitions]
        
        return {
            'total_transitions': len(strategy_transitions),
            'avg_transition_time_ms': sum(transition_times) / len(transition_times),
            'max_transition_time_ms': max(transition_times),
            'min_transition_time_ms': min(transition_times)
        }
```

## Integration Interfaces

### ExchangeInterface (Abstract)

```python
class StrategyExchangeInterface(ABC):
    """Abstract interface for exchange operations from strategy perspective."""
    
    @abstractmethod
    async def get_market_price(self, symbol: 'Symbol') -> float:
        """Get current market price for symbol."""
        pass
    
    @abstractmethod
    async def place_market_order(self, symbol: 'Symbol', side: 'Side', 
                               quantity: float) -> 'Order':
        """Place market order."""
        pass
    
    @abstractmethod
    async def place_limit_order(self, symbol: 'Symbol', side: 'Side', 
                              quantity: float, price: float) -> 'Order':
        """Place limit order."""
        pass
    
    @abstractmethod
    async def cancel_order(self, symbol: 'Symbol', order_id: str) -> 'Order':
        """Cancel existing order."""
        pass
    
    @abstractmethod
    async def get_order_status(self, symbol: 'Symbol', order_id: str) -> 'Order':
        """Get current order status."""
        pass
    
    @abstractmethod
    async def get_position(self, symbol: 'Symbol') -> Optional['Position']:
        """Get current position for symbol."""
        pass
```

## Performance Monitoring

### PerformanceTracker

```python
class StrategyPerformanceTracker:
    """Track performance metrics for strategies."""
    
    def __init__(self):
        self.metrics = {}
    
    def start_tracking(self, strategy_id: str):
        """Start tracking performance for strategy."""
        self.metrics[strategy_id] = {
            'start_time': time.perf_counter(),
            'state_transitions': 0,
            'orders_placed': 0,
            'errors': 0
        }
    
    def record_state_transition(self, strategy_id: str):
        """Record state transition."""
        if strategy_id in self.metrics:
            self.metrics[strategy_id]['state_transitions'] += 1
    
    def record_order_placed(self, strategy_id: str):
        """Record order placement."""
        if strategy_id in self.metrics:
            self.metrics[strategy_id]['orders_placed'] += 1
    
    def record_error(self, strategy_id: str):
        """Record error occurrence."""
        if strategy_id in self.metrics:
            self.metrics[strategy_id]['errors'] += 1
    
    def get_metrics(self, strategy_id: str) -> Dict[str, Any]:
        """Get performance metrics for strategy."""
        if strategy_id not in self.metrics:
            return {}
        
        metrics = self.metrics[strategy_id].copy()
        if 'start_time' in metrics:
            metrics['execution_time_ms'] = (time.perf_counter() - metrics['start_time']) * 1000
        
        return metrics
```

This base architecture provides:

1. **Common Interface**: All strategies implement the same base interface
2. **Performance Tracking**: Built-in metrics and timing
3. **Error Management**: Standardized error handling patterns
4. **State Management**: Clear state transitions with logging
5. **Factory Pattern**: Easy strategy instantiation and registration
6. **Resource Management**: Proper cleanup and disposal
7. **Monitoring Integration**: Hooks for external monitoring systems

The architecture is designed to be lightweight, performant, and maintainable while providing the flexibility needed for different trading strategies.