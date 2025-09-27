# PrivateFuturesRest Interface Specification

## Overview

The `PrivateFuturesRest` interface extends `PrivateSpotRest` with futures-specific trading operations. This interface adds position management, leverage control, and futures-specific order types to the base spot trading capabilities.

## Interface Purpose and Responsibilities

### Primary Purpose
- Enable authenticated futures trading operations
- Provide position and leverage management
- Support futures-specific order types
- Maintain HFT compliance for futures execution

### Core Responsibilities
1. **Position Management**: Query and manage futures positions
2. **Leverage Control**: Set and query leverage settings
3. **Inherited Trading**: All PrivateSpotRest functionality
4. **Futures Orders**: Reduce-only and position closing orders

## Architectural Position

```
PrivateSpotRest (parent - inherits all spot methods)
    └── PrivateFuturesRest (adds futures-specific)
            ├── GateioFuturesPrivateRest (concrete)
            ├── BinanceFuturesPrivateRest (concrete)
            └── [Other futures implementations]
```

## Key Abstract Methods (Futures-Specific)

### 1. `get_positions(symbol: Optional[Symbol] = None) -> List[Position]`
**Purpose**: Retrieve current futures positions
**HFT Requirements**: 
- Must complete within 50ms
- Critical for risk management
- No caching (real-time position data)
**Returns**: List of Position structs
```python
Position(
    symbol=Symbol,
    side=PositionSide.LONG or SHORT,
    quantity=Decimal,  # Position size
    entry_price=Decimal,
    mark_price=Decimal,
    liquidation_price=Decimal,
    unrealized_pnl=Decimal,
    realized_pnl=Decimal,
    margin=Decimal,
    leverage=int
)
```

## Inherited Methods from PrivateSpotRest

### From PrivateTradingInterface
- `get_account_balance()` - Futures wallet balances
- `place_order()` - Place futures orders
- `cancel_order()` - Cancel futures orders
- `get_order()` - Query order status
- `get_open_orders()` - List open orders

### From WithdrawalInterface
- `withdraw()` - Withdraw from futures wallet
- `get_withdrawal_status()` - Check withdrawal
- `get_withdrawal_history()` - Withdrawal history

## Futures-Specific Order Features

### Order Types
```python
# Reduce-only order (only reduces position)
order = await place_order(
    symbol=Symbol("BTC", "USDT"),
    side=Side.SELL,
    quantity=0.1,
    price=50000,
    reduce_only=True  # Futures-specific
)

# Close position order
order = await place_order(
    symbol=Symbol("BTC", "USDT"),
    side=Side.SELL,
    quantity=0.1,
    order_type=OrderType.MARKET,
    close_position=True  # Closes entire position
)
```

### Position Management
```python
# Get all positions
positions = await get_positions()

# Get specific symbol position
btc_positions = await get_positions(Symbol("BTC", "USDT"))

# Check position risk
for position in positions:
    if position.unrealized_pnl < -1000:
        # Risk alert
        await close_position(position.symbol)
```

## Data Flow Patterns

### Position Query Flow
```
1. get_positions() called
2. Authenticated REST request
3. Parse position data with PnL
4. Calculate liquidation prices
5. Return Position structs (no caching)
```

### Leverage Setting Flow
```
1. set_leverage() called with value
2. Validate leverage limits
3. Send authenticated request
4. Update position leverage
5. Confirm new settings
```

## HFT Performance Requirements

### Latency Targets
- **Position Queries**: <50ms (risk critical)
- **Order Operations**: <50ms (same as spot)
- **Leverage Changes**: <100ms (less frequent)

### Position Safety
- Real-time position updates required
- No caching of position data
- Immediate liquidation price updates
- Accurate PnL calculations

## Implementation Guidelines

### 1. Position Query Implementation
```python
async def get_positions(self, symbol: Optional[Symbol] = None) -> List[Position]:
    params = {}
    if symbol:
        params["symbol"] = self._format_futures_symbol(symbol)
    
    response = await self._transport_manager.get(
        endpoint="/futures/positions",
        params=self._sign_request(params)
    )
    
    positions = []
    for pos_data in response:
        positions.append(self._parse_position(pos_data))
    
    return positions
```

### 2. Futures Order Override

```python
async def place_order(self, **kwargs) -> Order:
    # Handle futures-specific parameters
    if kwargs.get("reduce_only"):
        kwargs["type"] = "REDUCE_ONLY"

    if kwargs.get("close_position"):
        # Get current position to determine close side
        position = await self.get_positions(kwargs["symbol"])
        kwargs["side"] = Side.SELL if position.side == PositionSide.LONG else Side.BUY
        kwargs["quantity"] = position.quantity_usdt

    # Call parent implementation
    return await super().place_order(**kwargs)
```

### 3. Position Risk Monitoring
```python
def _parse_position(self, data: Dict) -> Position:
    # Calculate liquidation price
    mark_price = Decimal(data["mark_price"])
    margin = Decimal(data["margin"])
    quantity = Decimal(data["position_amt"])
    
    # Simplified liquidation calculation
    if data["side"] == "LONG":
        liquidation_price = mark_price * (1 - 1/leverage + 0.005)
    else:
        liquidation_price = mark_price * (1 + 1/leverage - 0.005)
    
    return Position(
        symbol=self._parse_symbol(data["symbol"]),
        side=PositionSide[data["side"]],
        quantity=quantity,
        entry_price=Decimal(data["entry_price"]),
        mark_price=mark_price,
        liquidation_price=liquidation_price,
        unrealized_pnl=Decimal(data["unrealized_pnl"]),
        margin=margin,
        leverage=int(data["leverage"])
    )
```

## Risk Management Features

### Position Limits

```python
# Check position limits before ordering
async def validate_position_limit(self, symbol: Symbol, quantity: Decimal):
    positions = await self.get_positions(symbol)
    current_position = sum(p.quantity_usdt for p in positions)

    symbol_info = self.symbols_info[symbol]
    if current_position + quantity > symbol_info.max_position:
        raise PositionLimitExceeded()
```

### Margin Monitoring

```python
# Monitor margin levels
async def check_margin_health(self):
    positions = await self.get_positions()
    balance = await self.get_balances()

    total_margin = sum(p.margin for p in positions)
    free_balance = balance["USDT"].available

    margin_ratio = total_margin / (total_margin + free_balance)
    if margin_ratio > 0.8:  # 80% margin usage
        self.logger.warning("High margin usage", ratio=margin_ratio)
```

## Dependencies and Relationships

### External Dependencies
- All PrivateSpotRest dependencies
- `exchanges.structs.common.Position`: Position data
- Futures-specific enums and types

### Internal Relationships
- **Parent**: PrivateSpotRest (inherits all methods)
- **Used By**: CompositePrivateFuturesExchange
- **Siblings**: PublicFuturesRest (public data)

## Implementation Checklist

When implementing PrivateFuturesRest:

- [ ] Extend PrivateFuturesRest class
- [ ] Implement get_positions()
- [ ] Override place_order() for futures
- [ ] Add reduce_only order support
- [ ] Add close_position order support
- [ ] Implement position parsing
- [ ] Calculate liquidation prices
- [ ] Add margin monitoring
- [ ] Test position lifecycle
- [ ] Verify no position caching

## Critical Safety Rules

### Position Management Safety
```
NEVER CACHE:
- Position data (changes with price)
- Unrealized PnL (continuous updates)
- Liquidation prices (mark price dependent)
- Margin levels (dynamic)

CRITICAL CHECKS:
- Validate leverage before orders
- Monitor liquidation distance
- Track funding payments
- Check position limits
```

## Monitoring and Observability

### Key Metrics
- Position query latency
- Position count by symbol
- Total unrealized PnL
- Margin utilization ratio
- Liquidation distance

### Critical Alerts
- Position query >50ms
- High margin usage (>80%)
- Near liquidation (<5% buffer)
- Failed position updates
- Leverage change failures

## Future Enhancements

1. **Advanced Position Management**: Hedging strategies
2. **Cross Margin**: Shared margin across positions
3. **Portfolio Margin**: Risk-based margining
4. **Auto-Deleverage**: ADL queue monitoring
5. **Funding Optimization**: Funding rate arbitrage