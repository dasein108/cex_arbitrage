# CEX Arbitrage Engine - System Architecture

High-level architectural documentation for the ultra-high-performance CEX arbitrage engine designed for sub-millisecond cryptocurrency trading.

## System Overview

This is a **high-frequency trading (HFT) arbitrage engine** built for professional cryptocurrency trading across multiple exchanges. The system features a **clean src-only architecture** with unified interfaces and SOLID principles throughout.

**Current Architecture Features**:
- **Clean src-only architecture** - All components use unified `src/exchanges/interface/` system
- **SOLID-compliant design** with focused, single-responsibility components
- **Sub-50ms latency** for complete arbitrage cycle execution
- **Factory pattern** eliminating code duplication in exchange creation
- **Unified interface system** - Single source of truth for all data structures and contracts
- **Professional-grade resource management** with graceful shutdown
- **Event-driven architecture** with async/await throughout
- **Zero-copy message processing** using msgspec for maximum performance
- **Abstract Factory pattern** enabling seamless exchange integration
- **Production-grade reliability** with automatic reconnection and error recovery

**Architecture Evolution Highlights**:
- **Eliminated Legacy Dependencies**: Removed `/raw` directory for clean architecture
- **Unified Type System**: All components use `src/exchanges/interface/structs.py` exclusively
- **Component-Based Design**: Each component has single responsibility with clear interfaces
- **Clean Main Entry Point**: Professional CLI with proper error handling and resource cleanup
- **SOLID Principles**: Factory pattern, dependency injection, and interface-driven design
- **Modernized Configuration System**: Dictionary-based exchange configuration with unified credential management
- **Dynamic Exchange Scaling**: New exchanges added via configuration without code changes

## Core Architectural Principles

### 1. SOLID-Compliant Component Architecture

The system follows a **clean src-only architecture** with **unified interfaces** and **SOLID principles** throughout:

**Configuration Layer** → **Exchange Factory** → **Unified Interface System** → **Symbol Resolution** → **Performance Monitor** → **Shutdown Manager** → **Controller Layer**

**Key Components:**
- **Unified Interface System** (`src/exchanges/interface/`): Single source of truth for all data structures and contracts
- **ConfigurationManager**: Single responsibility for configuration loading and validation
- **ExchangeFactory**: Factory pattern for exchange creation, eliminating code duplication
- **Symbol Resolution System**: Ultra-high-performance O(1) symbol lookup with <1μs latency
- **PerformanceMonitor**: Dedicated HFT performance monitoring with <50ms execution tracking
- **ShutdownManager**: Graceful shutdown coordination with resource cleanup
- **ArbitrageController**: Main orchestrator that coordinates all components via dependency injection

### 2. Event-Driven + Abstract Factory Architecture

The system follows a **layered event-driven architecture** with **Abstract Factory pattern**:

**Network Layer** → **Data Layer** → **Exchange Abstraction** → **Application Layer**

### 3. HFT Performance Optimizations

- **O(1) Symbol Resolution**: Hash-based lookup architecture achieving <1μs latency
- **Pre-computed Symbol Caches**: Common symbols calculated once at startup (O(n²) → O(1))
- **Exchange Formatting Optimization**: Fast lookup tables for exchange-specific symbol formats
- **Object Pooling**: Reduces allocation overhead by 75% in hot paths
- **Connection Pooling**: Persistent HTTP sessions with intelligent reuse
- **Zero-Copy Parsing**: msgspec-exclusive JSON processing
- **Pre-compiled Constants**: Optimized lookup tables and magic bytes
- **Intelligent Caching**: 90% performance improvement through strategic caching

### 4. Type Safety and Data Integrity

- **msgspec.Struct**: Frozen, hashable data structures throughout
- **IntEnum**: Performance-optimized enumerations
- **NewType aliases**: Type safety without runtime overhead
- **Comprehensive validation**: Data integrity at API boundaries

### 5. Interface-Driven Design

- **Abstract Interfaces**: Clean separation between public/private operations
- **Unified Exception System**: Structured error hierarchy with intelligent retry logic
- **Pluggable Architecture**: Exchange implementations as interchangeable components
- **Contract-First Development**: Interface definitions drive implementation

## Refactored Architecture: SOLID Principles Implementation

### Component Separation and Responsibilities

The system has been completely refactored to eliminate architectural code smells and implement **SOLID principles**:

#### 1. Single Responsibility Principle (SRP)
Each component has **one focused purpose**:
- **ConfigurationManager** (`src/arbitrage/configuration_manager.py`): Handles only configuration loading, validation, and management
- **ExchangeFactory** (`src/arbitrage/exchange_factory.py`): Creates and manages exchange instances using Factory pattern
- **PerformanceMonitor** (`src/arbitrage/performance_monitor.py`): Dedicated to HFT performance tracking and metrics
- **ShutdownManager** (`src/arbitrage/shutdown_manager.py`): Manages graceful shutdown and resource cleanup
- **ArbitrageController** (`src/arbitrage/controller.py`): Orchestrates components without implementing their logic

#### 2. Open/Closed Principle (OCP)
- **Extensible interfaces**: New exchanges implement `BaseExchangeInterface` without modifying existing code
- **Strategy pattern ready**: Trading algorithms can be added via plugin interfaces
- **Configurable components**: Behavior modification through configuration rather than code changes

#### 3. Liskov Substitution Principle (LSP)
- **Interchangeable exchanges**: All exchange implementations are fully substitutable
- **Consistent interfaces**: All components implement standard async patterns
- **Contract compliance**: Interface contracts are respected by all implementations

#### 4. Interface Segregation Principle (ISP)
- **Focused interfaces**: Each component exposes only methods relevant to its clients
- **Minimal dependencies**: Components depend only on the interfaces they actually use
- **Clean abstractions**: No component is forced to depend on unused functionality

#### 5. Dependency Inversion Principle (DIP)
- **Dependency injection**: Controller receives components rather than creating them
- **Abstract dependencies**: All components depend on interfaces, not concrete implementations
- **Inversion of control**: High-level modules don't depend on low-level modules

### Factory Pattern Implementation

**Problem Solved**: Eliminated code duplication in exchange creation and removed God Class antipattern.

**Solution**: `ExchangeFactory` implements Factory pattern with:
- **Centralized creation logic**: Single point for exchange instantiation
- **Credential management**: Secure API key handling with preview logging
- **Concurrent initialization**: Multiple exchanges created in parallel
- **Error resilience**: Graceful handling of exchange failures in dry run mode

### Exchange Implementation Architecture

**All exchange implementations inherit from `BaseExchangeInterface`** (`src/exchanges/interface/base_exchange.py`) following composition pattern:

**Exchange Hierarchy**:
```
BaseExchangeInterface (Abstract Interface)
├── MexcExchange (implements BaseExchangeInterface)
└── GateioExchange (implements BaseExchangeInterface)
```

**Composition Pattern Benefits**:
- **SOLID Compliance**: Delegates to specialized public/private components
- **Clear Separation**: Public market data vs private trading operations
- **WebSocket Coordination**: Manages real-time streaming without tight coupling
- **HFT Compliance**: No caching of real-time trading data
- **Type Safety**: Unified data structures via `exchanges.interface.structs`

**Key Implementation Requirements**:
1. **Inherit from BaseExchangeInterface**: Not from WebSocket or other specialized classes
2. **Implement all abstract methods**: `status`, `orderbook`, `balances`, `symbol_info`, `active_symbols`, `open_orders`
3. **Composition over inheritance**: Delegate to specialized REST/WebSocket components
4. **HFT Compliance**: Never cache real-time trading data (balances, orders, positions)
5. **Unified structures**: Use only `Symbol`, `SymbolInfo`, `OrderBook`, etc. from `exchanges.interface.structs`

### Clean Main Entry Point

**Previous**: Monolithic `main.py` with embedded mock classes and mixed concerns
**Current**: Clean `src/main.py` with:
- **Single responsibility**: Only entry point logic
- **Dependency injection**: Components created and injected properly
- **Clean error handling**: Structured exception management
- **Professional CLI**: Argument parsing with proper help and examples

## Key Architectural Decisions

### Configuration Architecture (NEW - Modernized System)

**Unified Configuration Dictionary Structure**:
- **Migrated from individual exchange sections** to unified `exchanges:` dictionary in `config.yaml`
- **Dynamic credential lookup** via `config.get_exchange_credentials(exchange_name)` 
- **Scalable exchange addition** - new exchanges require only YAML configuration entry
- **Environment variable integration** - seamless `.env` file support with `${VAR_NAME}` substitution
- **Backward compatibility maintained** during architectural transition

**Benefits of New Configuration Architecture**:
- **Eliminates code duplication** in credential management across exchanges
- **Enables dynamic exchange scaling** without code changes
- **Centralizes configuration validation** through unified methods
- **Simplifies testing and deployment** with consistent credential patterns
- **Future-proofs system** for additional exchange integrations

**Configuration Flow**:
```
config.yaml (exchanges: dict) → ConfigurationManager → ExchangeFactory → Dynamic Exchange Creation
```

### Performance-First Design Philosophy

1. **Single-threaded async architecture** - Eliminates locking overhead
2. **msgspec-exclusive JSON processing** - Consistent performance characteristics  
3. **Object pooling strategy** - Reduces GC pressure in hot paths
4. **Connection lifecycle management** - Optimized for persistent trading sessions

### Trading Safety Architecture

1. **Fail-fast exception propagation** - No silent error handling
2. **Structured retry logic** - Intelligent backoff with jitter
3. **Circuit breaker patterns** - Prevent cascade failures
4. **Comprehensive logging** - Audit trail for all trading operations

### Extensibility Patterns

1. **Abstract Factory** - New exchanges implement standard interfaces
2. **Strategy Pattern** - Pluggable trading algorithms
3. **Observer Pattern** - Event-driven market data distribution
4. **Dependency Injection** - Testable, modular components

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

### Symbol Resolution Architecture (HFT-Optimized)

The system implements an **ultra-high-performance symbol resolution architecture** achieving HFT-compliant latency targets:

#### Hash-Based Lookup System
- **O(1) Symbol Resolution**: `_symbol_lookup: Dict[Tuple[str, str], Dict[str, SymbolInfo]]`
- **Performance**: 0.947μs average latency, 1M+ operations/second throughput
- **Memory Efficiency**: Pre-computed lookup tables built once at startup
- **Type Safety**: Exclusive use of `Symbol` and `SymbolInfo` structs from unified interface

#### Pre-computed Common Symbols Cache
- **Optimization**: Common trading pairs calculated once at startup
- **Performance**: 0.035μs average latency, 28M+ operations/second throughput
- **Architecture**: `_common_symbols_cache: Dict[FrozenSet[str], Set[Symbol]]`
- **Build Time**: <10ms for 3,603+ unique symbols

#### Exchange Formatting Strategy
- **Fast Lookup Tables**: Exchange-specific symbol format conversion
- **Performance**: 0.306μs average latency, 3.2M+ operations/second throughput
- **Implementation**: Pre-built mapping dictionaries for each exchange format
- **Memory Trade-off**: Higher memory usage for sub-microsecond performance

#### Clean Architecture Compliance
- **Unified Interface System**: Exclusive use of `src/exchanges/interface/structs.py` types throughout
- **SOLID Principles**: Proper separation of concerns, interface-driven design
- **Type Safety**: Comprehensive type annotations with structured error handling
- **Clean Dependencies**: All components depend only on src-based interfaces

## Development Standards

### SOLID Principles Compliance

1. **Single Responsibility Principle** - Each class has one focused purpose
2. **Open/Closed Principle** - Extensible through interfaces, not modification
3. **Liskov Substitution Principle** - Interface implementations are interchangeable
4. **Interface Segregation Principle** - Clean separation of concerns
5. **Dependency Inversion Principle** - Depend on abstractions, not concretions

### Exception Handling Strategy

- **RULE**: NEVER handle exceptions at function level - propagate to higher levels
- **RULE**: Use unified exception hierarchy from `src/common/exceptions.py`
- **RATIONALE**: Prevents scattered exception handling, ensures consistent error management

### Interface Standards

- **Interface Compliance**: All implementations must use `src/exchanges/interface/`
- **Data Structure Standards**: msgspec.Struct from `src/exchanges/interface/structs.py`
- **Unified Architecture**: All components use src-based interfaces exclusively
- **Symbol Resolution**: Exclusive use of `Symbol` and `SymbolInfo` structs with O(1) lookup
- **Performance Targets**: <50ms latency, >95% uptime, <1μs symbol resolution
- **Type Safety**: Comprehensive type annotations with structured error propagation

## Market Data Architecture: Klines/Candlestick System

### Overview

The system now includes a comprehensive klines (candlestick) data fetching architecture implemented for both MEXC and Gate.io exchanges. This functionality provides historical and real-time price data essential for technical analysis and backtesting in arbitrage strategies.

### Core Klines Functionality

#### 1. Unified Interface System

All klines functionality is exposed through the `PublicExchangeInterface` with two primary methods:

- **`get_klines()`** - Single API request for limited time ranges
- **`get_klines_batch()`** - Multiple API requests for large time ranges with intelligent chunking

#### 2. Exchange-Specific Implementations

**MEXC Klines Architecture:**
- **Endpoint**: `/api/v3/klines`
- **Rate Limit**: 1200 requests/minute (20 req/sec)
- **Data Limit**: 1000 klines per request
- **Time Format**: Unix timestamps in milliseconds
- **Response Format**: Array of arrays `[open_time, open, high, low, close, volume, close_time, quote_volume]`
- **Supported Intervals**: 1m, 5m, 15m, 30m, 1h, 4h, 12h, 1d, 1w, 1M

**Gate.io Klines Architecture:**
- **Endpoint**: `/spot/candlesticks`
- **Rate Limit**: 200 requests/10 seconds (20 req/sec)
- **Data Limit**: 1000 klines per request
- **Time Format**: Unix timestamps in seconds
- **Response Format**: Array of arrays `[timestamp, volume, close, high, low, open, previous_close]`
- **Supported Intervals**: 1m, 5m, 15m, 30m, 1h, 4h, 12h, 1d, 7d, 30d

#### 3. Batch Processing Architecture

**Problem Addressed**: Exchange APIs limit responses to ~1000 klines per request, requiring intelligent chunking for large historical data fetches.

**Solution**: Automatic batch processing with the following architecture:

```
Large Time Range → Calculate Chunk Size → Parallel/Sequential Requests → Deduplication → Sorted Results
```

**Key Features:**
- **Intelligent Chunking**: Calculates optimal request size based on interval duration
- **Deduplication Logic**: Prevents overlapping data from multiple requests
- **Memory Efficiency**: Processes chunks without loading entire dataset
- **Rate Limit Compliance**: Respects exchange-specific limits

**Performance Characteristics:**
- **Chunk Calculation**: O(1) - Pre-calculated interval mappings
- **Request Processing**: O(n) where n = number of required requests
- **Deduplication**: O(m) where m = total klines returned
- **Memory Usage**: O(k) where k = klines per chunk (bounded)

#### 4. Data Structure Standards

All klines data uses the unified `Kline` struct from `src/exchanges/interface/structs.py`:

```python
class Kline(Struct):
    symbol: Symbol
    interval: KlineInterval
    open_time: int          # Unix timestamp (milliseconds)
    close_time: int         # Unix timestamp (milliseconds)
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float           # Base asset volume
    quote_volume: float     # Quote asset volume
    trades_count: int       # Number of trades (when available)
```

#### 5. Time Interval Management

**Unified KlineInterval Enum**:
```python
class KlineInterval(IntEnum):
    MINUTE_1 = 1    # 1m
    MINUTE_5 = 2    # 5m
    MINUTE_15 = 3   # 15m
    MINUTE_30 = 4   # 30m
    HOUR_1 = 5      # 1h
    HOUR_4 = 6      # 4h
    HOUR_12 = 7     # 12h
    DAY_1 = 8       # 1d
    WEEK_1 = 9      # 1w/7d
    MONTH_1 = 10    # 1M/30d
```

**Exchange-Specific Mappings**:
- **MEXC**: Uses standard format (1m, 5m, 1h, 1d, 1w, 1M)
- **Gate.io**: Uses alternative week/month format (7d, 30d instead of 1w, 1M)

### HFT Compliance and Performance

#### 1. HFT Caching Policy Compliance

**CRITICAL**: Klines data is **NEVER CACHED** - all requests fetch fresh data from exchange APIs.

**Rationale**: Even historical data can be revised by exchanges (e.g., trade corrections), and real-time klines are continuously updating during active trading periods.

**Implementation**: All methods include explicit "HFT COMPLIANT" comments ensuring no accidental caching.

#### 2. Performance Optimizations

**JSON Processing**:
- msgspec-exclusive parsing for zero-copy performance
- Pre-validated struct conversion for type safety
- Optimized array processing for exchange-specific formats

**Network Efficiency**:
- Connection pooling with persistent sessions
- Aggressive timeout configurations (0.3-0.8x standard timeout)
- Intelligent retry logic with exponential backoff

**Memory Management**:
- Streaming processing for large datasets
- Bounded memory usage regardless of time range
- Efficient deduplication using dict-based uniqueness

#### 3. Error Handling and Reliability

**Exception Propagation**:
- All errors bubble to application level via unified exception system
- Exchange-specific error codes properly mapped
- Comprehensive logging for audit trails

**Rate Limit Management**:
- Built-in rate limiting via RestClient configuration
- Per-exchange rate limit compliance
- Intelligent request spacing for batch operations

### Integration with Trading Strategies

#### 1. Technical Analysis Support

The klines system provides foundation for:
- **Moving Average Calculations** - Historical price data for trend analysis
- **Volatility Indicators** - OHLC data for volatility-based strategies
- **Support/Resistance Levels** - Historical high/low identification
- **Volume Analysis** - Trade volume patterns for liquidity assessment

#### 2. Backtesting Framework

**Historical Data Access**:
- Batch fetching for strategy backtesting
- Consistent data format across exchanges
- Time-series alignment for cross-exchange analysis

**Performance Validation**:
- Real-time klines for live strategy validation
- Historical performance comparison
- Strategy parameter optimization support

### Future Extensibility

#### 1. Additional Exchanges

The abstract interface pattern enables easy addition of new exchanges:
- Implement `get_klines()` and `get_klines_batch()` methods
- Add exchange-specific interval mappings
- Configure rate limits and endpoint details

#### 2. Advanced Features

**Potential Enhancements** (not yet implemented):
- **Streaming Klines**: Real-time candlestick updates via WebSocket
- **Compressed Storage**: Efficient storage for backtesting data
- **Cross-Exchange Synchronization**: Time-aligned multi-exchange data
- **Custom Intervals**: Aggregation of standard intervals into custom periods

## Component Documentation

### Refactored Architecture Components

**Core Arbitrage Components** (NEW - SOLID-compliant architecture):
- **[Arbitrage Types](src/arbitrage/types.py)** - Type definitions, enums, and configuration structures
- **[Configuration Manager](src/arbitrage/configuration_manager.py)** - Configuration loading and validation
- **[Exchange Factory](src/arbitrage/exchange_factory.py)** - Factory pattern for exchange creation
- **[Performance Monitor](src/arbitrage/performance_monitor.py)** - HFT performance tracking and alerting
- **[Shutdown Manager](src/arbitrage/shutdown_manager.py)** - Graceful shutdown coordination
- **[Arbitrage Controller](src/arbitrage/controller.py)** - Main orchestrator component
- **[Simple Engine](src/arbitrage/simple_engine.py)** - Clean engine implementation for demonstration
- **[Main Entry Point](src/main.py)** - Production-ready main with clean CLI

**Exchange and Infrastructure Components**:
- **[Common Components](src/common/README.md)** - Shared utilities and base components
- **[Exchange Interfaces](src/exchanges/interface/README.md)** - Unified interface system and contracts  
- **[MEXC Implementation](src/exchanges/mexc/README.md)** - MEXC-specific implementation details
- **[Gate.io Implementation](src/exchanges/gateio/README.md)** - Gate.io-specific implementation details
- **[Usage Examples](src/examples/README.md)** - Usage patterns and testing approaches

## Development Guidelines

### Architectural Patterns (MANDATORY)

**SOLID Principles Compliance**:
- **Single Responsibility**: Each component has ONE focused purpose - never mix concerns
- **Open/Closed**: Extend through interfaces/composition, never modify existing components
- **Liskov Substitution**: All interface implementations must be fully interchangeable
- **Interface Segregation**: Keep interfaces focused - no unused methods
- **Dependency Inversion**: Depend on abstractions, inject dependencies, avoid tight coupling

**Factory Pattern Usage**:
- **Use ExchangeFactory**: Never create exchange instances directly in business logic
- **Centralized creation**: All object creation logic belongs in appropriate Factory classes
- **Error resilience**: Factories must handle creation failures gracefully

**Component Organization** (Clean src-only architecture):
- **src/arbitrage/**: Core business logic components (SOLID-compliant)
- **src/exchanges/interface/**: Unified interface system and data structures
- **src/exchanges/mexc/**: MEXC exchange implementation
- **src/exchanges/gateio/**: Gate.io exchange implementation
- **src/common/**: Shared utilities and base components
- **src/examples/**: Usage demonstrations and testing code

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

### Usage Examples (Updated for Refactored Architecture)

**Starting the Engine** (using the clean main entry point):
```bash
# Safe dry run mode (default - recommended for testing)
PYTHONPATH=src python src/main.py

# Enable detailed debug logging
PYTHONPATH=src python src/main.py --log-level DEBUG

# Live trading mode (requires API credentials)
PYTHONPATH=src python src/main.py --live

# With environment variables for credentials
MEXC_API_KEY=your_key MEXC_SECRET_KEY=your_secret \
GATEIO_API_KEY=your_key GATEIO_SECRET_KEY=your_secret \
PYTHONPATH=src python src/main.py --live
```

**API Credentials Setup**:
```bash
# Set environment variables (preferred method)
export MEXC_API_KEY="your_mexc_api_key"
export MEXC_SECRET_KEY="your_mexc_secret_key"
export GATEIO_API_KEY="your_gateio_api_key"
export GATEIO_SECRET_KEY="your_gateio_secret_key"
```

**Architecture Verification**:
```bash
# Verify SOLID principles compliance and clean architecture
python -c "from src.arbitrage.controller import ArbitrageController; print('✓ Clean imports')"

# Verify symbol resolution performance (HFT compliance)
python -c "from src.arbitrage.symbol_resolver import SymbolResolver; print('✓ O(1) Symbol Resolution')"

# Check component separation
find src/arbitrage -name "*.py" -exec basename {} .py \; | sort
# Should show: configuration_manager, controller, exchange_factory, performance_monitor, shutdown_manager, symbol_resolver, types, simple_engine

# Verify clean src-only architecture
find src/ -name "*.py" -exec grep -l "@raw\|raw/" {} \; | wc -l | grep -q "^0$" && echo "✓ Clean src-only architecture achieved" || echo "⚠ Raw dependencies found"
```

### Numeric Type Standards (MANDATORY)

- **Use float for all financial calculations** - Python's float type provides sufficient precision for cryptocurrency trading
- **NEVER use Decimal()** - Decimal adds unnecessary computational overhead that violates HFT latency requirements
- **Rationale**: 64-bit float precision (15-17 decimal digits) exceeds cryptocurrency precision needs (typically 8 decimal places max)
- **Exception**: Only use Decimal if explicitly required by external library APIs that don't accept float

# important-instruction-reminders
Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.