# WebSocket Book Ticker Implementation Plan

**Objective**: Add WebSocket book ticker (best bid/ask) channels to both MEXC and Gate.io exchanges for real-time price monitoring.

## Table of Contents

1. [Architecture Analysis](#architecture-analysis)
2. [API Specifications](#api-specifications)
3. [Implementation Steps](#implementation-steps)
4. [Technical Details](#technical-details)
5. [Integration Points](#integration-points)
6. [Testing Strategy](#testing-strategy)
7. [Performance Requirements](#performance-requirements)

## Architecture Analysis

### Current WebSocket Infrastructure

✅ **Existing Components**:
- `src/core/transport/websocket/strategies/subscription.py` - Abstract subscription strategy
- `src/cex/mexc/ws/strategies/public/subscription.py` - MEXC subscription implementation
- `src/cex/gateio/ws/strategies/public/subscription.py` - Gate.io subscription implementation
- `src/cex/mexc/ws/protobuf_parser.py` - MEXC protobuf parsing utilities
- Protobuf structs: `PublicAggreBookTickerV3Api_pb2.py` already exists

✅ **Current Channel Support**:
- **MEXC**: Depth orderbook, Trade deals
- **Gate.io**: Orderbook updates, Trade data

## API Specifications

### MEXC Book Ticker

**Channel Format**: `spot@public.aggre.book_ticker.v3.api.pb@10ms@{SYMBOL}`

**Subscription Method**:
```json
{
  "method": "SUBSCRIPTION",
  "params": ["spot@public.aggre.book_ticker.v3.api.pb@10ms@BTCUSDT"]
}
```

**Protobuf Response Structure**:
```protobuf
message PublicAggreBookTickerV3Api {
    string bidPrice = 1;      // Best bid price
    string bidQuantity = 2;   // Best bid quantity
    string askPrice = 3;      // Best ask price
    string askQuantity = 4;   // Best ask quantity
}
```

**Message Wrapper**: Uses `PushDataV3ApiWrapper` with `publicAggreBookTicker` field

### Gate.io Book Ticker

**Channel**: `spot.book_ticker`

**Subscription Method**:
```json
{
  "time": 1606293275,
  "channel": "spot.book_ticker", 
  "event": "subscribe",
  "payload": ["BTC_USDT"]
}
```

**JSON Response Structure**:
```json
{
  "result": {
    "t": 1606293275123,    // timestamp (ms)
    "u": 48733182,         // update_id
    "s": "BTC_USDT",       // symbol
    "b": "19177.79",       // bid_price
    "B": "0.0003341504",   // bid_quantity
    "a": "19179.38",       // ask_price
    "A": "0.09"            // ask_quantity
  }
}
```

## Implementation Steps

### Step 1: Add BookTicker Struct to Common Structs

**File**: `src/structs/common.py`

```python
class BookTicker(Struct):
    """Best bid/ask price information (book ticker)"""
    symbol: Symbol
    bid_price: float
    bid_quantity: float
    ask_price: float
    ask_quantity: float
    timestamp: int
    update_id: Optional[int] = None  # Gate.io provides this, MEXC doesn't
```

### Step 2: Update MEXC Subscription Strategy

**File**: `src/cex/mexc/ws/strategies/public/subscription.py`

**Changes Required**:

1. **Update `_get_channels_for_symbol()`**:
```python
def _get_channels_for_symbol(self, symbol: Symbol) -> List[str]:
    """Generate channel list for a symbol (single source of truth)."""
    symbol_str = self.symbol_mapper.to_pair(symbol).upper()

    return [
        f"spot@public.aggre.depth.v3.api.pb@10ms@{symbol_str}",      # Depth orderbook
        f"spot@public.aggre.deals.v3.api.pb@10ms@{symbol_str}",     # Trade deals
        f"spot@public.aggre.book_ticker.v3.api.pb@10ms@{symbol_str}" # Book ticker (NEW)
    ]
```

2. **Update `get_symbol_from_channel()` and `extract_symbol_from_channel()`**:
   - Add support for book ticker channel pattern recognition

### Step 3: Update Gate.io Subscription Strategy

**File**: `src/cex/gateio/ws/strategies/public/subscription.py`

**Changes Required**:

1. **Update `_get_channels_for_symbol()`**:
```python
def _get_channels_for_symbol(self, symbol: Symbol) -> List[str]:
    """Generate channel list for a symbol (single source of truth)."""
    symbol_str = self.symbol_mapper.to_pair(symbol).upper()

    return [
        f"spot.order_book_update.{symbol_str}",  # Orderbook updates
        f"spot.trades.{symbol_str}",             # Trade data
        f"spot.book_ticker.{symbol_str}"         # Book ticker (NEW)
    ]
```

2. **Update subscription message format**:
   - Gate.io uses different format for book ticker subscription
   - Need to handle the event-based subscription model

### Step 4: Create Message Parser Enhancements

#### MEXC Protobuf Parser Enhancement

**File**: `src/cex/mexc/ws/strategies/public/message_parser.py`

**Add BookTicker Parsing**:
```python
async def _handle_book_ticker_update(self, book_ticker_data) -> None:
    """Handle MEXC protobuf book ticker message."""
    try:
        # Extract symbol from protobuf channel
        symbol = self._extract_symbol_from_protobuf_channel(book_ticker_data)
        
        # Parse protobuf book ticker data
        book_ticker = BookTicker(
            symbol=symbol,
            bid_price=float(book_ticker_data.bidPrice),
            bid_quantity=float(book_ticker_data.bidQuantity),
            ask_price=float(book_ticker_data.askPrice),
            ask_quantity=float(book_ticker_data.askQuantity),
            timestamp=int(time.time() * 1000),  # MEXC doesn't provide timestamp
            update_id=None  # MEXC doesn't provide update_id
        )
        
        # Notify subscribers
        await self._notify_book_ticker_update(symbol, book_ticker)
        
    except Exception as e:
        self.logger.error(f"Failed to parse MEXC book ticker: {e}")
```

#### Gate.io JSON Parser Enhancement

**File**: `src/cex/gateio/ws/strategies/public/message_parser.py`

**Add BookTicker Parsing**:
```python
async def _handle_book_ticker_update(self, message: Dict[str, Any]) -> None:
    """Handle Gate.io JSON book ticker message."""
    try:
        result = message.get('result', {})
        
        # Parse symbol
        symbol_str = result.get('s', '')
        symbol = self.symbol_mapper.to_symbol(symbol_str)
        
        # Parse book ticker data
        book_ticker = BookTicker(
            symbol=symbol,
            bid_price=float(result.get('b', 0)),
            bid_quantity=float(result.get('B', 0)),
            ask_price=float(result.get('a', 0)),
            ask_quantity=float(result.get('A', 0)),
            timestamp=int(result.get('t', 0)),
            update_id=int(result.get('u', 0))
        )
        
        # Notify subscribers
        await self._notify_book_ticker_update(symbol, book_ticker)
        
    except Exception as e:
        self.logger.error(f"Failed to parse Gate.io book ticker: {e}")
```

### Step 5: Update WebSocket Base Classes

**Files**: 
- `src/cex/mexc/ws/mexc_ws_public.py`
- `src/cex/gateio/ws/gateio_ws_public.py`

**Add BookTicker Event Handling**:
```python
async def _notify_book_ticker_update(self, symbol: Symbol, book_ticker: BookTicker) -> None:
    """Notify subscribers of book ticker update."""
    # Add to event system or callback mechanism
    if self.on_book_ticker_update:
        await self.on_book_ticker_update(symbol, book_ticker)
```

### Step 6: Update WebSocket Public Demo

**File**: `src/examples/demo/websocket_public_demo.py`

**Add Book Ticker Demonstration**:
```python
@ws_api_test("book_ticker_stream")
async def check_book_ticker_stream(exchange, exchange_name: str):
    """Check WebSocket book ticker stream."""
    symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=False)
    
    # Subscribe to book ticker
    await exchange.subscribe_to_book_ticker([symbol])
    
    # Collect book ticker updates for 10 seconds
    book_tickers = []
    
    async def on_book_ticker(sym: Symbol, ticker: BookTicker):
        book_tickers.append({
            "symbol": f"{sym.base}/{sym.quote}",
            "bid_price": ticker.bid_price,
            "bid_quantity": ticker.bid_quantity,
            "ask_price": ticker.ask_price,
            "ask_quantity": ticker.ask_quantity,
            "spread": ticker.ask_price - ticker.bid_price,
            "timestamp": ticker.timestamp,
            "update_id": ticker.update_id
        })
    
    exchange.on_book_ticker_update = on_book_ticker
    
    # Wait for updates
    await asyncio.sleep(10)
    
    return {
        "symbol": f"{symbol.base}/{symbol.quote}",
        "updates_received": len(book_tickers),
        "sample_tickers": book_tickers[:5],  # Show first 5 updates
        "avg_spread": sum(t["spread"] for t in book_tickers) / len(book_tickers) if book_tickers else 0
    }
```

## Technical Details

### Protobuf Integration (MEXC)

**Channel Detection**:
```python
def _is_book_ticker_message(self, data: bytes) -> bool:
    """Detect if protobuf message is book ticker."""
    return b'aggre.book_ticker' in data[:100]  # Check first 100 bytes
```

**Protobuf Parsing**:
```python
async def _handle_protobuf_message_typed(self, data: bytes, msg_type: str):
    if b'aggre.book_ticker' in data[:50]:
        wrapper = PushDataV3ApiWrapper()
        wrapper.ParseFromString(data)
        if wrapper.HasField('publicAggreBookTicker'):
            await self._handle_book_ticker_update(wrapper.publicAggreBookTicker)
```

### JSON Integration (Gate.io)

**Message Type Detection**:
```python
def _is_book_ticker_message(self, message: Dict[str, Any]) -> bool:
    """Detect if JSON message is book ticker."""
    channel = message.get('channel', '')
    return 'book_ticker' in channel
```

**Subscription Format Difference**:
Gate.io book ticker uses event-based subscription unlike other channels:
```python
def _create_book_ticker_subscription(self, symbols: List[Symbol]) -> str:
    """Create Gate.io book ticker subscription."""
    symbol_pairs = [self.symbol_mapper.to_pair(s) for s in symbols]
    
    message = {
        "time": int(time.time()),
        "channel": "spot.book_ticker",
        "event": "subscribe",
        "payload": symbol_pairs
    }
    return msgspec.json.encode(message).decode()
```

## Integration Points

### 1. Event System Integration

**Add BookTicker Events**:
```python
# Base WebSocket class
class BaseWebSocketPublic:
    def __init__(self):
        self.on_book_ticker_update: Optional[Callable[[Symbol, BookTicker], None]] = None
        
    async def subscribe_to_book_ticker(self, symbols: List[Symbol]) -> None:
        """Subscribe to book ticker updates for symbols."""
        pass
```

### 2. Callback Registration

**Event Handler Registration**:
```python
# Usage example
exchange = MexcWebSocketPublic()

async def handle_book_ticker(symbol: Symbol, ticker: BookTicker):
    print(f"{symbol}: Bid: {ticker.bid_price}, Ask: {ticker.ask_price}")

exchange.on_book_ticker_update = handle_book_ticker
await exchange.subscribe_to_book_ticker([btc_usdt_symbol])
```

### 3. Error Handling

**Connection Recovery**:
```python
async def _on_reconnect(self):
    """Resubscribe to book ticker on reconnection."""
    if self._book_ticker_symbols:
        await self.subscribe_to_book_ticker(self._book_ticker_symbols)
```

## Testing Strategy

### Unit Tests

1. **Subscription Message Generation**:
   - Test MEXC protobuf channel format
   - Test Gate.io event-based subscription format
   - Test symbol extraction from channels

2. **Message Parsing**:
   - Test MEXC protobuf book ticker parsing
   - Test Gate.io JSON book ticker parsing
   - Test error handling for malformed messages

3. **Channel Management**:
   - Test channel generation for multiple symbols
   - Test subscription/unsubscription workflows

### Integration Tests

1. **Live WebSocket Connection**:
   - Test book ticker subscription for both exchanges
   - Test message reception and parsing
   - Test reconnection handling

2. **Performance Tests**:
   - Test message processing latency (<1ms)
   - Test memory usage under high-frequency updates
   - Test concurrent symbol subscriptions

### Demo Tests

1. **WebSocket Demo**:
   - Test book ticker stream demonstration
   - Test real-time spread calculation
   - Test multi-symbol monitoring

## Performance Requirements

### Latency Targets

- **Message Parsing**: <1μs per message
- **Channel Resolution**: <0.5μs per channel
- **Event Notification**: <0.1μs per callback
- **Total Processing**: <2μs end-to-end

### Memory Efficiency

- **Protobuf Parsing**: Zero-copy where possible
- **JSON Parsing**: msgspec for optimal performance
- **Struct Creation**: Minimal allocation overhead
- **Event Handling**: Efficient callback mechanisms

### Throughput Requirements

- **Message Rate**: 100+ messages/second per symbol
- **Symbol Capacity**: 50+ concurrent symbols
- **Update Frequency**: 10ms granularity support
- **Connection Stability**: >99.9% uptime

## Implementation Checklist

### Phase 1: Core Structure
- [ ] Add `BookTicker` struct to `src/structs/common.py`
- [ ] Update MEXC subscription strategy
- [ ] Update Gate.io subscription strategy
- [ ] Test channel generation

### Phase 2: Message Parsing
- [ ] Implement MEXC protobuf book ticker parser
- [ ] Implement Gate.io JSON book ticker parser
- [ ] Add message type detection
- [ ] Test parsing accuracy

### Phase 3: Integration
- [ ] Add event handling to base WebSocket classes
- [ ] Implement subscription management
- [ ] Add reconnection handling
- [ ] Test connection stability

### Phase 4: Demo & Testing
- [ ] Update WebSocket public demo
- [ ] Add book ticker demonstration
- [ ] Create integration tests
- [ ] Performance validation

### Phase 5: Documentation
- [ ] Update WebSocket documentation
- [ ] Add usage examples
- [ ] Document performance characteristics
- [ ] Create troubleshooting guide

## Risk Mitigation

### Technical Risks

1. **Protobuf Parsing Complexity**:
   - Risk: MEXC protobuf parsing failures
   - Mitigation: Robust error handling, fallback mechanisms

2. **Rate Limiting**:
   - Risk: Exchange rate limits on subscriptions
   - Mitigation: Connection pooling, subscription management

3. **Message Order**:
   - Risk: Out-of-order book ticker updates
   - Mitigation: Timestamp validation, sequence checking

### Performance Risks

1. **High-Frequency Updates**:
   - Risk: Performance degradation under load
   - Mitigation: Efficient parsing, callback optimization

2. **Memory Leaks**:
   - Risk: Memory growth from continuous updates
   - Mitigation: Object pooling, garbage collection monitoring

3. **Connection Stability**:
   - Risk: WebSocket disconnections affecting book ticker
   - Mitigation: Automatic reconnection, state restoration

## Success Criteria

### Functional Requirements
✅ **Book ticker data streams from both MEXC and Gate.io**
✅ **Real-time best bid/ask price updates**
✅ **Unified BookTicker struct for consistent data format**
✅ **Proper error handling and reconnection**

### Performance Requirements
✅ **<2μs total processing latency**
✅ **>99.9% message processing success rate**
✅ **Support for 50+ concurrent symbols**
✅ **Minimal memory footprint growth**

### Integration Requirements
✅ **Clean integration with existing WebSocket architecture**
✅ **Backward compatibility with current subscription system**
✅ **Comprehensive demo and testing coverage**
✅ **Clear documentation and usage examples**

---

**Implementation Timeline**: 4-6 hours for complete implementation
**Testing Timeline**: 2-3 hours for comprehensive testing
**Documentation**: 1-2 hours for complete documentation

**Total Estimated Effort**: 7-11 hours for full implementation with testing and documentation.