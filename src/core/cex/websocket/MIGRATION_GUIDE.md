# WebSocket Architecture Migration Guide

## Overview

This guide explains how to migrate from the inheritance-based `BaseExchangeWebsocketInterface` to the new composition-based `WebSocketManager` architecture.

## Key Architectural Changes

### Before: Inheritance-Based
```python
class MexcWebsocketPublic(BaseExchangeWebsocketInterface):
    def _create_subscriptions(self, symbol, action):
        # Exchange-specific logic mixed with cex logic
    
    async def _on_message(self, raw_message):
        # Parsing logic tightly coupled
```

### After: Composition-Based
```python
# Separate, focused strategies
connection_strategy = MexcPublicConnectionStrategy()
subscription_strategy = MexcPublicSubscriptionStrategy()
message_parser = MexcPublicMessageParser()

# Clean composition
manager = WebSocketManager(
    config=config,
    connection_strategy=connection_strategy,
    subscription_strategy=subscription_strategy,
    message_parser=message_parser
)
```

## Migration Steps

### Step 1: Create Strategy Implementations

For each exchange, create three strategy classes:

1. **ConnectionStrategy** - Handles connection, authentication, keep-alive
2. **SubscriptionStrategy** - Handles subscription formatting and channel mapping
3. **MessageParser** - Handles message parsing and type detection

Example structure:
```
src/exchanges/mexc/ws/
├── strategies_mexc.py          # All MEXC strategies
├── mexc_ws_public.py          # Legacy (to be migrated)
└── mexc_ws_private.py         # Legacy (to be migrated)
```

### Step 2: Extract Connection Logic

**Old Pattern:**
```python
class MexcWebsocketPrivate(BaseExchangeWebsocketInterface):
    def __init__(self, private_rest_client, config):
        # Mixed initialization
        self.rest_client = private_rest_client
        super().__init__(...)
    
    async def get_connect_url(self):
        # Connection URL generation
        listen_key = await self.rest_client.create_listen_key()
        return f"{url}?listenKey={listen_key}"
```

**New Pattern:**
```python
class MexcPrivateConnectionStrategy(ConnectionStrategy):
    def __init__(self, rest_client):
        self.rest_client = rest_client
    
    async def create_connection_context(self, is_private, api_key, secret_key):
        listen_key = await self.rest_client.create_listen_key()
        return ConnectionContext(
            url=f"{BASE_URL}?listenKey={listen_key}",
            auth_params={'listen_key': listen_key},
            keep_alive_interval=1800
        )
```

### Step 3: Extract Subscription Logic

**Old Pattern:**
```python
def _create_subscriptions(self, symbol, action):
    mexc_symbol = MexcUtils.format_symbol(symbol)
    return [
        json.dumps({
            "method": "SUBSCRIPTION",
            "params": [f"channel@{mexc_symbol}"]
        })
    ]
```

**New Pattern:**
```python
class MexcPublicSubscriptionStrategy(SubscriptionStrategy):
    def create_subscription_messages(self, symbols, channels, is_subscribe):
        messages = []
        action = "SUBSCRIPTION" if is_subscribe else "UNSUBSCRIPTION"
        
        for symbol in symbols:
            mexc_symbol = MexcUtils.format_symbol(symbol)
            for channel in channels:
                messages.append(msgspec.json.encode({
                    "method": action,
                    "params": [f"{channel}@{mexc_symbol}"]
                }).decode())
        
        return messages
```

### Step 4: Extract Message Parsing

**Old Pattern:**
```python
async def _on_message(self, raw_message):
    # All parsing logic mixed together
    wrapper = PushDataV3ApiWrapper()
    wrapper.ParseFromString(raw_message)
    
    if wrapper.HasField('depth'):
        # Parse orderbook
        self._handle_orderbook(...)
    elif wrapper.HasField('deals'):
        # Parse trades
        self._handle_trades(...)
```

**New Pattern:**
```python
class MexcPublicMessageParser(MessageParser):
    async def parse_message(self, raw_message, channel=None):
        wrapper = PushDataV3ApiWrapper()
        wrapper.ParseFromString(raw_message)
        
        if wrapper.HasField('depth'):
            yield self._parse_orderbook(wrapper.depth)
        elif wrapper.HasField('deals'):
            for trade in self._parse_trades(wrapper.deals):
                yield trade
```

### Step 5: Update Usage Code

**Old Usage:**
```python
# Direct instantiation with inheritance
ws_client = MexcWebsocketPublic(config)
await ws_client.initialize(symbols)
```

**New Usage:**

```python
# Strategy factory pattern
from core.cex.websocket import WebSocketStrategyFactory
from core.cex.websocket import WebSocketManager

# Create strategies
conn_strategy, sub_strategy, parser = WebSocketStrategyFactory.create_strategies(
    exchange='mexc',
    is_private=False
)

# Or manually create strategies for more control
conn_strategy = MexcPublicConnectionStrategy()
sub_strategy = MexcPublicSubscriptionStrategy()
parser = MexcPublicMessageParser()

# Create manager with strategies
manager = WebSocketManager(
    config=WebSocketManagerConfig(
        exchange_name='mexc',
        is_private=False,
        channel_types=[ChannelType.ORDERBOOK, ChannelType.TRADES]
    ),
    connection_strategy=conn_strategy,
    subscription_strategy=sub_strategy,
    message_parser=parser,
    message_handler=handle_market_data,
    error_handler=handle_error
)

# Initialize and run
await manager.initialize(symbols)
```

## Benefits of Migration

### 1. **SOLID Compliance**
- **S**: Each strategy has single responsibility
- **O**: New exchanges extend strategies without modifying manager
- **L**: All strategies are substitutable
- **I**: Focused interfaces for each concern
- **D**: Dependencies are injected, not created

### 2. **Testability**
```python
# Easy to test with mock strategies
mock_connection = MockConnectionStrategy()
mock_subscription = MockSubscriptionStrategy()
mock_parser = MockMessageParser()

manager = WebSocketManager(
    config=test_config,
    connection_strategy=mock_connection,
    subscription_strategy=mock_subscription,
    message_parser=mock_parser
)
```

### 3. **Flexibility**
- Swap strategies at runtime
- Mix and match strategies (e.g., use JSON parser with protobuf connection)
- Easy A/B testing of different implementations

### 4. **Performance**
- Strategies can be optimized independently
- Pre-computation in strategy constructors
- Strategy-specific optimizations don't affect other components

## Common Patterns

### Pattern 1: Authentication Strategies

**Listen Key Pattern (MEXC):**
```python
class ListenKeyConnectionStrategy(ConnectionStrategy):
    async def create_connection_context(self, ...):
        listen_key = await self._get_listen_key()
        return ConnectionContext(
            url=f"{base_url}?listenKey={listen_key}",
            keep_alive_interval=1800
        )
    
    async def handle_keep_alive(self, ...):
        await self._extend_listen_key()
```

**Signature Pattern (Gate.io):**
```python
class SignatureConnectionStrategy(ConnectionStrategy):
    async def authenticate(self, send_func, context):
        signature = self._create_signature()
        await send_func(json.dumps({
            "method": "auth",
            "params": [self.api_key, signature, timestamp]
        }))
        return True
```

### Pattern 2: Message Format Strategies

**Protobuf Parser:**
```python
class ProtobufMessageParser(MessageParser):
    def get_message_type(self, raw_message):
        # Quick byte inspection
        return self._signature_map.get(raw_message[:2])
    
    async def parse_message(self, raw_message, channel):
        # Protobuf parsing
        wrapper = WrapperClass()
        wrapper.ParseFromString(raw_message)
        yield self._convert_to_unified(wrapper)
```

**JSON Parser:**
```python
class JsonMessageParser(MessageParser):
    def __init__(self):
        self.decoder = msgspec.json.Decoder()
    
    async def parse_message(self, raw_message, channel):
        message = self.decoder.decode(raw_message)
        yield self._convert_to_unified(message)
```

## Testing the Migration

### Unit Tests for Strategies
```python
async def test_connection_strategy():
    strategy = MexcPublicConnectionStrategy()
    context = await strategy.create_connection_context()
    
    assert context.url == expected_url
    assert context.is_authenticated == False
```

### Integration Tests
```python
async def test_websocket_manager():
    # Use test strategies
    manager = WebSocketManager(
        config=test_config,
        connection_strategy=TestConnectionStrategy(),
        subscription_strategy=TestSubscriptionStrategy(),
        message_parser=TestMessageParser()
    )
    
    await manager.initialize([test_symbol])
    assert manager.is_connected
    assert test_symbol in manager.active_symbols
```

## Performance Considerations

### HFT Optimization Points

1. **Pre-compute in Strategy Constructors**
```python
class OptimizedSubscriptionStrategy(SubscriptionStrategy):
    def __init__(self):
        # Pre-compute channel mappings
        self._channel_map = {
            'orderbook': 'spot@public.limit.depth.v3.api',
            'trades': 'spot@public.deals.v3.api'
        }
        # Pre-compile message templates
        self._templates = self._build_templates()
```

2. **Use Object Pools in Parsers**
```python
class PooledMessageParser(MessageParser):
    def __init__(self):
        self._orderbook_pool = OrderBookPool(initial_size=100)
        self._trade_pool = TradePool(initial_size=200)
```

3. **Minimize Allocations**
```python
# Reuse buffers for parsing
self._parse_buffer = bytearray(1024 * 1024)  # 1MB buffer
```

## Rollback Plan

If issues arise during migration:

1. **Parallel Run**: Run both old and new implementations
2. **Feature Flag**: Use configuration to switch between implementations
3. **Gradual Migration**: Migrate one exchange at a time

```python
if config.use_new_websocket_architecture:
    manager = WebSocketManager(...)
else:
    manager = LegacyWebSocketClient(...)
```

## Checklist for Complete Migration

- [ ] Create strategy implementations for all exchanges
- [ ] Register strategies with factory
- [ ] Update exchange initialization code
- [ ] Migrate event handlers to new pattern
- [ ] Update tests for new architecture
- [ ] Performance testing and benchmarking
- [ ] Update documentation
- [ ] Remove legacy base class (after full migration)

## Support and Questions

For questions about the migration:
1. Review the strategy interface documentation
2. Check example implementations in `strategies_mexc.py`
3. Run performance benchmarks before and after migration
4. Ensure all HFT requirements are maintained