# CEX Arbitrage Engine - Architecture Overview

High-level architectural overview for the ultra-high-performance CEX arbitrage engine designed for sub-millisecond cryptocurrency trading.

## 🚨 Critical Development Guidelines

**MANDATORY READING**: **[PROJECT_GUIDES.md](PROJECT_GUIDES.md)** contains critical development rules, patterns, and implementation requirements that must be followed to maintain system integrity.

## System Overview

This is a **high-frequency trading (HFT) arbitrage engine** built for professional cryptocurrency trading across multiple exchanges, featuring a **separated domain architecture** where public and private interfaces are completely isolated with no overlap.

### **Separated Domain Architecture (Current)**

**Complete Domain Separation Achieved**:
- **CompositePublicExchange** - ONLY market data operations (orderbooks, trades, tickers, symbols)
- **CompositePrivateExchange** - ONLY trading operations (orders, balances, positions, leverage)
- **FullExchangeFactory** - Factory for creating separate public and private exchange instances
- **No Inheritance** - Private exchanges do NOT inherit from public exchanges
- **Minimal Shared Configuration** - Only static config like symbol_info, never real-time data
- **HFT Safety Compliance** - No caching of real-time trading data across all interfaces

### **Key Performance Achievements**

- **Sub-millisecond logging**: 1.16μs average latency, 859K+ messages/second
- **Symbol resolution**: 0.947μs per lookup with 1M+ ops/second throughput
- **Exchange formatting**: 0.306μs per conversion with 3.2M+ ops/second
- **Complete arbitrage cycle**: <50ms end-to-end execution
- **Memory efficiency**: >95% connection reuse, zero-copy message processing
- **Production reliability**: >99.9% uptime with automatic recovery

## Core Architectural Principles

### **Pragmatic Architecture Guidelines**

The system follows **balanced architectural principles** detailed in specialized documentation:

1. **[Pragmatic SOLID Principles](docs/patterns/pragmatic-solid-principles.md)** - Balanced application prioritizing value over dogma
2. **[LEAN Development Methodology](docs/development/lean-development-methodology.md)** - Implement necessity, avoid speculation
3. **[Exception Handling Patterns](docs/patterns/exception-handling-patterns.md)** - Simplified, composed error handling
4. **[Struct-First Data Policy](docs/data/struct-first-policy.md)** - msgspec.Struct over dict for all modeling
5. **[HFT Performance Requirements](docs/performance/hft-requirements-compliance.md)** - Sub-millisecond targets throughout

### **Separated Domain Architecture**

The system uses **complete domain separation** between public and private exchange operations:

**FullExchangeFactory** → **CompositePublicExchange** (parallel to) **CompositePrivateExchange** → **Exchange Implementations** → **Domain-Specific Data Structures**

**Core Components:**
- **[CompositePublicExchange](docs/architecture/composite-exchange-architecture.md)** - Pure market data interface
- **[CompositePrivateExchange](docs/architecture/composite-exchange-architecture.md)** - Pure trading operations interface
- **[FullExchangeFactory](docs/architecture/composite-exchange-architecture.md)** - Factory for creating separate domain instances
- **[Infrastructure Foundation](docs/infrastructure/)** - Shared networking, logging, and configuration systems
- **[Domain Data Structures](docs/data/struct-first-policy.md)** - msgspec.Struct types specific to each domain

### **Separated Domain Interface Hierarchy**

```
CompositePublicExchange (market data domain - NO authentication)
├── Orderbook Operations (real-time orderbook streaming)
├── Market Data (tickers, trades, klines)
├── Symbol Information (trading rules, precision)
└── Connection Management (public WebSocket lifecycle)

CompositePrivateExchange (trading domain - requires authentication)
├── Trading Operations (orders, positions, balances)
├── Account Management (portfolio tracking)
├── Trade Execution (spot and futures support)
└── Connection Management (private WebSocket lifecycle)
```

**Separated Domain Benefits**:
- **Complete Isolation**: Public and private domains have no overlap
- **No Inheritance**: Private exchanges are independent of public exchanges
- **Authentication Boundary**: Clear separation of authenticated vs non-authenticated operations
- **Independent Scaling**: Each domain can scale and optimize independently
- **Security**: Trading operations completely isolated from market data
- **HFT Optimized**: Sub-50ms execution targets in both domains

### **Separated Domain Factory Pattern**

**Independent Exchange Creation with Domain Separation**:

```python
from exchanges.full_exchange_factory import FullExchangeFactory
from exchanges.structs.common import Symbol

# Create factory
factory = FullExchangeFactory()

# Create public exchange (market data domain only)
public_exchange = await factory.create_public_exchange(
    exchange_name='mexc_spot',
    symbols=[Symbol('BTC', 'USDT')]
)
# public_exchange provides: orderbooks, trades, tickers, symbol_info
# public_exchange does NOT provide: balances, orders, positions

# Create private exchange (trading domain only)  
private_exchange = await factory.create_private_exchange(
    exchange_name='mexc_spot'
)
# private_exchange provides: orders, balances, positions, leverage
# private_exchange does NOT provide: orderbooks, trades, market data

# Create both domains separately (NO inheritance relationship)
public, private = await factory.create_exchange_pair(
    exchange_name='mexc_spot',
    symbols=[Symbol('BTC', 'USDT')]
)
# public and private are completely independent instances
# Only symbol_info configuration is shared, never real-time data

# Create multiple separated domain pairs
exchanges = await factory.create_multiple_exchange_pairs(
    exchange_names=['mexc_spot', 'gateio_spot'],
    symbols=[Symbol('BTC', 'USDT'), Symbol('ETH', 'USDT')]
)
```

**Separated Domain Factory Benefits**:
- **Pure Domain Creation**: Each interface handles only its domain
- **No Cross-Domain Dependencies**: Public and private are completely independent
- **Configuration Isolation**: Only static config (symbol_info) shared
- **Authentication Boundary**: Credentials only needed for private domain
- **Independent Optimization**: Each domain optimized for its specific operations

### **HFT Logging System**

Comprehensive high-performance logging architecture designed for sub-millisecond trading operations. Full details in **[HFT Logging System](docs/infrastructure/hft-logging-system.md)**.

**Performance Specifications Achieved**:
- **Latency**: 1.16μs average (target: <1ms) ✅
- **Throughput**: 859,598+ messages/second sustained ✅
- **Memory**: Ring buffer with configurable size
- **Async Dispatch**: Zero-blocking operations
- **Error Resilience**: Automatic backend failover

**Key Features**:
- **Factory-based injection** throughout the codebase
- **Hierarchical tagging system** for precise metrics routing
- **Environment-specific backends** (dev/prod/test configurations)
- **Performance tracking** with LoggingTimer context manager
- **Multi-backend system** supporting console, file, Prometheus, audit trails

## Architecture Documentation Structure

### **Comprehensive Documentation Suite**

The architecture is fully documented across specialized files:

#### **Core Architecture**
- **[Composite Exchange Architecture](docs/architecture/composite-exchange-architecture.md)** - Complete composite interface design
- **[System Architecture](docs/architecture/system-architecture.md)** - High-level system design and component relationships  
- **[Component Architecture](docs/architecture/component-architecture.md)** - Individual component designs

#### **Development Patterns**
- **[Pragmatic SOLID Principles](docs/patterns/pragmatic-solid-principles.md)** - Balanced SOLID implementation
- **[Factory Pattern Implementation](docs/patterns/factory-pattern.md)** - Unified factory design
- **[Exception Handling Patterns](docs/patterns/exception-handling-patterns.md)** - Simplified error handling

#### **Performance & HFT**  
- **[HFT Requirements Compliance](docs/performance/hft-requirements-compliance.md)** - Complete performance specifications
- **[Performance Benchmarks](docs/performance/benchmarks.md)** - Achieved performance metrics
- **[Caching Policy](docs/performance/caching-policy.md)** - Critical trading safety rules

#### **Infrastructure**
- **[HFT Logging System](docs/infrastructure/hft-logging-system.md)** - High-performance logging architecture
- **[Configuration System](docs/configuration/configuration-system.md)** - Unified configuration management
- **[Networking Infrastructure](docs/infrastructure/networking.md)** - REST and WebSocket foundations

#### **Data & Development**
- **[Struct-First Data Policy](docs/data/struct-first-policy.md)** - msgspec.Struct standards
- **[LEAN Development Methodology](docs/development/lean-development-methodology.md)** - Development approach
- **[Integration Workflows](docs/workflows/)** - Step-by-step integration processes

## Quick Reference

### **Getting Started**
1. Read **[PROJECT_GUIDES.md](PROJECT_GUIDES.md)** - Mandatory development rules
2. Review **[Composite Exchange Architecture](docs/architecture/composite-exchange-architecture.md)** - Core system design
3. Check **[HFT Requirements Compliance](docs/performance/hft-requirements-compliance.md)** - Performance targets
4. Follow **[LEAN Development Methodology](docs/development/lean-development-methodology.md)** - Development approach

### **Common Tasks**
- **Adding New Exchange**: [Exchange Integration Workflow](docs/workflows/exchange-integration.md)
- **Performance Optimization**: [HFT Compliance Guide](docs/performance/hft-requirements-compliance.md)
- **Configuration Changes**: [Configuration System](docs/configuration/configuration-system.md)
- **Debugging Issues**: [Exception Handling Patterns](docs/patterns/exception-handling-patterns.md)

### **Key Implementation Rules**
- **Separated Domain Architecture**: Public (market data) and private (trading) are completely isolated
- **No Inheritance**: Private exchanges do NOT inherit from public exchanges
- **Authentication Boundary**: Public operations require no auth, private operations require credentials
- **Minimal Configuration Sharing**: Only static config like symbol_info, never real-time data
- **HFT Caching Policy**: NEVER cache real-time trading data (balances, orders, positions, orderbooks)
- **Struct-First Policy**: msgspec.Struct over dict for all data modeling
- **LEAN Development**: Implement necessity, avoid speculation
- **Pragmatic SOLID**: Apply principles where they add value

## 🚨 Critical Trading Safety Rules

### **HFT Caching Policy**

**ABSOLUTE RULE**: Never cache real-time trading data in HFT systems.

**PROHIBITED (Real-time Data)**:
- Account balances, order status, position data
- Orderbook snapshots, recent trades, market data

**PERMITTED (Static Configuration)**:
- Symbol mappings, exchange configuration, trading rules

**RATIONALE**: Caching real-time data causes stale price execution, failed arbitrage, phantom liquidity, and compliance violations. This rule supersedes ALL performance considerations.

See **[Caching Policy](docs/performance/caching-policy.md)** for complete safety guidelines.

## Component Reference

### **Separated Domain Exchange Implementations**

**Core Domain Interfaces**:
- **[CompositePublicExchange](src/exchanges/interfaces/composite/spot/base_public_spot_composite.py)** - Pure market data interface
- **[CompositePrivateExchange](src/exchanges/interfaces/composite/spot/base_private_spot_composite.py)** - Pure trading operations interface
- **[FullExchangeFactory](src/exchanges/full_exchange_factory.py)** - Factory for creating separated domain instances

**Public Domain Implementations (Market Data Only)**:
- **[MexcPublicExchange](src/exchanges/integrations/mexc/public_exchange.py)** - MEXC market data (orderbooks, trades, tickers)
- **[GateioPublicExchange](src/exchanges/integrations/gateio/public_exchange.py)** - Gate.io spot market data
- **[GateioFuturesPublicExchange](src/exchanges/integrations/gateio/public_futures_exchange.py)** - Gate.io futures market data

**Private Domain Implementations (Trading Operations Only)**:
- Private exchange implementations for orders, balances, positions, and leverage management
- Completely separate from public implementations with no inheritance

**Infrastructure Foundation**:
- **[HFT Logging System](docs/infrastructure/hft-logging-system.md)** - Sub-millisecond logging
- **[Networking Infrastructure](docs/infrastructure/networking.md)** - REST/WebSocket foundations
- **[Configuration System](docs/configuration/configuration-system.md)** - Unified config management

### **Documentation Navigation**

**By User Type**:
- **Developers**: [System Architecture](docs/architecture/system-architecture.md) → [Integration Workflows](docs/workflows/exchange-integration.md)
- **Architects**: [Separated Domain Architecture](docs/architecture/composite-exchange-architecture.md) → [SOLID Principles](docs/patterns/pragmatic-solid-principles.md)
- **DevOps**: [Configuration System](docs/configuration/configuration-system.md) → [Performance Monitoring](docs/performance/benchmarks.md)

**By Topic**:
- **Performance**: [HFT Compliance](docs/performance/hft-requirements-compliance.md) → [Benchmarks](docs/performance/benchmarks.md)
- **Integration**: [Exchange Integration](docs/workflows/exchange-integration.md) → [Factory Patterns](docs/patterns/factory-pattern.md)
- **Development**: [LEAN Methodology](docs/development/lean-development-methodology.md) → [Exception Handling](docs/patterns/exception-handling-patterns.md)

---

*This architectural overview reflects the current separated domain architecture where public and private interfaces are completely isolated with no inheritance or overlap. For detailed implementation guidance, see the comprehensive documentation suite in the [docs/](docs/) directory.*

**Last Updated**: September 2025 - Post-Separated Domain Architecture Implementation