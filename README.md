# High-Performance CEX Arbitrage Engine

## Overview

This is an ultra-low-latency cryptocurrency arbitrage engine designed for high-frequency trading across multiple centralized exchanges (CEX). The system detects and executes profitable arbitrage opportunities by monitoring real-time order book data from multiple exchanges simultaneously.

## Architecture

### Core Design Principles

The engine follows a **high-performance event-driven architecture** with these foundational principles:

- **Single-threaded async architecture** to minimize locking overhead
- **Zero-copy data structures** using `msgspec.Struct` for maximum performance
- **Connection pooling and session reuse** for optimal network utilization
- **Sub-millisecond parsing** with specialized JSON and numeric conversion libraries
- **Intelligent rate limiting** with per-endpoint token bucket algorithms

### System Architecture Diagram

```
┌─────────────────┐    ┌───────────────┐    ┌──────────────────┐
│   Exchange WS 1 │    │ Exchange WS 2 │    │   Exchange WS N  │
└─────────┬───────┘    └───────┬───────┘    └─────────┬────────┘
          │                    │                      │
          │                    │                      │
    ┌─────┴────────────────────┴──────────────────────┴─────┐
    │         Connection Manager (uvloop + asyncio)         │
    │    - Manages reconnection/backoff, rate limits        │
    │    - Auto-healing WebSocket connections               │
    └─────┬────────────────────┬──────────────────┬─────────┘
          │                    │                  │
          │                    │                  │
    ┌─────┴─────┐        ┌─────┴─────┐    ┌─────┴─────┐
    │ Parser 1  │        │ Parser 2  │    │ Parser N  │
    │ msgspec + │        │ msgspec + │    │ msgspec + │
    │ fastfloat │        │ fastfloat │    │ fastfloat │
    └─────┬─────┘        └─────┬─────┘    └─────┬─────┘
          │                    │                │
          └────────────────────┼────────────────┘
                               │
    ┌──────────────────────────┴──────────────────────────┐
    │   Order Book Store (high-performance in-memory)    │
    │   - Incremental updates (apply diffs)              │
    │   - Minimal locks: single-threaded async updates   │
    └──────────────────┬─────────────────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         │                           │
    ┌────┴──────┐              ┌─────┴─────────────┐
    │Arbitrage  │              │ Execution Layer   │
    │Detector   │              │ - REST API calls  │
    │           │              │ - Rate limiting   │
    └───────────┘              │ - Retry logic     │
                               └───────────────────┘
```

## Core Components

### 1. **Unified Interface System** (`src/exchanges/interface/`)

**Purpose**: Standardized interfaces ensuring consistency across all exchange implementations

**MANDATORY Interface Compliance**:
- **All exchanges MUST implement `PublicExchangeInterface`** for market data operations
- **All exchanges MUST implement `PrivateExchangeInterface`** for trading operations  
- **All WebSocket implementations MUST use `BaseWebSocketInterface`**
- **NO USAGE of legacy `raw/common/interfaces/`** - deprecated and performance-degraded

**Key Files**:
- `public_exchange.py`: Market data operations (order books, trades, server time)
- `private_exchange.py`: Trading operations (orders, balances, account management)
- `base_ws.py`: WebSocket base interface for real-time data streaming

### 2. Data Layer (`src/structs/`)

**Purpose**: **UNIFIED** type-safe data structures using `msgspec.Struct` for maximum performance

**Key Files**:
- `exchange.py`: **STANDARDIZED** core trading data structures (Order, OrderBook, Trade, etc.)

**Performance Features**:
- `msgspec.Struct` provides 3-5x performance gain over `dataclasses`
- `IntEnum` for status codes enables fast integer comparisons
- `NewType` for type aliases with zero runtime overhead
- Optimized memory layout with `__slots__` where applicable

**CRITICAL**: **NEVER use legacy structures from `raw/common/entities.py`**

### 3. Network Layer (`src/common/rest.py`)

**Purpose**: **STANDARDIZED** ultra-high performance REST API client optimized for cryptocurrency trading

**CRITICAL**: **ALL exchanges MUST use `HighPerformanceRestClient` - NO custom HTTP clients allowed**

**Key Features**:
- **Connection pooling** with persistent aiohttp sessions
- **Advanced rate limiting** with per-endpoint token bucket controls
- **Fast JSON parsing** using msgspec exclusively (no fallbacks)
- **Concurrent request handling** with semaphore limiting
- **Intelligent retry strategies** with exponential backoff
- **Auth signature caching** for repeated requests
- **Memory-efficient** request/response processing

**Performance Metrics**:
- Target: <50ms end-to-end HTTP request latency
- Connection reuse: >95% hit rate
- Memory usage: O(1) per request
- JSON parsing: <1ms per message

### 4. Exception Handling (`src/common/exceptions.py`)

**Purpose**: **UNIFIED** structured error handling with exchange-specific error codes

**CRITICAL**: **ALL exchanges MUST use unified exception hierarchy - NO legacy exceptions allowed**

**Features**:
- Custom exception hierarchy for different error types
- Structured error information (code, message, api_code)
- Rate limiting exceptions with retry timing information
- Trading-specific exceptions (insufficient balance, trading disabled, etc.)

**DEPRECATED**: **NEVER use `raw/common/exceptions.py`** - incompatible with unified system

## Interface Standards Compliance

### **CRITICAL REQUIREMENTS** for All Exchange Implementations

⚠️ **FAILURE TO COMPLY WILL RESULT IN PRODUCTION ISSUES AND PERFORMANCE DEGRADATION**

#### ✅ **MUST USE** - Unified Standards:
- `src/exchanges/interface/PublicExchangeInterface` - Market data operations
- `src/exchanges/interface/PrivateExchangeInterface` - Trading operations  
- `src/structs/exchange.py` - All data structures (Order, OrderBook, Trade, etc.)
- `src/common/exceptions.py` - Exception handling (ExchangeAPIError, RateLimitError)
- `src/common/rest.HighPerformanceRestClient` - HTTP operations

#### ❌ **NEVER USE** - Legacy/Deprecated:
- `raw/common/interfaces/` - Legacy interface system (performance issues)
- `raw/common/entities.py` - Legacy data structures (lacks msgspec optimization)  
- `raw/common/exceptions.py` - MEXC-specific exceptions (incompatible attributes)
- Custom HTTP clients - Use standardized `HighPerformanceRestClient` only

#### 📋 **Compliance Verification**:
```bash
# Run interface compliance check
scripts/verify_interface_compliance.py your_exchange

# Performance benchmarks  
pytest tests/performance/test_your_exchange.py --benchmark

# Integration tests
pytest tests/exchanges/your_exchange/ --integration
```

See **`INTERFACE_STANDARDS.md`** for complete implementation guidelines.

## Performance Optimization Strategy

### JSON Processing Rules

```python
# ✅ ALWAYS use msgspec for JSON operations
import msgspec
DECODER = msgspec.json.Decoder()
ENCODER = msgspec.json.encode

# ✅ Use msgspec.Struct instead of dataclasses
class Order(msgspec.Struct):
    price: float
    size: float

# ❌ NEVER use try/except for JSON library fallbacks
# ❌ NEVER use standard library json module
```

### Data Structure Optimization

- **msgspec.Struct**: 3-5x faster than `@dataclass`
- **IntEnum**: Fast integer comparisons for status codes
- **NewType**: Type aliases without runtime overhead
- **list[T]**: Python 3.9+ syntax instead of `List[T]`

### Memory Management

- `__slots__` for classes with many instances
- LRU cache cleanup for auth signatures
- `deque` with `maxlen` for metrics collection
- Periodic cache clearing to prevent memory leaks

### Async Operations

- `asyncio.gather()` for concurrent operations
- Semaphores for connection limiting
- Connection pooling with aiohttp TCPConnector
- Aggressive timeouts for trading operations

## Development Setup

### Prerequisites

- Python 3.11+ (required for TaskGroup and improved asyncio performance)
- pip or poetry for dependency management

### Installation

```bash
# Install core dependencies
pip install -r requirements.txt

# Or install manually with core performance libraries:
pip install uvloop msgspec aiohttp anyio

# Development dependencies
pip install pytest pytest-asyncio black ruff mypy
```

### Running the System

```bash
# Run the architecture skeleton
python PRD/arbitrage_engine_architecture_python_skeleton.py

# Run tests (when implemented)
pytest

# Code formatting
black src/
ruff check src/
```

## Configuration

### Performance Tuning

The system uses several configuration classes for optimal performance:

```python
# Connection configuration for low-latency trading
connection_config = ConnectionConfig(
    connector_limit=100,           # Total connection pool size
    connector_limit_per_host=30,   # Per-host connection limit
    connect_timeout=5.0,           # Aggressive connection timeout
    total_timeout=30.0             # Total request timeout
)

# Request configuration for different operation types
market_data_config = RequestConfig(
    timeout=5.0,                   # Fast timeout for market data
    max_retries=2,                 # Quick retry for public data
    require_auth=False             # No authentication needed
)

trading_config = RequestConfig(
    timeout=10.0,                  # Longer timeout for trading
    max_retries=3,                 # More retries for critical operations
    require_auth=True              # Authentication required
)
```

## Usage Examples

### Basic REST Client Usage

```python
from src.common.rest import create_trading_client, create_market_data_config

async def example_usage():
    async with create_trading_client(
        base_url="https://api.exchange.com",
        api_key="your_api_key",
        secret_key="your_secret_key",
        enable_metrics=True
    ) as client:
        # Get market data
        config = create_market_data_config()
        ticker = await client.get("/api/v3/ticker/24hr", config=config)
        
        # Execute batch requests
        batch_requests = [
            (HTTPMethod.GET, "/api/v3/ticker/price", {"symbol": "BTCUSDT"}, config),
            (HTTPMethod.GET, "/api/v3/ticker/price", {"symbol": "ETHUSDT"}, config),
        ]
        results = await client.batch_request(batch_requests)
        
        # Monitor performance
        metrics = client.get_metrics()
        print(f"Average response time: {metrics.get('avg_response_time', 0):.3f}s")
```

### **Compliant Exchange Implementation Example**

```python
# ✅ CORRECT: Using unified interface standards
from src.exchanges.interface.public_exchange import PublicExchangeInterface
from src.exchanges.interface.private_exchange import PrivateExchangeInterface
from src.structs.exchange import Symbol, OrderBook, Order, ExchangeName
from src.common.rest import HighPerformanceRestClient, RequestConfig
from src.common.exceptions import ExchangeAPIError, RateLimitError

class BinancePublic(PublicExchangeInterface):
    """COMPLIANT implementation using unified standards"""
    
    def __init__(self):
        super().__init__(ExchangeName("binance"), "https://api.binance.com")
        
        # MANDATORY: Use standardized REST client
        self.client = HighPerformanceRestClient(
            base_url=self.base_url,
            max_concurrent_requests=40,
            enable_metrics=True
        )
    
    @property
    def exchange_name(self) -> ExchangeName:
        return ExchangeName("binance")
    
    async def get_orderbook(self, symbol: Symbol, limit: int = 100) -> OrderBook:
        """Implementation using unified data structures and REST client"""
        try:
            config = RequestConfig(timeout=5.0, max_retries=2)
            response = await self.client.get(f"/api/v3/depth", 
                                           params={"symbol": self.symbol_to_pair(symbol)}, 
                                           config=config)
            
            # Transform to unified OrderBook structure
            return self._transform_orderbook_response(response)
            
        except Exception as e:
            # MANDATORY: Use unified exception mapping
            raise self._map_exchange_error(e)
```

**Reference Implementation**: See `/Users/dasein/dev/cex_arbitrage/src/exchanges/mexc/public.py` for complete compliant implementation.

## Performance Targets

### Latency Requirements

- **JSON parsing**: <1ms per message
- **HTTP request latency**: <50ms end-to-end
- **WebSocket → detection**: <50ms end-to-end
- **Order book updates**: Sub-millisecond processing

### Throughput Requirements

- Support 10-20 exchanges simultaneously
- Process 1000+ messages/second per exchange
- Maintain >95% connection uptime
- Detect arbitrage opportunities ≥0.1% spread

### Success Criteria

- Stable connections to 10+ exchanges for >24h
- Trade execution success rate >95%
- Memory usage: O(1) per request
- Connection reuse hit rate: >95%

## Risk Management

### Built-in Safety Features

- Balance checks before execution
- Position limits and cooldown periods
- Idempotent order placement with retry logic
- Partial fill and race condition handling
- Circuit breaker patterns for failed exchanges

### Error Handling

- Structured exception hierarchy
- Automatic retry with exponential backoff
- Rate limit detection and handling
- Connection health monitoring
- Graceful degradation on partial failures

## Monitoring and Metrics

### Performance Monitoring

The system includes comprehensive metrics collection:

- Request/response latency percentiles
- Success/failure rates
- Rate limit hit counts
- Connection pool utilization
- Auth cache hit rates
- Memory usage patterns

### Health Checks

```python
# Built-in health check endpoint
health_status = await client.health_check()
print(f"Status: {health_status['status']}")
print(f"Response time: {health_status['response_time']:.3f}s")
```

## Future Optimizations

### Potential Enhancements

1. **Rust Integration**: Port critical paths to Rust via PyO3 for maximum performance
2. **Order Book Optimization**: Replace dict-based storage with sorted containers or B-trees
3. **SIMD Acceleration**: Use specialized libraries for numerical operations
4. **Memory Pooling**: Implement object pools for frequently allocated structures
5. **Protocol Optimization**: Consider binary protocols for exchange communication

### Scalability Considerations

- Horizontal scaling with worker processes
- Distributed order book synchronization
- Load balancing across multiple exchange connections
- Database integration for persistent state management

## Migration from Legacy Systems

### **CRITICAL MIGRATION REQUIRED** - Legacy `raw/` Directory Deprecation

The `raw/` directory contains legacy code that is **incompatible with unified interface standards** and causes significant performance degradation. All legacy code must be migrated to the unified system.

#### **Phase 1: Immediate Actions (REQUIRED)**

1. **Stop Using Legacy Imports**:
   ```python
   # ❌ REMOVE these imports immediately:
   from raw.common.interfaces.base_exchange import BaseSyncExchange
   from raw.common.entities import Order, SymbolInfo, AccountBalance
   from raw.common.exceptions import ExchangeAPIError
   
   # ✅ REPLACE with unified imports:
   from src.exchanges.interface.public_exchange import PublicExchangeInterface
   from src.structs.exchange import Order, SymbolInfo, AssetBalance
   from src.common.exceptions import ExchangeAPIError
   ```

2. **Update Exception Handling**:
   ```python
   # ❌ Legacy exception with mexc_code:
   try:
       response = await api_call()
   except ExchangeAPIError as e:
       print(f"MEXC Code: {e.mexc_code}")  # Incompatible
   
   # ✅ Unified exception with api_code:
   try:
       response = await api_call()
   except ExchangeAPIError as e:
       print(f"API Code: {e.api_code}")    # Standardized
   ```

3. **Replace Custom HTTP Clients**:
   ```python
   # ❌ Custom aiohttp usage:
   async with aiohttp.ClientSession() as session:
       async with session.get(url) as response:
           data = await response.json()
   
   # ✅ Use standardized client:
   from src.common.rest import HighPerformanceRestClient
   async with HighPerformanceRestClient(base_url) as client:
       data = await client.get(endpoint)
   ```

#### **Phase 2: Interface Migration (1-2 weeks)**

1. **Implement Unified Interfaces**:
   - Create `PublicExchangeInterface` implementation
   - Create `PrivateExchangeInterface` implementation
   - Migrate WebSocket handlers to `BaseWebSocketInterface`

2. **Data Structure Migration**:
   - Replace `@dataclass` with `msgspec.Struct`
   - Update type annotations to use `NewType` aliases
   - Ensure all structures use `IntEnum` for performance

3. **Testing Migration**:
   - Update all tests to use unified interfaces
   - Add performance benchmarks
   - Verify compliance with `scripts/verify_interface_compliance.py`

#### **Phase 3: Production Deployment**

1. **Performance Validation**:
   - Run full performance test suite
   - Verify <50ms latency requirements
   - Confirm >95% connection stability

2. **Monitoring Setup**:
   - Deploy with unified metrics collection
   - Monitor interface compliance in production
   - Set up alerts for performance degradation

### **Legacy Code Cleanup Schedule**

- **Week 1**: Stop all new development using `raw/` directory
- **Week 2-3**: Migrate existing implementations to unified standards  
- **Week 4**: Remove `raw/` directory from production deployments
- **Week 5**: Archive `raw/` directory for historical reference only

### **Support and Resources**

- **Complete Implementation Guide**: `INTERFACE_STANDARDS.md`
- **Performance Requirements**: `PERFORMANCE_RULES.md`  
- **Reference Implementation**: `src/exchanges/mexc/public.py`
- **Compliance Checker**: `scripts/verify_interface_compliance.py`
- **Migration Support**: Contact system architects for migration assistance

## Contributing

### Development Standards

- **MANDATORY**: Follow interface standards in `INTERFACE_STANDARDS.md`
- **MANDATORY**: Pass interface compliance verification
- Follow the performance rules in `PERFORMANCE_RULES.md`
- Use `msgspec.Struct` exclusively for data structures
- Maintain type safety with proper annotations
- Write comprehensive tests for critical paths
- Profile performance-critical code sections

### Code Quality

- Black for code formatting
- Ruff for linting
- MyPy for type checking
- Pytest for testing with async support

## License

[License information to be added]

## Support

[Support information to be added]