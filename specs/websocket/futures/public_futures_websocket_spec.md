# PublicFuturesWebsocket Interface Specification

## Overview

The `PublicFuturesWebsocket` interface extends `PublicSpotWebsocket` with futures-specific symbol handling. The key enhancement is automatic symbol fixing for futures contracts, ensuring proper formatting across different exchange conventions.

## Interface Purpose and Responsibilities

### Primary Purpose
- Provide futures market data streaming with symbol normalization
- Handle futures-specific data like funding rates and liquidations
- Maintain compatibility with spot WebSocket infrastructure

### Core Responsibilities
1. **Symbol Normalization**: Fix futures symbols to standard format
2. **Inherited Streaming**: All PublicSpotWebsocket functionality
3. **Futures Channels**: Support futures-specific channels (future enhancement)

## Architectural Position

```
PublicSpotWebsocket (parent - inherits all methods)
    └── PublicFuturesWebsocket (minimal extension)
            └── Implementations:
                    ├── GateioFuturesPublicWebsocket
                    ├── BinanceFuturesPublicWebsocket
                    └── [Other futures exchanges]
```

## Key Method Overrides

### 1. `initialize(symbols: List[Symbol], channels: List[PublicWebsocketChannelType]) -> None`
**Purpose**: Initialize with futures symbol normalization
**Implementation**:
```python
async def initialize(self, symbols: List[Symbol], channels=DEFAULT_CHANNELS) -> None:
    # Fix futures symbols before initialization
    fixed_symbols = fix_futures_symbols(symbols)
    await super().initialize(fixed_symbols, channels)
```

### 2. `subscribe(symbols: List[Symbol]) -> None`
**Purpose**: Add symbols with futures formatting
**Implementation**:
```python
async def subscribe(self, symbols: List[Symbol]) -> None:
    # Apply futures symbol fixing
    fixed_symbols = fix_futures_symbols(symbols)
    await super().subscribe(fixed_symbols)
```

### 3. `unsubscribe(symbols: List[Symbol]) -> None`
**Purpose**: Remove symbols with futures formatting
**Implementation**:
```python
async def unsubscribe(self, symbols: List[Symbol]) -> None:
    # Apply futures symbol fixing
    fixed_symbols = fix_futures_symbols(symbols)
    await super().unsubscribe(fixed_symbols)
```

## Symbol Normalization Logic

### fix_futures_symbols Function
```python
def fix_futures_symbols(symbols: List[Symbol]) -> List[Symbol]:
    """
    Normalize futures symbols to standard format
    
    Handles:
    - Perpetual contracts (BTC-USDT → BTCUSDT-PERP)
    - Dated futures (BTC-USDT-231229 → BTCUSDT231229)
    - Contract type suffixes (_PERP, _SWAP, etc.)
    """
    fixed = []
    for symbol in symbols:
        if symbol.is_futures:
            # Apply exchange-specific formatting
            fixed_symbol = _normalize_futures_symbol(symbol)
            fixed.append(fixed_symbol)
        else:
            fixed.append(symbol)
    return fixed
```

### Exchange-Specific Formatting
```python
# Binance Futures Format
"BTCUSDT" → "BTCUSDT"  # Perpetual
"BTCUSDT_231229" → "BTCUSDT_231229"  # Dated

# Gate.io Futures Format  
"BTC_USDT" → "BTC_USDT"  # Uses underscore
"BTC_USDT_20231229" → "BTC_USDT_20231229"

# OKX Format
"BTC-USDT-SWAP" → "BTC-USDT-SWAP"  # Swap suffix
"BTC-USD-231229" → "BTC-USD-231229"  # Dated
```

## Inherited Functionality

All methods from PublicSpotWebsocket are available:
- Connection management
- Handler injection
- Message routing
- Performance monitoring
- State management

### Inherited Handlers
The same `PublicWebsocketHandlers` structure is used:
- `orderbook_handler` - Futures orderbook updates
- `ticker_handler` - Futures ticker data
- `trades_handler` - Futures trades
- `book_ticker_handler` - Best bid/ask updates

## Future-Specific Enhancements (Planned)

### Additional Message Types
```python
# Future enhancements for futures-specific data
MessageType.FUNDING_RATE  # Funding rate updates
MessageType.MARK_PRICE    # Mark price updates
MessageType.LIQUIDATION   # Liquidation events
MessageType.OPEN_INTEREST # Open interest changes
```

### Enhanced Handler Structure
```python
# Future: Extended handlers for futures
class FuturesWebsocketHandlers(PublicWebsocketHandlers):
    funding_rate_handler: Callable[[FundingRate], Awaitable[None]]
    mark_price_handler: Callable[[MarkPrice], Awaitable[None]]
    liquidation_handler: Callable[[Liquidation], Awaitable[None]]
```

## Implementation Guidelines

### 1. Minimal Implementation Pattern
```python
class BinanceFuturesPublicWebsocket(PublicFuturesWebsocket):
    def __init__(self, config, handlers, logger):
        # Configure futures WebSocket URL
        config.websocket_url = "wss://fstream.binance.com/ws"
        super().__init__(config, handlers, logger)
    
    # That's it! Symbol fixing handled by parent
```

### 2. Custom Symbol Format Override
```python
class OKXFuturesPublicWebsocket(PublicFuturesWebsocket):
    def _format_symbol_for_subscription(self, symbol: Symbol) -> str:
        """Override for exchange-specific format"""
        if symbol.is_perpetual:
            return f"{symbol.base}-{symbol.quote}-SWAP"
        else:
            return f"{symbol.base}-{symbol.quote}-{symbol.expiry}"
```

### 3. Futures-Specific Channel Support
```python
async def _subscribe_to_futures_channels(self, symbols: List[Symbol]):
    """Subscribe to futures-specific channels"""
    for symbol in symbols:
        # Standard channels
        await self._subscribe_orderbook(symbol)
        await self._subscribe_trades(symbol)
        
        # Futures-specific channels
        await self._subscribe_funding_rate(symbol)
        await self._subscribe_mark_price(symbol)
```

## Symbol Handling Best Practices

### Symbol Validation
```python
def _validate_futures_symbol(self, symbol: Symbol) -> bool:
    """Validate futures symbol format"""
    # Check if symbol is futures
    if not symbol.is_futures:
        return False
    
    # Validate contract type
    if symbol.contract_type not in ['PERPETUAL', 'DATED']:
        return False
    
    # Check expiry for dated futures
    if symbol.contract_type == 'DATED' and not symbol.expiry:
        return False
    
    return True
```

### Symbol Mapping
```python
# Maintain mapping for symbol conversion
self._symbol_mapping = {
    "BTCUSDT": "BTC_USDT",      # Internal to exchange
    "BTC_USDT": "BTCUSDT",      # Exchange to internal
}
```

## Dependencies and Relationships

### External Dependencies
- All PublicSpotWebsocket dependencies
- `exchanges.utils.exchange_utils.fix_futures_symbols`

### Internal Relationships
- **Parent**: PublicSpotWebsocket (inherits everything)
- **Used By**: CompositePublicFuturesExchange
- **Siblings**: PrivateFuturesWebsocket

## Implementation Checklist

When implementing PublicFuturesWebsocket:

- [ ] Extend PublicFuturesWebsocket class
- [ ] Configure futures WebSocket URL
- [ ] Verify symbol fixing works correctly
- [ ] Test with perpetual contracts
- [ ] Test with dated futures (if supported)
- [ ] Verify all inherited handlers work
- [ ] Add futures-specific channels (if any)
- [ ] Document symbol format requirements
- [ ] Test reconnection with fixed symbols

## Monitoring Considerations

### Futures-Specific Metrics
- Symbol fix success rate
- Futures vs spot message ratio
- Contract type distribution
- Funding rate update frequency (future)

### Symbol Issues Detection
```python
def _log_symbol_issues(self, original: Symbol, fixed: Symbol):
    """Log symbol normalization for debugging"""
    if original != fixed:
        self.logger.debug(
            "Symbol normalized",
            original=str(original),
            fixed=str(fixed),
            is_perpetual=fixed.is_perpetual
        )
```

## Testing Requirements

### Symbol Testing
- Test perpetual contract symbols
- Test dated futures symbols
- Test symbol normalization
- Verify exchange format compliance

### Integration Testing
- Verify futures orderbook streaming
- Test futures trade data
- Confirm symbol subscriptions work
- Test with mixed spot/futures symbols

## Future Enhancements

1. **Funding Rate Streaming**: Real-time funding updates
2. **Mark Price Channel**: Dedicated mark price stream
3. **Liquidation Feed**: Real-time liquidation events
4. **Open Interest Updates**: Position size changes
5. **Index Price Streaming**: Underlying index updates