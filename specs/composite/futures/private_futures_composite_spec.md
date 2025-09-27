# CompositePrivateFuturesExchange Interface Specification

## Overview

The `CompositePrivateFuturesExchange` interface extends `CompositePrivateExchange` with futures-specific trading capabilities. It adds leverage management, position control, and futures-specific order types while reusing most spot functionality for efficiency.

## Interface Purpose and Responsibilities

### Primary Purpose
- Provide complete authenticated futures trading functionality
- Manage leverage and margin settings per symbol
- Track and control futures positions (long/short)
- Support futures-specific order types (reduce-only, close position)

### Core Responsibilities
1. **Inherited Trading**: All spot private functionality
2. **Position Management**: Track futures positions with PnL
3. **Leverage Control**: Set and manage leverage per symbol
4. **Margin Management**: Monitor margin levels and requirements
5. **Futures Orders**: Support reduce-only and position closing

## Architectural Position

```
CompositePrivateExchange (parent - inherits all private spot)
    └── CompositePrivateFuturesExchange (adds futures trading)
            └── Implementations:
                    ├── GateioPrivateFuturesExchange
                    ├── BinancePrivateFuturesExchange
                    └── [Other futures exchanges]
```

## Futures-Specific State

### Additional State Management
```python
# Futures-specific private data
self._leverage_settings: Dict[Symbol, Dict] = {}
self._margin_info: Dict[Symbol, Dict] = {}
self._futures_positions: Dict[Symbol, Position] = {}

# Alias for compatibility
self._positions = self._futures_positions  # Backward compatible

# Tag override
self._tag = f'{config.name}_private_futures'
```

### Position Structure
```python
Position(
    symbol=Symbol,
    side=PositionSide.LONG or SHORT,
    quantity=Decimal,          # Position size
    entry_price=Decimal,        # Average entry
    mark_price=Decimal,         # Current mark
    liquidation_price=Decimal,  # Liquidation level
    unrealized_pnl=Decimal,     # Current PnL
    realized_pnl=Decimal,       # Closed PnL
    margin=Decimal,            # Position margin
    leverage=int               # Current leverage
)
```

### Leverage Settings Structure
```python
{
    "symbol": Symbol,
    "leverage": 10,           # Current leverage
    "max_leverage": 125,      # Maximum allowed
    "margin_mode": "ISOLATED" # or "CROSS"
}
```

## Key Abstract Methods

### Leverage Management
```python
@abstractmethod
async def set_leverage(self, symbol: Symbol, leverage: int) -> bool:
    """Set leverage for a symbol"""
    # Validate leverage limits
    if leverage > self._max_leverage_for_symbol(symbol):
        raise ValueError(f"Leverage {leverage} exceeds limit")
    
    # Set via REST API
    success = await self._private_rest.set_leverage(symbol, leverage)
    
    # Update local state
    if success:
        self._leverage_settings[symbol] = {"leverage": leverage}
    
    return success

@abstractmethod
async def get_leverage(self, symbol: Symbol) -> Dict:
    """Get current leverage settings"""
    return self._leverage_settings.get(symbol, {"leverage": 1})
```

### Position Operations

```python
@abstractmethod
async def place_futures_order(
        self,
        symbol: Symbol,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        reduce_only: bool = False,
        close_position: bool = False,
        **kwargs
) -> Order:
    """Place futures order with advanced options"""
    # Handle close position
    if close_position:
        position = self._futures_positions.get(symbol)
        if position:
            side = Side.SELL if position.side == PositionSide.LONG else Side.BUY
            quantity = position.quantity_usdt

    # Place order
    order = await self._private_rest.place_futures_order(
        symbol, side, order_type, quantity, price,
        reduce_only=reduce_only, **kwargs
    )

    return order


@abstractmethod
async def close_position(
        self,
        symbol: Symbol,
        quantity: Optional[Decimal] = None
) -> List[Order]:
    """Close position partially or completely"""
    position = self._futures_positions.get(symbol)
    if not position:
        raise ValueError(f"No position for {symbol}")

    # Determine close parameters
    close_side = Side.SELL if position.side == PositionSide.LONG else Side.BUY
    close_qty = quantity or position.quantity_usdt

    # Place closing order(s)
    orders = []
    order = await self.place_futures_order(
        symbol, close_side, OrderType.MARKET, close_qty,
        reduce_only=True
    )
    orders.append(order)

    return orders
```

### Futures Data Loading
```python
@abstractmethod
async def _load_leverage_settings(self) -> None:
    """Load leverage configuration"""
    for symbol in self._active_symbols:
        settings = await self._private_rest.get_leverage(symbol)
        self._leverage_settings[symbol] = settings

@abstractmethod
async def _load_margin_info(self) -> None:
    """Load margin requirements"""
    margin_data = await self._private_rest.get_margin_info()
    for symbol, info in margin_data.items():
        self._margin_info[symbol] = info

@abstractmethod
async def _load_futures_positions(self) -> None:
    """Load current positions"""
    positions = await self._private_rest.get_positions()
    for position in positions:
        self._futures_positions[position.symbol] = position
```

## Enhanced WebSocket Handlers

### Extended Handler Creation
```python
async def _get_websocket_handlers(self) -> PrivateWebsocketHandlers:
    """Create handlers including position handler"""
    return PrivateWebsocketHandlers(
        order_handler=self._order_handler,
        balance_handler=self._balance_handler,
        execution_handler=self._execution_handler,
        position_handler=self._position_handler  # Futures addition
    )
```

### Position Event Handler

```python
async def _position_handler(self, position: Position) -> None:
    """Handle position updates from WebSocket"""
    # Update position state
    self._update_futures_position(position)

    # Check risk metrics
    if position.margin_ratio > 0.8:
        self.logger.warning(
            "High margin usage",
            symbol=position.symbol,
            ratio=position.margin_ratio,
            liquidation_price=position.liquidation_price
        )

    # Log position change
    self.logger.info(
        "Position updated",
        symbol=position.symbol,
        side=position.side.name,
        size=position.quantity_usdt,
        pnl=position.unrealized_pnl,
        margin=position.margin
    )
```

## Enhanced Initialization

### Futures-Specific Initialization
```python
async def initialize(self, symbols_info: SymbolsInfo) -> None:
    """Initialize with futures-specific data"""
    # Initialize base private functionality
    await super().initialize(symbols_info)
    
    try:
        # Load futures-specific data (parallel)
        await asyncio.gather(
            self._load_leverage_settings(),
            self._load_margin_info(),
            self._load_futures_positions(),
            return_exceptions=True
        )
        
        self.logger.info(
            f"{self._tag} futures data initialized",
            positions=len(self._futures_positions),
            leverage_configs=len(self._leverage_settings)
        )
        
    except Exception as e:
        self.logger.error(f"Futures init failed: {e}")
        raise
```

## Position Management

### Position State Updates
```python
def _update_futures_position(self, position: Position) -> None:
    """Update position with risk calculations"""
    # Store position
    self._futures_positions[position.symbol] = position
    
    # Calculate additional metrics
    if position.mark_price and position.entry_price:
        # Calculate ROE (Return on Equity)
        if position.side == PositionSide.LONG:
            roe = (position.mark_price - position.entry_price) / position.entry_price
        else:
            roe = (position.entry_price - position.mark_price) / position.entry_price
        
        position.roe_percent = roe * position.leverage * 100
    
    self.logger.debug(f"Position updated: {position}")
```

### Risk Monitoring
```python
def get_position_risk(self, symbol: Symbol) -> Dict:
    """Calculate position risk metrics"""
    position = self._futures_positions.get(symbol)
    if not position:
        return {}
    
    mark = position.mark_price
    liquidation = position.liquidation_price
    
    # Distance to liquidation
    if position.side == PositionSide.LONG:
        liq_distance = (mark - liquidation) / mark
    else:
        liq_distance = (liquidation - mark) / mark
    
    return {
        'symbol': symbol,
        'unrealized_pnl': position.unrealized_pnl,
        'margin_ratio': position.margin_ratio,
        'liquidation_distance': liq_distance,
        'leverage': position.leverage,
        'roe_percent': position.roe_percent
    }
```

## Enhanced Trading Statistics

### Futures-Specific Stats
```python
def get_trading_stats(self) -> Dict[str, Any]:
    """Get enhanced trading statistics"""
    base_stats = super().get_trading_stats()
    
    # Add futures metrics
    base_stats['active_positions'] = len(self._futures_positions)
    base_stats['total_unrealized_pnl'] = sum(
        p.unrealized_pnl for p in self._futures_positions.values()
    )
    base_stats['total_margin_used'] = sum(
        p.margin for p in self._futures_positions.values()
    )
    
    # Risk metrics
    high_risk_positions = [
        p for p in self._futures_positions.values()
        if p.margin_ratio > 0.7
    ]
    base_stats['high_risk_positions'] = len(high_risk_positions)
    
    return base_stats
```

## Implementation Pattern

### Minimal Implementation
```python
class BinancePrivateFuturesExchange(CompositePrivateFuturesExchange):
    # Factory methods
    async def _create_private_rest(self) -> PrivateFuturesRest:
        return BinanceFuturesPrivateRest(self.config, self.logger)
    
    async def _create_private_ws_with_handlers(
        self,
        handlers: PrivateWebsocketHandlers
    ) -> PrivateFuturesWebsocket:
        return BinanceFuturesPrivateWebsocket(
            self.config,
            handlers,
            self.logger
        )
    
    # Implement futures-specific methods
    async def set_leverage(self, symbol: Symbol, leverage: int) -> bool:
        return await self._private_rest.set_leverage(symbol, leverage)
    
    # ... other required methods
```

## Dependencies and Relationships

### External Dependencies
- All CompositePrivateExchange dependencies
- `exchanges.structs.common.Position`: Position data
- Futures-specific enums and types

### Internal Relationships
- **Parent**: CompositePrivateExchange (inherits all)
- **Uses**: PrivateFuturesRest, PrivateFuturesWebsocket
- **Sibling**: CompositePublicFuturesExchange

## Implementation Checklist

When implementing futures private composite:

- [ ] Extend CompositePrivateFuturesExchange
- [ ] Implement leverage management methods
- [ ] Implement position operations
- [ ] Add futures data loading methods
- [ ] Override factory methods for futures
- [ ] Test position lifecycle
- [ ] Verify leverage changes
- [ ] Test reduce-only orders
- [ ] Monitor margin levels
- [ ] Validate risk calculations

## Critical Safety Considerations

### Position Safety
```
CRITICAL CHECKS:
- Validate leverage before orders
- Monitor liquidation distance
- Track margin requirements
- Check position limits
- Handle ADL (auto-deleverage) events

NEVER CACHE:
- Position data (real-time changes)
- Margin levels (dynamic)
- Liquidation prices (mark dependent)
- Unrealized PnL (continuous updates)
```

### Order Safety
```python
# Always validate reduce-only orders
if reduce_only and not self._has_position(symbol):
    raise ValueError("Cannot place reduce-only without position")

# Check position before close
if close_position and symbol not in self._futures_positions:
    raise ValueError(f"No position to close for {symbol}")
```

## Future Enhancements

1. **Cross Margin Support**: Shared margin across positions
2. **Hedge Mode**: Simultaneous long/short positions
3. **Portfolio Margin**: Risk-based margining
4. **Auto-Rebalancing**: Maintain target leverage
5. **Liquidation Protection**: Auto-reduce before liquidation