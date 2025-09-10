# Performance Optimization Rules

## Interface Standards Compliance

- **ALWAYS** implement `PublicExchangeInterface` and `PrivateExchangeInterface` from `src/exchanges/interface/`
- **NEVER** use legacy interfaces from `raw/common/interfaces/` - they are deprecated and performance-degraded
- **ALWAYS** use unified data structures from `src/structs/exchange.py`
- **NEVER** use legacy entities from `raw/common/entities.py` - they lack performance optimizations
- **ALWAYS** use unified exception hierarchy from `src/common/exceptions.py`
- **NEVER** use legacy exceptions from `raw/common/exceptions.py` - they are MEXC-specific and incompatible

## JSON Processing
- **ALWAYS** use `msgspec` for JSON serialization/deserialization
- **NEVER** use try/except blocks for JSON library fallbacks - use msgspec only
- Use `msgspec.Struct` for all data classes instead of `@dataclass`
- Use `msgspec.json.encode` and `msgspec.json.Decoder()` consistently

## Data Structures
- Use `msgspec.Struct` instead of `dataclasses.dataclass` for 3-5x performance gain
- Use `IntEnum` for status codes to enable fast integer comparisons
- Use `NewType` for type aliases without runtime overhead
- Prefer `list[T]` over `List[T]` (Python 3.9+ syntax)

## Imports
- Import only what you need - avoid wildcard imports
- Use direct imports: `from msgspec import Struct` not `import msgspec`
- **NEVER** use conditional imports with try/except - choose the fastest library and use it exclusively

## Error Handling
- **ALWAYS** use unified exception hierarchy from `src/common/exceptions.py`
- **NEVER** use legacy exceptions from `raw/common/exceptions.py` 
- **ALWAYS** implement exchange-specific error mapping to standardized exceptions
- **MANDATORY**: Let exceptions bubble to application level - NO try-catch anti-patterns at method level
- **ALWAYS** use `traceback.print_exc()` in application-level error handlers for full debugging context
- Pass structured error information (code, message, api_code) consistently
- Avoid generic `Exception` catching - use specific exception types
- **MUST** implement retry logic for `RateLimitError` with exponential backoff
- Only catch exceptions at method level when specific recovery logic exists

## Async Operations
- **ALWAYS** use `HighPerformanceRestClient` from `src/common/rest.py` for all HTTP operations
- **NEVER** create custom HTTP clients - use the standardized high-performance client
- Use `asyncio.gather()` for concurrent operations with proper error handling
- Implement semaphores for connection limiting (handled by standardized client)
- Use connection pooling with aiohttp TCPConnector (pre-configured in standard client)
- Set aggressive timeouts for trading operations (<50ms target latency)

## Memory Management
- Use `__slots__` for classes with many instances
- Implement LRU cache cleanup for auth signatures
- Use deque with maxlen for metrics collection
- Clear caches periodically to prevent memory leaks

## Example Violations to Avoid

```python
# BAD: Using legacy interfaces
from raw.common.interfaces.base_exchange import BaseSyncExchange
from raw.common.entities import Order, SymbolInfo

# GOOD: Use unified interfaces
from src.exchanges.interface.public_exchange import PublicExchangeInterface
from src.structs.exchange import Order, SymbolInfo

# BAD: Using legacy exceptions
from raw.common.exceptions import ExchangeAPIError  # Has mexc_code attribute

# GOOD: Use unified exceptions  
from src.common.exceptions import ExchangeAPIError  # Has api_code attribute

# BAD: Try/except for library selection
try:
    import orjson
    JSON_LIB = orjson
except ImportError:
    import json
    JSON_LIB = json

# GOOD: Use msgspec directly
import msgspec
DECODER = msgspec.json.Decoder()

# BAD: Using dataclass
@dataclass
class Order:
    price: float
    size: float

# GOOD: Using msgspec.Struct
class Order(msgspec.Struct):
    price: float
    size: float

# BAD: Custom HTTP client
async with aiohttp.ClientSession() as session:
    async with session.get(url) as response:
        data = await response.json()

# GOOD: Use standardized client
from src.common.rest import HighPerformanceRestClient, RequestConfig

async with HighPerformanceRestClient(base_url) as client:
    data = await client.get(endpoint, config=RequestConfig())

# BAD: Try-catch anti-pattern at method level
async def ping(self) -> bool:
    try:
        await self.client.get(self.ENDPOINTS['ping'])
        return True
    except Exception as e:
        self.logger.warning(f"Ping failed: {e}")
        return False

# GOOD: Let exceptions bubble to application level
async def ping(self) -> bool:
    await self.client.get(self.ENDPOINTS['ping'])
    return True

# Application level with proper traceback
async def test_connectivity():
    try:
        await exchange.ping()
    except Exception as e:
        logger.error(f"Ping failed: {e}")
        traceback.print_exc()
```

## Performance Targets
- **Interface compliance**: 100% adherence to unified interface standards
- JSON parsing: <1ms per message (msgspec requirement)
- HTTP request latency: <50ms end-to-end (HighPerformanceRestClient requirement)
- Memory usage: O(1) per request (msgspec.Struct requirement)
- Connection reuse: >95% hit rate (standardized client requirement)
- Exchange uptime: >95% WebSocket connection stability
- Error handling: <10ms exception processing overhead

## Compliance Verification
- Run `scripts/verify_interface_compliance.py` for all exchange implementations
- Use `pytest tests/performance/` for latency benchmarks
- Monitor production metrics for performance degradation
- All new exchanges MUST pass interface compliance tests before production deployment