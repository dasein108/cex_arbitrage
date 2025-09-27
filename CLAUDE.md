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

1. **[Pragmatic SOLID Principles](specs/patterns/pragmatic-solid-principles.md)** - Balanced application prioritizing value over dogma
2. **[LEAN Development Methodology](specs/patterns/lean-development-methodology.md)** - Implement necessity, avoid speculation
3. **[Exception Handling Patterns](specs/patterns/exception-handling-patterns.md)** - Simplified, composed error handling
4. **[Struct-First Data Policy](specs/data/struct-first-policy.md)** - msgspec.Struct over dict for all modeling
5. **[HFT Performance Requirements](specs/performance/hft-requirements-compliance.md)** - Sub-millisecond targets throughout

### **Separated Domain Architecture**

The system uses **complete domain separation** between public and private exchange operations:

**FullExchangeFactory** → **CompositePublicExchange** (parallel to) **CompositePrivateExchange** → **Exchange Implementations** → **Domain-Specific Data Structures**

**Core Components:**
- **[CompositePublicExchange](specs/architecture/unified-exchange-architecture.md)** - Pure market data interface
- **[CompositePrivateExchange](specs/architecture/unified-exchange-architecture.md)** - Pure trading operations interface
- **[Unified Exchange Factory](docs/factory/unified-exchange-factory.md)** - Single entry point for all exchange components
- **[Networking Infrastructure](specs/networking/)** - High-performance REST and WebSocket systems
- **[Domain Data Structures](specs/data/struct-first-policy.md)** - msgspec.Struct types specific to each domain

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

### **Unified Exchange Factory Pattern**

**Single Entry Point for All Exchange Components**:

```python
from exchanges.factory import create_exchange_component
from exchanges.structs.common import Symbol
from exchanges.structs.enums import ExchangeEnum

# Unified factory with explicit component selection
# REST client for direct API integration
rest_client = create_exchange_component(
    exchange=ExchangeEnum.MEXC,
    config=mexc_config,
    component_type='rest',
    is_private=False
)

# WebSocket client for real-time streaming  
ws_client = create_exchange_component(
    exchange=ExchangeEnum.MEXC,
    config=mexc_config,
    component_type='websocket',
    is_private=False,
    handlers=public_handlers
)

# Full composite exchange for trading operations
trading_exchange = create_exchange_component(
    exchange=ExchangeEnum.MEXC,
    config=mexc_config,
    component_type='composite',
    is_private=True  # Requires credentials
)

# Separated domain pair for HFT systems
public_exchange, private_exchange = create_exchange_component(
    exchange=ExchangeEnum.MEXC,
    config=mexc_config,
    component_type='pair'  # Returns both domains separately
)
# public_exchange: market data only (orderbooks, trades, tickers)
# private_exchange: trading operations only (orders, balances, positions)
# Complete isolation with no inheritance relationship
```

**Unified Factory Benefits**:
- **Single Entry Point**: One factory for all exchange components eliminates confusion
- **Explicit Component Selection**: Clear `component_type` parameter ('rest', 'websocket', 'composite', 'pair')
- **Type Safety**: Comprehensive validation prevents runtime errors
- **Performance Optimized**: <1ms component creation with intelligent caching
- **Separated Domain Support**: Complete isolation between public/private domains
- **Backward Compatible**: Existing code continues to work via convenience functions

### **HFT Logging System**

Comprehensive high-performance logging architecture designed for sub-millisecond trading operations. Full details in **[Configuration Integration](specs/configuration/hft-logging-integration-spec.md)**.

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

## Exchange Integration Architecture

### **Production Exchange Integrations**

The system provides comprehensive integrations for major cryptocurrency exchanges with separated domain architecture:

#### **MEXC Exchange Integration**
- **Type**: Spot trading with Protocol Buffer optimization
- **Performance**: <50ms latency, extensive protobuf message support
- **Features**: Binary message parsing, object pooling (75% allocation reduction), high-frequency optimizations
- **Documentation**: [MEXC Integration Specification](specs/integrations/mexc/mexc-integration-specification.md)

**Key MEXC Capabilities**:
- **Protocol Buffer Support**: 15+ protobuf message types for ultra-fast parsing
- **Dual Format Handling**: Automatic JSON/protobuf detection and processing
- **HFT Optimizations**: Symbol conversion caching (90% performance improvement), connection pooling
- **Custom Connection Strategy**: Minimal headers to avoid blocking, 30s ping intervals
- **Error Recovery**: Specialized 1005 error handling, exponential backoff

#### **Gate.io Exchange Integration**
- **Type**: Spot + Futures trading with comprehensive market support
- **Performance**: <50ms latency, >99% connection stability
- **Features**: Dual market support, leverage management, funding rate tracking
- **Documentation**: [Gate.io Integration Specification](specs/integrations/gateio/gateio-integration-specification.md)

**Key Gate.io Capabilities**:
- **Dual Market Support**: Complete spot and futures implementations
- **Futures Features**: Position management, leverage control (up to 100x), funding rate tracking
- **Advanced Data**: Mark prices, index prices, open interest, liquidation feeds
- **Stable Connectivity**: Custom ping/pong, compression support, fewer 1005 errors
- **Risk Management**: Position limits, margin tracking, reduce-only orders

#### **Common Integration Patterns**
- **Documentation**: [Integration Patterns Specification](specs/integrations/common/integration-patterns-specification.md)
- **Strategy Patterns**: Connection, retry, message parsing, authentication strategies
- **Performance Patterns**: Object pooling, caching, connection management
- **Testing Patterns**: Integration tests, performance benchmarks, health monitoring

**Integration Architecture Benefits**:
- **Consistent API**: Unified interface across all exchanges
- **Exchange-Specific Optimizations**: Tailored for each exchange's characteristics
- **Performance Compliance**: HFT-optimized with sub-millisecond targets
- **Extensibility**: Standardized patterns for adding new exchanges

## Architecture Documentation Structure

### **Comprehensive Documentation Suite**

The architecture is fully documented across specialized files:

#### **Core Architecture**
- **[System Architecture](specs/architecture/system-architecture.md)** - High-level system design and component relationships  
- **[Unified Exchange Architecture](specs/architecture/unified-exchange-architecture.md)** - Complete separated domain interface design

#### **Configuration Management**
- **[Configuration System Overview](specs/configuration/README.md)** - Complete configuration management system
- **[Core Configuration Manager](specs/configuration/core-configuration-manager-spec.md)** - Primary configuration orchestrator
- **[Exchange Configuration](specs/configuration/exchange-configuration-spec.md)** - Exchange-specific settings
- **[Database Configuration](specs/configuration/database-configuration-spec.md)** - Database and data collection
- **[Network Configuration](specs/configuration/network-configuration-spec.md)** - Network and transport layer
- **[HFT Logging Integration](specs/configuration/hft-logging-integration-spec.md)** - High-performance logging

#### **Development Patterns**
- **[Pragmatic SOLID Principles](specs/patterns/pragmatic-solid-principles.md)** - Balanced SOLID implementation
- **[Factory Pattern Implementation](specs/patterns/factory-pattern.md)** - Unified factory design
- **[Exception Handling Patterns](specs/patterns/exception-handling-patterns.md)** - Simplified error handling
- **[LEAN Development Methodology](specs/patterns/lean-development-methodology.md)** - Development approach

#### **Performance & HFT**  
- **[HFT Requirements Compliance](specs/performance/hft-requirements-compliance.md)** - Complete performance specifications
- **[Caching Policy](specs/performance/caching-policy.md)** - Critical trading safety rules
- **[HFT Compliance](specs/performance/hft-compliance.md)** - Performance validation

#### **Data & Workflows**
- **[Struct-First Data Policy](specs/data/struct-first-policy.md)** - msgspec.Struct standards
- **[Integration Workflows](specs/workflows/)** - Step-by-step integration processes

## Quick Reference

### **Getting Started**
1. Read **[PROJECT_GUIDES.md](PROJECT_GUIDES.md)** - Mandatory development rules
2. Review **[Unified Exchange Architecture](specs/architecture/unified-exchange-architecture.md)** - Core system design
3. Check **[HFT Requirements Compliance](specs/performance/hft-requirements-compliance.md)** - Performance targets
4. Follow **[LEAN Development Methodology](specs/patterns/lean-development-methodology.md)** - Development approach

### **Common Tasks**
- **Adding New Exchange**: [Exchange Integration Workflow](specs/workflows/exchange-integration.md)
- **Performance Optimization**: [HFT Compliance Guide](specs/performance/hft-requirements-compliance.md)
- **Configuration Changes**: [Configuration System](specs/configuration/README.md)
- **Debugging Issues**: [Exception Handling Patterns](specs/patterns/exception-handling-patterns.md)

### **Exchange Integration References**
- **MEXC Integration**: [Complete MEXC Specification](specs/integrations/mexc/mexc-integration-specification.md)
- **Gate.io Integration**: [Complete Gate.io Specification](specs/integrations/gateio/gateio-integration-specification.md)
- **Integration Patterns**: [Common Patterns & Strategies](specs/integrations/common/integration-patterns-specification.md)
- **Adding New Exchanges**: Follow common patterns specification for consistency

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

See **[Caching Policy](specs/performance/caching-policy.md)** for complete safety guidelines.

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
- **[HFT Logging Integration](specs/configuration/hft-logging-integration-spec.md)** - Sub-millisecond logging
- **[Network Configuration](specs/configuration/network-configuration-spec.md)** - REST/WebSocket foundations
- **[Configuration System](specs/configuration/README.md)** - Unified config management

### **Documentation Navigation**

**By User Type**:
- **Developers**: [System Architecture](specs/architecture/system-architecture.md) → [Integration Workflows](specs/workflows/exchange-integration.md)
- **Architects**: [Separated Domain Architecture](specs/architecture/unified-exchange-architecture.md) → [SOLID Principles](specs/patterns/pragmatic-solid-principles.md)
- **DevOps**: [Configuration System](specs/configuration/README.md) → [Performance Monitoring](specs/performance/hft-requirements-compliance.md)

**By Topic**:
- **Performance**: [HFT Compliance](specs/performance/hft-requirements-compliance.md) → [Caching Policy](specs/performance/caching-policy.md)
- **Integration**: [Exchange Integration](specs/workflows/exchange-integration.md) → [Factory Patterns](specs/patterns/factory-pattern.md)
- **Development**: [LEAN Methodology](specs/patterns/lean-development-methodology.md) → [Exception Handling](specs/patterns/exception-handling-patterns.md)

---

*This architectural overview reflects the current separated domain architecture where public and private interfaces are completely isolated with no inheritance or overlap. For detailed implementation guidance, see the comprehensive specification suite in the [specs/](specs/) directory.*

**Last Updated**: September 2025 - Post-Separated Domain Architecture Implementation