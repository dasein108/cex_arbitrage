# CEX Arbitrage Engine - System Architecture

High-level architectural documentation for the ultra-high-performance CEX arbitrage engine designed for sub-millisecond cryptocurrency trading.

## System Overview

This is a **high-frequency trading (HFT) arbitrage engine** built for professional cryptocurrency trading across multiple exchanges. The system features a **clean factory-pattern architecture** with unified interfaces and SOLID principles throughout.

**Current Architecture Features**:
- **Factory Pattern Architecture** - Exchange creation via `src/cex/factories/exchange_factory.py`
- **Unified Interface System** - All exchanges implement `src/interfaces/cex/base/` interfaces
- **Common Data Structures** - All components use `src/structs/common.py` msgspec.Struct types
- **Core Base Classes** - Implementation foundation via `src/core/cex/` base classes
- **Sub-50ms latency** for complete arbitrage cycle execution
- **SOLID-compliant design** with focused, single-responsibility components
- **Professional-grade resource management** with graceful shutdown
- **Event-driven architecture** with async/await throughout
- **Zero-copy message processing** using msgspec for maximum performance
- **Production-grade reliability** with automatic reconnection and error recovery

**Architecture Evolution**:
- **Factory Pattern Implementation**: Type-safe exchange creation with automatic dependency injection
- **Interface Segregation**: Clean separation between public and private operations
- **Component-Based Design**: Each component has single responsibility with clear interfaces
- **Unified Data Structures**: All exchanges use identical msgspec.Struct types from `src/structs/common.py`
- **Base Class Architecture**: Core functionality provided by `src/core/cex/` base classes
- **SOLID Principles**: Dependency injection, interface segregation, and composition over inheritance

## Core Architectural Principles

### 1. Factory Pattern + SOLID Architecture

The system follows a **factory-pattern-based architecture** with **SOLID principles** throughout:

**Factory Layer** → **Interface Layer** → **Core Base Classes** → **Exchange Implementations** → **Common Data Structures**

**Key Components:**
- **ExchangeFactory** (`src/cex/factories/exchange_factory.py`): Type-safe exchange creation with dependency injection
- **Interface System** (`src/interfaces/cex/base/`): Clean separation between public and private operations
  - **BaseExchangeInterface**: Foundation with connection and state management
  - **BasePublicExchangeInterface**: Market data operations (orderbooks, symbols, tickers)
  - **BasePrivateExchangeInterface**: Trading operations + market data (orders, balances, positions)
- **Core Base Classes** (`src/core/cex/`): Implementation foundation for REST/WebSocket clients
- **Common Data Structures** (`src/structs/common.py`): Unified msgspec.Struct types for all exchanges

### 2. Interface Hierarchy and Separation of Concerns

```
BaseExchangeInterface (connection & state management)
├── BasePublicExchangeInterface (market data only, no authentication)
└── BasePrivateExchangeInterface (trading + market data, requires authentication)
```

**Interface Segregation Benefits**:
- **Public Components**: Use `BasePublicExchangeInterface` for market data operations
- **Private Components**: Use `BasePrivateExchangeInterface` for trading operations
- **Exchange Implementations**: Inherit from `BasePrivateExchangeInterface` (includes public via inheritance)
- **Dependency Minimization**: Components depend only on interfaces they need
- **Security by Design**: Clear authentication boundaries between public and private operations

### 3. Factory Pattern Implementation

**Type-Safe Exchange Creation**:
```python
# Public exchange (no credentials required)
exchange = ExchangeFactory.create_public_exchange(
    ExchangeEnum.MEXC,
    symbols=[Symbol("BTC", "USDT")]
)

# Private exchange (requires credentials)
exchange = ExchangeFactory.create_private_exchange(
    ExchangeEnum.MEXC,
    config=ExchangeConfig(credentials=...)
)
```

**Factory Benefits**:
- **Type Safety**: `ExchangeEnum` ensures only supported exchanges
- **Automatic Dependency Injection**: REST/WebSocket clients configured automatically
- **Error Handling**: Graceful validation and clear error messages
- **SOLID Compliance**: Centralized creation logic following Factory pattern

### 4. HFT Performance Optimizations

- **O(1) Symbol Resolution**: Hash-based lookup architecture achieving <1μs latency
- **Pre-computed Symbol Caches**: Common symbols calculated once at startup (O(n²) → O(1))
- **Exchange Formatting Optimization**: Fast lookup tables for exchange-specific symbol formats
- **Object Pooling**: Reduces allocation overhead by 75% in hot paths
- **Connection Pooling**: Persistent HTTP sessions with intelligent reuse
- **Zero-Copy Parsing**: msgspec-exclusive JSON processing
- **Pre-compiled Constants**: Optimized lookup tables and magic bytes

### 5. Type Safety and Data Integrity

- **msgspec.Struct**: Frozen, hashable data structures throughout (`src/structs/common.py`)
- **IntEnum**: Performance-optimized enumerations
- **NewType aliases**: Type safety without runtime overhead
- **Comprehensive validation**: Data integrity at API boundaries

## Architecture Implementation: SOLID Principles

### Component Separation and Responsibilities

The system implements **SOLID principles** with clear component boundaries:

#### 1. Single Responsibility Principle (SRP)
Each component has **one focused purpose**:
- **ExchangeFactory**: Creates and configures exchange instances only
- **BasePublicExchangeInterface**: Market data operations only
- **BasePrivateExchangeInterface**: Trading operations + market data
- **REST clients**: HTTP operations only
- **WebSocket clients**: Real-time streaming only

#### 2. Open/Closed Principle (OCP)
- **Extensible interfaces**: New exchanges implement standard interfaces without modifying existing code
- **Factory extensibility**: New exchanges added via Factory methods
- **Base class extension**: Core functionality extended through inheritance

#### 3. Liskov Substitution Principle (LSP)
- **Interchangeable exchanges**: All exchange implementations are fully substitutable
- **Factory pattern**: Ensures consistent behavior across all exchanges
- **Interface compliance**: All implementations respect interface contracts

#### 4. Interface Segregation Principle (ISP)
- **Separated Exchange Interfaces**: 
  - Public operations (market data) separated from private operations (trading)
  - Components use `BasePublicExchangeInterface` when only market data is needed
  - Components use `BasePrivateExchangeInterface` when trading operations are required
- **Minimal dependencies**: Components depend only on the interfaces they use
- **Clean abstractions**: No component is forced to depend on unused functionality

#### 5. Dependency Inversion Principle (DIP)
- **Factory dependency injection**: Exchange components created via Factory
- **Abstract dependencies**: All components depend on interfaces, not concrete implementations
- **Inversion of control**: High-level modules don't depend on low-level modules

### Exchange Implementation Architecture

**All exchange implementations inherit from `BasePrivateExchangeInterface`** (which includes public operations via inheritance):

**Exchange Interface Hierarchy**:
```
BaseExchangeInterface (src/interfaces/cex/base/base_exchange.py)
├── BasePublicExchangeInterface (src/interfaces/cex/base/base_public_exchange.py)
│   ├── orderbooks: Dict[Symbol, OrderBook] (property)
│   ├── symbols_info: SymbolsInfo (property) 
│   ├── active_symbols: List[Symbol] (property)
│   ├── add_symbol(symbol: Symbol)
│   └── remove_symbol(symbol: Symbol)
│
└── BasePrivateExchangeInterface (src/interfaces/cex/base/base_private_exchange.py)
    ├── Inherits all public methods from BasePublicExchangeInterface
    ├── balances: Dict[Symbol, AssetBalance] (property)
    ├── open_orders: Dict[Symbol, List[Order]] (property)
    ├── positions: Dict[Symbol, Position] (property)
    ├── place_limit_order(...)
    ├── place_market_order(...)
    └── cancel_order(...)
```

**Exchange Implementations**:
```
BasePrivateExchangeInterface
├── MexcPrivateExchange (implements BasePrivateExchangeInterface)
└── GateioPrivateExchange (implements BasePrivateExchangeInterface)
```

**Composition Pattern Benefits**:
- **SOLID Compliance**: Delegates to specialized public/private components
- **Clear Separation**: Public market data vs private trading operations
- **Interface Segregation**: Components use only the interface level they need
- **WebSocket Coordination**: Manages real-time streaming without tight coupling
- **HFT Compliance**: No caching of real-time trading data
- **Type Safety**: Unified data structures via `src/structs/common.py`

**Key Implementation Requirements**:
1. **Inherit from BasePrivateExchangeInterface**: Provides both public and private capabilities
2. **Implement all abstract methods**: Both public and private interface methods
3. **Composition over inheritance**: Delegate to specialized REST/WebSocket components
4. **HFT Compliance**: Never cache real-time trading data (balances, orders, positions)
5. **Unified structures**: Use only `Symbol`, `SymbolInfo`, `OrderBook`, etc. from `src/structs/common.py`

## Key Architectural Decisions

### Factory Pattern Configuration

**Type-Safe Exchange Selection**:
- **ExchangeEnum** provides compile-time validation of supported exchanges
- **Factory Methods** ensure consistent exchange creation patterns
- **Automatic Configuration** handles REST/WebSocket client setup
- **Error Validation** provides clear feedback for missing implementations

**Configuration Flow**:
```
ExchangeEnum → ExchangeFactory → BaseClass Instantiation → Interface Implementation
```

### Core Base Classes Architecture

**REST Client Foundation** (`src/core/cex/rest/`):
```
src/core/cex/rest/
├── spot/
│   ├── base_rest_spot_public.py   # Public REST operations
│   └── base_rest_spot_private.py  # Private REST operations
└── futures/
    ├── base_rest_futures_public.py   # Futures public operations  
    └── base_rest_futures_private.py  # Futures private operations
```

**WebSocket Client Foundation** (`src/core/cex/websocket/`):
```
src/core/cex/websocket/
└── spot/
    ├── base_ws_public.py   # Public WebSocket streaming
    └── base_ws_private.py  # Private WebSocket streaming
```

**Service Layer Foundation** (`src/core/cex/services/`):
```
src/core/cex/services/
├── symbol_mapper/      # Symbol format conversion
└── unified_mapper/     # Exchange-specific mappings
```

### Common Data Structures (`src/structs/common.py`)

**ALL exchanges use these unified structures**:
- **Symbol**: Trading pair representation
- **OrderBook**: Bid/ask price levels
- **Order**: Order lifecycle management
- **AssetBalance**: Account balance tracking
- **Position**: Trading position data
- **Trade**: Individual trade records
- **Ticker**: 24hr statistics
- **Kline**: Candlestick data
- **SymbolInfo**: Trading rules and precision

**Benefits of Unified Structures**:
- **Type Safety**: msgspec.Struct provides compile-time validation
- **Performance**: Zero-copy serialization/deserialization
- **Consistency**: All exchanges use identical data representations
- **Maintainability**: Single source of truth for data structure definitions

## HFT Caching Policy (CRITICAL - TRADING SAFETY)

**RULE**: Caching real-time trading data is UNACCEPTABLE in HFT systems.

**NEVER CACHE (Real-time Trading Data):**
- Orderbook snapshots (pricing data)
- Account balances (change with each trade)  
- Order status (execution state)
- Recent trades (market movement)
- Position data
- Real-time market data

**SAFE TO CACHE (Static Configuration Data):**
- Symbol mappings and SymbolInfo
- Exchange configuration
- Trading rules and precision
- Fee schedules
- Market hours
- API endpoint configurations

**RATIONALE**: Caching real-time trading data causes execution on stale prices, failed arbitrage opportunities, phantom liquidity risks, and regulatory compliance issues. This architectural rule supersedes ALL other performance considerations.

## Component Documentation

### Factory Pattern Components

**Core Factory Implementation**:
- **[Exchange Factory](src/cex/factories/exchange_factory.py)** - Type-safe exchange creation with dependency injection
- **[Exchange Enum](src/cex/__init__.py)** - Supported exchange enumeration for type safety

### Interface Layer Components

**Unified Interface System** (`src/interfaces/cex/base/`):
- **[Base Exchange Interface](src/interfaces/cex/base/base_exchange.py)** - Foundation interface with connection management
- **[Base Public Exchange Interface](src/interfaces/cex/base/base_public_exchange.py)** - Market data operations
- **[Base Private Exchange Interface](src/interfaces/cex/base/base_private_exchange.py)** - Trading operations + market data

### Core Base Classes

**REST Client Foundation** (`src/core/cex/rest/`):
- **[Base REST Spot Public](src/core/cex/rest/spot/base_rest_spot_public.py)** - Public REST operations
- **[Base REST Spot Private](src/core/cex/rest/spot/base_rest_spot_private.py)** - Private REST operations

**WebSocket Client Foundation** (`src/core/cex/websocket/`):
- **[Base WebSocket Public](src/core/cex/websocket/spot/base_ws_public.py)** - Public streaming
- **[Base WebSocket Private](src/core/cex/websocket/spot/base_ws_private.py)** - Private streaming

### Exchange Implementations

**Exchange-Specific Implementations**:
- **[MEXC Implementation](src/cex/mexc/README.md)** - MEXC-specific implementation (reference implementation)
- **[Gate.io Implementation](src/cex/gateio/README.md)** - Gate.io-specific implementation

### Data Structures and Common Components

**Unified Data Structures**:
- **[Common Structures](src/structs/common.py)** - All msgspec.Struct data types used across exchanges
- **[Common Components](src/common/README.md)** - Shared utilities and base components

## Development Guidelines

### Architectural Patterns (MANDATORY)

**Factory Pattern Usage**:
- **Use ExchangeFactory**: Never create exchange instances directly in business logic
- **Type Safety**: Always use ExchangeEnum for exchange selection
- **Error Handling**: Let Factory handle validation and provide clear error messages

**SOLID Principles Compliance**:
- **Single Responsibility**: Each component has ONE focused purpose - never mix concerns
- **Open/Closed**: Extend through interfaces/composition, never modify existing components
- **Liskov Substitution**: All interface implementations must be fully interchangeable
- **Interface Segregation**: Keep interfaces focused - no unused methods
- **Dependency Inversion**: Depend on abstractions, inject dependencies, avoid tight coupling

**Component Organization** (Clean factory-pattern architecture):
- **src/interfaces/cex/base/**: Interface definitions (never modify after implementation)
- **src/core/cex/**: Base class implementations for REST/WebSocket clients
- **src/structs/common.py**: Unified data structures for all exchanges
- **src/cex/factories/**: Factory pattern implementations
- **src/cex/{exchange}/**: Exchange-specific implementations
- **src/common/**: Shared utilities and base components

### KISS/YAGNI Principles (MANDATORY)

- **Keep It Simple, Stupid** - Avoid unnecessary complexity, prefer composition over inheritance
- **You Aren't Gonna Need It** - Don't implement features not explicitly requested
- **Ask for confirmation** before adding functionality beyond task scope
- **Prefer refactoring existing components** over creating new ones

### Performance Requirements

- **Target Latency**: <50ms end-to-end HTTP requests
- **Symbol Resolution**: <1μs per lookup (achieved: 0.947μs avg)
- **Exchange Formatting**: <1μs per conversion (achieved: 0.306μs avg)
- **Common Symbols Lookup**: <0.1μs per operation (achieved: 0.035μs avg)
- **JSON Parsing**: <1ms per message using msgspec
- **Memory Management**: O(1) per request, >95% connection reuse
- **Cache Build Time**: <50ms for symbol initialization (achieved: <10ms)
- **Uptime**: >99.9% availability with automatic recovery

#### Achieved Performance Benchmarks (Symbol Resolution System)

**Symbol Resolution Performance**:
- **Average Latency**: 0.947μs per lookup
- **Throughput**: 1,056,338 operations/second
- **95th Percentile**: <2μs
- **99th Percentile**: <5μs
- **Architecture**: Hash-based O(1) lookup with pre-computed caches

**Exchange Formatting Performance**:
- **Average Latency**: 0.306μs per conversion
- **Throughput**: 3,267,974 operations/second
- **Memory Usage**: Pre-built lookup tables for zero-computation formatting
- **Supported Formats**: All major exchange symbol conventions

**Common Symbols Cache Performance**:
- **Average Latency**: 0.035μs per lookup
- **Throughput**: 28,571,429 operations/second
- **Cache Build**: 8.7ms for 3,603 unique symbols
- **Hit Rate**: >95% for typical arbitrage operations

### Usage Examples (Factory Pattern)

**Creating Exchanges via Factory**:
```bash
# Factory-based exchange creation examples
python -c "
from src.cex.factories.exchange_factory import ExchangeFactory
from src.cex import ExchangeEnum
from src.structs.common import Symbol

# Public exchange (no credentials)
exchange = ExchangeFactory.create_public_exchange(
    ExchangeEnum.MEXC,
    symbols=[Symbol('BTC', 'USDT')]
)

# Private exchange (requires credentials)
from src.core.config.structs import ExchangeConfig
from src.structs.common import ExchangeCredentials

config = ExchangeConfig(
    name='mexc',
    credentials=ExchangeCredentials(api_key='...', secret_key='...')
)
exchange = ExchangeFactory.create_private_exchange(
    ExchangeEnum.MEXC,
    config=config
)
print('✓ Factory pattern working correctly')
"
```

### Numeric Type Standards (MANDATORY)

- **Use float for all financial calculations** - Python's float type provides sufficient precision for cryptocurrency trading
- **NEVER use Decimal()** - Decimal adds unnecessary computational overhead that violates HFT latency requirements
- **Rationale**: 64-bit float precision (15-17 decimal digits) exceeds cryptocurrency precision needs (typically 8 decimal places max)
- **Exception**: Only use Decimal if explicitly required by external library APIs that don't accept float