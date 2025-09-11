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

2. **Data Layer** (`src/structs/exchange.py`): **COMPLETE** Type-safe data structures using msgspec.Struct
   - **Zero-copy JSON parsing** with structured data validation and frozen structs for hashability
   - **Performance-optimized enums**: IntEnum for fast comparisons, comprehensive trading enums
   - **NewType aliases** for type safety without runtime overhead (ExchangeName, AssetName, OrderId)
   - **Recent Major Additions**: Fixed missing OrderSide enum (aliased to Side), added TimeInForce, KlineInterval, Ticker, Kline, TradingFee, AccountInfo
   - **Complete Trading Support**: All essential structures for order management, market data, and account operations

3. **Exchange Abstraction** (`src/exchanges/interface/`): **UNIFIED INTERFACE SYSTEM**
   - **PublicExchangeInterface**: Market data operations with integrated WebSocket streaming
   - **PrivateExchangeInterface**: Trading operations (orders, balances, account management)
   - **BaseWebSocketInterface**: Real-time data streaming with reconnection logic
   - **Advanced WebSocket Integration**: Auto-connecting orderbook streams in public interface
   - Abstract Factory pattern allows easy addition of new exchanges
   - **CRITICAL**: All implementations MUST use `src/` interfaces, NOT `raw/` legacy interfaces

4**Exception Hierarchy** (`src/common/exceptions.py`): **STANDARDIZED ERROR HANDLING**
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
- **REST Client**: MUST use `RestClient` for all HTTP operations
- **Performance Targets**: <50ms latency, >95% uptime, sub-millisecond parsing
- **Type Safety**: Comprehensive type annotations required throughout

**DEPRECATED SYSTEMS** - DO NOT USE, only for example purposes:
- `raw/common/interfaces/` - Legacy interface system with incompatible patterns
- `raw/common/entities.py` - Legacy data structures with performance issues
- `raw/common/exceptions.py` - Incompatible exception hierarchy with MEXC-specific attributes

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

## Development Setup

```bash
# Install dependencies
pip install -r requirements.txt

```

## Implementation Guidelines

### Code Architecture Principles

#### MANDATORY ARCHITECTURAL RULES - 2025 Update

**1. HFT CACHING POLICY** (CRITICAL - TRADING SAFETY)
- **RULE**: Caching trading data is UNACCEPTABLE in HFT systems. NO caching for real-time data.
- **RATIONALE**: Caching real-time trading data causes execution on stale prices, failed arbitrage, phantom liquidity, and regulatory compliance issues
- **ENFORCEMENT**: This is a CRITICAL architectural principle that must be followed without exception

**NEVER CACHE (Real-time Trading Data):**
- Orderbook snapshots (pricing data)
- Account balances (change with each trade)  
- Order status (execution state)
- Recent trades (market movement)
- Position data
- Real-time market data

**SAFE TO CACHE (Static Configuration Data):**
- Symbol mappings and SymbolInfo
- Exchange configuration
- Trading rules and precision
- Fee schedules
- Market hours
- API endpoint configurations

**2. Abstract Interface Separation** (CRITICAL - Prevents Circular Imports)
- **RULE**: Abstract interfaces MUST NOT import concrete exchange implementations
- **RATIONALE**: Prevents circular import dependencies that break the module system
- **ENFORCEMENT**: Each exchange handles its own WebSocket integration internally
- **EXAMPLE**: `PublicExchangeInterface` cannot import `MexcWebSocketPublicStream`

#### Core Development Standards

1. **KISS/YAGNI Principles** (MANDATORY)
   - **RULE**: Keep It Simple, Stupid - avoid unnecessary complexity
   - **RULE**: You Aren't Gonna Need It - don't implement features not explicitly requested
   - **ENFORCEMENT**: Ask for explicit user confirmation before adding functionality beyond task scope
   - **RATIONALE**: Prevents feature creep and maintains code clarity

2. **Exception Handling Strategy**: **MANDATORY** - strictly use unified exceptions from `src/common/exceptions.py`
   - **RULE**: NEVER use standard Exception classes - create specific exceptions in `src/common/exceptions.py`
   - **RULE**: NEVER handle exceptions at function level - propagate to higher levels for centralized handling
   - **RATIONALE**: Prevents scattered exception handling and ensures consistent error management
   - **ENFORCEMENT**: All functions must let exceptions bubble up to application/API level

3. **Interface Standards Compliance**: MUST implement unified interfaces from `src/exchanges/interface/`

4. **Type Safety First**: Always use proper type annotations and msgspec.Struct for data structures

5. **Async Best Practices**: Use asyncio.gather() for concurrent operations, implement proper semaphore limiting

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
from src.common.rest import RestClient, RestConfig


```

### Module Organization

- `src/structs/`: **UNIFIED** core data structures using msgspec.Struct exclusively
- `src/common/`: **STANDARDIZED** shared utilities (REST client, unified exceptions)
- `src/exchanges/interface/`: **MANDATORY** abstract interfaces for all exchange implementations
  - `public_exchange.py`: Public market data interface (REQUIRED)
  - `private_exchange.py`: Private trading interface (REQUIRED)
  - `base_ws.py`: WebSocket base interface (REQUIRED for real-time data)
- `src/exchanges/{exchange_name}/`: Individual exchange implementations
  - `{exchange_name}_public_.py`: PublicExchangeInterface implementation
  - `{exchange_name}_private.py`: PrivateExchangeInterface implementation
  - `{exchange_name}_ws_public.py`: Public WebSocket implementation
  - `{exchange_name}_ws_private.py`: Private WebSocket implementation
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

