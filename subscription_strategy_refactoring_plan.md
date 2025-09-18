# SubscriptionStrategy Refactoring Plan

## Problem Analysis

**Current Flawed Design**:
- SubscriptionStrategy generates "channels" first, then formats them into messages
- WebSocketManager concatenates channels and assumes generic format
- Exchange-specific message structures are forced into channel-based model
- Complex two-step process: `generate_channels() → format_subscription_messages()`

## Correct WebSocket Message Formats

**MEXC Public** (symbol included in params):
```json
{
    "method": "SUBSCRIPTION",
    "params": [
        "spot@public.aggre.bookTicker.v3.api.pb@100ms@BTCUSDT"
    ]
}
```

**MEXC Private** (no symbol in params):
```json
{
    "method": "SUBSCRIPTION", 
    "params": [
        "spot@private.account.v3.api.pb"
    ]
}
```

**Gate.io Public** (payload with symbols):
```json
{
    "time": 1234567890,
    "channel": "spot.orders_v2",
    "event": "subscribe",
    "payload": ["BTC_USDT"]
}
```

**Gate.io Private** (payload with !all):
```json
{
    "time": 1234567890,
    "channel": "spot.usertrades_v2", 
    "event": "subscribe",
    "payload": ["!all"]
}
```

## New Architecture Design

### 1. Simplified SubscriptionStrategy Interface

**BREAKING CHANGE**: Remove all channel-based methods, implement direct message creation:

```python
class SubscriptionStrategy(ABC):
    """
    Direct message-based subscription strategy.
    
    Takes symbols only, generates complete WebSocket messages internally.
    """
    
    @abstractmethod
    async def create_subscription_messages(
        self, 
        action: SubscriptionAction,
        symbols: List[Symbol]
    ) -> List[Dict[str, Any]]:
        """
        Create complete WebSocket subscription/unsubscription messages.
        
        Args:
            action: SUBSCRIBE or UNSUBSCRIBE
            symbols: Symbols to subscribe/unsubscribe to/from
        
        Returns:
            List of complete message dictionaries ready for WebSocket sending
        """
        pass
    
    @abstractmethod  
    async def parse_subscription_response(
        self, 
        message: Dict[str, Any]
    ) -> Optional[SubscriptionResult]:
        """
        Parse WebSocket response to subscription request.
        
        Args:
            message: Raw WebSocket message from exchange
            
        Returns:
            SubscriptionResult with success/error info, or None if not subscription response
        """
        pass
    
    @abstractmethod
    def extract_symbol_from_message(
        self, 
        message: Dict[str, Any]
    ) -> Optional[Symbol]:
        """
        Extract symbol from data message for routing.
        
        Args:
            message: Parsed WebSocket data message
            
        Returns:
            Symbol if message contains symbol info, None for global messages
        """
        pass
```

### 2. Exchange-Specific Implementation Strategy

#### MEXC Public Strategy
```python
class MexcPublicSubscriptionStrategy(SubscriptionStrategy):
    
    async def create_subscription_messages(
        self, 
        action: SubscriptionAction,
        symbols: List[Symbol]
    ) -> List[Dict[str, Any]]:
        """
        Create MEXC public subscription messages.
        Symbol included in params: "spot@public.aggre.bookTicker.v3.api.pb@100ms@BTCUSDT"
        """
        method = "SUBSCRIPTION" if action == SubscriptionAction.SUBSCRIBE else "UNSUBSCRIPTION"
        
        params = []
        for symbol in symbols:
            exchange_symbol = self.symbol_mapper.to_exchange_symbol(symbol)
            params.extend([
                f"spot@public.aggre.depth.v3.api.pb@10ms@{exchange_symbol}",
                f"spot@public.aggre.deals.v3.api.pb@10ms@{exchange_symbol}",
                f"spot@public.aggre.bookTicker.v3.api.pb@100ms@{exchange_symbol}"
            ])
        
        return [{
            "method": method,
            "params": params
        }]
```

#### MEXC Private Strategy  
```python
class MexcPrivateSubscriptionStrategy(SubscriptionStrategy):
    
    async def create_subscription_messages(
        self, 
        action: SubscriptionAction,
        symbols: List[Symbol]  # Ignored for private channels
    ) -> List[Dict[str, Any]]:
        """
        Create MEXC private subscription messages.
        No symbol in params: "spot@private.account.v3.api.pb"
        """
        method = "SUBSCRIPTION" if action == SubscriptionAction.SUBSCRIBE else "UNSUBSCRIPTION"
        
        return [{
            "method": method,
            "params": [
                "spot@private.account.v3.api.pb",
                "spot@private.deals.v3.api.pb",
                "spot@private.orders.v3.api.pb"
            ]
        }]
```

#### Gate.io Public Strategy
```python
class GateioPublicSubscriptionStrategy(SubscriptionStrategy):
    
    async def create_subscription_messages(
        self, 
        action: SubscriptionAction,
        symbols: List[Symbol]
    ) -> List[Dict[str, Any]]:
        """
        Create Gate.io public subscription messages.
        Format: {"time": X, "channel": Y, "event": Z, "payload": ["BTC_USDT"]}
        """
        current_time = int(time.time())
        event = "subscribe" if action == SubscriptionAction.SUBSCRIBE else "unsubscribe"
        messages = []
        
        if symbols:
            # Convert symbols to Gate.io format  
            symbol_pairs = [self.symbol_mapper.to_exchange_symbol(s) for s in symbols]
            
            # Create separate message for each channel type
            messages.extend([
                {
                    "time": current_time,
                    "channel": "spot.order_book_update",
                    "event": event,
                    "payload": symbol_pairs
                },
                {
                    "time": current_time,
                    "channel": "spot.book_ticker",
                    "event": event, 
                    "payload": symbol_pairs
                },
                {
                    "time": current_time,
                    "channel": "spot.trades",
                    "event": event,
                    "payload": symbol_pairs
                }
            ])
        
        return messages
```

#### Gate.io Private Strategy
```python
class GateioPrivateSubscriptionStrategy(SubscriptionStrategy):
    
    async def create_subscription_messages(
        self, 
        action: SubscriptionAction,
        symbols: List[Symbol]  # Ignored for private channels
    ) -> List[Dict[str, Any]]:
        """
        Create Gate.io private subscription messages.
        Format: {"time": X, "channel": Y, "event": Z, "payload": ["!all"]}
        """
        current_time = int(time.time())
        event = "subscribe" if action == SubscriptionAction.SUBSCRIBE else "unsubscribe"
        
        return [
            {
                "time": current_time,
                "channel": "spot.orders_v2",
                "event": event,
                "payload": ["!all"]
            },
            {
                "time": current_time,
                "channel": "spot.usertrades_v2",
                "event": event,
                "payload": ["!all"]
            },
            {
                "time": current_time,
                "channel": "spot.balances",
                "event": event,
                "payload": ["!all"]
            }
        ]
```

### 3. Simplified WebSocketManager Flow

**NEW FLOW**: `symbols → create_subscription_messages() → send dict messages`

```python
class WebSocketManager:
    
    async def subscribe(self, symbols: List[Symbol]) -> None:
        """
        Simplified subscription flow with direct message sending.
        """
        if not self.is_connected():
            raise BaseExchangeError(503, "WebSocket not connected")
        
        try:
            # Get complete message objects from strategy
            messages = await self.strategies.subscription_strategy.create_subscription_messages(
                action=SubscriptionAction.SUBSCRIBE,
                symbols=symbols
            )
            
            self.logger.info(f"Sending {len(messages)} subscription messages for {len(symbols)} symbols")
            
            # Send each complete message
            for message in messages:
                await self.send_message(message)
                
        except Exception as e:
            self.logger.error(f"Subscription failed: {e}")
            raise BaseExchangeError(400, f"Subscription failed: {e}")
    
    async def send_message(self, message: Dict[str, Any]) -> None:
        """
        Send complete message object through WebSocket.
        """
        if not self.ws_client or self.connection_state != ConnectionState.CONNECTED:
            raise BaseExchangeError(503, "WebSocket not connected")
        
        try:
            # Send as dict object - WebSocket client handles JSON encoding
            await self.ws_client.send_message(message)
            
        except Exception as e:
            self.logger.error(f"Failed to send message: {e}")
            raise BaseExchangeError(400, f"Message send failed: {e}")
```

### 4. Subscription Response Handling

**New Structure for Tracking Subscription Results**:

```python
@dataclass
class SubscriptionResult:
    """Result of subscription operation."""
    success: bool
    channel: Optional[str] = None
    symbols: Optional[List[Symbol]] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
```

**Message Parser Integration**:
```python
class GateioPublicMessageParser(MessageParser):
    
    async def parse_message(self, raw_message: Any) -> Optional[ParsedMessage]:
        """
        Parse Gate.io WebSocket messages including subscription responses.
        """
        try:
            # Parse JSON
            if isinstance(raw_message, str):
                message = msgspec.json.decode(raw_message)
            else:
                message = raw_message
            
            # Check if subscription response first
            subscription_result = await self.subscription_strategy.parse_subscription_response(message)
            if subscription_result:
                return ParsedMessage(
                    message_type=MessageType.SUBSCRIPTION_CONFIRM if subscription_result.success else MessageType.ERROR,
                    data={'subscription_result': subscription_result}
                )
            
            # Handle regular data messages...
            
        except Exception as e:
            self.logger.error(f"Error parsing message: {e}")
            return None
```

## Implementation Steps

### Phase 1: Core Interface Refactoring
1. **Update SubscriptionStrategy base class** - Remove channel methods, add new interface
2. **Update WebSocketManager V2** - Simplify subscription flow  
3. **Add SubscriptionResult structure** - For response tracking
4. **Update MessageParser base** - Add subscription response parsing

### Phase 2: Exchange-Specific Implementation
1. **Implement Gate.io public strategy** - Complete message objects with proper format
2. **Implement Gate.io private strategy** - !all pattern with no payload for balances
3. **Implement MEXC public strategy** - Protobuf channel generation
4. **Implement MEXC private strategy** - Private channel message format

### Phase 3: Testing and Validation
1. **Test Gate.io public WebSocket** - Verify message format acceptance
2. **Test Gate.io private WebSocket** - Verify authentication and !all pattern
3. **Test MEXC public WebSocket** - Verify protobuf compatibility  
4. **Test MEXC private WebSocket** - Verify private message handling

### Phase 4: Clean Up
1. **Remove deprecated methods** - Clean up old channel-based code
2. **Update documentation** - Reflect new architecture
3. **Performance validation** - Ensure HFT compliance maintained

## Breaking Changes Summary

1. **SubscriptionStrategy interface completely changed** - No backward compatibility
2. **WebSocketManager subscription flow simplified** - No channel concatenation
3. **Message format assumption removed** - Each exchange creates complete objects  
4. **Symbol-only input requirement** - Internal channel generation
5. **Subscription response parsing added** - Error handling based on WebSocket responses

## Benefits of New Architecture

1. **Exchange-native message formats** - No forced abstractions
2. **Simplified flow** - Direct symbols → messages → send  
3. **Proper error handling** - Based on actual WebSocket responses
4. **Cleaner code** - Single responsibility for each component
5. **HFT compliance maintained** - No additional processing overhead
6. **Future-proof** - Easy to add new exchanges with different message formats

## Risk Mitigation

1. **Comprehensive testing** - Validate each exchange individually
2. **Gradual rollout** - Test public before private WebSockets
3. **Error logging enhanced** - Detailed logging for debugging
4. **Fallback planning** - Keep old V1 implementations as backup
5. **Performance monitoring** - Ensure latency targets maintained