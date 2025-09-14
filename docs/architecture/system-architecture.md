# System Architecture Overview

## High-Level Architecture

The CEX Arbitrage Engine follows a **layered, event-driven architecture** with **SOLID principles** and **Abstract Factory patterns** for maximum extensibility and performance.

```
┌─────────────────────────────────────────────────────────────────┐
│                        Application Layer                        │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │ ArbitrageController │  │ PerformanceMonitor │  │ ShutdownManager │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                               │
┌─────────────────────────────────────────────────────────────────┐
│                      Configuration Layer                        │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │ConfigurationMgr │  │  ExchangeFactory │  │  SymbolResolver │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                               │
┌─────────────────────────────────────────────────────────────────┐
│                       Exchange Layer                            │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  MEXC Exchange  │  │ Gate.io Exchange│  │  Future Exchange│  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                               │
┌─────────────────────────────────────────────────────────────────┐
│                     Network/Interface Layer                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │   REST Client   │  │  WebSocket Client│  │   Common Utils  │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Core Architectural Patterns

### 1. SOLID-Compliant Component Design

**Single Responsibility Principle (SRP)**:
- `ConfigurationManager` - Handles only configuration loading and validation
- `ExchangeFactory` - Creates and manages exchange instances using Factory pattern
- `PerformanceMonitor` - Dedicated to HFT performance tracking
- `ShutdownManager` - Manages graceful shutdown and resource cleanup
- `ArbitrageController` - Orchestrates components without implementing their logic

**Open/Closed Principle (OCP)**:
- New exchanges implement `BaseExchangeInterface` without modifying existing code
- Trading algorithms can be added via plugin interfaces
- Behavior modification through configuration rather than code changes

**Liskov Substitution Principle (LSP)**:
- All exchange implementations are fully substitutable
- Consistent async patterns across all components
- Interface contracts respected by all implementations

**Interface Segregation Principle (ISP)**:
- Components expose only methods relevant to their clients
- Minimal dependencies - components depend only on interfaces they use
- No component forced to depend on unused functionality

**Dependency Inversion Principle (DIP)**:
- Controller receives components rather than creating them
- All components depend on interfaces, not concrete implementations
- High-level modules don't depend on low-level modules

### 2. Abstract Factory Pattern

**Problem Solved**: Eliminated code duplication in exchange creation and removed God Class antipattern.

**Implementation**:
```python
class ExchangeFactory:
    EXCHANGE_CLASSES: Dict[str, Type[BaseExchangeInterface]] = {
        'MEXC': MexcExchange,
        'GATEIO': GateioExchange,
    }
    
    async def create_exchange(self, exchange_name: str) -> BaseExchangeInterface:
        # Centralized creation logic with error handling
        # Credential management with secure preview logging
        # Concurrent initialization for performance
```

**Benefits**:
- **Centralized creation logic** - Single point for exchange instantiation
- **Credential management** - Secure API key handling with preview logging
- **Concurrent initialization** - Multiple exchanges created in parallel
- **Error resilience** - Graceful handling of exchange failures

### 3. Unified Interface System

**Central Design Principle**: All components use `src/exchanges/interface/` as the single source of truth.

**Key Interfaces**:
- `BaseExchangeInterface` - Core exchange operations (ALL exchanges inherit from this)
- `PublicExchangeInterface` - Public market data operations
- `PrivateExchangeInterface` - Private trading operations
- `Symbol`, `SymbolInfo` - Unified symbol representation

**Exchange Implementation Architecture**:

```
BaseExchangeInterface (Abstract Interface)
├── MexcExchange (implements BaseExchangeInterface)
└── GateioExchange (implements BaseExchangeInterface)

NOT WebSocketExchange or other specialized inheritance!
```

**Composition Pattern Implementation**:
```python
class MexcExchange(BaseExchangeInterface):  # <- Inherits from BASE interface
    """Uses composition, NOT inheritance from specialized classes"""
    
    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None):
        super().__init__('MEXC', api_key, secret_key)  # <- Call base constructor
        
        # Composition - delegate to specialized components
        self._public_api: Optional[MexcPublicExchange] = None
        self._private_api: Optional[MexcPrivateExchange] = None
        self._ws_client: Optional[MexcWebsocketPublic] = None
```

**Key Design Rules**:
1. **MUST inherit from BaseExchangeInterface** - Not WebSocket or other specialized classes
2. **Use composition for specialization** - Delegate to REST/WebSocket components
3. **Implement ALL abstract methods** - `status`, `orderbook`, `balances`, etc.
4. **HFT compliance mandatory** - No caching of real-time trading data
5. **Unified data structures only** - Use `Symbol`, `SymbolInfo`, etc. from interface package

**Data Structures** (from `src/exchanges/interface/structs.py`):
```python
@struct
class Symbol:
    base: AssetName
    quote: AssetName
    is_futures: bool = False

@struct  
class SymbolInfo:
    symbol: Symbol
    exchange: str
    base_precision: int
    quote_precision: int
    min_qty: float
    max_qty: float
    min_notional: float
    status: str
```

## Configuration Architecture Evolution

### Legacy Architecture (Pre-Refactor)
```yaml
# Individual sections (legacy)
mexc:
  api_key: "..."
  secret_key: "..."

gateio:
  api_key: "..."
  secret_key: "..."
```

### Modern Unified Architecture
```yaml
# Unified dictionary structure
exchanges:
  mexc:
    api_key: "${MEXC_API_KEY}"
    secret_key: "${MEXC_SECRET_KEY}"
    base_url: "https://api.mexc.com"
  
  gateio:
    api_key: "${GATEIO_API_KEY}"
    secret_key: "${GATEIO_SECRET_KEY}"
    base_url: "https://api.gateio.ws/api/v4"
```

### Configuration Flow
```
config.yaml → ConfigurationManager → ExchangeFactory → Dynamic Exchange Creation
     ↓              ↓                      ↓                     ↓
 Unified Dict → get_exchange_config() → create_exchange() → BaseExchangeInterface
```

**Key Improvements**:
- **Eliminates code duplication** in credential management
- **Enables dynamic scaling** - new exchanges added via YAML only
- **Centralizes validation** through unified methods
- **Simplifies deployment** with consistent patterns
- **Future-proof design** for additional integrations

## Performance Architecture

### HFT-Compliant Design Principles

**Sub-Microsecond Symbol Resolution**:
- **O(1) Hash-based lookups** with pre-computed caches
- **Average latency: 0.947μs** per symbol resolution
- **Throughput: 1M+ operations/second**
- **Pre-built lookup tables** for exchange-specific formatting

**Zero-Copy Message Processing**:
- **msgspec-exclusive JSON parsing** for consistent performance
- **Structured data types** with no runtime overhead
- **Connection pooling** with intelligent reuse
- **Object pooling** to reduce GC pressure

**Event-Driven Async Architecture**:
- **Single-threaded async** eliminates locking overhead
- **Non-blocking I/O** throughout the system
- **Intelligent connection management** for persistent sessions
- **Circuit breaker patterns** prevent cascade failures

### Critical Performance Targets

| Component | Target | Achieved | Status |
|-----------|---------|----------|---------|
| Symbol Resolution | <1μs | 0.947μs | ✅ |
| Exchange Formatting | <1μs | 0.306μs | ✅ |
| Common Symbols Cache | <0.1μs | 0.035μs | ✅ |
| Total Request Latency | <50ms | <30ms | ✅ |
| Symbol Cache Build | <50ms | <10ms | ✅ |

## System Initialization Flow

```
1. Load Environment Variables (.env)
         ↓
2. Parse Configuration (config.yaml)
         ↓
3. Initialize ConfigurationManager
         ↓
4. Create ExchangeFactory
         ↓
5. Initialize Exchanges (concurrent)
         ↓
6. Build Symbol Resolution System
         ↓
7. Start PerformanceMonitor
         ↓
8. Initialize ArbitrageController
         ↓
9. Begin Trading Operations
```

## Error Handling Strategy

### Fail-Fast Propagation
- **NEVER handle exceptions at function level** - propagate to higher levels
- **Use unified exception hierarchy** from `src/common/exceptions.py`
- **Structured error information** with context preservation
- **Comprehensive logging** for audit trails

### Intelligent Retry Logic
- **Exponential backoff with jitter** for network operations
- **Circuit breaker patterns** to prevent cascade failures
- **Exchange-specific error handling** with appropriate retry strategies
- **Graceful degradation** when components fail

## Extensibility Points

### Adding New Exchanges
1. **Implement BaseExchangeInterface** in new exchange module
2. **Add to ExchangeFactory.EXCHANGE_CLASSES** dictionary
3. **Configure in config.yaml** under `exchanges:` section
4. **No other code changes required**

### Adding New Trading Strategies
1. **Implement strategy interface** (future extension point)
2. **Register strategy in configuration**
3. **Plug into ArbitrageController**

### Adding New Data Sources
1. **Implement data source interface**
2. **Integrate with unified symbol system**
3. **Configure through standard patterns**

## Security Architecture

### API Key Management
- **Environment variable injection** via `${VAR_NAME}` syntax
- **Secure credential validation** without exposing keys in logs
- **Preview logging** shows key prefixes/suffixes only
- **Separated public/private operations** based on credential availability

### Trading Safety
- **Dry run mode by default** prevents accidental live trading
- **Comprehensive validation** at all system boundaries
- **Circuit breakers** prevent runaway trading
- **Audit trails** for all trading operations

## Monitoring and Observability

### Performance Monitoring
- **Real-time latency tracking** for all critical operations
- **HFT compliance monitoring** with <50ms targets
- **Exchange health monitoring** with automatic failover
- **Resource utilization tracking** for optimization

### Operational Metrics
- **Initialization success rates** per exchange
- **Symbol resolution performance** with percentile tracking
- **Configuration validation results** with error categorization
- **System health dashboards** (future extension)

---

*This architecture documentation reflects the production-ready system with modernized configuration and SOLID principles compliance. All architectural decisions prioritize HFT performance while maintaining code clarity and extensibility.*