# CompositePublicExchange Interface Specification

## Overview

The `CompositePublicExchange` interface is the orchestration layer that combines REST and WebSocket interfaces to provide unified public market data operations. This is a key architectural component that eliminates code duplication across exchange implementations through the Template Method pattern.

**Key Update**: The interface now works in conjunction with the new capabilities architecture, where public exchanges focus purely on market data without any trading capabilities, supporting complete domain separation.

## Interface Purpose and Responsibilities

### Primary Purpose
- Orchestrate REST and WebSocket interfaces for market data
- Provide unified initialization and lifecycle management
- Manage orderbook updates and propagation to arbitrage layer
- Ensure HFT-compliant data flow with sub-50ms latency

### Core Responsibilities
1. **Interface Orchestration**: Coordinate REST and WebSocket clients
2. **Initialization Sequence**: Template method for consistent initialization
3. **State Management**: Maintain orderbooks, tickers, and best bid/ask
4. **Event Broadcasting**: Notify arbitrage layer of market updates
5. **Performance Tracking**: Monitor HFT compliance metrics

## Architectural Position

```
BaseCompositeExchange (parent - common functionality)
    └── CompositePublicExchange (public market data)
            ├── Uses: PublicSpotRest (REST interface)
            ├── Uses: PublicSpotWebsocket (WebSocket interface)
            └── Implementations:
                    ├── MexcPublicExchange
                    ├── GateioPublicExchange
                    └── [Other exchanges]
```

## Key Components and State

### Internal State Management

```python
# Market data state (HFT-critical)
self._orderbooks: Dict[Symbol, OrderBook] = {}
self._tickers: Dict[Symbol, Ticker] = {}
self._book_ticker: Dict[Symbol, BookTicker] = {}
self._book_ticker_update: Dict[Symbol, float] = {}

# Symbol tracking
self._active_symbols: Set[Symbol] = set()
self._symbols_info: Optional[SymbolsInfo] = None

# Client instances
self._public_rest: Optional[PublicSpotRest] = None
self._public_ws: Optional[PublicSpotWebsocket] = None

# Performance metrics
self._book_ticker_update_count = 0
self._book_ticker_latency_sum = 0.0
```

### Orderbook Update Handlers
```python
# Arbitrage layer notification
self._orderbook_update_handlers: List[
    Callable[[Symbol, OrderBook, OrderbookUpdateType], Awaitable[None]]
] = []
```

## Abstract Factory Methods

### 1. `_create_public_rest() -> PublicSpotRest`
**Purpose**: Create exchange-specific REST client
**Pattern**: Abstract Factory
**Implementation Required**: Each exchange must provide
```python
async def _create_public_rest(self) -> PublicSpotRest:
    return MexcPublicRest(
        config=self.config,
        logger=self.logger.get_child("rest.public")
    )
```

### 2. `_create_public_ws_with_handlers(handlers: PublicWebsocketHandlers) -> Optional[PublicSpotWebsocket]`
**Purpose**: Create WebSocket with injected handlers
**Pattern**: Dependency Injection
**Key Insight**: Eliminates manual handler setup
```python
async def _create_public_ws_with_handlers(
    self, 
    handlers: PublicWebsocketHandlers
) -> Optional[PublicSpotWebsocket]:
    return MexcPublicWebsocket(
        config=self.config,
        handlers=handlers,  # Injected handlers
        logger=self.logger.get_child("ws.public")
    )
```

## Template Method Pattern

### Initialization Orchestration
```python
async def initialize(self, symbols: List[Symbol] = None) -> None:
    """
    Template method orchestrating initialization
    ELIMINATES: 70%+ code duplication across exchanges
    """
    # Step 1: Create REST client
    self._public_rest = await self._create_public_rest()
    
    # Step 2: Load initial data (parallel)
    await asyncio.gather(
        self._load_symbols_info(),
        self._refresh_exchange_data()
    )
    
    # Step 3: Create WebSocket with handlers
    await self._initialize_public_websocket()
    
    # Step 4: Mark as initialized
    self._initialized = True
```

### Benefits of Template Method
1. **Consistency**: Same initialization flow for all exchanges
2. **Error Handling**: Centralized error recovery
3. **Performance**: Optimized parallel loading
4. **Maintainability**: Single place to update logic

## Handler Injection Architecture

### Creating Handler Objects
```python
def _get_websocket_handlers(self) -> PublicWebsocketHandlers:
    """Create handler object for WebSocket"""
    return PublicWebsocketHandlers(
        orderbook_handler=self._handle_orderbook,
        ticker_handler=self._handle_ticker,
        trades_handler=self._handle_trade,
        book_ticker_handler=self._handle_book_ticker
    )
```

### Handler Implementations

```python
async def _handle_orderbook(self, orderbook: OrderBook) -> None:
    """Process orderbook updates from WebSocket"""
    # Update internal state
    self._orderbooks[orderbook.symbol] = orderbook

    # Notify arbitrage layer
    await self._notify_orderbook_update(
        orderbook.symbol,
        orderbook,
        OrderbookUpdateType.DIFF
    )


async def _handle_book_ticker(self, book_ticker: BookTicker) -> None:
    """Process best bid/ask updates (HFT-critical)"""
    start_time = time.perf_counter()

    # Update state (HFT critical path)
    self._book_ticker[book_ticker.symbol] = book_ticker

    # Track performance
    latency = (time.perf_counter() - start_time) * 1000000
    if latency > 500:  # 500μs threshold
        self.logger.warning("Slow book ticker", latency_us=latency)
```

## Data Flow Patterns

### Initialization Data Flow
```
1. Exchange creates CompositePublicExchange
2. initialize() called with symbols
3. REST client created via factory
4. Symbols info loaded from REST
5. Initial orderbook snapshots loaded
6. WebSocket client created with handlers
7. WebSocket subscriptions started
8. Real-time streaming begins
```

### Orderbook Update Flow
```
1. WebSocket receives orderbook message
2. Message parsed by exchange strategy
3. Handler called with OrderBook object
4. Internal state updated
5. Arbitrage handlers notified async
6. Latency tracked for HFT monitoring
```

### Best Bid/Ask Flow (HFT-Critical)
```
1. Book ticker received (<100μs)
2. Timestamp validated (<200μs)
3. State updated (<300μs)
4. Performance tracked (<400μs)
Total: <500μs target
```

## HFT Performance Optimizations

### State Access Patterns

```python
def get_best_bid_ask(self, symbol: Symbol) -> Optional[BookTicker]:
    """Direct dictionary access - no validation overhead"""
    return self._book_ticker.get(symbol)


@property
def orderbooks(self) -> Dict[Symbol, OrderBook]:
    """Return copy for thread safety"""
    return self._orderbooks.copy()
```

### Performance Monitoring
```python
def get_book_ticker_performance_stats(self) -> Dict[str, float]:
    if self._book_ticker_update_count == 0:
        return {"count": 0, "avg_latency_us": 0.0}
    
    avg_latency = self._book_ticker_latency_sum / self._book_ticker_update_count
    return {
        "count": self._book_ticker_update_count,
        "avg_latency_us": avg_latency,
        "hft_compliant": avg_latency < 500.0
    }
```

## Public Methods

### Symbol Management
- `add_symbol(symbol: Symbol)` - Start tracking symbol
- `remove_symbol(symbol: Symbol)` - Stop tracking symbol
- `get_active_symbols() -> Set[Symbol]` - Query tracked symbols

### Handler Management
- `add_orderbook_update_handler(handler)` - Register arbitrage handler
- `remove_orderbook_update_handler(handler)` - Unregister handler

### State Queries
- `get_best_bid_ask(symbol) -> BookTicker` - Get best prices
- `get_orderbook_stats() -> Dict` - Performance metrics

## Implementation Guidelines

### Exchange Implementation Pattern
```python
class MexcPublicExchange(CompositePublicExchange):
    async def _create_public_rest(self) -> PublicSpotRest:
        """Factory: Create MEXC REST client"""
        return MexcPublicRest(self.config, self.logger)
    
    async def _create_public_ws_with_handlers(
        self, 
        handlers: PublicWebsocketHandlers
    ) -> PublicSpotWebsocket:
        """Factory: Create MEXC WebSocket with handlers"""
        return MexcPublicWebsocket(
            self.config, 
            handlers,  # Key: handlers injected
            self.logger
        )
```

### Minimal Implementation Required
```python
# Only 2 methods to implement!
# Compare to 500+ lines previously duplicated
class NewExchange(CompositePublicExchange):
    async def _create_public_rest(self):
        return NewExchangePublicRest(...)
    
    async def _create_public_ws_with_handlers(self, handlers):
        return NewExchangePublicWebsocket(..., handlers, ...)
```

## Dependencies and Relationships

### External Dependencies
- `exchanges.interfaces.rest.spot`: PublicSpotRest
- `exchanges.interfaces.ws.spot`: PublicSpotWebsocket
- `infrastructure.networking.websocket.handlers`: Handler interfaces
- `exchanges.structs.common`: Data structures

### Internal Relationships
- **Parent**: BaseCompositeExchange
- **Creates**: REST and WebSocket clients
- **Notifies**: Arbitrage layer
- **Extended By**: CompositePublicFuturesExchange

## Implementation Checklist

When implementing for a new exchange:

- [ ] Extend CompositePublicExchange
- [ ] Implement _create_public_rest()
- [ ] Implement _create_public_ws_with_handlers()
- [ ] Ensure handlers are passed to WebSocket
- [ ] Test initialization sequence
- [ ] Verify orderbook updates work
- [ ] Check best bid/ask updates
- [ ] Monitor HFT performance
- [ ] Test symbol management
- [ ] Verify arbitrage notifications

## Monitoring and Observability

### Key Metrics
- Initialization time (<100ms target)
- Orderbook update latency
- Best bid/ask processing time
- WebSocket message rate
- Handler execution time

### Health Indicators

```python
def get_orderbook_stats(self) -> Dict[str, any]:
    return {
        'exchange': self.config.name,
        'active_symbols': len(self._active_symbols),
        'cached_orderbooks': len(self._orderbooks),
        'connection_healthy': self.is_connected,
        'best_bid_ask_count': len(self._book_ticker),
        'avg_book_ticker_latency_us': self._get_avg_latency()
    }
```

## Critical Benefits

### Code Reduction
- **70%+ less code** per exchange implementation
- **Standardized flow** across all exchanges
- **Single maintenance point** for common logic

### Performance Gains
- **Parallel initialization** for faster startup
- **Optimized state management** for HFT
- **Direct handler injection** eliminates overhead

### Reliability Improvements
- **Consistent error handling** across exchanges
- **Automatic reconnection** logic
- **Standardized monitoring** metrics

## Future Enhancements

1. **Smart Orderbook Caching**: Adaptive caching strategies
2. **Differential Updates**: Bandwidth optimization
3. **Multi-Connection Support**: Load balancing
4. **Latency Routing**: Choose fastest connection
5. **Snapshot Synchronization**: Periodic state validation