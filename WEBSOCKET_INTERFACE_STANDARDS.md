# WebSocket Interface Standards

## Overview

The `BaseWebSocketInterface` provides a unified, data format agnostic foundation for all exchange WebSocket implementations. It handles connection management, automatic reconnection, subscription management, and error recovery while being completely independent of specific data formats (JSON, protobuf, etc.).

## Key Features

### 🚀 **High-Performance Design**
- **Async/await architecture** for non-blocking operations
- **Automatic reconnection** with exponential backoff
- **Connection pooling** and state management
- **Performance metrics** collection
- **Sub-millisecond message processing** capabilities

### 📡 **Data Format Agnostic**
- **No assumptions** about message format (JSON, protobuf, binary)
- **Abstract parsing methods** for exchange-specific implementation
- **Unified message interface** regardless of underlying format
- **Flexible subscription models** adaptable to any exchange API

### 🔄 **Robust Connection Management**
- **Automatic reconnection** with configurable backoff
- **Connection state tracking** (disconnected, connecting, connected, etc.)
- **Health checks** and monitoring
- **Graceful shutdown** and resource cleanup

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                 Exchange-Specific Implementation             │
│  ┌─────────────────┐  ┌──────────────────┐ ┌──────────────┐ │
│  │ _connect()      │  │ _parse_message() │ │ _send_sub()  │ │
│  │ (WebSocket URL) │  │ (JSON/Protobuf) │ │ (Sub format) │ │
│  └─────────────────┘  └──────────────────┘ └──────────────┘ │
└─────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│                  BaseWebSocketInterface                     │
│  ┌─────────────────┐  ┌──────────────────┐ ┌──────────────┐ │
│  │ Connection Mgmt │  │ Subscription Mgmt│ │ Error Handle │ │
│  │ • Reconnection  │  │ • Sub/Unsub      │ │ • Recovery   │ │
│  │ • State Track   │  │ • Stream Track   │ │ • Logging    │ │
│  │ • Health Check  │  │ • Queue Pending  │ │ • Metrics    │ │
│  └─────────────────┘  └──────────────────┘ └──────────────┘ │
└─────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│                    Unified Message Bus                      │
│              (Standard Dict[str, Any] interface)            │
└─────────────────────────────────────────────────────────────┘
```

## Implementation Requirements

### 1. **Required Abstract Methods**

Every exchange implementation MUST implement these methods:

```python
@abstractmethod
async def _connect(self) -> None:
    """Establish WebSocket connection - set self._ws"""
    pass

@abstractmethod
async def _send_subscription_message(
    self, 
    streams: List[str], 
    action: SubscriptionAction
) -> None:
    """Send exchange-specific subscription message"""
    pass

@abstractmethod
async def _parse_message(self, raw_message: Union[str, bytes]) -> Optional[Dict[str, Any]]:
    """Parse raw message to standardized dict"""
    pass

@abstractmethod
def _extract_stream_info(self, message: Dict[str, Any]) -> Optional[tuple[str, StreamType]]:
    """Extract stream ID and type from parsed message"""
    pass
```

### 2. **Configuration Standards**

Use `WebSocketConfig` for all connection parameters:

```python
config = WebSocketConfig(
    url="wss://stream.exchange.com/ws",
    timeout=10.0,          # Aggressive for trading
    ping_interval=20.0,
    max_reconnect_attempts=10,
    reconnect_delay=1.0,
    reconnect_backoff=2.0,
    enable_compression=True
)
```

### 3. **Message Handling Standards**

All parsed messages must be `Dict[str, Any]` format:

```python
# Input (exchange-specific):
raw_json = '{"stream":"btcusdt@depth","data":{"bids":[["50000","1.0"]]}'
raw_protobuf = b'\x08\x96...'  # Binary protobuf data

# Output (standardized):
parsed = {
    "stream": "btcusdt@depth",
    "data": {
        "bids": [["50000", "1.0"]],
        "asks": [["51000", "0.5"]]
    },
    "timestamp": 1234567890
}
```

## Exchange Implementation Examples

### Example 1: Binance-style JSON WebSocket

```python
from src.exchanges.interface.base_ws import BaseWebSocketInterface
import websockets
import msgspec

class BinanceWebSocket(BaseWebSocketInterface):
    async def _connect(self) -> None:
        self._ws = await websockets.connect(self.config.url)
    
    async def _send_subscription_message(self, streams: List[str], action: SubscriptionAction) -> None:
        message = {
            "method": "SUBSCRIBE" if action == SubscriptionAction.SUBSCRIBE else "UNSUBSCRIBE",
            "params": streams,
            "id": int(time.time())
        }
        await self.send_message(message)
    
    async def _parse_message(self, raw_message: Union[str, bytes]) -> Optional[Dict[str, Any]]:
        if isinstance(raw_message, str):
            return msgspec.json.decode(raw_message)
        return None
    
    def _extract_stream_info(self, message: Dict[str, Any]) -> Optional[tuple[str, StreamType]]:
        if "stream" in message:
            stream_id = message["stream"]
            if "@depth" in stream_id:
                return (stream_id, StreamType.ORDERBOOK)
            elif "@trade" in stream_id:
                return (stream_id, StreamType.TRADES)
        return None
```

### Example 2: MEXC-style with Protobuf Support

```python
class MexcWebSocket(BaseWebSocketInterface):
    async def _parse_message(self, raw_message: Union[str, bytes]) -> Optional[Dict[str, Any]]:
        try:
            if isinstance(raw_message, str):
                # JSON format
                return msgspec.json.decode(raw_message)
            else:
                # Protobuf format
                from exchanges.mexc.pb import PushDataWrapper_pb2
                result = PushDataWrapper_pb2.PushDataWrapper()
                result.ParseFromString(raw_message)
                return json_format.MessageToDict(result, preserving_proto_field_name=True)
        except Exception:
            return None  # Skip malformed messages
```

## Performance Requirements

### 1. **Latency Targets**
- **Message processing**: <1ms per message
- **Connection establishment**: <2s
- **Reconnection time**: <5s average
- **Subscription acknowledgment**: <100ms

### 2. **Throughput Targets**
- **Messages per second**: 1000+ per connection
- **Concurrent connections**: 20+ exchanges simultaneously
- **Memory usage**: <100MB per connection
- **CPU usage**: <10% per connection

### 3. **Reliability Targets**
- **Connection uptime**: >99.5%
- **Message delivery**: >99.9%
- **Reconnection success**: >95%
- **Error recovery**: <30s average

## Error Handling Standards

### 1. **Exception Mapping**
All WebSocket errors must use unified exception hierarchy:

```python
from src.common.exceptions import ExchangeAPIError

# Connection errors
raise ExchangeAPIError(500, "WebSocket connection failed")

# Message parsing errors  
raise ExchangeAPIError(400, "Invalid message format")

# Subscription errors
raise ExchangeAPIError(403, "Subscription rejected by exchange")
```

### 2. **Logging Standards**
Use structured logging with appropriate levels:

```python
self.logger.info("WebSocket connected successfully")
self.logger.warning("Reconnection attempt {attempt}/{max_attempts}")
self.logger.error("Failed to parse message: {error}")
self.logger.debug("Received message: {message_type}")
```

## Monitoring and Metrics

### 1. **Required Metrics**
Every implementation must track:
- `messages_received`: Total messages processed
- `messages_sent`: Total messages sent
- `connections`: Total connection attempts
- `reconnections`: Total reconnection attempts  
- `errors`: Total error count
- `connection_uptime`: Current connection duration

### 2. **Health Check Requirements**
Implement comprehensive health checks:

```python
health = await websocket.health_check()
# Returns:
{
    'exchange': 'MEXC',
    'state': 'connected',
    'is_connected': True,
    'subscriptions': 5,
    'reconnect_attempts': 0,
    'last_message_age': 0.5,
    'metrics': {...}
}
```

## Usage Patterns

### 1. **Basic Connection**

```python
from src.exchanges.mexc.websocket import MexcWebSocket

config = create_websocket_config("wss://stream.mexc.com/ws")

async def handle_message(message: Dict[str, Any]):
    print(f"Received: {message}")

async def main():
    async with MexcWebSocket(ExchangeName("MEXC"), config, handle_message) as ws:
        await ws.subscribe(["btcusdt@depth", "ethusdt@trade"])
        await asyncio.sleep(60)  # Listen for 1 minute
```

### 2. **Advanced Usage with Error Handling**

```python
async def handle_error(error: Exception):
    logger.error(f"WebSocket error: {error}")

websocket = MexcWebSocket(
    ExchangeName("MEXC"), 
    config, 
    message_handler=handle_message,
    error_handler=handle_error
)

await websocket.start()
try:
    await websocket.subscribe(["btcusdt@depth"])
    await asyncio.sleep(3600)  # Run for 1 hour
finally:
    await websocket.stop()
```

## Testing Requirements

### 1. **Unit Tests**
- Connection establishment and failure
- Message parsing for all supported formats  
- Subscription management
- Error handling and recovery
- Metrics collection

### 2. **Integration Tests**
- End-to-end message flow
- Reconnection scenarios
- Performance under load
- Multi-exchange concurrent connections

### 3. **Performance Tests**
- Latency measurements
- Throughput benchmarks
- Memory usage profiling
- Connection stability testing

## Migration from Legacy Code

### 1. **Immediate Actions**
- **STOP** using `raw/common/interfaces/base_ws.py`
- **START** using `src/exchanges/interface/base_ws.py`
- **MIGRATE** existing WebSocket implementations

### 2. **Migration Steps**
1. **Analyze current implementation** in raw directory
2. **Create exchange-specific class** inheriting from `BaseWebSocketInterface`
3. **Implement required abstract methods**
4. **Test thoroughly** with existing message flows
5. **Deploy** and monitor performance

### 3. **Compliance Verification**
Run these checks before deployment:

```bash
# Check imports
grep -r "from raw" src/exchanges/  # Should return nothing

# Check interface compliance
python scripts/verify_websocket_compliance.py

# Performance benchmark
python scripts/benchmark_websocket_performance.py
```

## Conclusion

The unified WebSocket interface provides a robust, high-performance foundation for all exchange WebSocket implementations. By following these standards, all exchange implementations will have consistent behavior, error handling, and performance characteristics while maintaining the flexibility to handle exchange-specific message formats and protocols.

**Key Benefits:**
- **Reduced development time** through standardized patterns
- **Consistent error handling** across all exchanges
- **Improved reliability** with built-in reconnection and recovery
- **Better monitoring** with standardized metrics
- **Enhanced performance** through optimized connection management
- **Easier maintenance** with unified codebase patterns