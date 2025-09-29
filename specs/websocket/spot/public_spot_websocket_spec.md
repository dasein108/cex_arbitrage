# PublicSpotWebsocket Interface Specification

## Overview

The `PublicSpotWebsocket` interface provides real-time market data streaming for spot markets via WebSocket connections. This interface uses a strategy-driven architecture with handler objects for clean separation of concerns and efficient message routing.

## Interface Purpose and Responsibilities

### Primary Purpose
- Stream real-time market data with sub-millisecond latency
- Manage WebSocket lifecycle and reconnections
- Route parsed messages to appropriate handlers
- Maintain active symbol subscriptions

### Core Responsibilities
1. **Connection Management**: Initialize, maintain, and close WebSocket connections
2. **Subscription Control**: Add/remove symbol subscriptions dynamically
3. **Message Routing**: Parse and route messages to handler functions
4. **State Management**: Track active symbols and connection state
5. **Performance Monitoring**: Track latency and throughput metrics

## Architectural Position

```
BaseWebsocketInterface (optional parent)
    └── PublicSpotWebsocket (strategy-driven)
            ├── Uses: WebSocketManager V2 (infrastructure)
            ├── Uses: PublicWebsocketHandlers (event handlers)
            └── Implementations:
                    ├── MexcPublicWebsocket
                    ├── GateioPublicWebsocket
                    └── [Other exchanges]
```

## Handler Architecture

### PublicWebsocketHandlers Structure
```python
class PublicWebsocketHandlers:
    orderbook_handler: Callable[[OrderBook], Awaitable[None]]
    ticker_handler: Callable[[Ticker], Awaitable[None]]
    trades_handler: Callable[[Trade], Awaitable[None]]
    book_ticker_handler: Callable[[BookTicker], Awaitable[None]]
```

### Handler Injection Pattern

```python
# Constructor injection for clean separation
def __init__(
        self,
        config: ExchangeConfig,
        handlers: PublicWebsocketHandlers,  # Injected handlers
        logger: HFTLogger,
        state_change_handler: Optional[Callable] = None
):
    self.handlers = handlers  # Store for message routing
    # Create WebSocket manager with message handler
    self._ws_manager = create_websocket_manager(
        exchange_config=config,
        is_private=False,
        message_handler=self._handle_message
    )
```

## Key Methods

### 1. `initialize(symbols: List[Symbol], channels: List[PublicWebsocketChannelType]) -> None`
**Purpose**: Initialize WebSocket and subscribe to symbols
**Parameters**:
- `symbols`: Initial symbols to subscribe
- `channels`: Channel types (orderbook, trades, ticker, book_ticker)
**Flow**:
```
1. Initialize WebSocket manager
2. Subscribe to specified channels
3. Begin message streaming
```

### 2. `subscribe(symbols: List[Symbol]) -> None`
**Purpose**: Add symbols to active subscriptions
**HFT Requirements**: 
- Must complete within 100ms
- Non-blocking operation
**State Changes**:
- Updates `_active_symbols` set
- Sends subscription messages

### 3. `unsubscribe(symbols: List[Symbol]) -> None`
**Purpose**: Remove symbols from subscriptions
**State Changes**:
- Removes from `_active_symbols`
- Sends unsubscribe messages

### 4. `get_active_symbols() -> Set[Symbol]`
**Purpose**: Query currently subscribed symbols
**Returns**: Set of active Symbol objects

### 5. `close() -> None`
**Purpose**: Gracefully close WebSocket connection
**Cleanup**:
- Close WebSocket manager
- Clear active symbols
- Log closure

### 6. `is_connected() -> bool`
**Purpose**: Check connection status
**Returns**: True if WebSocket connected

### 7. `get_performance_metrics() -> Dict[str, any]`
**Purpose**: Retrieve performance statistics
**Metrics**:
- Message processing latency
- Messages per second
- Connection uptime
- Reconnection count

## Message Routing Implementation

### Internal Message Handler

```python
async def _handle_parsed_message(self, message: ParsedMessage) -> None:
    """Route parsed messages to appropriate handlers"""
    try:
        if message.message_type == MessageType.ORDERBOOK:
            # Convert to ParsedOrderbookUpdate format
            orderbook_update = ParsedOrderbookUpdate(
                orderbook=message.data,
                symbol=message.symbol
            )
            await self.handlers.handle_orderbook_diff(orderbook_update)

        elif message.message_type == MessageType.EXECUTION:
            # Handle single or multiple trades
            if isinstance(message.data, list):
                for trade in message.data:
                    await self.handlers.handle_trade(trade)
            else:
                await self.handlers.handle_trade(message.data)

        elif message.message_type == MessageType.BOOK_TICKER:
            await self.handlers.handle_book_ticker(message.data)

        elif message.message_type == MessageType.SUBSCRIPTION_CONFIRM:
            self.logger.debug(f"Subscription confirmed: {message.channel}")

        elif message.message_type == MessageType.ERROR:
            self.logger.error(f"WebSocket error: {message.raw_data}")

    except Exception as e:
        self.logger.error(f"Error handling message: {e}")
```

## Data Flow Patterns

### Initialization Flow
```
1. PublicSpotWebsocket created with handlers
2. initialize() called with symbols
3. WebSocketManager V2 created
4. Connection established
5. Subscriptions sent
6. Message streaming begins
```

### Message Processing Flow
```
1. Raw message received by WebSocketManager
2. Message parsed by exchange-specific strategy
3. ParsedMessage created with type and data
4. _handle_parsed_message routes to handler
5. Handler processes data (e.g., updates orderbook)
6. Latency tracked for HFT monitoring
```

### Subscription Management Flow
```
1. subscribe() called with new symbols
2. WebSocketManager sends subscription request
3. Symbols added to _active_symbols
4. Confirmation message received
5. Data streaming begins for new symbols
```

## HFT Performance Requirements

### Latency Targets
- **Message Processing**: <500μs per message
- **Handler Execution**: <1ms including routing
- **Subscription Changes**: <100ms

### Throughput Requirements
- Handle 10,000+ messages/second
- Support 100+ concurrent symbols
- Zero-copy message parsing (msgspec)

### Connection Stability
- Automatic reconnection within 1 second
- Message buffering during reconnection
- State recovery after reconnection

## State Management

### Internal State
```python
# Symbol tracking
self._active_symbols: Set[Symbol] = set()

# Performance tracking
self._book_ticker_update_count = 0
self._book_ticker_latency_sum = 0.0

# Connection state (delegated to manager)
self._ws_manager  # Handles connection state
```

### State Change Handling
```python
async def _handle_state_change(self, state: ConnectionState) -> None:
    """Handle connection state changes"""
    self.logger.info(f"State changed: {state.name}")
    
    if self._state_change_handler:
        await self._state_change_handler(state)
    
    if state == ConnectionState.RECONNECTED:
        # Resubscribe to all active symbols
        await self.subscribe(list(self._active_symbols))
```

## Implementation Guidelines

### 1. Exchange Implementation Pattern
```python
class MexcPublicWebsocket(PublicSpotWebsocket):
    def __init__(self, config, handlers, logger):
        # Exchange-specific configuration
        config.websocket_url = "wss://ws.mexc.com"
        super().__init__(config, handlers, logger)
    
    def _create_subscribe_message(self, symbols):
        # Exchange-specific subscription format
        return {
            "method": "SUBSCRIPTION",
            "params": [f"{s.lower()}@depth" for s in symbols]
        }
```

### 2. Handler Implementation Pattern
```python
# In CompositePublicExchange
async def _handle_orderbook(self, orderbook: OrderBook) -> None:
    """Handler for orderbook updates"""
    # Update internal state
    self._orderbooks[orderbook.symbol] = orderbook
    
    # Track performance
    self._track_operation("orderbook_update")
    
    # Notify arbitrage layer
    await self._notify_orderbook_update(
        orderbook.symbol, 
        orderbook, 
        OrderbookUpdateType.DIFF
    )
```

### 3. Error Recovery Pattern
```python
async def _handle_parsed_message(self, message):
    try:
        # Message routing logic
        ...
    except Exception as e:
        self.logger.error(f"Handler error: {e}")
        
        # Don't crash on handler errors
        if message.symbol:
            # Mark symbol for resubscription
            self._pending_resubscribe.add(message.symbol)
```

## Dependencies and Relationships

### External Dependencies
- `infrastructure.networking.websocket`: WebSocketManager V2
- `infrastructure.networking.websocket.handlers`: Handler interfaces
- `exchanges.structs.common`: Data structures
- `config.structs`: ExchangeConfig

### Internal Relationships
- **Used By**: CompositePublicExchange
- **Uses**: WebSocketManager V2 (infrastructure)
- **Handlers From**: CompositePublicExchange
- **Siblings**: PublicFuturesWebsocket

## Implementation Checklist

When implementing PublicSpotWebsocket for an exchange:

- [ ] Create exchange-specific class extending PublicSpotWebsocket
- [ ] Configure WebSocket URL in constructor
- [ ] Implement subscription message format (if needed)
- [ ] Create exchange-specific parsing strategy
- [ ] Handle exchange-specific message types
- [ ] Add reconnection logic if custom
- [ ] Test with all channel types
- [ ] Verify latency compliance
- [ ] Add performance logging
- [ ] Document exchange quirks

## Monitoring and Observability

### Key Metrics
- Messages processed per second
- Average processing latency
- Handler execution time
- Reconnection frequency
- Subscription success rate

### Performance Tracking
```python
def get_performance_metrics(self) -> Dict[str, any]:
    return {
        "messages_processed": self._message_count,
        "avg_latency_us": self._total_latency / self._message_count,
        "active_symbols": len(self._active_symbols),
        "uptime_seconds": time.time() - self._start_time,
        "reconnections": self._reconnection_count
    }
```

## Future Enhancements

1. **Message Compression**: Support for compressed streams
2. **Adaptive Subscriptions**: Dynamic subscription based on activity
3. **Priority Queuing**: Prioritize critical symbols
4. **Failover Support**: Multiple WebSocket endpoints
5. **Message Recording**: Record/replay for testing