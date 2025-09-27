# CEX Arbitrage Engine Specifications

Business domain-focused implementation guide for the ultra-high-performance CEX arbitrage engine. This documentation emphasizes trading logic, component relationships, and practical implementation patterns over directory structures.

## Overview

This specifications directory is organized around **business domains** rather than technical file structures. Each domain focuses on core business logic, performance requirements, and integration patterns essential for HFT cryptocurrency arbitrage.

## Business Domain Organization

### **🎯 Market Data Domain**
Real-time market data processing, price discovery, and orderbook management for arbitrage opportunity detection.

**Core Business Logic**:
- **Orderbook Processing** - Real-time bid/ask streaming with sub-millisecond updates
- **Price Feed Management** - Multi-exchange price aggregation and normalization
- **Market Analysis** - Arbitrage opportunity detection and profit calculation
- **Symbol Resolution** - Ultra-fast symbol mapping (0.947μs, 1M+ ops/sec)

**Performance Characteristics**:
- **Latency**: Symbol resolution <1μs, price updates <5ms
- **Throughput**: 1M+ symbol lookups/sec, 100K+ price updates/sec
- **Data Freshness**: Real-time WebSocket streams, reject data >5 seconds
- **Memory Efficiency**: Zero-copy message processing, connection pooling

### **💰 Trading Domain** 
Order execution, position management, and balance tracking for profitable arbitrage trades.

**Core Business Logic**:
- **Order Execution** - Concurrent buy/sell orders with <50ms total latency
- **Position Management** - Real-time portfolio tracking and risk assessment
- **Balance Tracking** - Fresh API calls for all trading decisions (HFT safe)
- **Trade Settlement** - Post-trade analysis and profit realization

**Performance Characteristics**:
- **Execution Speed**: Complete arbitrage cycle <30ms (target: <50ms)
- **Safety Compliance**: NEVER cache balances/orders/positions
- **Concurrency**: Parallel order placement across exchanges
- **Risk Management**: Real-time exposure monitoring and circuit breakers

### **⚙️ Configuration Domain**
System configuration, exchange settings, and performance tuning for operational excellence.

**Core Business Logic**:
- **Exchange Configuration** - Multi-exchange credential and endpoint management
- **Performance Tuning** - HFT-optimized settings for sub-millisecond operations
- **Environment Management** - Dev/prod/test configuration isolation
- **Runtime Configuration** - Hot-reload for non-critical settings

**Performance Characteristics**:
- **Loading Speed**: Configuration resolution <10ms
- **Validation**: Comprehensive schema validation with error reporting
- **Security**: Environment variable injection, credential protection
- **Flexibility**: Dynamic exchange addition without code changes

### **🏗️ Infrastructure Domain**
Foundational networking, logging, and factory systems supporting all business domains.

**Core Business Logic**:
- **Factory Systems** - Unified exchange creation with dependency injection
- **HFT Logging** - Sub-microsecond logging (1.16μs, 859K+ msg/sec)
- **Networking Foundation** - REST/WebSocket clients with connection pooling
- **Error Handling** - Composed exception patterns with circuit breakers

**Performance Characteristics**:
- **Logging Latency**: 1.16μs average (target: <1ms)
- **Connection Reuse**: >95% HTTP connection pooling efficiency
- **Factory Speed**: Exchange creation <5 seconds (concurrent)
- **Error Recovery**: Automatic reconnection with exponential backoff

## Domain Interaction Patterns

### **Domain Relationship Diagram**

```
┌─────────────────────────────────────────────────────────────────┐
│                    ARBITRAGE ORCHESTRATION                     │
│              (Business Logic Coordination)                      │
└─────────────────────┬───────────────────────────────────────────┘
                      │
              ┌───────┼───────┐
              ▼       ▼       ▼
    ┌─────────────┬─────────────┬─────────────┐
    │ Market Data │   Trading   │   Config    │
    │   Domain    │   Domain    │  Domain     │
    └─────────────┴─────────────┴─────────────┘
              │       │       │
              └───────┼───────┘
                      ▼
              ┌─────────────┐
              │Infrastructure│
              │   Domain    │
              └─────────────┘
```

### **Data Flow Architecture**

```
Market Data Flow (Real-time):
WebSocket → OrderBook Update → Opportunity Detection → Trading Signal
     ↓              ↓                    ↓                ↓
 Symbol         Price Feed         Profit Calc      Risk Assessment
Resolution     Normalization        (>$0.50)        (Position Limits)

Trading Flow (Execution):
Trading Signal → Balance Check → Order Placement → Trade Settlement
      ↓              ↓              ↓                ↓
  Risk Validation  Fresh API     Concurrent      Profit Tracking
  (Circuit Breaker)  Calls       Execution       (Performance)

Configuration Flow (System Setup):
Environment → Config Loading → Exchange Creation → Domain Initialization
     ↓              ↓                ↓                    ↓
   .env File    YAML Parsing    Factory Pattern     Interface Setup
   Credentials   Validation      Dependency Injection  Resource Management
```

### **Interface Hierarchy**

```
UnifiedCompositeExchange (Abstract Interface)
├── Market Data Operations Interface
│   ├── get_orderbook() → OrderBook struct
│   ├── get_recent_trades() → List[Trade] struct
│   ├── subscribe_orderbook() → WebSocket stream
│   └── get_symbol_info() → SymbolInfo struct
│
├── Trading Operations Interface  
│   ├── get_balances() → Dict[str, Balance] (FRESH API)
│   ├── place_order() → Order struct
│   ├── get_order_status() → OrderStatus struct (FRESH API)
│   └── cancel_order() → CancelResult struct
│
└── Resource Management Interface
    ├── async __aenter__() → Self
    ├── async __aexit__() → None
    └── health_check() → HealthStatus struct

Exchange Implementations:
├── MexcUnifiedExchange (Complete implementation)
├── GateioUnifiedExchange (Complete implementation)  
└── [Future Exchanges] (Plug-and-play via factory)
```

## Critical Trading Safety Rules

### **HFT Caching Policy (ABSOLUTE RULE)**

**NEVER CACHE (Real-time Trading Data)**:
- Account balances (change with each trade)
- Order status (execution state)
- Position data (margin/futures)
- Orderbook snapshots (pricing data)
- Recent trades (market movement)

**SAFE TO CACHE (Static Configuration Data)**:
- Symbol mappings and SymbolInfo
- Exchange configuration and endpoints
- Trading rules and precision requirements
- Fee schedules and rate limits

**RATIONALE**: Caching real-time trading data causes:
- Execution on stale prices → Lost profit opportunities
- Failed arbitrage → Phantom liquidity risks
- Regulatory compliance violations → Legal exposure
- **This rule supersedes ALL performance considerations**

## Domain Implementation Patterns

### **Market Data Domain Implementation**

**Core Pattern**: Real-time streaming with zero-copy processing
```python
# CORRECT: Fresh WebSocket data only
async def get_orderbook(self, symbol: Symbol) -> OrderBook:
    # No caching - always fresh from WebSocket stream
    return await self._orderbook_stream.get_latest(symbol)

# PROHIBITED: Caching trading data
# orderbook_cache[symbol] = cached_data  # NEVER DO THIS
```

**Performance Pattern**: Sub-microsecond symbol resolution
```python
# Symbol resolution optimized for HFT
symbol_info = await exchange.get_symbol_info(Symbol('BTC', 'USDT'))
# 0.947μs average latency, 1M+ ops/sec throughput
```

### **Trading Domain Implementation**

**Core Pattern**: Fresh API calls for all trading operations
```python
# CORRECT: Always fresh balance data
async def execute_arbitrage(self, opportunity):
    # Fresh API call - NEVER cache balances
    mexc_balances = await mexc_exchange.get_balances()
    gateio_balances = await gateio_exchange.get_balances()
    
    # Concurrent order execution
    buy_task = mexc_exchange.place_order(buy_order)
    sell_task = gateio_exchange.place_order(sell_order)
    
    results = await asyncio.gather(buy_task, sell_task)
    return results
```

**Safety Pattern**: HFT-compliant order management
```python
# Fresh order status checks
order_status = await exchange.get_order_status(order_id)  # Fresh API
# NEVER: cached_orders[order_id]  # PROHIBITED
```

### **Configuration Domain Implementation**

**Core Pattern**: Environment-driven configuration with validation
```python
# Unified configuration loading
config = get_config()  # Loads from config.yaml + environment
exchange_config = config.get_exchange_config('mexc_spot')

# Dynamic exchange creation
exchange = await factory.create_exchange('mexc_spot', config)
```

### **Infrastructure Domain Implementation**

**Core Pattern**: Factory-based dependency injection
```python
# Unified factory with automatic resource management
factory = FullExchangeFactory()
exchanges = await factory.create_multiple_exchanges([
    'mexc_spot', 'gateio_spot'
], symbols=[Symbol('BTC', 'USDT')])

# Automatic cleanup
await factory.close_all()
```

## Domain-Focused Navigation Guide

### **By Business Domain**

#### **🎯 Market Data Domain**
**Primary Focus**: Real-time orderbook processing and arbitrage opportunity detection

**Implementation Guides**:
- **[Symbol Resolution System](data/struct-first-policy.md)** - Ultra-fast symbol mapping patterns
- **[WebSocket Infrastructure](websocket/)** - Real-time price feed management
- **[Market Analysis Workflow](workflows/unified-arbitrage-workflow.md#phase-1-opportunity-detection)** - Opportunity detection logic

#### **💰 Trading Domain**  
**Primary Focus**: Order execution and position management with HFT safety compliance

**Implementation Guides**:
- **[HFT Caching Policy](performance/caching-policy.md)** - Critical trading safety rules
- **[Order Execution Patterns](composite/spot/)** - Concurrent trading implementation
- **[Balance Management](workflows/unified-arbitrage-workflow.md#phase-2-pre-trade-validation)** - Fresh API call patterns

#### **⚙️ Configuration Domain**
**Primary Focus**: System configuration and performance tuning

**Implementation Guides**:
- **[Configuration System](configuration/README.md)** - Unified config management
- **[Exchange Configuration](configuration/exchange-configuration-spec.md)** - Multi-exchange setup
- **[Performance Tuning](performance/hft-requirements-compliance.md)** - HFT optimization settings

#### **🏗️ Infrastructure Domain**
**Primary Focus**: Foundational systems supporting all business domains

**Implementation Guides**:
- **[Factory Patterns](factory/)** - Unified exchange creation
- **[HFT Logging System](configuration/hft-logging-integration-spec.md)** - Sub-microsecond logging
- **[Error Handling Patterns](patterns/exception-handling-patterns.md)** - Composed exception handling

### **By Implementation Task**

#### **Adding New Exchange**
1. **[Factory Registration](factory/composite_exchange_factory_spec.md)** - Register exchange implementation
2. **[Interface Implementation](composite/spot/)** - Implement UnifiedCompositeExchange
3. **[Configuration Setup](configuration/exchange-configuration-spec.md)** - Add exchange config
4. **[Integration Testing](workflows/exchange-integration.md)** - Validation workflow

#### **Performance Optimization**
1. **[HFT Requirements](performance/hft-requirements-compliance.md)** - Performance targets and validation
2. **[Symbol Resolution](data/struct-first-policy.md)** - Optimize lookup performance  
3. **[Networking Optimization](networking/)** - Connection pooling and efficiency
4. **[Logging Performance](configuration/hft-logging-integration-spec.md)** - Sub-microsecond logging

#### **Trading Strategy Implementation**
1. **[Market Data Integration](composite/spot/public_spot_composite_spec.md)** - Real-time price feeds
2. **[Trading Logic](composite/spot/private_spot_composite_spec.md)** - Order execution patterns
3. **[Risk Management](workflows/unified-arbitrage-workflow.md#phase-2-pre-trade-validation)** - Safety validation
4. **[Performance Monitoring](patterns/)** - Strategy performance tracking

### **By User Role**

#### **For Trading Engineers**
**Focus**: Business logic implementation and trading strategy development
- **Market Data Domain** → **Trading Domain** → **Performance Validation**
- Critical path: Real-time data → Opportunity detection → Order execution

#### **For Infrastructure Engineers**  
**Focus**: System performance and reliability
- **Infrastructure Domain** → **Configuration Domain** → **Monitoring Setup**
- Critical path: Factory patterns → HFT logging → Performance compliance

#### **For DevOps Engineers**
**Focus**: System deployment and operational monitoring
- **Configuration Domain** → **Performance Monitoring** → **Error Handling**
- Critical path: Environment setup → HFT compliance → System health

## Key Implementation Examples

### **Market Data Domain - Real-time Processing**
```python
# Ultra-fast symbol resolution (0.947μs average)
symbol_info = await exchange.get_symbol_info(Symbol('BTC', 'USDT'))

# Fresh orderbook data (no caching)
orderbook = await exchange.get_orderbook(symbol)  # WebSocket stream

# Opportunity detection
price_diff = gateio_ask - mexc_bid
if price_diff > min_profit_threshold:
    opportunity = ArbitrageOpportunity(symbol, price_diff, ...)
```

### **Trading Domain - HFT Execution**
```python
# Fresh balance validation (MANDATORY for HFT safety)
mexc_balances = await mexc_exchange.get_balances()  # Fresh API call
gateio_balances = await gateio_exchange.get_balances()  # Fresh API call

# Concurrent order execution (<30ms total)
buy_task = mexc_exchange.place_order(market_buy_order)
sell_task = gateio_exchange.place_order(limit_sell_order)

results = await asyncio.gather(buy_task, sell_task)
```

### **Configuration Domain - Dynamic Setup**
```python
# Unified configuration with environment injection
config = get_config()  # Loads config.yaml + .env variables
exchange_config = config.get_exchange_config('mexc_spot')

# Dynamic exchange creation (no code changes)
exchange = await factory.create_exchange('mexc_spot', exchange_config)
```

### **Infrastructure Domain - Factory Pattern**
```python
# Unified factory with resource management
factory = FullExchangeFactory()
exchanges = await factory.create_multiple_exchanges([
    'mexc_spot', 'gateio_spot'
], symbols=[Symbol('BTC', 'USDT')])

# Automatic cleanup and health monitoring
await factory.close_all()
```

## Performance Achievements Summary

| Domain | Component | Target | Achieved | Business Impact |
|--------|-----------|---------|----------|-----------------|
| Market Data | Symbol Resolution | <1μs | 0.947μs | 1M+ lookups/sec for real-time analysis |
| Trading | Arbitrage Cycle | <50ms | <30ms | Faster execution = higher profit capture |
| Infrastructure | HFT Logging | <1ms | 1.16μs | 859K+ msg/sec with zero blocking |
| Configuration | System Startup | <30s | <10s | Faster deployment and recovery |

## Domain-Focused Development Approach

### **Business Logic First**
- **Market Data Domain**: Focus on real-time streaming and opportunity detection
- **Trading Domain**: Emphasize execution speed and safety compliance
- **Configuration Domain**: Prioritize flexibility and validation
- **Infrastructure Domain**: Optimize for performance and reliability

### **Implementation Priorities**
1. **Trading Safety** - HFT caching policy compliance supersedes all other considerations
2. **Performance Targets** - Sub-millisecond operations throughout critical paths
3. **Business Value** - Focus on profit-generating features and arbitrage efficiency
4. **Operational Excellence** - Reliable, monitorable, maintainable systems

### **Domain Boundaries**
- **Clear Separation**: Each domain has distinct responsibilities and performance characteristics
- **Minimal Coupling**: Domains interact through well-defined interfaces only
- **Independent Scaling**: Each domain can be optimized and scaled independently
- **Business Alignment**: Domain organization reflects actual trading workflow

## Future Domain Evolution

### **Extensibility Points**
- **Market Data Domain**: Additional price feeds, new data sources, advanced analysis
- **Trading Domain**: New execution strategies, position sizing algorithms, risk models
- **Configuration Domain**: Advanced validation, dynamic reconfiguration, A/B testing
- **Infrastructure Domain**: Enhanced monitoring, distributed architecture, performance tuning

---

*This domain-focused specification guide provides a business-centric view of the CEX Arbitrage Engine, emphasizing trading logic and component relationships over technical directory structures. All documentation is organized around the four core business domains that drive profitable cryptocurrency arbitrage operations.*

**Architecture Focus**: Business domains → Implementation patterns → Performance optimization
**Last Updated**: September 2025 - Domain-Focused Restructure Complete