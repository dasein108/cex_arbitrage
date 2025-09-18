# WebSocket Refactoring Summary & Implementation Plan

## Message Format Summary

### MEXC
**Public** (symbol in params):
```json
{"method": "SUBSCRIPTION", "params": ["spot@public.aggre.bookTicker.v3.api.pb@100ms@BTCUSDT"]}
```

**Private** (no symbol):
```json  
{"method": "SUBSCRIPTION", "params": ["spot@private.account.v3.api.pb"]}
```

### Gate.io
**Public** (payload with symbols):
```json
{"time": 1234567890, "channel": "spot.orders_v2", "event": "subscribe", "payload": ["BTC_USDT"]}
```

**Private** (payload with !all):
```json
{"time": 1234567890, "channel": "spot.usertrades_v2", "event": "subscribe", "payload": ["!all"]}
```

## Architecture Changes (Breaking)

### 1. New SubscriptionStrategy Interface
```python
class SubscriptionStrategy(ABC):
    @abstractmethod
    async def create_subscription_messages(
        self, action: SubscriptionAction, symbols: List[Symbol]
    ) -> List[Dict[str, Any]]:
        """Return complete message dict objects ready for WebSocket."""
        pass
        
    @abstractmethod
    async def parse_subscription_response(self, message: Dict[str, Any]) -> Optional[SubscriptionResult]:
        """Parse subscription confirmation/error responses."""
        pass
        
    @abstractmethod
    def extract_symbol_from_message(self, message: Dict[str, Any]) -> Optional[Symbol]:
        """Extract symbol from data message for routing."""
        pass
```

### 2. Simplified WebSocketManager Flow
**OLD**: `symbols → generate_channels() → format_subscription_messages() → send`
**NEW**: `symbols → create_subscription_messages() → send dict objects`

### 3. Implementation Strategy
- **MEXC Public**: Bundle all symbols into single message with multiple params
- **MEXC Private**: Single message with fixed params (no symbols)  
- **Gate.io Public**: Separate message per channel type, symbols in payload
- **Gate.io Private**: Separate message per channel type, "!all" in payload

## Implementation Plan

### Phase 1: Core Refactoring
1. **Update SubscriptionStrategy base class** - Remove all channel-based methods
2. **Update WebSocketManager V2** - Remove channel logic, direct dict message sending
3. **Add SubscriptionResult struct** - For response parsing
4. **Remove deprecated methods** - Clean up old channel-based code

### Phase 2: MEXC Implementation  
1. **MexcPublicSubscriptionStrategy** - Implement message creation with symbol-in-params format
2. **MexcPrivateSubscriptionStrategy** - Implement fixed params format
3. **Update MEXC message parsers** - Add subscription response parsing
4. **Test MEXC WebSockets** - Verify both public and private

### Phase 3: Gate.io Implementation
1. **GateioPublicSubscriptionStrategy** - Implement time/channel/event/payload format
2. **GateioPrivateSubscriptionStrategy** - Implement !all payload format  
3. **Update Gate.io message parsers** - Add subscription response parsing
4. **Test Gate.io WebSockets** - Verify both public and private

### Phase 4: Integration & Testing
1. **Update WebSocket base classes** - Use new strategy interface
2. **Update factory methods** - Create new strategy instances
3. **Comprehensive testing** - All exchange/type combinations
4. **Performance validation** - Ensure HFT compliance maintained

## Key Benefits

1. **Exchange-Native Formats** - No more forced abstractions
2. **Simplified Architecture** - Direct symbols-to-messages flow
3. **Proper Error Handling** - Parse actual WebSocket responses
4. **Future-Proof** - Easy to add new exchanges with different formats
5. **Breaking Change Approach** - Clean architecture without legacy baggage

## Files to Modify

1. **`src/core/transport/websocket/strategies/subscription.py`** - New interface
2. **`src/core/transport/websocket/ws_manager_v2.py`** - Simplified flow  
3. **`src/cex/mexc/ws/strategies/public/subscription_v3.py`** - New MEXC public
4. **`src/cex/mexc/ws/strategies/private/subscription_v3.py`** - New MEXC private
5. **`src/cex/gateio/ws/strategies/public/subscription_v3.py`** - New Gate.io public
6. **`src/cex/gateio/ws/strategies/private/subscription_v3.py`** - New Gate.io private
7. **Update all message parsers** - Add subscription response parsing

## Ready to Implement

All format details confirmed, architecture planned, breaking changes accepted. 
No backward compatibility needed - clean refactoring approach.