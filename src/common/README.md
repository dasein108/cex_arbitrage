# Common Components

Shared utilities and base components providing core functionality for the HFT arbitrage engine.

## Overview

The `src/common/` directory contains foundational components used throughout the system:

- **SimpleLogger**: Ultra-high performance logging system with <2μs emit latency
- **REST Client**: Ultra-high performance HTTP client optimized for trading APIs
- **WebSocket Client**: Real-time data streaming with automatic reconnection
- **Exception System**: Unified error handling with structured exception hierarchy
- **Configuration**: YAML-based configuration management
- **Zero Allocation Buffers**: Memory-optimized data structures for HFT

## Components

### SimpleLogger (`simple_logger.py`)

Ultra-high-performance logging system designed for HFT (High-Frequency Trading) applications with sub-2μs emit latency and optional console output.

#### Key Features
- **<2μs emit latency** (vs 1000μs+ for standard logging)
- **Async file batching** to eliminate I/O blocking
- **JSON structured output** for efficient parsing
- **Optional console output** with colored formatting
- **Memory-efficient ring buffer** for log batching
- **Graceful shutdown** with flush guarantee
- **Drop-in replacement** for `logging.getLogger()`

#### Performance Characteristics
- **Emit Latency**: <2μs average
- **Throughput**: 500,000+ messages/second
- **Memory Usage**: Ring buffer with 10,000 message capacity
- **File Format**: JSON Lines (.jsonl) for streaming analysis

#### Basic Usage

```python
from common.logging.simple_logger import getLogger, shutdown_all_loggers

# Drop-in replacement for logging.getLogger()
logger = getLogger(__name__)

logger.info("Application started")
logger.info("Trade executed", extra={
    "symbol": "BTCUSDT",
    "price": 45000.50,
    "quantity": 0.001,
    "latency_us": 180
})

# Clean shutdown (important for log integrity)
shutdown_all_loggers()
```

#### Console Output Configuration

```python
from common.logging.simple_logger import configure_console, LogLevel

# Development mode - all levels with colors
configure_console(enabled=True, min_level=LogLevel.DEBUG, use_colors=True)

# Production mode - warnings and errors only
configure_console(enabled=True, min_level=LogLevel.WARNING, use_colors=True)

# HFT mode - console disabled for maximum performance (default)
configure_console(enabled=False)
```

#### SOLID Principles Integration
SimpleLogger follows dependency injection patterns for seamless integration:

```python
class PerformanceMonitor:
    def __init__(self, logger: SimpleLogger):
        self.logger = logger  # Dependency injection
    
    def record_latency(self, operation: str, latency_us: float) -> None:
        if latency_us > 50000:  # > 50ms
            self.logger.warning(f"High latency: {operation}", extra={
                "operation": operation,
                "latency_us": latency_us,
                "threshold_us": 50000
            })
```

#### Migration from Standard Logging

**Before (Standard Logging)**:
```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info("Message")
```

**After (SimpleLogger)**:

```python
from common.logging.simple_logger import getLogger, configure_console, LogLevel, shutdown_all_loggers

configure_console(enabled=True, min_level=LogLevel.INFO)
logger = getLogger(__name__)
logger.info("Message")
shutdown_all_loggers()  # Required for proper cleanup
```

#### Performance Benefits
| Aspect | Standard Logging | SimpleLogger | Improvement |
|--------|-----------------|--------------|-------------|
| **Emit Latency** | 1000-5000μs | <2μs | **500-2500x faster** |
| **File Format** | Text | JSON | **Structured parsing** |
| **Async I/O** | Synchronous | Async batched | **Non-blocking** |
| **Memory Usage** | Unbounded | Ring buffer | **Bounded memory** |
| **Console Control** | Handler-based | Global config | **Simpler setup** |

#### Environment-Specific Configuration
```python
import os

def setup_logging():
    env = os.getenv('ENVIRONMENT', 'development')
    
    if env == 'production':
        configure_console(enabled=True, min_level=LogLevel.WARNING, use_colors=False)
    elif env == 'development':
        configure_console(enabled=True, min_level=LogLevel.DEBUG, use_colors=True)
    elif env == 'hft':
        configure_console(enabled=False)  # Maximum performance
```

---

### RestClient (`rest_client.py`)

Ultra-simple high-performance REST API client optimized for cryptocurrency trading with minimal complexity.

#### Key Features
- **Connection pooling** with persistent aiohttp sessions
- **Ultra-fast JSON parsing** with msgspec (zero fallbacks)
- **Generic HMAC-SHA256 authentication** suitable for most exchanges
- **Simple exponential backoff** retry logic
- **Aggressive timeout configurations** for trading
- **Memory-efficient** request/response handling

#### Performance Targets
- **Time Complexity**: O(1) for all core operations
- **Space Complexity**: O(1) per request, O(n) for connection pool
- **Latency**: <50ms HTTP request latency, <1ms JSON parsing

#### Usage Example

```python
from core.transport.rest.rest_client_legacy import RestClient, RestConfig

# Initialize client
config = RestConfig(timeout=10.0, max_retries=3, require_auth=True)
async with RestClient(
        base_url="https://api.exchange.com",
        api_key="your_key",
        secret_key="your_secret",
        signature_generator=your_signature_function,
        config=config
) as client:
    # Make authenticated request
    result = await client.get("/api/v3/account")
```

#### Configuration
```python
class RestConfig(msgspec.Struct):
    timeout: float = 10.0           # Request timeout in seconds
    max_retries: int = 3            # Maximum retry attempts
    retry_delay: float = 1.0        # Base retry delay
    require_auth: bool = False      # Whether to add authentication
    max_concurrent: int = 50        # Max concurrent requests
```

### WebsocketClient (`ws_client.py`)

High-performance WebSocket client for real-time market data streaming with automatic reconnection.

#### Key Features
- **Automatic reconnection** with exponential backoff
- **Subscription management** with queuing for disconnected state
- **Error handling and recovery** with structured exception propagation
- **Connection lifecycle management** with proper cleanup
- **Pre-computed backoff delays** for performance optimization
- **Message batching** and efficient async processing

#### Performance Optimizations
- **Object pooling** for subscription data structures
- **Pre-compiled backoff delays** - no power calculations in hot path
- **Lazy logging** to avoid string formatting overhead
- **Efficient deque operations** for subscription queuing
- **Fast message type detection** with binary patterns

#### Usage Example

```python
from core.transport.websocket.ws_client import WebsocketClient, WebSocketConfig

# Configure WebSocket
config = WebSocketConfig(
    name="market_data",
    url="wss://stream.exchange.com/ws",
    timeout=30.0,
    ping_interval=20.0,
    max_reconnect_attempts=10
)


# Initialize client
async def message_handler(message):
    print(f"Received: {message}")


async def error_handler(error):
    print(f"Error: {error}")


client = WebsocketClient(
    config=config,
    message_handler=message_handler,
    error_handler=error_handler
)

# Start connection
await client.start()

# Subscribe to streams
await client.subscribe(["btcusdt@depth", "ethusdt@trade"])

# Stop when done
await client.stop()
```

#### Connection States
```python
class ConnectionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting" 
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"
    CLOSING = "closing"
    CLOSED = "closed"
```

### Exception System (`exceptions.py`)

Unified exception hierarchy for consistent error handling across all exchange implementations.

#### Exception Hierarchy
```
ExchangeAPIError (base)
├── RateLimitError - Rate limiting with retry timing
├── TradingDisabled - Trading functionality disabled
├── InsufficientPosition - Insufficient balance/position
├── OversoldException - Oversold condition
└── UnknownException - Unclassified errors
```

#### Key Features
- **Structured error information** with exchange-specific error codes
- **Rate limiting exceptions** with retry timing information
- **Trading-specific exceptions** for different failure modes
- **Mandatory propagation** - exceptions must bubble to application level

#### Usage Example

```python
from core.exceptions.exchange import BaseExchangeError, RateLimitErrorBase

# Standard API error
raise BaseExchangeError(400, "Invalid symbol", api_code=1100)

# Rate limit error with retry information
raise RateLimitError(429, "Rate limit exceeded", retry_after=60)

# Exception handling (at application level only)
try:
    await exchange_operation()
except RateLimitError as e:
    print(f"Rate limited, retry after {e.retry_after} seconds")
except ExchangeAPIError as e:
    print(f"API Error {e.status_code}: {e.message}")
```

### Configuration (`config.py`)

YAML-based configuration management system for environment-specific settings.

#### Features
- **Environment-based configuration** (development, staging, production)
- **Validation and type safety** with structured loading
- **Exchange-specific settings** with inheritance
- **Performance tuning parameters** for HFT optimization

#### Usage Example

```python
from core.config.config_manager import config

# Access configuration values
base_url = config.MEXC_BASE_URL
timeout = config.REQUEST_TIMEOUT
rate_limit = config.MEXC_RATE_LIMIT_PER_SECOND

# Exchange-specific configs
rest_config = RestConfig(
    timeout=config.REQUEST_TIMEOUT * 0.8,
    max_retries=config.MAX_RETRIES,
    require_auth=True
)
```

### Zero Allocation Buffers (`zero_alloc_buffers.py`)

Memory-optimized data structures for high-frequency trading applications.

#### Key Features
- **Object pooling** for frequently allocated structures
- **Pre-allocated buffers** to avoid GC pressure
- **Circular buffers** for time-series data
- **Memory-mapped structures** for persistence

#### Performance Benefits
- **75% reduction** in allocation overhead
- **Zero garbage collection** pauses in hot paths
- **O(1) buffer operations** with pre-allocation
- **Memory locality optimization** for cache efficiency

## Architecture Patterns

### Dependency Injection
All common components use dependency injection for testability:
```python
# Inject signature generator
client = RestClient(
    base_url=url,
    signature_generator=custom_signature_function
)

# Inject message handlers
ws_client = WebsocketClient(
    config=config,
    message_handler=custom_message_handler,
    error_handler=custom_error_handler
)
```

### Interface Compliance
Common components implement abstract interfaces for extensibility:
- RestClient implements HTTP client interface
- WebsocketClient implements streaming interface  
- Exceptions follow structured hierarchy

### Performance First
All components prioritize performance:
- **Zero-copy operations** where possible
- **Pre-compiled optimizations** (backoff delays, magic bytes)
- **Object pooling** for frequently used structures
- **Lazy evaluation** and efficient data structures

## Error Handling Strategy

### Exception Propagation
- **NEVER handle exceptions** at function level
- **Always propagate** to application/API level
- **Use structured exceptions** from the unified hierarchy
- **Include context** (error codes, retry timing, etc.)

### Logging Strategy
- **Lazy logging** to avoid performance overhead
- **Structured logging** with consistent format
- **Debug information** only when explicitly enabled
- **Performance metrics** embedded in log messages

## Testing Patterns

### Mocking and Stubbing
```python
# Mock REST client for testing
class MockRestClient(RestClient):
    async def request(self, method, endpoint, **kwargs):
        return mock_response_data

# Mock WebSocket for testing  
class MockWebsocketClient(WebsocketClient):
    async def _connect(self):
        self._ws = MockWebSocket()
```

### Performance Testing
- **Latency benchmarks** for critical paths
- **Memory profiling** for allocation patterns
- **Load testing** for concurrent operation limits
- **Integration testing** with real exchange APIs

## Integration Guidelines

### REST Client Integration
1. **Configure for exchange** - Set timeouts, retry logic, rate limits
2. **Implement signature generator** - Exchange-specific authentication
3. **Handle exchange errors** - Use custom exception handler
4. **Connection lifecycle** - Use async context manager

### WebSocket Integration
1. **Define message handlers** - Parse exchange-specific formats
2. **Implement subscription format** - Exchange-specific stream names
3. **Handle reconnection** - Manage state during disconnections
4. **Error recovery** - Graceful handling of connection issues

### Exception Integration
1. **Map exchange errors** - Convert to unified exceptions
2. **Preserve error context** - Include exchange-specific details
3. **Implement retry logic** - Based on exception type
4. **Audit trail** - Log all exceptions for analysis

## Performance Monitoring

### Metrics Collection
- **Request latency** distribution and percentiles
- **Connection pool** utilization and efficiency
- **Memory allocation** patterns and GC pressure
- **Error rates** and failure classification

### Optimization Guidelines
- **Profile hot paths** regularly for performance regressions
- **Monitor memory usage** for leak detection
- **Track connection efficiency** and pool utilization
- **Measure end-to-end latency** for trading operations