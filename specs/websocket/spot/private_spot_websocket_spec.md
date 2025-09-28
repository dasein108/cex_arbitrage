# PrivateSpotWebsocket Interface Specification

## Overview

The `PrivateSpotWebsocket` interface provides real-time account and trading updates via authenticated WebSocket connections. This interface handles order updates, balance changes, and trade executions with message routing through injected handlers.

## Interface Purpose and Responsibilities

### Primary Purpose
- Stream real-time account updates with authentication
- Handle order lifecycle events in real-time
- Process balance updates and trade executions
- Maintain authenticated WebSocket connection

### Core Responsibilities
1. **Authentication Management**: Handle API key authentication for WebSocket
2. **Order Event Processing**: Real-time order status updates
3. **Balance Streaming**: Live balance change notifications
4. **Trade Execution Events**: Fill and execution reports
5. **Message Routing**: Route private events to handlers

## Architectural Position

```
BaseWebsocketInterface (parent)
    └── PrivateSpotWebsocket
            ├── Uses: WebSocketManager V2 (infrastructure)
            ├── Uses: PrivateWebsocketHandlers (event handlers)
            └── Implementations:
                    ├── MexcPrivateWebsocket
                    ├── GateioPrivateWebsocket
                    └── [Other exchanges]
```

## Handler Architecture

### PrivateWebsocketHandlers Structure
```python
class PrivateWebsocketHandlers:
    order_handler: Callable[[Order], Awaitable[None]]
    balance_handler: Callable[[Dict[AssetName, AssetBalance]], Awaitable[None]]
    execution_handler: Callable[[Trade], Awaitable[None]]
    # Optional for futures
    position_handler: Optional[Callable[[Position], Awaitable[None]]] = None
```

### Handler Injection Pattern

```python
def __init__(
        self,
        config: ExchangeConfig,
        handlers: PrivateWebsocketHandlers,  # Injected handlers
        **kwargs
):
    self.handlers = handlers
    super().__init__(
        config=config,
        is_private=True,  # Authenticated connection
        message_handler=self._handle_message
    )
```

## Message Routing Implementation

### Core Message Handler
```python
async def _handle_parsed_message(self, parsed_message) -> None:
    """Route private messages to appropriate handlers"""
    try:
        message_type = parsed_message.message_type
        
        if message_type == MessageType.BALANCE:
            await self._handle_balance_message(parsed_message)
            
        elif message_type == MessageType.ORDER:
            await self._handle_order_message(parsed_message)
            
        elif message_type == MessageType.TRADE:
            await self._handle_trade_message(parsed_message)
            
        elif message_type == MessageType.HEARTBEAT:
            self.logger.debug("Received private heartbeat")
            
        elif message_type == MessageType.SUBSCRIPTION_CONFIRM:
            self.logger.info(f"Private subscription confirmed: {parsed_message.channel}")
            
        elif message_type == MessageType.ERROR:
            self.logger.error(f"Private WebSocket error: {parsed_message.raw_data}")
            
    except Exception as e:
        self.logger.error(f"Error handling private message: {e}")
```

### Specialized Message Handlers
```python
async def _handle_balance_message(self, parsed_message) -> None:
    """Handle balance update messages"""
    try:
        if parsed_message.data:
            await self.handlers.handle_balance(parsed_message.data)
    except Exception as e:
        self.logger.error(f"Error handling balance: {e}")

async def _handle_order_message(self, parsed_message) -> None:
    """Handle order update messages"""
    try:
        if parsed_message.data:
            await self.handlers.handle_order(parsed_message.data)
    except Exception as e:
        self.logger.error(f"Error handling order: {e}")

async def _handle_trade_message(self, parsed_message) -> None:
    """Handle trade execution messages"""
    try:
        if parsed_message.data:
            await self.handlers.handle_execution(parsed_message.data)
    except Exception as e:
        self.logger.error(f"Error handling trade: {e}")
```

## Authentication Patterns

### API Key Authentication
```python
# Exchange-specific authentication in implementation
class MexcPrivateWebsocket(PrivateSpotWebsocket):
    async def _authenticate(self):
        """Send authentication message after connection"""
        timestamp = int(time.time() * 1000)
        signature = self._generate_signature(timestamp)
        
        auth_message = {
            "method": "LOGIN",
            "params": {
                "apiKey": self.config.api_key,
                "signature": signature,
                "timestamp": timestamp
            }
        }
        
        await self._ws_manager.send_message(auth_message)
```

### Signature Generation
```python
def _generate_signature(self, timestamp: int) -> str:
    """Generate HMAC signature for authentication"""
    message = f"GET/realtime{timestamp}"
    signature = hmac.new(
        self.config.secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    return signature
```

## Event Types and Data Flow

### Order Lifecycle Events
```
1. Order Placed → ORDER_NEW event
2. Order Partially Filled → ORDER_PARTIAL_FILL event
3. Order Fully Filled → ORDER_FILLED event
4. Order Cancelled → ORDER_CANCELLED event
5. Order Rejected → ORDER_REJECTED event
```

### Balance Update Events
```
1. Trade Executed → Balance decreased/increased
2. Deposit Confirmed → Balance increased
3. Withdrawal Processed → Balance decreased
4. Fee Deducted → Balance decreased
```

### Trade Execution Events
```
1. Order Matched → TRADE event with details
2. Contains: price, quantity, fee, timestamp
3. Links to order via order_id
4. Indicates maker/taker status
```

## HFT Performance Requirements

### Latency Targets
- **Order Updates**: <1ms processing time
- **Balance Updates**: <2ms processing time
- **Trade Executions**: <1ms processing time

### Reliability Requirements
- Must maintain persistent connection
- Automatic reconnection with auth
- No missed events during reconnection
- Event sequence validation

## State Management Considerations

### No Internal State Caching
```python
# Private WebSocket does NOT cache state
# All state management delegated to handlers
# This ensures HFT compliance (no stale data)

async def _handle_order_message(self, parsed_message):
    # Direct pass-through to handler
    await self.handlers.handle_order(parsed_message.data)
    # No internal state update
```

### Handler State Updates
```python
# In CompositePrivateExchange handler
async def _order_handler(self, order: Order) -> None:
    """Update exchange state with order event"""
    if is_order_done(order):
        self._remove_open_order(order)
        self._update_executed_order(order)
    else:
        self._update_open_order(order)
```

## Implementation Guidelines

### 1. Exchange Implementation Pattern
```python
class GateioPrivateWebsocket(PrivateSpotWebsocket):
    def __init__(self, config, handlers, logger):
        # Configure private WebSocket URL
        config.private_websocket_url = "wss://api.gateio.ws/ws/v4/"
        super().__init__(config, handlers, logger)
    
    async def initialize(self):
        """Initialize with authentication"""
        await super().initialize()
        await self._authenticate()
        await self._subscribe_to_private_channels()
```

### 2. Channel Subscription Pattern
```python
async def _subscribe_to_private_channels(self):
    """Subscribe to account-specific channels"""
    channels = [
        "spot.orders",      # Order updates
        "spot.balances",    # Balance changes
        "spot.usertrades"   # Trade executions
    ]
    
    for channel in channels:
        await self._ws_manager.subscribe(channel)
```

### 3. Error Recovery Pattern
```python
async def _handle_disconnection(self):
    """Handle disconnection with re-authentication"""
    self.logger.warning("Private WebSocket disconnected")
    
    # Attempt reconnection
    if await self._ws_manager.reconnect():
        # Re-authenticate
        await self._authenticate()
        
        # Resubscribe to channels
        await self._subscribe_to_private_channels()
        
        # Request snapshot of current state
        await self._request_order_snapshot()
        await self._request_balance_snapshot()
```

## Dependencies and Relationships

### External Dependencies
- `infrastructure.networking.websocket`: WebSocketManager
- `infrastructure.networking.websocket.handlers`: PrivateWebsocketHandlers
- `exchanges.structs.common`: Order, AssetBalance, Trade
- `config.structs`: ExchangeConfig with credentials

### Internal Relationships
- **Parent**: BaseWebsocketInterface
- **Used By**: CompositePrivateExchange
- **Handlers From**: CompositePrivateExchange
- **Siblings**: PrivateFuturesWebsocket

## Security Considerations

### Authentication Security
- Secure storage of API credentials
- Signature generation for each session
- Session timeout handling
- IP whitelist support

### Message Validation
```python
def _validate_message_authenticity(self, message):
    """Verify message is from exchange"""
    # Check message signature if provided
    # Validate sequence numbers
    # Detect replay attacks
```

## Implementation Checklist

When implementing PrivateSpotWebsocket:

- [ ] Extend PrivateSpotWebsocket class
- [ ] Implement authentication method
- [ ] Add signature generation
- [ ] Configure private WebSocket URL
- [ ] Implement channel subscriptions
- [ ] Handle all message types
- [ ] Add reconnection with re-auth
- [ ] Test order lifecycle events
- [ ] Verify balance updates
- [ ] Test trade execution events

## Monitoring and Observability

### Key Metrics
- Authentication success rate
- Order event latency
- Balance update frequency
- Connection stability
- Message sequence gaps

### Critical Alerts
- Authentication failures
- Missing order events
- Stale balance data
- Connection drops
- High event latency

## Testing Requirements

### Unit Tests
- Mock authentication flow
- Test message routing
- Verify handler calls
- Test error paths

### Integration Tests
- Real authentication
- Order lifecycle testing
- Balance update verification
- Reconnection scenarios

## Future Enhancements

1. **Multi-Account Support**: Handle multiple sub-accounts
2. **Event Replay**: Request missed events after reconnection
3. **Snapshot Sync**: Periodic state synchronization
4. **Dead Man's Switch**: Automatic order cancellation on disconnect
5. **Event Filtering**: Subscribe to specific symbols only