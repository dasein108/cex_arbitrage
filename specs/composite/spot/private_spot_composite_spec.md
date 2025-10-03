# CompositePrivateExchange Interface Specification

## Overview

The `CompositePrivateExchange` interface orchestrates authenticated trading operations by combining private REST and WebSocket interfaces with public market data capabilities. This is the complete trading interface providing order management, balance tracking, and account operations.

**Key Update**: The interface now implements trading capabilities through the protocol-based composition pattern, enabling runtime capability detection and flexible interface composition. Private exchanges implement `TradingCapability`, `BalanceCapability`, and optionally `WithdrawalCapability` protocols.

## Interface Purpose and Responsibilities

### Primary Purpose
- Provide complete authenticated trading functionality
- Combine public market data with private account operations
- Manage order lifecycle and balance updates in real-time
- Ensure HFT-compliant execution with sub-50ms latency

### Core Responsibilities
1. **Trading Operations**: Order placement, cancellation, and tracking
2. **Account Management**: Balance and position monitoring
3. **Order State Management**: Track open and executed orders
4. **WebSocket Integration**: Real-time account updates
5. **Withdrawal Operations**: Cryptocurrency withdrawal support

## Architectural Position

```
CompositePublicExchange (parent - inherits all public functionality)
    └── CompositePrivateExchange (adds private operations)
            ├── Uses: PrivateSpotRest (authenticated REST)
            ├── Uses: PrivateSpotWebsocket (authenticated WS)
            └── Implementations:
                    ├── MexcPrivateExchange
                    ├── GateioPrivateExchange
                    └── [Other exchanges]
```

## Key Components and State

### Private State Management
```python
# Account state (HFT: no caching of real-time data)
self._balances: Dict[AssetName, AssetBalance] = {}
self._open_orders: Dict[Symbol, Dict[OrderId, Order]] = {}

# Executed orders cache (HFT-safe: completed orders only)
self._executed_orders: Dict[Symbol, Dict[OrderId, Order]] = {}
self._max_executed_orders_per_symbol = 1000  # Memory management

# Client instances
self._private_rest: Optional[PrivateSpotRest] = None
self._private_ws: Optional[PrivateSpotWebsocket] = None

# Connection tracking
self._private_rest_connected = False
self._private_ws_connected = False
```

## Enhanced Order Lifecycle Management

### Order State Tracking
```python
def _update_order(self, order: Order):
    """Smart order state management"""
    if is_order_done(order):
        # Move to executed cache
        self._remove_open_order(order)
        self._update_executed_order(order)
    else:
        # Update open orders
        self._update_open_order(order)
```

### Executed Orders Cache
```python
def _update_executed_order(self, order: Order):
    """Cache completed orders for fast lookups"""
    if order.symbol not in self._executed_orders:
        self._executed_orders[order.symbol] = {}
    
    self._executed_orders[order.symbol][order.order_id] = order
    
    # Prevent memory leak
    if len(self._executed_orders[order.symbol]) > self._max_executed_orders_per_symbol:
        self._cleanup_executed_orders(order.symbol)
```

### Smart Order Lookup

```python
async def get_active_order(self, symbol: Symbol, order_id: OrderId) -> Optional[Order]:
    """Intelligent order retrieval with fallback"""
    # 1. Check open orders (real-time)
    order = self._get_open_order(symbol, order_id)
    if order:
        return order

    # 2. Check executed cache (completed)
    order = self._get_executed_order(symbol, order_id)
    if order:
        return order

    # 3. Fallback to REST API
    try:
        order = await self._private_rest.fetch_order(symbol, order_id)
        self._update_order(order)
        return order
    except Exception as e:
        self.logger.error(f"Order lookup failed: {e}")
        return None
```

## Abstract Factory Methods

### 1. `_create_private_rest() -> PrivateSpotRest`
**Purpose**: Create authenticated REST client
```python
async def _create_private_rest(self) -> PrivateSpotRest:
    return MexcPrivateRest(
        config=self.config,
        logger=self.logger.get_child("rest.private")
    )
```

### 2. `_create_private_ws_with_handlers(handlers: PrivateWebsocketHandlers) -> Optional[PrivateSpotWebsocket]`
**Purpose**: Create authenticated WebSocket with handlers
```python
async def _create_private_ws_with_handlers(
    self,
    handlers: PrivateWebsocketHandlers
) -> Optional[PrivateSpotWebsocket]:
    if not self.config.has_credentials():
        return None
    
    return MexcPrivateWebsocket(
        config=self.config,
        handlers=handlers,  # Injected handlers
        logger=self.logger.get_child("ws.private")
    )
```

## Trading Operations

### Order Placement
```python
async def place_limit_order(
    self,
    symbol: Symbol,
    side: Side,
    quantity: float,
    price: float,
    **kwargs
) -> Order:
    """Place limit order with tracking"""
    # Place via REST
    order = await self._private_rest.place_limit_order(
        symbol, side, quantity, price, **kwargs
    )
    
    # Track in open orders
    self._update_open_order(order)
    
    # Track operation for metrics
    self._track_operation("place_limit_order")
    
    return order
```

### Order Cancellation
```python
async def cancel_order(self, symbol: Symbol, order_id: OrderId) -> Order:
    """Cancel order with state update"""
    # Cancel via REST
    order = await self._private_rest.cancel_order(symbol, order_id)
    
    # Update state
    self._update_order(order)
    
    return order
```

## WebSocket Handler Architecture

### Handler Creation
```python
async def _get_websocket_handlers(self) -> PrivateWebsocketHandlers:
    """Create handlers for private WebSocket"""
    return PrivateWebsocketHandlers(
        order_handler=self._order_handler,
        balance_handler=self._balance_handler,
        execution_handler=self._execution_handler
    )
```

### Handler Implementations

```python
async def _order_handler(self, order: Order) -> None:
    """Process order updates from WebSocket"""
    self._update_order(order)
    self.logger.info(
        "Order updated",
        order_id=order.order_id,
        status=order.status.name,
        filled=f"{order.filled_quantity}/{order.quantity_usdt}"
    )


async def _balance_handler(self, balances: Dict[AssetName, AssetBalance]) -> None:
    """Process balance updates"""
    self._balances.update(balances)
    non_zero = [b for b in balances.values() if b.available > 0 or b.locked > 0]
    self.logger.info(f"Balance updated: {len(non_zero)} non-zero assets")


async def _execution_handler(self, trade: Trade) -> None:
    """Process trade execution events"""
    self.logger.info(
        "Trade executed",
        symbol=trade.symbol,
        side=trade.side.name,
        price=trade.price,
        quantity=trade.quantity_usdt
    )
```

## Initialization Template Method

### Complete Initialization Flow
```python
async def initialize(self, symbols_info: SymbolsInfo) -> None:
    """Initialize with public and private components"""
    # Step 1: Initialize public functionality (parent)
    await super().initialize()
    
    # Step 2: Store symbols info
    self._symbols_info = symbols_info
    
    # Step 3: Create private REST client
    self._private_rest = await self._create_private_rest()
    
    # Step 4: Load private data
    await self._refresh_exchange_data()
    
    # Step 5: Initialize private WebSocket
    await self._initialize_private_websocket()
```

### Private WebSocket Initialization

```python
async def _initialize_private_websocket(self) -> None:
    """Initialize with handler injection"""
    if not self.config.has_credentials():
        return

    # Create handlers
    handlers = await self._create_inner_websocket_handlers()

    # Create WebSocket with handlers
    self._private_ws = await self._create_private_websocket(handlers)

    if self._private_ws:
        await self._private_ws.initialize()
        self._private_ws_connected = True
```

## Data Loading Operations

### Balance Loading

```python
async def _load_balances(self) -> None:
    """Load balances from REST API"""
    with LoggingTimer(self.logger, "load_balances") as timer:
        balances_data = await self._private_rest.get_balances()
        self._balances = balances_data

    self.logger.info(
        "Balances loaded",
        count=len(balances_data),
        time_ms=timer.elapsed_ms
    )
```

### Open Orders Loading
```python
async def _load_open_orders(self) -> None:
    """Load open orders from REST API"""
    with LoggingTimer(self.logger, "load_open_orders") as timer:
        orders = await self._private_rest.get_open_orders()
        for order in orders:
            self._update_open_order(order)
    
    self.logger.info(
        "Open orders loaded",
        count=len(orders),
        time_ms=timer.elapsed_ms
    )
```

## Withdrawal Operations

### Withdrawal Request
```python
async def withdraw(self, request: WithdrawalRequest) -> WithdrawalResponse:
    """Submit withdrawal request"""
    # Validate request
    self._validate_withdrawal_request(request)
    
    # Submit via REST
    response = await self._private_rest.withdraw(request)
    
    # Log for audit
    self.logger.info(
        "Withdrawal submitted",
        asset=request.asset,
        amount=request.amount,
        tx_id=response.transaction_id
    )
    
    return response
```

## HFT Safety Compliance

### Critical Safety Rules
```python
# NEVER CACHE these (real-time data):
- Account balances (change with trades)
- Order status (execution state)
- Open orders (dynamic state)

# SAFE TO CACHE these (static/completed):
- Executed orders (completed, immutable)
- Symbol info (static configuration)
- Withdrawal history (historical data)
```

### Memory Management
```python
def _cleanup_executed_orders(self, symbol: Symbol) -> None:
    """Prevent memory leaks in executed orders cache"""
    executed = self._executed_orders[symbol]
    if len(executed) > self._max_executed_orders_per_symbol:
        # Keep most recent 80%
        target_size = int(self._max_executed_orders_per_symbol * 0.8)
        oldest_keys = list(executed.keys())[:-target_size]
        for key in oldest_keys:
            del executed[key]
```

## Monitoring and Diagnostics

### Trading Statistics
```python
def get_trading_stats(self) -> Dict[str, Any]:
    """Enhanced trading metrics"""
    executed_count = sum(
        len(orders) for orders in self._executed_orders.values()
    )
    
    return {
        'total_balances': len(self._balances),
        'open_orders_count': sum(len(o) for o in self._open_orders.values()),
        'executed_orders_count': executed_count,
        'has_credentials': self.config.has_credentials(),
        'connection_status': {
            'private_rest': self._private_rest_connected,
            'private_ws': self._private_ws_connected
        }
    }
```

## Implementation Guidelines

### Minimal Exchange Implementation
```python
class NewExchangePrivate(CompositePrivateExchange):
    # Only implement 2 factory methods!
    
    async def _create_private_rest(self) -> PrivateSpotRest:
        return NewExchangePrivateRest(self.config, self.logger)
    
    async def _create_private_ws_with_handlers(
        self,
        handlers: PrivateWebsocketHandlers
    ) -> PrivateSpotWebsocket:
        return NewExchangePrivateWebsocket(
            self.config,
            handlers,  # Key: inject handlers
            self.logger
        )
    
    # Optionally override trading methods for exchange-specific logic
```

## Dependencies and Relationships

### External Dependencies
- `exchanges.interfaces.rest.spot`: PrivateSpotRest
- `exchanges.interfaces.ws.spot`: PrivateSpotWebsocket
- All CompositePublicExchange dependencies

### Internal Relationships
- **Parent**: CompositePublicExchange (inherits public)
- **Creates**: Private REST and WebSocket clients
- **Extended By**: CompositePrivateFuturesExchange

## Implementation Checklist

When implementing for a new exchange:

- [ ] Extend CompositePrivateExchange
- [ ] Implement _create_private_rest()
- [ ] Implement _create_private_ws_with_handlers()
- [ ] Test order placement and cancellation
- [ ] Verify balance loading
- [ ] Test WebSocket order updates
- [ ] Check executed orders cache
- [ ] Test withdrawal operations
- [ ] Monitor memory usage
- [ ] Verify HFT compliance

## Critical Benefits

### Architecture Benefits
- **Inheritance Reuse**: All public functionality included
- **Handler Injection**: Clean separation of concerns
- **State Management**: Intelligent order tracking
- **Memory Safety**: Automatic cache cleanup

### Performance Benefits
- **Smart Lookups**: Multi-level order retrieval
- **Cached Completions**: Fast executed order access
- **Parallel Loading**: Concurrent data initialization
- **HFT Compliance**: No real-time data caching

## Future Enhancements

1. **Order Book Integration**: Combine private orders with orderbook
2. **Risk Management**: Automated position limits
3. **Smart Order Router**: Multi-exchange order routing
4. **Portfolio Analytics**: Real-time PnL tracking
5. **Advanced Order Types**: OCO, trailing stop support