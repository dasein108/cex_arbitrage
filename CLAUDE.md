# CEX Arbitrage Engine - System Architecture

High-level architectural documentation for the ultra-high-performance CEX arbitrage engine designed for sub-millisecond cryptocurrency trading.

## System Overview

This is a **high-frequency trading (HFT) arbitrage engine** built for professional cryptocurrency trading across multiple exchanges with the following characteristics:

- **Sub-50ms latency** for complete arbitrage cycle execution
- **Event-driven architecture** with async/await throughout
- **Zero-copy message processing** using msgspec for maximum performance
- **Abstract Factory pattern** enabling seamless exchange integration
- **Production-grade reliability** with automatic reconnection and error recovery

## Core Architectural Principles

### 1. Event-Driven + Abstract Factory Architecture

The system follows a **layered event-driven architecture** with **Abstract Factory pattern**:

**Network Layer** → **Data Layer** → **Exchange Abstraction** → **Application Layer**

### 2. HFT Performance Optimizations

- **Object Pooling**: Reduces allocation overhead by 75% in hot paths
- **Connection Pooling**: Persistent HTTP sessions with intelligent reuse
- **Zero-Copy Parsing**: msgspec-exclusive JSON processing
- **Pre-compiled Constants**: Optimized lookup tables and magic bytes
- **Intelligent Caching**: 90% performance improvement through strategic caching

### 3. Type Safety and Data Integrity

- **msgspec.Struct**: Frozen, hashable data structures throughout
- **IntEnum**: Performance-optimized enumerations
- **NewType aliases**: Type safety without runtime overhead
- **Comprehensive validation**: Data integrity at API boundaries

### 4. Interface-Driven Design

- **Abstract Interfaces**: Clean separation between public/private operations
- **Unified Exception System**: Structured error hierarchy with intelligent retry logic
- **Pluggable Architecture**: Exchange implementations as interchangeable components
- **Contract-First Development**: Interface definitions drive implementation

## Key Architectural Decisions

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
- **Performance Targets**: <50ms latency, >95% uptime, sub-millisecond parsing
- **Type Safety**: Comprehensive type annotations required throughout

## Component Documentation

For detailed implementation guidance and usage examples, see component-specific documentation:

- **[Common Components](src/common/README.md)** - Shared utilities and base components
- **[Exchange Interfaces](src/exchanges/interface/README.md)** - Core interface patterns and contracts  
- **[MEXC Implementation](src/exchanges/mexc/README.md)** - MEXC-specific implementation details
- **[Usage Examples](src/examples/README.md)** - Usage patterns and testing approaches

## Development Guidelines

### KISS/YAGNI Principles (MANDATORY)

- **Keep It Simple, Stupid** - Avoid unnecessary complexity
- **You Aren't Gonna Need It** - Don't implement features not explicitly requested
- **Ask for confirmation** before adding functionality beyond task scope

### Performance Requirements

- **Target Latency**: <50ms end-to-end HTTP requests
- **JSON Parsing**: <1ms per message using msgspec
- **Memory Management**: O(1) per request, >95% connection reuse
- **Uptime**: >99.9% availability with automatic recovery

# important-instruction-reminders
Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.