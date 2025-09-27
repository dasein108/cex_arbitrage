# PrivateFuturesWebsocket Interface Specification

## Overview

The `PrivateFuturesWebsocket` interface extends `PrivateSpotWebsocket` for futures trading. Currently a minimal extension, it inherits all private spot WebSocket functionality while providing a foundation for future futures-specific enhancements.

## Interface Purpose and Responsibilities

### Primary Purpose
- Provide authenticated futures trading updates via WebSocket
- Handle futures position updates (planned enhancement)
- Maintain compatibility with spot private WebSocket

### Core Responsibilities
1. **Inherited Functionality**: All PrivateSpotWebsocket capabilities
2. **Future Position Support**: Framework for position updates
3. **Futures Order Events**: Futures-specific order handling (planned)

## Architectural Position

```
PrivateSpotWebsocket (parent - inherits all)
    └── PrivateFuturesWebsocket (minimal extension)
            └── Implementations:
                    ├── GateioFuturesPrivateWebsocket
                    ├── BinanceFuturesPrivateWebsocket
                    └── [Other futures exchanges]
```

## Current Implementation

### Minimal Extension
```python
class PrivateFuturesWebsocket(PrivateSpotWebsocket):
    pass  # Currently inherits everything
```

## Inherited Functionality

All methods and handlers from PrivateSpotWebsocket:

### Inherited Handlers
- `order_handler` - Futures order updates
- `balance_handler` - Futures wallet balance changes
- `execution_handler` - Futures trade executions

### Inherited Methods
- Authentication management
- Message routing
- Connection handling
- State management

## Planned Enhancements

### Position Handler Support
```python
class PrivateFuturesWebsocket(PrivateSpotWebsocket):
    async def _handle_position_message(self, parsed_message) -> None:
        """Handle position update messages"""
        try:
            if parsed_message.data:
                # Position handler available in futures composite
                if hasattr(self.handlers, 'position_handler'):
                    await self.handlers.position_handler(parsed_message.data)
        except Exception as e:
            self.logger.error(f"Error handling position: {e}")
```

### Enhanced Message Routing
```python
async def _handle_parsed_message(self, parsed_message) -> None:
    """Extended routing for futures messages"""
    # Handle standard private messages
    await super()._handle_parsed_message(parsed_message)
    
    # Add futures-specific message types
    if parsed_message.message_type == MessageType.POSITION:
        await self._handle_position_message(parsed_message)
    
    elif parsed_message.message_type == MessageType.MARGIN_CALL:
        await self._handle_margin_call(parsed_message)
    
    elif parsed_message.message_type == MessageType.LIQUIDATION_WARNING:
        await self._handle_liquidation_warning(parsed_message)
```

## Futures-Specific Events (Planned)

### Position Events
```
POSITION_OPENED - New position created
POSITION_UPDATED - Size/margin changed
POSITION_CLOSED - Position fully closed
POSITION_LIQUIDATED - Forced liquidation
```

### Margin Events
```
MARGIN_CALL - Margin requirement increased
MARGIN_UPDATED - Margin balance changed
AUTO_MARGIN - Auto margin adjustment
```

### Risk Events
```
LIQUIDATION_WARNING - Near liquidation
LIQUIDATION_EXECUTED - Position liquidated
ADL_WARNING - Auto-deleveraging risk
```

## Implementation Pattern

### Current Minimal Implementation
```python
class BinanceFuturesPrivateWebsocket(PrivateFuturesWebsocket):
    def __init__(self, config, handlers, logger):
        # Configure futures private WebSocket
        config.private_websocket_url = "wss://fstream.binance.com/ws"
        super().__init__(config, handlers, logger)
    
    # Everything else inherited from PrivateSpotWebsocket
```

### Future Enhanced Implementation
```python
class BinanceFuturesPrivateWebsocket(PrivateFuturesWebsocket):
    async def _subscribe_to_private_channels(self):
        """Subscribe to futures-specific channels"""
        # Standard private channels
        await super()._subscribe_to_private_channels()
        
        # Futures-specific channels
        channels = [
            "futures.positions",     # Position updates
            "futures.margin",        # Margin changes
            "futures.liquidation"    # Risk warnings
        ]
        
        for channel in channels:
            await self._ws_manager.subscribe(channel)
```

## Position Update Handler (Future)

### Handler Interface Extension
```python
class FuturesPrivateWebsocketHandlers(PrivateWebsocketHandlers):
    position_handler: Callable[[Position], Awaitable[None]]
    margin_handler: Callable[[MarginInfo], Awaitable[None]]
    liquidation_handler: Callable[[LiquidationWarning], Awaitable[None]]
```

### Position Event Processing

```python
async def _position_handler(self, position: Position) -> None:
    """Process position updates in composite layer"""
    # Update position state
    self._futures_positions[position.symbol] = position

    # Check risk metrics
    if position.margin_ratio > 0.8:
        self.logger.warning(
            "High margin usage",
            symbol=position.symbol,
            ratio=position.margin_ratio
        )

    # Track PnL
    self.logger.info(
        "Position updated",
        symbol=position.symbol,
        size=position.quantity_usdt,
        pnl=position.unrealized_pnl
    )
```

## Authentication Considerations

### Futures-Specific Auth
```python
async def _authenticate(self):
    """Authenticate for futures private data"""
    # Standard authentication
    await super()._authenticate()
    
    # Request initial position snapshot
    await self._request_positions_snapshot()
    
    # Set leverage preferences
    await self._configure_leverage_settings()
```

## Dependencies and Relationships

### External Dependencies
- All PrivateSpotWebsocket dependencies
- Future: Position, MarginInfo data structures

### Internal Relationships
- **Parent**: PrivateSpotWebsocket (inherits all)
- **Used By**: CompositePrivateFuturesExchange
- **Handlers From**: CompositePrivateFuturesExchange
- **Siblings**: PublicFuturesWebsocket

## Implementation Checklist

For current minimal implementation:

- [ ] Extend PrivateFuturesWebsocket class
- [ ] Configure futures private WebSocket URL
- [ ] Verify authentication works
- [ ] Test order updates for futures
- [ ] Test balance updates
- [ ] Test trade executions
- [ ] Document any futures-specific behavior

For future enhanced implementation:

- [ ] Add position message handling
- [ ] Implement margin event processing
- [ ] Add liquidation warning support
- [ ] Extend handler interface
- [ ] Test position lifecycle
- [ ] Add risk monitoring
- [ ] Implement position snapshot sync

## Monitoring Considerations

### Current Metrics
- All PrivateSpotWebsocket metrics apply
- Order update latency
- Balance change frequency
- Authentication success rate

### Future Metrics
- Position update frequency
- Margin utilization
- Liquidation warnings
- Position count by symbol
- PnL tracking

## Testing Requirements

### Current Testing
- Verify futures order events
- Test futures balance updates
- Confirm trade executions
- Test authentication flow

### Future Testing
- Position lifecycle events
- Margin call scenarios
- Liquidation warnings
- Risk event handling
- Position/order synchronization

## Migration Path

### From Current to Enhanced
```python
# Step 1: Add position handler to composite
async def _get_websocket_handlers(self) -> PrivateWebsocketHandlers:
    handlers = await super()._get_websocket_handlers()
    handlers.position_handler = self._position_handler
    return handlers

# Step 2: Update WebSocket to handle position messages
# (Implementation in PrivateFuturesWebsocket)

# Step 3: Test with exchanges that support position updates
# No breaking changes for exchanges without position support
```

## Future Enhancements

1. **Position Streaming**: Real-time position updates
2. **Margin Monitoring**: Margin call notifications
3. **Risk Alerts**: Liquidation warnings
4. **Funding Payments**: Real-time funding events
5. **Cross Margin**: Unified margin updates
6. **Portfolio View**: Aggregate position tracking