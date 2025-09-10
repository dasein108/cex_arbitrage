# MEXC Exchange Implementation

High-performance MEXC cryptocurrency exchange client with WebSocket streaming support, optimized for arbitrage trading.

## Features

### 🚀 **Performance Optimized**
- **Sub-millisecond message processing** with `__slots__` optimization
- **Connection pooling** and persistent HTTP sessions  
- **Differential orderbook updates** to minimize memory usage
- **Efficient JSON parsing** with `orjson` library
- **Protobuf support** for binary message formats

### 📡 **WebSocket Streaming**
- **Automatic reconnection** with exponential backoff
- **Multi-format parsing** (JSON and protobuf)
- **Real-time trades and orderbook** data
- **Stream health monitoring** and diagnostics
- **Graceful error handling** with comprehensive logging

### 🔄 **Unified Interface**
- Implements `PublicExchangeInterface` standards
- **Consistent data structures** across all exchanges
- **Symbol mapping** between MEXC and unified formats
- **Type-safe operations** with msgspec structs

## Components

### 1. MexcPublicExchange (`public.py`)
REST API client for public market data:

```python
from src.exchanges.mexc import MexcPublicExchange
from src.structs.exchange import Symbol, AssetName

# Initialize exchange
exchange = MexcPublicExchange()
symbols = [Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))]
await exchange.init(symbols)

# Get market data
orderbook = await exchange.get_orderbook(symbols[0], limit=100)
trades = await exchange.get_recent_trades(symbols[0], limit=500)
```

### 2. MexcWebSocketPublicStream (`websocket.py`)  
High-performance WebSocket client for real-time data:

```python
from src.exchanges.mexc import MexcWebSocketPublicStream
from src.structs.exchange import ExchangeName

async def handle_message(message):
    stream_type = message.get('stream_type')
    if stream_type == 'trades':
        print(f"New trades: {len(message['data'])}")
    elif stream_type == 'orderbook':
        print(f"Orderbook update: {message['symbol']}")

# Create WebSocket connection
ws = MexcWebSocketPublicStream(
    exchange_name=ExchangeName("MEXC"),
    on_message=handle_message,
    timeout=30.0
)

# Subscribe to streams
await ws.subscribe([
    "BTCUSDT@deal",   # BTC trades
    "BTCUSDT@depth"   # BTC orderbook
])
```

### 3. Stream Manager Example (`stream_example.py`)
Complete integration example combining REST and WebSocket:

```python
from src.examples.mexc_public_stream import MexcStreamManager

# Create manager with symbols
manager = MexcStreamManager()
await manager.init([
    Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
    Symbol(base=AssetName("ETH"), quote=AssetName("USDT"))
])

# Start streaming (blocks until interrupted)  
await manager.start_streaming()
```

## Message Formats

### Trade Messages
```python
{
    'stream': 'btcusdt@deal',
    'stream_type': 'trades', 
    'symbol': Symbol(base='BTC', quote='USDT', is_futures=False),
    'data': [
        Trade(
            price=50000.0,
            amount=0.1,
            side=Side.BUY,
            timestamp=1234567890000,
            is_maker=False
        )
    ],
    'timestamp': 1234567890.123
}
```

### Orderbook Messages
```python
{
    'stream': 'btcusdt@depth',
    'stream_type': 'orderbook',
    'symbol': Symbol(base='BTC', quote='USDT', is_futures=False), 
    'data': OrderBook(
        bids=[OrderBookEntry(price=49950.0, size=1.5)],
        asks=[OrderBookEntry(price=50050.0, size=2.0)],
        timestamp=1234567890.123
    ),
    'timestamp': 1234567890.123
}
```

## Stream Types

### Available Streams

| Stream Pattern | Description | Update Frequency |
|----------------|-------------|------------------|
| `{symbol}@deal` | Aggregate trades | Real-time |  
| `{symbol}@depth` | Order book depth | 100ms |
| `{symbol}@ticker` | 24hr statistics | 1000ms |
| `{symbol}@kline_{interval}` | Candlestick data | Interval-based |

### Symbol Format
MEXC uses uppercase symbols without separators:
- `BTCUSDT` for BTC/USDT
- `ETHBTC` for ETH/BTC  
- `BNBUSDT` for BNB/USDT

## Performance Characteristics

### Latency Targets
- **Message Processing**: <1ms per message
- **Connection Establishment**: <2s  
- **Reconnection Time**: <5s average
- **Subscription Response**: <100ms

### Throughput Targets  
- **Messages/Second**: 1000+ per connection
- **Concurrent Symbols**: 50+ simultaneously
- **Memory Usage**: <50MB per connection
- **CPU Usage**: <5% per connection

### Reliability Targets
- **Connection Uptime**: >99.5%
- **Message Delivery**: >99.9% 
- **Reconnection Success**: >95%
- **Error Recovery**: <30s average

## Error Handling

### Connection Errors
```python
try:
    ws = MexcWebSocketPublicStream(...)
    await ws.subscribe(["BTCUSDT@deal"])
except ExchangeAPIError as e:
    if e.status_code == 500:
        # Connection failed
        await asyncio.sleep(5)  # Backoff
    elif e.status_code == 408:  
        # Timeout
        await ws.stop()
        await ws.restart()
```

### Message Parsing Errors
- Invalid messages are logged and skipped
- Protobuf parsing failures fall back to JSON
- Malformed JSON messages are discarded silently

### Automatic Recovery
- **Exponential backoff**: 1s, 2s, 4s, 8s, 16s, 30s (max)  
- **Max retry attempts**: 10 before giving up
- **Health monitoring**: Connection status tracking
- **Graceful degradation**: Continues with available data

## Testing

### Unit Tests
```bash
python -m pytest tests/exchanges/mexc/ -v
```

### Integration Tests  
```bash  
python test_mexc_websocket.py
```

### Performance Tests
```bash
python -m pytest tests/performance/mexc_websocket_performance.py
```

## Configuration

### Environment Variables
```bash
# Optional - for private streams
MEXC_API_KEY=your_api_key
MEXC_SECRET_KEY=your_secret_key

# WebSocket settings
MEXC_WS_URL=wss://wbs.mexc.com/ws
MEXC_WS_TIMEOUT=30
MEXC_MAX_RETRIES=10
```

### Performance Tuning
```python
# High-frequency trading setup
ws = MexcWebSocketPublicStream(
    exchange_name=ExchangeName("MEXC"),
    on_message=handle_message,
    timeout=10.0,        # Aggressive timeout
    max_retries=5        # Fast failover
)

# Monitoring setup  
ws = MexcWebSocketPublicStream(
    exchange_name=ExchangeName("MEXC"),
    on_message=handle_message,
    timeout=60.0,        # Patient timeout
    max_retries=20       # Persistent connection
)
```

## Architecture

```
┌─────────────────────────────────────┐
│            Application              │
├─────────────────────────────────────┤
│         MexcStreamManager           │  ← High-level integration
├─────────────────────────────────────┤
│  MexcPublicExchange │ MexcWebSocket │  ← Core components
├─────────────────────────────────────┤  
│        Unified Interfaces           │  ← Standard data structures
├─────────────────────────────────────┤
│      REST Client    │   WebSocket   │  ← Network layer
├─────────────────────────────────────┤
│         MEXC API Endpoints          │  ← External service
└─────────────────────────────────────┘
```

## Migration from Raw Implementation

### Before (raw/mexc_api/websocket/mexc_ws.py)
```python  
from exchanges.mexc_api.websocket.mexc_ws import MexcWebSocketBase

ws = MexcWebSocketBase("mexc", handle_message)
# Manual connection management
# No unified data structures  
# Limited error handling
```

### After (src/exchanges/mexc/websocket.py)
```python
from src.exchanges.mexc import MexcWebSocketPublicStream

ws = MexcWebSocketPublicStream(
    exchange_name=ExchangeName("MEXC"),
    on_message=handle_message
)
# Automatic connection management
# Unified data structures (Symbol, Trade, OrderBook)
# Comprehensive error handling with exponential backoff
```

## Conclusion

The MEXC WebSocket implementation provides enterprise-grade reliability and performance for high-frequency arbitrage trading. By following unified interface standards and implementing comprehensive error handling, it ensures consistent behavior across all supported exchanges while maintaining the flexibility to handle MEXC-specific message formats and protocols.