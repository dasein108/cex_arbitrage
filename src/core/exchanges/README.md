# Exchange Interface System

Core interface patterns and contracts defining the unified interface system for seamless exchange integration.

## Overview

The `src/exchanges/interface/` directory defines the **Abstract Factory pattern** that enables seamless integration of multiple cryptocurrency exchanges with consistent APIs and behavior.

## Architecture Pattern

The interface system follows a **layered abstraction approach**:

```
BaseExchangeInterface (Unified)
├── REST Interfaces
│   ├── PublicExchangeInterface (Market Data)
│   └── PrivateExchangeInterface (Trading Operations)
└── WebSocket Interfaces
    ├── BaseExchangeWebsocketInterface (Real-time Data)
    ├── PublicWebsocketInterface (Market Streams)
    └── PrivateWebsocketInterface (Account Streams)
```

## Core Components

### Data Structures (`structs.py`)

Unified data structures using `msgspec.Struct` for maximum performance and type safety.

#### Trading Enums
```python
class OrderStatus(IntEnum):
    UNKNOWN = -1
    NEW = 1
    FILLED = 2
    PARTIALLY_FILLED = 3
    CANCELED = 4
    PARTIALLY_CANCELED = 5
    EXPIRED = 6
    REJECTED = 7

class OrderType(IntEnum):
    LIMIT = 1
    MARKET = 2
    LIMIT_MAKER = 3
    IMMEDIATE_OR_CANCEL = 4
    FILL_OR_KILL = 5
    STOP_LIMIT = 6
    STOP_MARKET = 7

class Side(IntEnum):
    BUY = 1
    SELL = 2

class TimeInForce(IntEnum):
    GTC = 1  # Good Till Cancelled
    IOC = 2  # Immediate or Cancel
    FOK = 3  # Fill or Kill
    GTD = 4  # Good Till Date
```

#### Core Data Structures
```python
class Symbol(Struct, frozen=True):
    """Immutable trading symbol representation"""
    base: AssetName
    quote: AssetName
    is_futures: bool = False

class OrderBook(Struct):
    """Real-time order book data"""
    bids: list[OrderBookEntry]
    asks: list[OrderBookEntry]
    timestamp: float

class Order(Struct):
    """Unified order representation"""
    symbol: Symbol
    side: Side
    order_type: OrderType
    price: float
    amount: float
    amount_filled: float = 0.0
    order_id: Optional[OrderId] = None
    client_order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.NEW
    timestamp: Optional[datetime] = None
    fee: float = 0.0

class AssetBalance(Struct):
    """Account balance information"""
    asset: AssetName
    available: float = 0.0
    free: float = 0.0
    locked: float = 0.0
    
    @property
    def total(self) -> float:
        return self.free + self.locked
```

#### Market Data Structures
```python
class Trade(Struct):
    """Individual trade/execution"""
    price: float
    amount: float
    side: Side
    timestamp: int
    is_maker: bool = False

class Ticker(Struct):
    """24hr ticker price change statistics"""
    symbol: Symbol
    price: float
    price_change: float = 0.0
    price_change_percent: float = 0.0
    high_price: float = 0.0
    low_price: float = 0.0
    volume: float = 0.0
    quote_volume: float = 0.0
    open_price: float = 0.0
    timestamp: float = 0.0
```

#### Performance Optimizations
- **msgspec.Struct**: 3-5x performance gain over dataclasses
- **Frozen structures**: Hashable and immutable for caching
- **IntEnum**: Optimized comparisons and serialization
- **NewType aliases**: Type safety without runtime overhead

### Base Exchange Interface (`base_exchange.py`)

Unified interface combining both public and private exchange operations.

#### Key Properties
```python
class BaseExchangeInterface(ABC):
    
    @property
    @abstractmethod
    def orderbook(self) -> OrderBook:
        """Current primary orderbook snapshot"""
        pass
        
    @property
    @abstractmethod
    def balances(self) -> Dict[Symbol, AssetBalance]:
        """Current account balances mapped by symbol"""
        pass
        
    @property 
    @abstractmethod
    def active_symbols(self) -> List[Symbol]:
        """Currently subscribed symbols"""
        pass
        
    @property
    @abstractmethod
    def open_orders(self) -> Dict[Symbol, List[Order]]:
        """Open orders by symbol"""
        pass
```

#### Lifecycle Management
```python
@abstractmethod
async def init(self, symbols: List[Symbol] = None) -> None:
    """Initialize exchange with optional symbol list"""
    pass

@abstractmethod
async def add_symbol(self, symbol: Symbol) -> None:
    """Start data streaming for symbol"""
    pass

@abstractmethod
async def remove_symbol(self, symbol: Symbol) -> None:
    """Stop data streaming for symbol"""
    pass
```

### REST Interfaces

#### PublicExchangeInterface (`rest/base_rest_public.py`)

Interface for public market data operations (no authentication required).

```python
class PublicExchangeInterface(ABC):
    """Abstract exchanges for public exchange operations"""
    
    @abstractmethod
    async def get_exchange_info(self) -> Dict[Symbol, SymbolInfo]:
        """Get trading rules and symbol information"""
        pass
        
    @abstractmethod
    async def get_orderbook(self, symbol: Symbol, limit: int = 100) -> OrderBook:
        """Get order book for symbol"""
        pass
        
    @abstractmethod
    async def get_recent_trades(self, symbol: Symbol, limit: int = 500) -> List[Trade]:
        """Get recent trades for symbol"""
        pass
        
    @abstractmethod
    async def get_server_time(self) -> int:
        """Get exchange server timestamp"""
        pass
        
    @abstractmethod
    async def ping(self) -> bool:
        """Test connectivity to exchange"""
        pass
```

#### PrivateExchangeInterface (`rest/base_rest_private.py`)

Interface for authenticated trading operations.

```python
class PrivateExchangeInterface(ABC):
    """Abstract exchanges for private exchange operations"""
    
    # Account Management
    @abstractmethod
    async def get_account_balance(self) -> List[AssetBalance]:
        """Get account balance for all assets"""
        pass
        
    @abstractmethod
    async def get_asset_balance(self, asset: AssetName) -> Optional[AssetBalance]:
        """Get balance for specific asset"""
        pass
    
    # Order Management
    @abstractmethod
    async def place_order(
        self,
        symbol: Symbol,
        side: Side,
        order_type: OrderType,
        amount: Optional[float] = None,
        price: Optional[float] = None,
        **kwargs
    ) -> Order:
        """Place new order"""
        pass
        
    @abstractmethod
    async def cancel_order(self, symbol: Symbol, order_id: OrderId) -> Order:
        """Cancel existing order"""
        pass
        
    @abstractmethod
    async def cancel_all_orders(self, symbol: Symbol) -> List[Order]:
        """Cancel all open orders for symbol"""
        pass
        
    @abstractmethod
    async def get_order(self, symbol: Symbol, order_id: OrderId) -> Order:
        """Get order status"""
        pass
        
    @abstractmethod
    async def get_open_orders(self, symbol: Optional[Symbol] = None) -> List[Order]:
        """Get all open orders"""
        pass
        
    @abstractmethod
    async def modify_order(
        self,
        symbol: Symbol,
        order_id: OrderId,
        amount: Optional[float] = None,
        price: Optional[float] = None,
        **kwargs
    ) -> Order:
        """Modify existing order"""
        pass
```

### WebSocket Interfaces

#### BaseExchangeWebsocketInterface (`websocket/base_ws.py`)

Abstract base interface for real-time data streaming.

```python
class BaseExchangeWebsocketInterface(ABC):
    """Abstract exchanges for WebSocket operations"""
    
    def __init__(self, exchange: ExchangeName, config: WebSocketConfig,
                 get_connect_url: Optional[Callable[[], Awaitable[str]]] = None):
        self.exchange = exchange
        self.config = config
        self.symbols: List[Symbol] = []
        self.ws_client = WebsocketClient(config,
                                         message_handler=self._on_message,
                                         error_handler=self.on_error,
                                         get_connect_url=get_connect_url)

    async def init(self, symbols: List[Symbol]):
        """Initialize WebSocket connection with symbols"""
        pass

    async def start_symbol(self, symbol: Symbol):
        """Start streaming data for symbol"""
        pass

    async def stop_symbol(self, symbol: Symbol):
        """Stop streaming data for symbol"""
        pass

    @abstractmethod
    def _create_subscriptions(self, symbol: Symbol, action: SubscriptionAction) -> List[str]:
        """Create exchange-specific subscription messages"""
        pass

    @abstractmethod
    async def _on_message(self, message: Dict[str, Any]):
        """Handle incoming WebSocket messages"""
        pass

    @abstractmethod
    async def on_error(self, error: Exception):
        """Handle WebSocket errors"""
        pass
```

## Implementation Guidelines

### SOLID Principles Compliance

#### Single Responsibility Principle (SRP) ✅
- Each interface focuses on one aspect (public data, private trading, WebSocket streaming)
- Clear separation of concerns between market data and trading operations

#### Open/Closed Principle (OCP) ✅
- Interfaces are closed for modification but open for extension
- New exchanges implement interfaces without changing core contracts

#### Liskov Substitution Principle (LSP) ✅
- All exchange implementations are interchangeable through interfaces
- Consistent behavior and return types across implementations

#### Interface Segregation Principle (ISP) ✅
- Interfaces are focused and cohesive
- Public operations separate from private operations
- Clients depend only on needed interfaces

#### Dependency Inversion Principle (DIP) ✅
- High-level modules depend on abstractions (interfaces)
- Concrete implementations depend on interfaces, not other concrete classes

### Implementation Requirements

#### Mandatory Interface Implementation
All exchange implementations MUST:

1. **Implement all abstract methods** - No partial implementations
2. **Use unified data structures** - From `structs.py` only
3. **Follow error handling patterns** - Use unified exception hierarchy
4. **Maintain type safety** - Comprehensive type annotations
5. **Meet performance targets** - <50ms latency, >95% uptime

#### Performance Requirements
- **Latency**: <50ms for REST operations, <1ms for data parsing
- **Throughput**: Support >1000 messages/second WebSocket processing
- **Memory**: O(1) per operation, efficient object reuse
- **Reliability**: >99.9% uptime with automatic recovery

### Exchange Implementation Pattern

#### 1. Data Structure Mapping
```python
# Map exchange-specific data to unified structures
def transform_exchange_order_to_unified(exchange_order) -> Order:
    return Order(
        symbol=parse_exchange_symbol(exchange_order.symbol),
        side=map_exchange_side(exchange_order.side),
        order_type=map_exchange_order_type(exchange_order.type),
        price=float(exchange_order.price),
        amount=float(exchange_order.quantity),
        # ... other fields
    )
```

#### 2. Error Handling

```python
def handle_exchange_error(exchange_error) -> ExchangeAPIError:
    # Map exchange-specific errors to unified exceptions
    error_code = exchange_error.status_code
    if error_code in RATE_LIMIT_CODES:
        return RateLimitError(429, exchange_error.message,
                              retry_after=exchange_error.retry_after)
    elif error_code in TRADING_DISABLED_CODES:
        return TradingDisabled(403, exchange_error.message)
    else:
        return ExchangeAPIError(400, exchange_error.message)
```

#### 3. WebSocket Integration

```python
async def _on_message(self, message):
    """Process exchange-specific WebSocket messages"""
    if self._is_orderbook_update(message):
        orderbook = self._parse_orderbook(message)
        symbol = self._extract_symbol(message)
        await self._handle_orderbook_diff_update(symbol, orderbook)
    elif self._is_trade_update(message):
        trades = self._parse_trades(message)
        symbol = self._extract_symbol(message)
        await self._handle_trades_update(symbol, trades)
```

## Testing Strategy

### Interface Compliance Testing
```python
class TestExchangeCompliance:
    """Test that exchange implementations comply with interfaces"""
    
    def test_implements_public_interface(self):
        assert isinstance(exchange, PublicExchangeInterface)
        
    def test_implements_private_interface(self):
        assert isinstance(exchange, PrivateExchangeInterface)
        
    def test_returns_correct_types(self):
        orderbook = await exchange.get_orderbook(symbol)
        assert isinstance(orderbook, OrderBook)
        assert all(isinstance(bid, OrderBookEntry) for bid in orderbook.bids)
```

### Performance Testing
```python
async def test_performance_requirements():
    """Verify performance targets are met"""
    start_time = time.time()
    orderbook = await exchange.get_orderbook(symbol)
    latency = time.time() - start_time
    
    assert latency < 0.05  # <50ms requirement
    assert len(orderbook.bids) > 0
    assert len(orderbook.asks) > 0
```

### Integration Testing

```python
async def test_end_to_end_trading():
    """Test complete trading workflow"""
    # Initialize exchange
    await exchange.initialize([symbol])

    # Check initial balance
    balance = await exchange.get_asset_balance(asset)
    initial_free = balance.free

    # Place order
    order = await exchange.place_order(
        symbol=symbol,
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        amount=0.001,
        price=50000.0
    )
    assert order.status == OrderStatus.NEW

    # Check order status
    order_status = await exchange.get_order(symbol, order.order_id)
    assert order_status.order_id == order.order_id

    # Cancel order
    cancelled_order = await exchange.cancel_order(symbol, order.order_id)
    assert cancelled_order.status == OrderStatus.CANCELED
```

## Error Handling Patterns

### Exception Hierarchy Integration
```python
# Exchange implementations should map to unified exceptions
class ExchangeSpecificException(ExchangeAPIError):
    """Map exchange errors to unified hierarchy"""
    pass

# In exchange implementation
def _handle_api_error(self, response):
    if response.status_code == 429:
        raise RateLimitError(429, "Rate limit exceeded", 
                           retry_after=response.headers.get('Retry-After'))
    elif response.status_code >= 500:
        raise ExchangeAPIError(response.status_code, "Server error")
```

### Retry Logic

```python
# Implement intelligent retry logic
async def with_retry(self, operation, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await operation()
        except RateLimitError as e:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(e.retry_after or 1.0)
        except ExchangeAPIError as e:
            if e.status_code >= 500 and attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                raise
```

## Integration Examples

### Public Market Data

```python
from core.exchanges.rest import PublicExchangeSpotRestInterface


class MyExchangePublic(PublicExchangeSpotRestInterface):
    async def get_orderbook(self, symbol: Symbol, limit: int = 100) -> OrderBook:
        # Implementation specific to MyExchange
        response = await self._client.get(f"/orderbook/{symbol}", params={"limit": limit})
        return self._transform_to_orderbook(response, symbol)
```

### Private Trading

```python
from core.exchanges.rest.spot.base_rest_spot_private import PrivateExchangeSpotRestInterface


class MyExchangePrivate(PrivateExchangeSpotRestInterface):
    async def place_order(self, symbol: Symbol, side: Side, order_type: OrderType,
                          amount: float, price: float = None) -> Order:
        # Implementation specific to MyExchange
        params = self._build_order_params(symbol, side, order_type, amount, price)
        response = await self._client.post("/order", params=params)
        return self._transform_to_order(response)
```

### WebSocket Streaming

```python
from core.exchanges.websocket import BaseExchangeWebsocketInterface


class MyExchangeWebSocket(BaseExchangeWebsocketInterface):
    def _create_subscriptions(self, symbol: Symbol, action: SubscriptionAction) -> List[str]:
        symbol_str = f"{symbol.base}{symbol.quote}".upper()
        return [f"orderbook@{symbol_str}", f"trades@{symbol_str}"]

    async def _on_message(self, message):
        if "orderbook" in message.get("stream", ""):
            await self._handle_orderbook_update(message)
        elif "trades" in message.get("stream", ""):
            await self._handle_trades_update(message)
```

## Best Practices

### Interface Design
1. **Keep interfaces focused** - Single responsibility per interface
2. **Use composition over inheritance** - Combine interfaces as needed
3. **Maintain backward compatibility** - Extend interfaces, don't break them
4. **Document contracts clearly** - Specify behavior, not just signatures

### Performance Optimization
1. **Use object pooling** for frequently created objects
2. **Cache static data** - Exchange info, symbol mappings, etc.
3. **Avoid blocking operations** in async methods
4. **Implement circuit breakers** for external API calls

### Error Handling
1. **Fail fast** - Don't silently handle errors
2. **Provide context** - Include relevant error information
3. **Use structured exceptions** - Map to unified hierarchy
4. **Implement retry logic** - With exponential backoff and jitter

### Testing
1. **Test interface compliance** - Ensure all methods implemented
2. **Mock external dependencies** - Test logic, not network calls
3. **Measure performance** - Verify latency and throughput requirements
4. **Integration testing** - Test real exchange behavior