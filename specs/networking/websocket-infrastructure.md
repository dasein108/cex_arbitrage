# WebSocket Infrastructure Specification

## Overview

The WebSocket infrastructure provides high-performance, real-time connectivity for market data streaming and private account data. Built around a strategy-driven architecture, it achieves sub-millisecond message processing while maintaining robust connection management and error recovery.

## Core Components

### **WebSocketManager (V3) - Strategy-Driven Architecture**

The WebSocketManager serves as the central coordinator for all WebSocket operations, utilizing a strategy-based approach for maximum flexibility and performance.

**Location**: `src/infrastructure/networking/websocket/ws_manager.py`

#### **Key Features**

1. **Automatic Initialization with Connect + Subscribe**
   ```python
   # The initialize() method automatically connects AND subscribes
   await ws_manager.initialize(
       symbols=[Symbol('BTC', 'USDT'), Symbol('ETH', 'USDT')],
       default_channels=[PublicWebsocketChannelType.ORDERBOOK, PublicWebsocketChannelType.EXECUTION]
   )
   # After this call: connected = True, subscribed to all symbols/channels
   ```

2. **Strategy-Driven Connection Management**
   - Direct `strategy.connect()` usage eliminates intermediate client layers
   - Exchange-specific reconnection policies with intelligent backoff
   - Strategy-encapsulated authentication and heartbeat handling

3. **High-Performance Message Processing**
   - Asynchronous message queue with configurable depth (default: 1000 messages)
   - Zero-copy message parsing using msgspec
   - Sub-millisecond processing targets with performance tracking

#### **Performance Specifications**

- **Target Latency**: <1ms message processing
- **Throughput**: 859,598+ messages/second sustained
- **Connection Recovery**: <100ms reconnection time
- **Memory Efficiency**: Ring buffer processing, >95% connection reuse

#### **Architecture Flow**

```
WebSocketManager Initialization Flow:
1. initialize() called with symbols and channels
2. Strategy-driven connection establishment via strategy.connect()
3. Authentication (if required) via strategy.authenticate()
4. Automatic subscription to provided symbols/channels
5. Message reader task started for continuous processing
6. Message processing task started for async handling
7. Optional heartbeat task started for custom ping requirements

Message Processing Flow:
1. Raw message received via WebSocket
2. Queued in async message queue (non-blocking)
3. Strategy message parser processes message
4. Parsed message routed to application handler
5. Performance metrics updated (latency, throughput)
```

### **WebSocket Strategy Set Container**

**Location**: `src/infrastructure/networking/websocket/strategies/strategy_set.py`

The WebSocketStrategySet provides zero-allocation access to all required strategies with initialization-time validation.

```python
class WebSocketStrategySet:
    def __init__(
        self,
        connection_strategy: ConnectionStrategy,
        subscription_strategy: SubscriptionStrategy,
        message_parser: MessageParser
    ):
        # Strategies validated at initialization for zero runtime overhead
        self._validate_strategies()
```

#### **Strategy Validation**
- All strategies must be provided (no optional strategies)
- Compatibility validation performed at initialization
- Zero runtime validation overhead

## Strategy Implementations

### **1. ConnectionStrategy - Connection Lifecycle Management**

**Location**: `src/infrastructure/networking/websocket/strategies/connection.py`

Handles WebSocket connection establishment, authentication, and lifecycle management.

#### **Core Responsibilities**
- **Connection Establishment**: Exchange-specific URL building and connection setup
- **Authentication**: Exchange-specific authentication message handling
- **Heartbeat Management**: Custom ping/pong strategies supplementing built-in WebSocket ping
- **Reconnection Policies**: Exchange-specific reconnection logic and backoff strategies
- **Error Classification**: Intelligent error categorization for appropriate responses

#### **Key Methods**

```python
# Direct connection establishment
async def connect() -> WebSocketClientProtocol:
    """Establish and return WebSocket connection"""

# Exchange-specific reconnection policy
def get_reconnection_policy() -> ReconnectionPolicy:
    """Return strategy-specific reconnection settings"""

# Authentication handling
async def authenticate() -> bool:
    """Perform authentication using internal WebSocket"""

# Custom heartbeat for exchanges requiring it
async def handle_heartbeat() -> None:
    """Send exchange-specific heartbeat/ping messages"""

# Intelligent error handling
def should_reconnect(self, error: Exception) -> bool:
    """Determine if reconnection should be attempted"""
```

#### **Reconnection Policy Configuration**

```python
@dataclass
class ReconnectionPolicy:
    max_attempts: int              # Maximum reconnection attempts
    initial_delay: float           # Initial delay between attempts
    backoff_factor: float          # Exponential backoff multiplier
    max_delay: float              # Maximum delay cap
    reset_on_1005: bool = True    # Reset attempts on WebSocket 1005 errors
```

### **2. SubscriptionStrategy - Message Subscription Management**

**Location**: `src/infrastructure/networking/websocket/strategies/subscription.py`

Creates complete WebSocket subscription/unsubscription messages for exchange-specific formats.

#### **Core Functionality**
- **Message Generation**: Creates complete WebSocket messages ready for transmission
- **Symbol Translation**: Converts internal Symbol objects to exchange-specific formats
- **Channel Management**: Handles channel subscription/unsubscription logic
- **Batch Operations**: Supports batch subscription for multiple symbols

#### **Key Method**

```python
async def create_subscription_messages(
    self,
    action: SubscriptionAction,     # SUBSCRIBE or UNSUBSCRIBE
    *args,                          # Positional arguments (symbols, channels)
    **kwargs                        # Keyword arguments for flexibility
) -> List[Dict[str, Any]]:
    """
    Create complete WebSocket subscription messages.
    
    Common patterns:
    - Public: action, symbols, channels
    - Private: action (with **kwargs for exchange-specific parameters)
    
    Returns:
        List of complete message dictionaries ready for WebSocket sending
    """
```

#### **Performance Target**
- **Message Formatting**: <1μs per message generation

### **3. MessageParser - High-Speed Message Processing**

**Location**: `src/infrastructure/networking/websocket/strategies/message_parser.py`

Parses incoming WebSocket messages and routes them to appropriate handlers.

#### **Core Responsibilities**
- **Message Parsing**: High-speed parsing of exchange-specific message formats
- **Type Classification**: Determines message type (orderbook, trades, ticker, etc.)
- **Symbol Extraction**: Extracts trading pair information from messages
- **Data Transformation**: Converts exchange data to internal format structures

#### **Message Classification**

```python
class MessageType(IntEnum):
    ORDERBOOK = 1               # Orderbook snapshots and updates
    TRADES = 2                  # Trade executions
    BOOK_TICKER = 3            # Best bid/ask updates
    TICKER = 4                  # 24hr ticker statistics
    TRADE = 5                   # Private trade confirmations
    BALANCE = 6                 # Account balance updates
    ORDER = 7                   # Order status updates
    SUBSCRIPTION_CONFIRM = 0    # Subscription confirmations
    HEARTBEAT = 999            # Heartbeat/ping messages
    ERROR = -1                  # Error messages
    OTHER = 888                 # Valid but specialized data
    UNKNOWN = -999             # Unrecognized messages
```

#### **Performance Optimization**
- **Zero-Copy Processing**: msgspec usage for minimal memory allocation
- **Fast Routing**: Integer-based message type classification
- **Batch Processing**: Support for message batching when beneficial

## Data Structures

### **Connection Management**

```python
class ConnectionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"
    CLOSING = "closing"
    CLOSED = "closed"

@dataclass(frozen=True)
class ConnectionContext:
    url: str                        # WebSocket connection URL
    headers: Dict[str, str]         # Connection headers
    auth_required: bool = False     # Authentication requirement
    auth_params: Optional[Dict[str, Any]] = None
    ping_interval: float = 30       # Ping interval (seconds)
    ping_timeout: float = 10        # Ping timeout (seconds)
    max_reconnect_attempts: int = 10
    reconnect_delay: float = 1.0
    ping_message: Optional[str] = None  # Custom ping message
```

### **Message Processing**

```python
@dataclass
class ParsedMessage:
    message_type: MessageType       # Classified message type
    symbol: Optional[Symbol] = None # Trading pair symbol
    channel: Optional[str] = None   # Channel identifier
    data: Optional[Any] = None      # Parsed message data
    timestamp: float = 0.0          # Processing timestamp
    raw_data: Optional[Union[Dict[str, Any], List[Any]]] = None
```

### **Performance Metrics**

```python
@dataclass
class PerformanceMetrics:
    messages_processed: int = 0
    messages_per_second: float = 0.0
    avg_processing_time_ms: float = 0.0
    max_processing_time_ms: float = 0.0
    sub_1ms_messages: int = 0       # HFT compliance tracking
    orderbook_updates: int = 0
    latency_violations: int = 0     # Messages over 1ms
    reconnection_count: int = 0
    error_count: int = 0
```

## Configuration

### **WebSocket Manager Configuration**

```python
@dataclass
class WebSocketManagerConfig:
    max_reconnect_attempts: int = 10    # Global reconnection limit
    reconnect_delay: float = 1.0        # Base reconnection delay
    message_timeout: float = 30.0       # Message processing timeout
    enable_performance_tracking: bool = True
    max_pending_messages: int = 1000    # Message queue depth
    batch_processing_enabled: bool = True
    batch_size: int = 100              # Batch processing size
```

## Usage Examples

### **Basic WebSocket Manager Usage**

```python
from infrastructure.networking.websocket.ws_manager import WebSocketManager
from infrastructure.networking.websocket.strategies.strategy_set import WebSocketStrategySet
from exchanges.structs.common import Symbol

# Create strategy set (exchange-specific implementations)
strategies = WebSocketStrategySet(
   connection_strategy=ExchangeConnectionStrategy(config),
   subscription_strategy=ExchangeSubscriptionStrategy(),
   message_parser=ExchangeMessageParser()
)

# Create manager
ws_manager = WebSocketManager(
   config=websocket_config,
   strategies=strategies,
   message_handler=handle_parsed_message,
   connection_handler=handle_connection_state
)

# Initialize with automatic connect + subscribe
await ws_manager.initialize(
   symbols=[Symbol('BTC', 'USDT'), Symbol('ETH', 'USDT')],
   default_channels=[PublicWebsocketChannelType.ORDERBOOK, PublicWebsocketChannelType.EXECUTION]
)

# Manager is now connected and subscribed to all symbols/channels
# Messages will flow to handle_parsed_message callback
```

### **Manual Subscription Management**

```python
# Subscribe to additional symbols after initialization
await ws_manager.subscribe([Symbol('ADA', 'USDT')])

# Unsubscribe from symbols
await ws_manager.unsubscribe([Symbol('ETH', 'USDT')])

# Send custom messages
await ws_manager.send_message({'method': 'custom_request', 'params': {}})
```

### **Performance Monitoring**

```python
# Get current performance metrics
metrics = ws_manager.get_performance_metrics()
print(f"Messages processed: {metrics['messages_processed']}")
print(f"Average latency: {metrics['avg_processing_time_ms']:.3f}ms")
print(f"HFT compliance: {metrics['sub_1ms_messages'] / metrics['messages_processed'] * 100:.1f}%")

# Check connection status
if ws_manager.is_connected():
    print("WebSocket is connected and operational")
```

## Error Handling and Recovery

### **Connection Error Classification**

The WebSocket infrastructure uses intelligent error classification for appropriate responses:

- **Abnormal Closure (1005)**: Typically transient, triggers immediate reconnection
- **Connection Refused**: Network issues, exponential backoff applied
- **Timeout Errors**: May indicate network congestion, moderate backoff
- **Authentication Failures**: Requires credential verification, limited retries

### **Automatic Recovery Features**

1. **Intelligent Reconnection**: Exchange-specific policies prevent unnecessary retries
2. **State Preservation**: Active symbols and channels automatically resubscribed
3. **Performance Monitoring**: Latency violations and error rates tracked for optimization
4. **Circuit Breakers**: Automatic connection termination on repeated failures

### **Error Handling Flow**

```
Error Detection → Error Classification → Recovery Decision → Reconnection Strategy → State Restoration
```

## HFT Compliance Features

### **Performance Targets**

- **Message Processing**: <1ms average latency
- **Connection Recovery**: <100ms reconnection time
- **Throughput**: >800,000 messages/second sustained
- **Memory Usage**: Minimal allocation through zero-copy processing

### **Monitoring and Alerting**

- Real-time latency percentile calculations (P95, P99)
- HFT compliance rate tracking (percentage of sub-1ms messages)
- Performance degradation detection and alerting
- Connection stability metrics and uptime tracking

### **Optimization Features**

- Connection pooling and reuse
- TCP keepalive optimization
- DNS caching for reduced lookup latency
- Ring buffer message processing for memory efficiency

## Integration with Exchange Implementations

### **Strategy Implementation Requirements**

Exchange implementations must provide:

1. **ConnectionStrategy**: Exchange-specific connection handling
2. **SubscriptionStrategy**: Exchange-specific message formatting
3. **MessageParser**: Exchange-specific message parsing

### **Factory Integration**

The WebSocket infrastructure integrates with the factory pattern:

```python
# Factory creates appropriate strategy set for each exchange
public_exchange = await factory.create_public_exchange(
    exchange_name='mexc_spot',
    symbols=[Symbol('BTC', 'USDT')]
)
# WebSocket manager configured with MEXC-specific strategies
```

## Debugging and Troubleshooting

### **Logging Integration**

The WebSocket infrastructure integrates with the HFT logging system:

- Structured logging with exchange and connection context
- Performance metrics automatically logged
- Error events with full context and stack traces
- Debug-level message content logging (when enabled)

### **Common Issues and Solutions**

1. **High Latency**: Check message queue depth and processing handler performance
2. **Connection Drops**: Review reconnection policy settings and network stability
3. **Missing Messages**: Verify subscription strategy message formatting
4. **Authentication Failures**: Check credential configuration and strategy implementation

This specification provides complete coverage of the WebSocket infrastructure's capabilities, performance characteristics, and integration patterns within the CEX Arbitrage Engine.