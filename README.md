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

### 1. Data Layer (`src/structs/`)

**Purpose**: Type-safe data structures using `msgspec.Struct` for maximum performance

**Key Files**:
- `exchange.py`: Core trading data structures (Order, OrderBook, Trade, etc.)

**Performance Features**:
- `msgspec.Struct` provides 3-5x performance gain over `dataclasses`
- `IntEnum` for status codes enables fast integer comparisons
- `NewType` for type aliases with zero runtime overhead
- Optimized memory layout with `__slots__` where applicable

### 2. Network Layer (`src/common/rest.py`)

**Purpose**: Ultra-high performance REST API client optimized for cryptocurrency trading

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

### 3. Exchange Interfaces (`src/exchanges/interface/`)

**Purpose**: Abstract interfaces ensuring consistent API across different exchanges

**Architecture**:
- `PublicExchangeInterface`: Market data operations (order books, trades, server time)
- `PrivateExchangeInterface`: Trading operations (orders, balances, account management)

**Design Pattern**: **Abstract Factory Pattern** with exchange-specific implementations

### 4. Exception Hierarchy (`src/common/exceptions.py`)

**Purpose**: Structured error handling with exchange-specific error codes

**Features**:
- Custom exception hierarchy for different error types
- Structured error information (code, message, api_code)
- Rate limiting exceptions with retry timing information
- Trading-specific exceptions (insufficient balance, trading disabled, etc.)

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

### Exchange Interface Implementation

```python
from src.exchanges.interface import PublicExchangeInterface
from src.structs.exchange import Symbol, OrderBook, ExchangeName

class BinancePublic(PublicExchangeInterface):
    def __init__(self):
        super().__init__(
            exchange=ExchangeName("binance"),
            base_url="https://api.binance.com"
        )
    
    @property
    def exchange_name(self) -> ExchangeName:
        return ExchangeName("binance")
    
    async def get_orderbook(self, symbol: Symbol, limit: int = 100) -> OrderBook:
        # Implementation using the high-performance REST client
        # ...
        pass
```

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

## Contributing

### Development Standards

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