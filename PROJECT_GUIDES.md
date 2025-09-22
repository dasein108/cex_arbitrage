# CEX Arbitrage Engine - Project-Specific Development Guidelines

**MANDATORY** development rules and patterns for the CEX arbitrage engine. These guidelines ensure code consistency, prevent common issues, and maintain HFT performance standards.

## Table of Contents

1. [ExchangeEnum Usage Rules](#exchangeenum-usage-rules)
2. [Factory Pattern Requirements](#factory-pattern-requirements)
3. [Auto-Registration Patterns](#auto-registration-patterns)
4. [Import Dependencies for Proper Registration](#import-dependencies-for-proper-registration)
5. [Code Organization Standards](#code-organization-standards)
6. [Type Safety Rules](#type-safety-rules)
7. [SOLID Principles Application](#solid-principles-application)
8. [Performance Standards (HFT Requirements)](#performance-standards-hft-requirements)
9. [Common Implementation Patterns](#common-implementation-patterns)
10. [Error Handling Standards](#error-handling-standards)
11. [Development Checklists](#development-checklists)

---

## ExchangeEnum Usage Rules

### MANDATORY: Always Use ExchangeEnum

**Rule**: NEVER use raw strings for exchange identification. Always use `ExchangeEnum`.

**✅ Correct:**
```python
from structs.common import ExchangeEnum

# Factory registration
PublicWebSocketExchangeFactory.register(ExchangeEnum.MEXC, MexcWebsocketPublic)

# Factory injection
exchange = PublicWebSocketExchangeFactory.inject(ExchangeEnum.MEXC, config=config)

# Configuration
if exchange_enum == ExchangeEnum.MEXC:
    # MEXC-specific logic
```

**❌ Incorrect:**
```python
# NEVER use raw strings
PublicWebSocketExchangeFactory.register("mexc", MexcWebsocketPublic)
exchange = PublicWebSocketExchangeFactory.inject("mexc", config=config)
```

### Entry Point Pattern

**Rule**: Factory interfaces accept both string and ExchangeEnum for backward compatibility, but **immediately convert to ExchangeEnum**.

**Implementation Pattern:**
```python
from core.utils.exchange_utils import exchange_name_to_enum

@classmethod
def register(cls, exchange: Union[str, ExchangeEnum], implementation_class: Type) -> None:
    # Convert to ExchangeEnum at entry point
    exchange_enum = exchange_name_to_enum(exchange)
    
    # Use ExchangeEnum internally
    cls._implementations[exchange_enum] = implementation_class
```

### Available Exchanges

**Current ExchangeEnum Values:**
- `ExchangeEnum.MEXC` → `"MEXC_SPOT"`
- `ExchangeEnum.GATEIO` → `"GATEIO_SPOT"`
- `ExchangeEnum.GATEIO_FUTURES` → `"GATEIO_FUTURES"`

---

## Factory Pattern Requirements

### MANDATORY: Use Factories for All Exchange Creation

**Rule**: NEVER create exchange instances directly. Always use factory methods.

**✅ Correct:**
```python
from core.factories.websocket import PublicWebSocketExchangeFactory
from core.config import get_exchange_config

# Create WebSocket via factory
config = get_exchange_config("mexc")
ws_exchange = PublicWebSocketExchangeFactory.inject(ExchangeEnum.MEXC, config=config)
```

**❌ Incorrect:**
```python
# NEVER instantiate directly
ws_exchange = MexcWebsocketPublic(config=config)
```

### Factory Types and Usage

**Available Factories:**
1. **PublicWebSocketExchangeFactory** - Public WebSocket connections
2. **PrivateWebSocketExchangeFactory** - Private WebSocket connections  
3. **PublicRestExchangeFactory** - Public REST clients
4. **PrivateRestExchangeFactory** - Private REST clients

**Factory Methods:**
- `register(exchange, implementation_class)` - Register implementation
- `inject(exchange, **kwargs)` - Create/retrieve instance
- `is_registered(exchange)` - Check registration
- `get_registered_exchanges()` - List available exchanges

---

## Auto-Registration Patterns

### MANDATORY: Follow Auto-Registration Pattern

**Rule**: All exchange implementations must auto-register on import using the established pattern.

**Implementation Template:**
```python
# In exchange implementation module (e.g., mexc_ws_public.py)
from core.factories.websocket import PublicWebSocketExchangeFactory
from structs.common import ExchangeEnum

class MexcWebsocketPublic(BaseExchangePublicWebsocketInterface):
    # Implementation here
    pass

# Auto-register on import (at module level)
PublicWebSocketExchangeFactory.register(ExchangeEnum.MEXC, MexcWebsocketPublic)
```

### Registration Location Rules

**Registration happens in implementation modules:**
- REST implementations: Register in `mexc_rest_public.py`, `mexc_rest_private.py`
- WebSocket implementations: Register in `mexc_ws_public.py`, `mexc_ws_private.py`
- Service implementations: Register in respective service modules

**NEVER register in:**
- Factory modules themselves
- `__init__.py` files
- Configuration files
- Main application files

---

## Import Dependencies for Proper Registration

### CRITICAL: Import Order for Auto-Registration

**Rule**: Import exchange modules to trigger auto-registration BEFORE using factories.

**✅ Correct Import Pattern:**
```python
# 1. Import exchange modules FIRST (triggers registration)
from exchanges.mexc import MexcWebsocketPublic  # Auto-registers
from exchanges.gateio import GateioWebsocketPublic  # Auto-registers

# 2. THEN import and use factories
from core.factories.websocket import PublicWebSocketExchangeFactory

# 3. NOW factories have registrations available
ws_exchange = PublicWebSocketExchangeFactory.inject(ExchangeEnum.MEXC, config=config)
```

**❌ Common Mistake:**
```python
# Wrong: Using factory before imports
from core.factories.websocket import PublicWebSocketExchangeFactory

# This will fail - no registrations exist yet!
ws_exchange = PublicWebSocketExchangeFactory.inject(ExchangeEnum.MEXC, config=config)

# Too late - import after factory usage
from exchanges.mexc import MexcWebsocketPublic
```

### Package-Level Import Pattern

**In exchange `__init__.py` files:**
```python
# exchanges/mexc/__init__.py

# Auto-register services (symbol mapper, mappings)
from . import services

# Auto-register REST strategies  
from .rest import strategies

# Auto-register WebSocket strategies (triggers registration)
from .ws import strategies as ws_strategies

# Import main implementations (triggers their registration)
from .public_exchange import MexcPublicExchange
from .private_exchange import MexcPrivateExchange
```

### Application-Level Import Requirements

**In main application files:**
```python
# Data collector, tools, examples MUST import exchange packages
import exchanges.mexc  # Triggers all MEXC registrations
import exchanges.gateio  # Triggers all Gate.io registrations

# NOW factories are ready to use
from core.factories.websocket import PublicWebSocketExchangeFactory
```

---

## Code Organization Standards

### Directory Structure (MANDATORY)

```
src/
├── core/                           # Core framework components
│   ├── factories/                  # Factory implementations
│   │   ├── websocket/             # WebSocket factories
│   │   ├── rest/                  # REST factories
│   │   └── base_exchange_factory.py
│   ├── exchanges/                 # Base classes for implementations
│   │   ├── rest/spot/            # REST base classes
│   │   └── websocket/spot/       # WebSocket base classes
│   ├── transport/                # Transport layer (REST/WebSocket)
│   ├── config/                   # Configuration management
│   └── utils/                    # Utility functions
├── exchanges/                     # Exchange-specific implementations
│   ├── mexc/                     # MEXC implementation
│   │   ├── rest/                 # MEXC REST clients
│   │   ├── ws/                   # MEXC WebSocket clients
│   │   ├── services/             # MEXC services (mappers, etc.)
│   │   ├── public_exchange.py    # Main public interface
│   │   └── private_exchange.py   # Main private interface
│   └── gateio/                   # Gate.io implementation (same structure)
├── structs/                      # Common data structures
│   └── common.py                 # All msgspec.Struct definitions
└── interfaces/                   # Abstract interfaces
    └── cex/base/                 # Base exchange interfaces
```

### File Naming Conventions

**Exchange Implementations:**
- `{exchange}_rest_public.py` - Public REST client
- `{exchange}_rest_private.py` - Private REST client  
- `{exchange}_ws_public.py` - Public WebSocket client
- `{exchange}_ws_private.py` - Private WebSocket client
- `public_exchange.py` - Main public interface
- `private_exchange.py` - Main private interface

**Services and Strategies:**
- `mapper.py` - Symbol mapping services
- `subscription.py` - WebSocket subscription strategies
- `message_parser.py` - Message parsing strategies
- `connection.py` - Connection management strategies

---

## Type Safety Rules

### MANDATORY: Strong Typing Requirements

**Rule**: All function signatures must include complete type hints.

**✅ Correct:**
```python
from typing import Optional, List, Dict, Union
from structs.common import Symbol, OrderBook, ExchangeEnum
from core.config.structs import ExchangeConfig

def create_exchange(
    exchange: ExchangeEnum,
    config: ExchangeConfig,
    symbols: Optional[List[Symbol]] = None
) -> BaseExchangeInterface:
    """Type-safe exchange creation."""
```

**❌ Incorrect:**
```python
def create_exchange(exchange, config, symbols=None):
    """No type hints - forbidden"""
```

### msgspec.Struct Usage

**Rule**: ALL data structures must use `msgspec.Struct` from `structs.common.py`.

**✅ Correct:**
```python
from structs.common import Symbol, OrderBook, Trade, BookTicker

def process_orderbook(orderbook: OrderBook) -> None:
    """Use unified structures."""
```

**❌ Incorrect:**
```python
# NEVER create custom data classes
@dataclass
class CustomOrderBook:
    bids: List[Tuple[float, float]]
```

### Type Validation Pattern

**Implementation Pattern:**
```python
from core.utils.exchange_utils import exchange_name_to_enum

def validate_exchange_input(exchange: Union[str, ExchangeEnum]) -> ExchangeEnum:
    """Convert and validate exchange input."""
    return exchange_name_to_enum(exchange)  # Raises ValueError if invalid
```

---

## SOLID Principles Application

### Single Responsibility Principle (SRP)

**Rule**: Each class/module has ONE focused purpose.

**✅ Examples:**
- `PublicWebSocketExchangeFactory` - Only creates WebSocket instances
- `MexcWebsocketPublic` - Only handles MEXC WebSocket operations
- `SymbolMapper` - Only converts symbol formats

**❌ Violations:**
- Mixing REST and WebSocket in one class
- Combining data processing with connection management
- Including business logic in factory classes

### Open/Closed Principle (OCP)

**Rule**: Extend through interfaces/composition, never modify existing components.

**✅ New Exchange Implementation:**
```python
# Add new exchange by implementing interface
class KucoinWebsocketPublic(BaseExchangePublicWebsocketInterface):
    """New exchange - no existing code modified."""

# Register with factory
PublicWebSocketExchangeFactory.register(ExchangeEnum.KUCOIN, KucoinWebsocketPublic)
```

### Interface Segregation Principle (ISP)

**Rule**: Use the most specific interface needed.

**✅ Correct Interface Usage:**
```python
# Market data only - use public interface
def collect_data(exchange: BasePublicExchangeInterface) -> None:
    orderbooks = exchange.orderbooks
    symbols = exchange.active_symbols

# Trading operations - use private interface  
def execute_trade(exchange: BasePrivateExchangeInterface) -> None:
    balance = exchange.balances
    exchange.place_limit_order(...)
```

### Dependency Inversion Principle (DIP)

**Rule**: Depend on abstractions, inject dependencies.

**✅ Correct Dependency Injection:**
```python
class ArbitrageEngine:
    def __init__(
        self,
        public_exchange: BasePublicExchangeInterface,  # Abstract interface
        private_exchange: BasePrivateExchangeInterface  # Abstract interface
    ):
        self.public_exchange = public_exchange
        self.private_exchange = private_exchange
```

---

## Performance Standards (HFT Requirements)

### Latency Requirements

**MANDATORY Performance Targets:**
- **Factory Operations**: <1ms (achieved: <0.5ms)
- **Exchange Creation**: <10ms 
- **Symbol Resolution**: <1μs (achieved: 0.947μs)
- **Exchange Formatting**: <1μs (achieved: 0.306μs)
- **REST Requests**: <50ms end-to-end
- **WebSocket Message Processing**: <1ms

### Memory Management Rules

**MANDATORY:**
1. **Use object pooling** for frequently allocated objects
2. **Reuse HTTP sessions** - never create new sessions per request
3. **Pre-compile symbol mappings** at startup
4. **Cache static data only** (never real-time trading data)

**✅ Correct Caching:**
```python
# Safe to cache - static configuration
symbol_mappings = {"BTC/USDT": "BTCUSDT"}  # OK
exchange_info = {"min_qty": 0.001}  # OK

# NEVER cache - real-time data  
orderbook_cache = {}  # FORBIDDEN
balance_cache = {}    # FORBIDDEN
```

### HFT Caching Policy (CRITICAL)

**RULE**: NEVER cache real-time trading data.

**FORBIDDEN to Cache:**
- Orderbook snapshots
- Account balances  
- Order status
- Recent trades
- Position data
- Market data

**Safe to Cache:**
- Symbol mappings
- Exchange configuration
- Trading rules
- Fee schedules

---

## Common Implementation Patterns

### Exchange Implementation Template

**Base Implementation Pattern:**
```python
from core.factories.websocket import PublicWebSocketExchangeFactory
from core.exchanges.websocket.spot.base_ws_public import BaseExchangePublicWebsocketInterface
from structs.common import ExchangeEnum

class ExchangeWebsocketPublic(BaseExchangePublicWebsocketInterface):
    """Exchange-specific WebSocket implementation."""
    
    def __init__(self, config: ExchangeConfig, **kwargs):
        super().__init__(config, **kwargs)
        # Exchange-specific initialization
    
    async def connect(self) -> None:
        """Implement connection logic."""
        pass
    
    async def disconnect(self) -> None:
        """Implement disconnection logic."""
        pass

# Auto-register on import
PublicWebSocketExchangeFactory.register(ExchangeEnum.EXCHANGE_NAME, ExchangeWebsocketPublic)
```

### Factory Usage Pattern

**Standard Factory Usage:**
```python
# 1. Import exchanges for registration
import exchanges.mexc
import exchanges.gateio

# 2. Import factory
from core.factories.websocket import PublicWebSocketExchangeFactory

# 3. Create instances
config = get_exchange_config("mexc")
ws_exchange = PublicWebSocketExchangeFactory.inject(ExchangeEnum.MEXC, config=config)
```

### Error Handling Pattern

**Standard Error Handling:**
```python
try:
    exchange = PublicWebSocketExchangeFactory.inject(ExchangeEnum.MEXC, config=config)
except ValueError as e:
    logger.error(f"Exchange creation failed: {e}")
    # Handle specific error types
    if "not registered" in str(e):
        # Registration missing
        raise RuntimeError(f"MEXC WebSocket not registered. Import exchanges.mexc first.")
    raise
```

---

## Error Handling Standards

### Factory Error Patterns

**Common Factory Errors and Solutions:**

1. **"No implementation registered"**
   ```python
   # Problem: Missing import for auto-registration
   # Solution: Import exchange module first
   import exchanges.mexc  # Triggers registration
   ```

2. **"Unknown exchange"**
   ```python
   # Problem: Invalid exchange identifier
   # Solution: Use ExchangeEnum
   factory.inject(ExchangeEnum.MEXC, config=config)  # Correct
   ```

3. **"Config required"**
   ```python
   # Problem: Missing required configuration
   # Solution: Provide valid ExchangeConfig
   config = get_exchange_config("mexc")
   factory.inject(ExchangeEnum.MEXC, config=config)
   ```

### Logging Standards

**MANDATORY Logging Pattern:**
```python
import logging

logger = logging.getLogger(__name__)

# Factory registration
logger.debug(f"Registered {implementation_class.__name__} for {exchange.value}")

# Factory injection  
logger.info(f"Created {implementation_class.__name__} instance for {exchange.value}")

# Errors
logger.error(f"Failed to create instance for {exchange.value}: {error}")
```

---

## Development Checklists

### New Exchange Implementation Checklist

**Before implementing a new exchange:**

- [ ] Add exchange to `ExchangeEnum` in `structs/common.py`
- [ ] Create exchange directory: `src/exchanges/{exchange_name}/`
- [ ] Implement required interfaces:
  - [ ] `BasePublicExchangeInterface`
  - [ ] `BasePrivateExchangeInterface` (if trading supported)
- [ ] Create WebSocket implementations:
  - [ ] Public WebSocket with auto-registration
  - [ ] Private WebSocket with auto-registration (if needed)
- [ ] Create REST implementations:
  - [ ] Public REST with auto-registration  
  - [ ] Private REST with auto-registration (if needed)
- [ ] Implement services:
  - [ ] Symbol mapper with auto-registration
  - [ ] Exchange mappings with auto-registration
- [ ] Create package `__init__.py` with proper imports
- [ ] Add integration tests
- [ ] Update documentation

### Factory Registration Checklist

**When adding factory registration:**

- [ ] Use `ExchangeEnum` for exchange identification
- [ ] Implement auto-registration in implementation module
- [ ] Add registration at module level (not in class)
- [ ] Test registration with `is_registered()` method
- [ ] Verify import triggers registration
- [ ] Add logging for registration events
- [ ] Handle registration errors gracefully

### Code Review Checklist

**Before merging code:**

- [ ] All exchange references use `ExchangeEnum`
- [ ] Factory pattern used for all exchange creation
- [ ] Auto-registration implemented correctly
- [ ] Import dependencies correct for registration
- [ ] Type hints complete and accurate
- [ ] SOLID principles followed
- [ ] Performance requirements met
- [ ] Error handling implemented
- [ ] Logging added appropriately
- [ ] Tests cover new functionality

### Performance Validation Checklist

**Before production deployment:**

- [ ] Factory operations <1ms
- [ ] Symbol resolution <1μs  
- [ ] No real-time data caching
- [ ] HTTP session reuse enabled
- [ ] Object pooling implemented
- [ ] Memory usage optimized
- [ ] Connection pooling active
- [ ] Latency benchmarks met

---

## Common Anti-Patterns (AVOID)

### ❌ Direct Instantiation
```python
# WRONG: Direct instantiation
exchange = MexcWebsocketPublic(config)

# CORRECT: Factory usage
exchange = PublicWebSocketExchangeFactory.inject(ExchangeEnum.MEXC, config=config)
```

### ❌ String-Based Exchange IDs
```python
# WRONG: String usage
if exchange_name == "mexc":

# CORRECT: Enum usage  
if exchange_enum == ExchangeEnum.MEXC:
```

### ❌ Manual Registration
```python
# WRONG: Manual registration in main code
PublicWebSocketExchangeFactory.register("mexc", MexcWebsocketPublic)

# CORRECT: Auto-registration in implementation module
```

### ❌ Missing Import Dependencies
```python
# WRONG: Factory usage without imports
ws = PublicWebSocketExchangeFactory.inject(ExchangeEnum.MEXC, config=config)  # Fails

# CORRECT: Import first, then use
import exchanges.mexc
ws = PublicWebSocketExchangeFactory.inject(ExchangeEnum.MEXC, config=config)
```

### ❌ Real-Time Data Caching
```python
# WRONG: Caching real-time data
self.orderbook_cache[symbol] = orderbook  # HFT violation

# CORRECT: Always fetch fresh data
orderbook = exchange.get_orderbook(symbol)
```

---

**These guidelines are MANDATORY for all development work on the CEX arbitrage engine. Violations will cause system failures, performance degradation, and potential trading losses.**