# Performance Optimization Rules

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
- Use custom exception hierarchy from `src.common.exceptions`
- Pass structured error information (code, message, api_code)
- Avoid generic `Exception` catching - be specific

## Async Operations
- Use `asyncio.gather()` for concurrent operations
- Implement semaphores for connection limiting
- Use connection pooling with aiohttp TCPConnector
- Set aggressive timeouts for trading operations

## Memory Management
- Use `__slots__` for classes with many instances
- Implement LRU cache cleanup for auth signatures
- Use deque with maxlen for metrics collection
- Clear caches periodically to prevent memory leaks

## Example Violations to Avoid

```python
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
```

## Performance Targets
- JSON parsing: <1ms per message
- HTTP request latency: <50ms end-to-end
- Memory usage: O(1) per request
- Connection reuse: >95% hit rate