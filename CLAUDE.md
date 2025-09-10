# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a high-performance CEX (Centralized Exchange) arbitrage engine designed for ultra-low-latency trading across multiple cryptocurrency exchanges. The system detects and executes arbitrage opportunities by monitoring real-time order book data from multiple exchanges simultaneously.

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

3. **Exchange Abstraction** (`src/exchanges/interface/`): Clean separation of concerns
   - PublicExchangeInterface: Market data operations (order books, trades, server time)
   - PrivateExchangeInterface: Trading operations (orders, balances, account management)
   - Abstract Factory pattern allows easy addition of new exchanges

4. **Exception Hierarchy** (`src/common/exceptions.py`): Structured error handling
   - Exchange-specific error codes and structured error information
   - Rate limiting exceptions with retry timing information
   - Trading-specific exceptions for different failure modes

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

## Development Commands

Since this is a skeleton project without dependencies installed:

```bash
# Install core dependencies
pip install uvloop msgspec fastfloat aiohttp anyio

# Run the skeleton engine
python PRD/arbitrage_engine_architecture_python_skeleton.py
```

## Implementation Guidelines

### Code Architecture Principles

1. **Type Safety First**: Always use proper type annotations and msgspec.Struct for data structures
2. **Performance by Design**: Follow PERFORMANCE_RULES.md strictly - no exceptions for library fallbacks
3. **Async Best Practices**: Use asyncio.gather() for concurrent operations, implement proper semaphore limiting
4. **Error Handling Strategy**: Use the custom exception hierarchy, never catch generic Exception
5. **Memory Efficiency**: Implement LRU cache cleanup, use deque with maxlen for metrics

### Module Organization

- `src/structs/`: Core data structures using msgspec.Struct exclusively
- `src/common/`: Shared utilities (REST client, exceptions)
- `src/exchanges/interface/`: Abstract interfaces for exchange implementations
- `PRD/`: Product requirements and architecture skeleton

### Performance Critical Paths

1. **JSON Processing**: Always use msgspec.json.Decoder() - never fallback to other libraries
2. **Data Structures**: msgspec.Struct provides 3-5x performance gain over @dataclass
3. **Network Operations**: Use connection pooling, implement aggressive timeouts
4. **Rate Limiting**: Token bucket algorithm with per-endpoint controls

## Important Design Decisions

- **Python 3.11+ required** for TaskGroup and improved asyncio performance
- **Single-threaded async architecture** to minimize locking overhead
- **msgspec-only JSON processing** for consistent performance characteristics
- **Connection pooling strategy** optimized for high-frequency trading
- **Abstract Factory pattern** for exchange implementations enables easy extensibility
- **Structured exception hierarchy** for intelligent error handling and recovery

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