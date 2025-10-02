# Directory Structure - State Machine Organization

## Proposed Directory Layout

```
src/trading/state_machines/
├── __init__.py
├── base/
│   ├── __init__.py
│   ├── base_strategy_state_machine.py      # Abstract base class
│   ├── strategy_context.py                 # Base context dataclasses  
│   ├── strategy_states.py                  # Common state enums
│   ├── strategy_result.py                  # Result and metrics classes
│   ├── strategy_factory.py                 # Factory pattern implementation
│   ├── performance_tracker.py              # Performance monitoring
│   └── exchange_interface.py               # Abstract exchange interface
├── hedging/
│   ├── __init__.py
│   ├── base_hedging.py                     # Base hedging state machine
│   ├── spot_futures_hedging.py            # Spot/Futures hedging strategy
│   ├── futures_futures_hedging.py         # Futures/Futures hedging strategy
│   └── hedging_context.py                 # Hedging-specific context classes
├── market_making/
│   ├── __init__.py
│   ├── market_maker.py                     # Enhanced market making strategy
│   ├── spread_calculator.py               # Spread calculation utilities
│   ├── inventory_manager.py               # Inventory management logic
│   └── market_making_context.py           # Market making context classes
├── arbitrage/
│   ├── __init__.py
│   ├── base_arbitrage.py                   # Base arbitrage state machine
│   ├── simple_arbitrage.py                # Cross-exchange arbitrage
│   ├── triangular_arbitrage.py            # Multi-step arbitrage
│   ├── opportunity_detector.py            # Arbitrage opportunity detection
│   └── arbitrage_context.py               # Arbitrage-specific context classes
├── utils/
│   ├── __init__.py
│   ├── state_validators.py                # State transition validation
│   ├── timing_utilities.py                # Performance timing helpers
│   ├── error_handlers.py                  # Common error handling patterns
│   └── logging_helpers.py                 # Strategy-specific logging
└── tests/
    ├── __init__.py
    ├── test_base/
    │   ├── test_base_state_machine.py
    │   ├── test_strategy_context.py
    │   └── test_strategy_factory.py
    ├── test_hedging/
    │   ├── test_spot_futures_hedging.py
    │   └── test_futures_futures_hedging.py
    ├── test_market_making/
    │   └── test_market_maker.py
    ├── test_arbitrage/
    │   ├── test_simple_arbitrage.py
    │   └── test_triangular_arbitrage.py
    └── test_utils/
        ├── test_state_validators.py
        └── test_timing_utilities.py
```

## Module Responsibilities

### Base Module (`base/`)

**Purpose**: Core infrastructure and abstract classes for all strategies

**Key Files**:
- `base_strategy_state_machine.py`: Abstract base class with common lifecycle methods
- `strategy_context.py`: Base context dataclass and common context utilities
- `strategy_states.py`: Common state enums shared across strategies
- `strategy_result.py`: Result classes and performance metrics
- `strategy_factory.py`: Factory pattern for strategy instantiation
- `performance_tracker.py`: Performance monitoring and metrics collection
- `exchange_interface.py`: Abstract interface for exchange operations

**Dependencies**: None (foundation layer)

### Hedging Module (`hedging/`)

**Purpose**: Hedging strategies for risk management and delta-neutral positions

**Key Files**:
- `base_hedging.py`: Common hedging state machine with shared hedge logic
- `spot_futures_hedging.py`: Long spot position hedged with short futures
- `futures_futures_hedging.py`: Cross-exchange or calendar spread hedging
- `hedging_context.py`: Hedging-specific context classes and position tracking

**Dependencies**: `base/`

**Strategy Types**:
- **Spot/Futures Hedging**: Hedge spot exposure with futures contracts
- **Futures/Futures Hedging**: Hedge between different futures contracts or exchanges
- **Calendar Spread Hedging**: Time-based spread hedging strategies

### Market Making Module (`market_making/`)

**Purpose**: Liquidity provision strategies with bid/ask spread capture

**Key Files**:
- `market_maker.py`: Enhanced market making state machine (evolution of current demo)
- `spread_calculator.py`: Dynamic spread calculation based on market conditions
- `inventory_manager.py`: Inventory risk management and position balancing
- `market_making_context.py`: Market making context with order tracking

**Dependencies**: `base/`

**Features**:
- **Dynamic Spread Adjustment**: Adapt spreads based on volatility and liquidity
- **Inventory Management**: Balance positions to avoid directional risk
- **Multi-Exchange Market Making**: Provide liquidity across multiple venues

### Arbitrage Module (`arbitrage/`)

**Purpose**: Price difference exploitation across exchanges and instruments

**Key Files**:
- `base_arbitrage.py`: Common arbitrage state machine with opportunity validation
- `simple_arbitrage.py`: Cross-exchange price arbitrage (hedging + swap)
- `triangular_arbitrage.py`: Multi-step currency arbitrage
- `opportunity_detector.py`: Real-time arbitrage opportunity detection
- `arbitrage_context.py`: Arbitrage-specific context with multi-exchange tracking

**Dependencies**: `base/`

**Strategy Types**:
- **Simple Arbitrage**: Buy low on one exchange, sell high on another
- **Triangular Arbitrage**: Multi-step trades through currency pairs
- **Statistical Arbitrage**: Mean reversion and correlation-based strategies

### Utils Module (`utils/`)

**Purpose**: Common utilities and helpers for all strategy types

**Key Files**:
- `state_validators.py`: Validation logic for state transitions
- `timing_utilities.py`: Performance timing and latency measurement
- `error_handlers.py`: Common error handling patterns and recovery strategies
- `logging_helpers.py`: Strategy-specific logging formatters and utilities

**Dependencies**: `base/`

## Import Structure

### Base Level Imports
```python
# Public API imports
from trading.state_machines import (
    BaseStrategyStateMachine,
    StrategyFactory,
    HedgingContext,
    ArbitrageContext,
    MarketMakingContext
)

# Strategy imports
from trading.state_machines.hedging import SpotFuturesHedging
from trading.state_machines.market_making import MarketMaker
from trading.state_machines.arbitrage import SimpleArbitrage
```

### Internal Module Imports
```python
# Within hedging module
from ..base import BaseStrategyStateMachine, BaseStrategyContext
from .hedging_context import HedgingContext, PositionTracker

# Within arbitrage module  
from ..base import BaseStrategyStateMachine, ArbitrageState
from ..utils import OpportunityValidator, TimingUtilities
```

## File Naming Conventions

### Classes
- **State Machines**: `{Strategy}StateMachine` (e.g., `SpotFuturesHedgingStateMachine`)
- **Contexts**: `{Strategy}Context` (e.g., `HedgingContext`, `ArbitrageContext`)
- **States**: `{Strategy}State` (e.g., `HedgingState`, `ArbitrageState`)
- **Results**: `{Strategy}Result` (e.g., `HedgingResult`, `ArbitrageResult`)

### Files
- **State Machines**: `snake_case` matching strategy name (e.g., `spot_futures_hedging.py`)
- **Utilities**: Descriptive names (e.g., `opportunity_detector.py`, `spread_calculator.py`)
- **Base Classes**: `base_` prefix (e.g., `base_strategy_state_machine.py`)

### Tests
- **Test Files**: `test_` prefix matching module name (e.g., `test_spot_futures_hedging.py`)
- **Test Classes**: `Test{ClassName}` (e.g., `TestSpotFuturesHedging`)
- **Test Methods**: `test_{functionality}` (e.g., `test_state_transitions`)

## Configuration Management

### Strategy Registration
```python
# In __init__.py files
from .strategy_factory import StrategyFactory
from .hedging import SpotFuturesHedging, FuturesFuturesHedging
from .arbitrage import SimpleArbitrage, TriangularArbitrage
from .market_making import MarketMaker

# Register strategies
StrategyFactory.register_strategy("spot_futures_hedging", SpotFuturesHedging)
StrategyFactory.register_strategy("futures_futures_hedging", FuturesFuturesHedging)
StrategyFactory.register_strategy("simple_arbitrage", SimpleArbitrage)
StrategyFactory.register_strategy("triangular_arbitrage", TriangularArbitrage)
StrategyFactory.register_strategy("market_maker", MarketMaker)
```

### Module Initialization
```python
# trading/state_machines/__init__.py
"""
Trading Strategy State Machines

High-performance state machines for HFT trading strategies.
Provides foundation for hedging, arbitrage, and market making strategies.
"""

from .base import (
    BaseStrategyStateMachine,
    BaseStrategyContext,
    StrategyResult,
    StrategyFactory,
    StrategyState
)

from .hedging import (
    SpotFuturesHedging,
    FuturesFuturesHedging,
    HedgingContext,
    HedgingState
)

from .arbitrage import (
    SimpleArbitrage,
    TriangularArbitrage, 
    ArbitrageContext,
    ArbitrageState
)

from .market_making import (
    MarketMaker,
    MarketMakingContext,
    MarketMakingState
)

__all__ = [
    # Base classes
    "BaseStrategyStateMachine",
    "BaseStrategyContext", 
    "StrategyResult",
    "StrategyFactory",
    "StrategyState",
    
    # Hedging strategies
    "SpotFuturesHedging",
    "FuturesFuturesHedging",
    "HedgingContext",
    "HedgingState",
    
    # Arbitrage strategies
    "SimpleArbitrage", 
    "TriangularArbitrage",
    "ArbitrageContext",
    "ArbitrageState",
    
    # Market making strategies
    "MarketMaker",
    "MarketMakingContext", 
    "MarketMakingState"
]

# Version and metadata
__version__ = "1.0.0"
__author__ = "HFT Trading System"
__description__ = "High-performance trading strategy state machines"
```

## Dependency Management

### Internal Dependencies
```python
# Dependency hierarchy (no circular imports)
base/ (no dependencies)
├── utils/ (depends on base/)
├── hedging/ (depends on base/, utils/)
├── arbitrage/ (depends on base/, utils/)
└── market_making/ (depends on base/, utils/)
```

### External Dependencies
```python
# Required external packages
asyncio           # Async/await support
dataclasses       # Context data structures
enum              # State enums
typing            # Type hints
time              # Performance timing
abc               # Abstract base classes

# Optional performance packages
uvloop           # High-performance event loop
msgspec          # Fast serialization (if needed)
```

## Development Workflow

### Adding New Strategy
1. **Create strategy directory** under appropriate category
2. **Implement state machine** extending base class
3. **Define strategy-specific context** and states
4. **Add to factory registration** in `__init__.py`
5. **Write unit tests** for state transitions
6. **Update module exports** and documentation

### Testing Strategy
1. **Unit tests** for individual state transitions
2. **Integration tests** with mock exchanges
3. **Performance tests** for timing requirements
4. **End-to-end tests** with real market data

### Code Review Checklist
- [ ] Follows PROJECT_GUIDES.md principles
- [ ] Uses float-only for all prices/quantities
- [ ] Implements all abstract methods
- [ ] Has proper error handling
- [ ] Includes comprehensive tests
- [ ] Maintains <10 cyclomatic complexity
- [ ] Has clear state transition logic
- [ ] Proper resource cleanup

This directory structure provides:

1. **Clear Separation**: Each strategy type has its own module
2. **Shared Foundation**: Common base classes and utilities
3. **Scalable Architecture**: Easy to add new strategies
4. **Testing Support**: Comprehensive test structure
5. **Import Clarity**: Clean public API with internal organization
6. **Dependency Management**: Clear hierarchy with no circular imports