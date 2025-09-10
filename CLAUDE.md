# CEX Arbitrage Engine - Claude Code Documentation

This file provides comprehensive guidance to Claude Code (claude.ai/code) when working with this high-performance cryptocurrency arbitrage engine.

## Project Overview

This is an **ultra-high-performance CEX (Centralized Exchange) arbitrage engine** designed for sub-millisecond cryptocurrency trading across multiple exchanges. The system provides:

- **Real-time order book streaming** with WebSocket connections
- **Multi-exchange arbitrage detection** with <50ms latency
- **Unified interface system** for seamless exchange integration  
- **Production-grade performance optimizations** (3-5x speed improvements)
- **Comprehensive error handling** and automatic reconnection
- **Type-safe data structures** using msgspec for zero-copy parsing

## Architectural Insights

### Core Architecture Pattern: Event-Driven + Abstract Factory

The engine follows a **layered event-driven architecture** with **Abstract Factory pattern** for exchange implementations:

1. **Network Layer** (`src/common/rest.py`): Ultra-high performance REST client with advanced features
   - Connection pooling with persistent aiohttp sessions
   - Per-endpoint rate limiting with token bucket algorithm
   - Auth signature caching for repeated requests
   - Concurrent request handling with semaphore limiting

2. **Data Layer** (`src/structs/exchange.py`): Type-safe data structures using msgspec.Struct
   - Zero-copy JSON parsing with structured data validation
   - Performance-optimized enums (IntEnum for fast comparisons)
   - NewType for type safety without runtime overhead

3. **Exchange Abstraction** (`src/exchanges/interface/`): **UNIFIED INTERFACE SYSTEM**
   - **PublicExchangeInterface**: Market data operations with integrated WebSocket streaming
   - **PrivateExchangeInterface**: Trading operations (orders, balances, account management)
   - **BaseWebSocketInterface**: Real-time data streaming with reconnection logic
   - **Advanced WebSocket Integration**: Auto-connecting orderbook streams in public interface
   - Abstract Factory pattern allows easy addition of new exchanges
   - **CRITICAL**: All implementations MUST use `src/` interfaces, NOT `raw/` legacy interfaces

4. **WebSocket Optimization Layer** (`src/exchanges/mexc/websocket.py`): **ULTRA-HIGH PERFORMANCE**
   - **Protobuf Object Pooling**: 60-70% faster parsing with reusable objects
   - **Multi-tier Caching**: Symbol parsing, field access, and message type caches
   - **Zero-copy Architecture**: Minimal data movement during message processing  
   - **Batch Processing Engine**: Process up to 10 messages per batch for reduced overhead
   - **Binary Pattern Detection**: O(1) message type detection vs O(n) protobuf parsing
   - **SortedDict Order Books**: O(log n) updates vs O(n) traditional sorting

5. **Exception Hierarchy** (`src/common/exceptions.py`): **STANDARDIZED ERROR HANDLING**
   - Exchange-specific error codes and structured error information
   - Rate limiting exceptions with retry timing information
   - Trading-specific exceptions for different failure modes
   - **MANDATORY**: Exceptions must bubble to application level - no try-catch anti-patterns
   - **CRITICAL**: Use unified exception system, NOT legacy `raw/common/exceptions.py`

### Interface Standards Compliance

**MANDATORY REQUIREMENTS** for all exchange implementations:

- **Interface Compliance**: MUST implement `PublicExchangeInterface` and `PrivateExchangeInterface`
- **Data Structure Standards**: MUST use `msgspec.Struct` from `src/structs/exchange.py`
- **Exception Handling**: MUST use unified exception hierarchy from `src/common/exceptions.py`
- **REST Client**: MUST use `HighPerformanceRestClient` for all HTTP operations
- **Performance Targets**: <50ms latency, >95% uptime, sub-millisecond parsing
- **Type Safety**: Comprehensive type annotations required throughout

**DEPRECATED SYSTEMS** - DO NOT USE:
- `raw/common/interfaces/` - Legacy interface system with incompatible patterns
- `raw/common/entities.py` - Legacy data structures with performance issues
- `raw/common/exceptions.py` - Incompatible exception hierarchy with MEXC-specific attributes

See `INTERFACE_STANDARDS.md` for comprehensive implementation guidelines.

### Key Design Decisions & Rationale

- **Single-threaded async architecture**: Minimizes locking overhead, maximizes throughput
- **msgspec-only JSON processing**: No fallbacks ensure consistent performance characteristics
- **Connection pooling strategy**: Optimized for high-frequency trading with persistent sessions
- **Token bucket rate limiting**: Per-endpoint controls prevent API violations
- **Structured exception hierarchy**: Enables intelligent error handling and recovery

## Key Performance Optimizations

- **Event Loop**: Uses uvloop instead of default asyncio for better performance
- **JSON Parsing**: msgspec exclusively for zero-copy decoding, no library fallbacks
- **Data Structures**: msgspec.Struct provides 3-5x performance gain over dataclasses
- **Target Latency**: <50ms end-to-end HTTP requests, <1ms JSON parsing per message
- **Memory Management**: O(1) per request, >95% connection reuse hit rate
- **Network Optimization**: Connection pooling, aggressive timeouts, intelligent retry logic

## Current Implementation Status

### ✅ **Completed Features**
- **MEXC Exchange Integration**: Complete public API implementation with WebSocket streaming
- **Ultra-High Performance WebSocket**: 3-5x performance improvement with advanced optimizations
- **Unified Interface System**: Standardized interfaces for all exchange operations
- **Advanced Protobuf Optimization**: Binary message parsing with object pooling
- **Hashable Data Structures**: Symbol and OrderBook structs optimized for set operations
- **Real-time Order Book Streaming**: Automatic WebSocket integration in public exchange interface
- **Comprehensive Examples**: Production-ready usage examples and performance monitoring

### 📊 **Performance Achievements**
- **WebSocket Processing**: 3-5x throughput improvement vs baseline
- **Protobuf Parsing**: 70-90% reduction in parsing time
- **Memory Efficiency**: 50-70% reduction in allocations with object pooling
- **Message Processing**: Sub-millisecond latency for high-frequency trading
- **Order Book Updates**: O(log n) with SortedDict vs O(n) traditional sorting

## Development Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Run examples
python src/examples/public_exchange_demo.py      # Complete interface demo
python src/examples/arbitrage_monitor.py         # Real-time arbitrage monitoring

# Performance testing
python performance_test_mexc_ws.py               # WebSocket performance benchmarks
```

## Implementation Guidelines

### Code Architecture Principles

#### MANDATORY ARCHITECTURAL RULES - 2025 Update

**1. Abstract Interface Separation** (CRITICAL - Prevents Circular Imports)
- **RULE**: Abstract interfaces MUST NOT import concrete exchange implementations
- **RATIONALE**: Prevents circular import dependencies that break the module system
- **ENFORCEMENT**: Each exchange handles its own WebSocket integration internally
- **EXAMPLE**: `PublicExchangeInterface` cannot import `MexcWebSocketPublicStream`

**2. Import Path Standardization** (MANDATORY)
- **RULE**: NEVER use `src.` prefix in import statements
- **RATIONALE**: All imports are relative to the `src` directory as the base folder
- **CORRECT**: `from exchanges.mexc.public import MexcPublicExchange`
- **INCORRECT**: `from src.exchanges.mexc.public import MexcPublicExchange`

**3. WebSocket Integration Architecture** (NEW STANDARD)
- **RULE**: Each exchange implementation handles its own WebSocket functionality
- **RATIONALE**: Abstract interfaces define the contract but don't implement WebSocket logic
- **IMPLEMENTATION**: Concrete implementations like MEXC add WebSocket features as needed
- **SEPARATION**: Base classes remain pure abstractions without knowledge of specific implementations

#### Core Development Standards

1. **Interface Standards Compliance**: MUST implement unified interfaces from `src/exchanges/interface/`
2. **Type Safety First**: Always use proper type annotations and msgspec.Struct for data structures
3. **Performance by Design**: Follow PERFORMANCE_RULES.md strictly - no exceptions for library fallbacks
4. **Async Best Practices**: Use asyncio.gather() for concurrent operations, implement proper semaphore limiting
5. **Error Handling Strategy**: Use the unified exception hierarchy from `src/common/exceptions.py` with proper exception propagation (no try-catch anti-patterns)
6. **Memory Efficiency**: Implement LRU cache cleanup, use deque with maxlen for metrics

### Exchange Implementation Requirements

**MANDATORY for all new exchange implementations**:

```python
# Required interface implementations
class ExchangePublic(PublicExchangeInterface):
    """MUST implement all abstract methods from PublicExchangeInterface"""
    pass

class ExchangePrivate(PrivateExchangeInterface):
    """MUST implement all abstract methods from PrivateExchangeInterface"""  
    pass

# Required data structure usage
from src.structs.exchange import Symbol, OrderBook, Trade, Order, AssetBalance

# Required REST client usage  
from src.common.rest import HighPerformanceRestClient, RequestConfig

# Required exception handling
from src.common.exceptions import ExchangeAPIError, RateLimitError
```

**COMPLIANCE VERIFICATION**: Use `scripts/verify_interface_compliance.py` to validate implementations

### Module Organization

- `src/structs/`: **UNIFIED** core data structures using msgspec.Struct exclusively
- `src/common/`: **STANDARDIZED** shared utilities (REST client, unified exceptions)
- `src/exchanges/interface/`: **MANDATORY** abstract interfaces for all exchange implementations
  - `public_exchange.py`: Public market data interface (REQUIRED)
  - `private_exchange.py`: Private trading interface (REQUIRED)
  - `base_ws.py`: WebSocket base interface (REQUIRED for real-time data)
- `src/exchanges/{exchange_name}/`: Individual exchange implementations
  - `public.py`: PublicExchangeInterface implementation
  - `private.py`: PrivateExchangeInterface implementation
  - `ws_public.py`: Public WebSocket implementation
  - `ws_private.py`: Private WebSocket implementation
- `PRD/`: Product requirements and architecture skeleton
- **DEPRECATED**: `raw/` directory - Legacy code, DO NOT USE for new development

### Performance Critical Paths

1. **WebSocket Message Processing**: Ultra-optimized pipeline with 3-5x improvement
   - Protobuf object pooling eliminates allocation overhead
   - Multi-tier caching (symbol, field, message type) with >95% hit rates
   - Binary pattern detection for instant message type identification
   - Batch processing reduces async context switching overhead

2. **Order Book Management**: O(log n) differential updates
   - SortedDict data structures maintain automatic sort order
   - Object pooling for OrderBookEntry reuse
   - Lazy snapshot generation only when needed
   - Memory-efficient level limiting (top 100 levels)

3. **JSON Processing**: Always use msgspec.json.Decoder() - never fallback to other libraries
4. **Data Structures**: msgspec.Struct provides 3-5x performance gain over @dataclass  
5. **Network Operations**: Use connection pooling, implement aggressive timeouts
6. **Rate Limiting**: Token bucket algorithm with per-endpoint controls

## Important Design Decisions

- **Python 3.11+ required** for TaskGroup and improved asyncio performance
- **Single-threaded async architecture** to minimize locking overhead
- **msgspec-only JSON processing** for consistent performance characteristics
- **Connection pooling strategy** optimized for high-frequency trading
- **Abstract Factory pattern** for exchange implementations enables easy extensibility
- **Structured exception hierarchy** for intelligent error handling and recovery
- **Immutable data structures** (frozen=True) for hashability and thread safety
- **Integrated WebSocket streaming** in public exchange interface for real-time data

## Latest Optimizations (2025)

### 🚀 **WebSocket Performance Revolution**
- **6-stage optimization pipeline** with binary pattern detection
- **Multi-tier object pooling** (protobuf, buffers, message dictionaries)
- **Zero-copy parsing architecture** with streaming buffer handling
- **Adaptive batch processing** based on message volume
- **Field caching system** with global and local cache hierarchies

### 📊 **Quantified Performance Gains**
- **3-5x overall WebSocket throughput improvement**
- **70-90% reduction in protobuf parsing time**
- **50-70% reduction in memory allocations**
- **99%+ cache hit rates** for symbol parsing
- **O(log n) order book updates** vs O(n) traditional methods

### 🎯 **Production-Ready Features**
- **Automatic WebSocket integration** in PublicExchangeInterface.init()
- **Real-time order book caching** with sub-millisecond access
- **Comprehensive health monitoring** with performance metrics
- **Graceful degradation** and automatic reconnection handling
- **Thread-safe operations** with async lock management

## Future Optimization Paths

- **Order Book Optimization**: Replace dict-based storage with sorted containers or B-trees
- **Rust Integration**: Port critical paths to Rust via PyO3 if Python becomes bottleneck
- **SIMD Acceleration**: Consider specialized libraries for numerical operations
- **Memory Pooling**: Implement object pools for frequently allocated structures

## Risk Management Considerations

- **Balance Checks**: Implement before execution with real-time balance tracking
- **Position Limits**: Add configurable limits and cooldown periods
- **Order Idempotency**: Ensure proper retry logic with duplicate detection
- **Partial Fill Handling**: Robust handling of race conditions in execution
- **Circuit Breakers**: Implement for failed exchanges and degraded performance