# Separated Domain Exchange Architecture

Complete documentation for the CEX Arbitrage Engine's **separated domain architecture** that completely isolates public market data and private trading operations into independent interfaces with constructor injection patterns, optimized for HFT arbitrage trading.

## Architecture Evolution Summary

### **Separated Domain Implementation (September 2025)**

**Eliminated Legacy Unified Approach**:
- ❌ **Single unified interface complexity** replaced with clean domain separation
- ❌ **Factory method patterns** replaced with constructor injection
- ❌ **Abstract factory hierarchies** simplified to direct mapping tables
- ❌ **Interface segregation overhead** eliminated with focused domain interfaces

**Achieved Separated Domain Excellence**:
- ✅ **Complete Domain Isolation** - Public and private operations completely separated
- ✅ **Constructor Injection Pattern** - REST/WebSocket clients injected at creation time
- ✅ **Explicit Cooperative Inheritance** - WebsocketBindHandlerInterface explicitly initialized
- ✅ **Handler Binding Pattern** - WebSocket channels bound using .bind() method
- ✅ **Simplified Factory** - Direct mapping with 76% code reduction (110 vs 467 lines)
- ✅ **HFT Safety Compliance** - No caching of real-time trading data across domains
- ✅ **Performance Achievement** - All HFT targets exceeded with domain-specific optimizations

## Separated Domain Architecture Overview

### **Core Design Philosophy**

**Domain Separation Approach**:
- **Two independent interfaces** - BasePublicComposite and BasePrivateComposite
- **Complete isolation** - No inheritance or shared state between domains
- **Authentication boundary** - Clear separation of authenticated vs non-authenticated operations
- **HFT performance targets** - Sub-50ms execution with domain-specific optimizations
- **Constructor injection** - Dependencies injected at creation time, not via factory methods
- **Clear responsibility** - Market data observation separate from trade execution

### **Domain Interface Hierarchy**

```
BasePublicComposite (Market Data Domain)
├── Orderbook Operations (real-time streaming)
├── Market Data (tickers, trades, symbols)
├── Symbol Information (trading rules, precision)
└── Connection Management (public WebSocket lifecycle)

BasePrivateComposite (Trading Domain - Separate)
├── Trading Operations (orders, positions, balances)
├── Account Management (portfolio tracking)
├── Trade Execution (spot and futures support)
└── Connection Management (private WebSocket lifecycle)
```

**Key Domain Separation Principles**:
1. **No Inheritance** - Private exchanges do NOT inherit from public exchanges
2. **Complete Isolation** - Public and private domains have no overlap or shared state
3. **Authentication Boundary** - Public operations require no auth, private operations require credentials
4. **Independent Scaling** - Each domain optimizes independently for specific use cases
5. **Constructor Injection** - Dependencies injected at creation time via constructor parameters

## BasePublicComposite Interface

### **Public Domain Specification**

```python
class BasePublicComposite(BaseCompositeExchange[PublicRestType, PublicWebsocketType],
                          WebsocketBindHandlerInterface[PublicWebsocketChannelType]):
    """
    Base public composite exchange interface for market data operations.
    
    This interface handles ONLY public market data operations that require
    no authentication. Completely isolated from trading operations.
    """
    
    def __init__(self, 
                 config: ExchangeConfig,
                 rest_client: PublicRestType,
                 websocket_client: PublicWebsocketType,
                 logger: Optional[HFTLoggerInterface] = None):
        """
        Initialize public exchange interface with dependency injection.
        
        Args:
            config: Exchange configuration (credentials not required)
            rest_client: Injected public REST client instance
            websocket_client: Injected public WebSocket client instance
            logger: Optional injected HFT logger
        """
        # Explicit cooperative inheritance pattern
        WebsocketBindHandlerInterface.__init__(self)
        super().__init__(config, rest_client=rest_client, websocket_client=websocket_client, 
                         is_private=False, logger=logger)
        
        # Handler binding pattern - WebSocket channels bound to handler methods
        websocket_client.bind(PublicWebsocketChannelType.BOOK_TICKER, self._handle_book_ticker)
        websocket_client.bind(PublicWebsocketChannelType.ORDERBOOK, self._handle_orderbook)
        websocket_client.bind(PublicWebsocketChannelType.TICKER, self._handle_ticker)
        websocket_client.bind(PublicWebsocketChannelType.PUB_TRADE, self._handle_trade)
        
    # ========================================
    # Market Data Operations (NO Authentication Required)
    # ========================================
    
    @property
    @abstractmethod
    def symbols_info(self) -> Optional[SymbolsInfo]:
        """Get symbols information and trading rules."""
        
    @property
    def active_symbols(self) -> Set[Symbol]:
        """Get currently active symbols for market data streaming."""
        
    @property
    def orderbooks(self) -> Dict[Symbol, OrderBook]:
        """Get current orderbooks for all active symbols."""
        
    async def get_book_ticker(self, symbol: Symbol, force=False) -> Optional[BookTicker]:
        """Get current best bid/ask for symbol. HFT OPTIMIZED: <500μs processing."""
        
    async def add_symbol(self, symbol: Symbol) -> None:
        """Start streaming data for a new symbol."""
        
    async def remove_symbol(self, symbol: Symbol) -> None:
        """Stop streaming data for a symbol."""
        
    # Handler methods for WebSocket events (bound via .bind() pattern)
    async def _handle_orderbook(self, orderbook: OrderBook) -> None:
        """Handle orderbook updates from WebSocket."""
        
    async def _handle_ticker(self, ticker: Ticker) -> None:
        """Handle ticker updates from WebSocket."""
        
    async def _handle_trade(self, trade: Trade) -> None:
        """Handle trade updates from WebSocket."""
        
    async def _handle_book_ticker(self, book_ticker: BookTicker) -> None:
        """Handle book ticker events. HFT CRITICAL: <500μs processing time."""
```

### **Public Domain Benefits**

1. **Pure Market Data Focus** - Only handles orderbooks, tickers, trades, symbols
2. **No Authentication Required** - All operations are public, no API credentials needed
3. **HFT Optimized** - Sub-500μs book ticker processing, <1ms orderbook access
4. **Constructor Injection** - REST/WebSocket clients injected at creation time
5. **Handler Binding** - WebSocket channels explicitly bound in constructor
6. **Performance Tracking** - Built-in metrics for HFT compliance monitoring

## BasePrivateComposite Interface

### **Private Domain Specification**

```python
class BasePrivateComposite(BaseCompositeExchange[PrivateRestType, PrivateWebsocketType],
                           WebsocketBindHandlerInterface[PrivateWebsocketChannelType]):
    """
    Base private composite exchange interface for trading operations.
    
    This interface handles ONLY private trading operations that require
    authentication. Completely isolated from public market data.
    """
    
    def __init__(self,
                 config: ExchangeConfig,
                 rest_client: PrivateRestType,
                 websocket_client: PrivateWebsocketType,
                 logger: Optional[HFTLoggerInterface] = None):
        """
        Initialize private exchange interface with dependency injection.
        
        Args:
            config: Exchange configuration with API credentials
            rest_client: Injected private REST client instance
            websocket_client: Injected private WebSocket client instance
            logger: Optional injected HFT logger
        """
        # Explicit cooperative inheritance pattern
        WebsocketBindHandlerInterface.__init__(self)
        super().__init__(config, rest_client=rest_client, websocket_client=websocket_client,
                         is_private=True, logger=logger)
        
        # Handler binding pattern - WebSocket channels bound to handler methods
        websocket_client.bind(PrivateWebsocketChannelType.BALANCE, self._balance_handler)
        websocket_client.bind(PrivateWebsocketChannelType.ORDER, self._order_handler)
        websocket_client.bind(PrivateWebsocketChannelType.EXECUTION, self._execution_handler)
        
        # Authentication validation
        if not config.has_credentials():
            self.logger.error("No API credentials provided - trading operations will fail")
            
    # ========================================
    # Trading Operations (Authentication Required)
    # ========================================
    
    # HFT SAFETY RULE: All trading data methods are async and fetch fresh from API
    # NEVER cache real-time trading data (balances, orders, positions)
    
    @property
    def balances(self) -> Dict[AssetName, AssetBalance]:
        """Get current account balances (thread-safe copy)."""
        
    @property
    def open_orders(self) -> Dict[Symbol, List[Order]]:
        """Get current open orders (thread-safe copy)."""
        
    async def get_open_orders(self, symbol: Optional[Symbol] = None, force=False) -> List[Order]:
        """Get current open orders with optional fresh API call. HFT COMPLIANT."""
        
    async def place_limit_order(self, symbol: Symbol, side: Side, quantity: float, price: float, **kwargs) -> Order:
        """Place a limit order. HFT TARGET: <50ms execution time."""
        
    async def place_market_order(self, symbol: Symbol, side: Side, quote_quantity: float, **kwargs) -> Order:
        """Place a market order. HFT TARGET: <50ms execution time."""
        
    async def cancel_order(self, symbol: Symbol, order_id: OrderId) -> Order:
        """Cancel an order. HFT TARGET: <50ms execution time."""
        
    async def get_order(self, symbol: Symbol, order_id: OrderId) -> Order:
        """Get current status of an order with fresh API call."""
        
    async def get_asset_balance(self, asset: AssetName, force=False) -> Optional[AssetBalance]:
        """Get balance for specific asset with optional fresh API call."""
        
    # Handler methods for WebSocket events (bound via .bind() pattern)
    async def _order_handler(self, order: Order) -> None:
        """Handle order update events from private WebSocket."""
        
    async def _balance_handler(self, balance: AssetBalance) -> None:
        """Handle balance update events from private WebSocket."""
        
    async def _execution_handler(self, trade: Trade) -> None:
        """Handle execution report/trade events from private WebSocket."""
```

### **Private Domain Benefits**

1. **Pure Trading Focus** - Only handles orders, balances, positions, executions
2. **Authentication Required** - All operations require valid API credentials
3. **HFT Safety Compliant** - No caching of real-time trading data
4. **Constructor Injection** - Private REST/WebSocket clients injected at creation time
5. **Handler Binding** - Private WebSocket channels explicitly bound in constructor
6. **Real-time Updates** - WebSocket-based order and balance updates

## Simplified Exchange Factory

### **Direct Mapping Factory Design**

The new factory eliminates complex validation and decision matrices by using simple dictionary-based lookups with constructor injection.

```python
# Direct mapping tables for component lookup
EXCHANGE_REST_MAP = {
    (ExchangeEnum.MEXC, False): MexcPublicSpotRestInterface,
    (ExchangeEnum.MEXC, True): MexcPrivateSpotRestInterface,
    (ExchangeEnum.GATEIO, False): GateioPublicSpotRestInterface,
    (ExchangeEnum.GATEIO, True): GateioPrivateSpotRestInterface,
    (ExchangeEnum.GATEIO_FUTURES, False): GateioPublicFuturesRestInterface,
    (ExchangeEnum.GATEIO_FUTURES, True): GateioPrivateFuturesRestInterface,
}

EXCHANGE_WS_MAP = {
    (ExchangeEnum.MEXC, False): MexcPublicSpotWebsocket,
    (ExchangeEnum.MEXC, True): MexcPrivateSpotWebsocket,
    (ExchangeEnum.GATEIO, False): GateioPublicSpotWebsocket,
    (ExchangeEnum.GATEIO, True): GateioPrivateSpotWebsocket,
    (ExchangeEnum.GATEIO_FUTURES, False): GateioPublicFuturesWebsocket,
    (ExchangeEnum.GATEIO_FUTURES, True): GateioPrivateFuturesWebsocket,
}

# (is_futures, is_private) -> Composite Class
COMPOSITE_AGNOSTIC_MAP = {
    (False, False): CompositePublicSpotExchange,
    (False, True): CompositePrivateSpotExchange,
    (True, False): CompositePublicFuturesExchange,
    (True, True): CompositePrivateFuturesExchange,
}

def get_composite_implementation(exchange_config: ExchangeConfig, is_private: bool):
    """Create composite exchange with constructor injection pattern."""
    # Create components using direct mapping
    rest_client = get_rest_implementation(exchange_config, is_private)
    ws_client = get_ws_implementation(exchange_config, is_private)
    is_futures = exchange_config.is_futures
    
    # Get composite class from mapping
    composite_class = COMPOSITE_AGNOSTIC_MAP.get((is_futures, is_private))
    if not composite_class:
        raise ValueError(f"No Composite implementation found for exchange {exchange_config.name}")
    
    # Constructor injection pattern - pass dependencies at creation time
    return composite_class(exchange_config, rest_client, ws_client)
```

### **Factory Benefits**

1. **Direct Mapping** - Simple dictionary lookups eliminate complex validation logic
2. **Constructor Injection** - Dependencies passed at creation time, not via factory methods
3. **No Caching** - Eliminates validation and decision matrix complexity
4. **Performance** - 76% code reduction (110 lines vs 467 lines)
5. **Type Safety** - Clear mapping tables prevent runtime errors
6. **Backward Compatibility** - Existing code works via compatibility wrappers

## Constructor Injection Pattern

### **Dependency Injection Architecture**

The constructor injection pattern eliminates factory methods in base classes by injecting all dependencies at creation time.

**Old Pattern (Eliminated)**:
```python
# OLD: Factory methods in base class
class BaseExchange(ABC):
    @abstractmethod
    def _create_rest_client(self) -> RestClient:
        """Abstract factory method - ELIMINATED"""
        
    @abstractmethod 
    def _create_websocket_client(self) -> WebsocketClient:
        """Abstract factory method - ELIMINATED"""
```

**New Pattern (Implemented)**:
```python
# NEW: Constructor injection pattern
class BasePublicComposite:
    def __init__(self, 
                 config: ExchangeConfig,
                 rest_client: PublicRestType,        # INJECTED
                 websocket_client: PublicWebsocketType,  # INJECTED
                 logger: Optional[HFTLoggerInterface] = None):
        
        # Explicit cooperative inheritance
        WebsocketBindHandlerInterface.__init__(self)
        super().__init__(config, rest_client=rest_client, websocket_client=websocket_client, 
                         is_private=False, logger=logger)
        
        # Handler binding pattern
        websocket_client.bind(PublicWebsocketChannelType.ORDERBOOK, self._handle_orderbook)
```

### **Constructor Injection Benefits**

1. **Explicit Dependencies** - All dependencies visible in constructor signature
2. **No Abstract Factory Methods** - Eliminates factory methods in base classes
3. **Clear Initialization** - Dependencies available immediately in constructor
4. **Testability** - Easy to inject mock dependencies for testing
5. **Performance** - No dynamic creation overhead during runtime
6. **Type Safety** - Dependencies are type-checked at creation time

## Handler Binding Pattern

### **WebSocket Channel Binding**

The handler binding pattern uses the `.bind()` method to connect WebSocket channels to handler methods during constructor execution.

```python
class BasePublicComposite:
    def __init__(self, config, rest_client, websocket_client, logger=None):
        # Explicit cooperative inheritance
        WebsocketBindHandlerInterface.__init__(self)
        
        # Handler binding pattern - connect channels to methods
        websocket_client.bind(PublicWebsocketChannelType.BOOK_TICKER, self._handle_book_ticker)
        websocket_client.bind(PublicWebsocketChannelType.ORDERBOOK, self._handle_orderbook)
        websocket_client.bind(PublicWebsocketChannelType.TICKER, self._handle_ticker)
        websocket_client.bind(PublicWebsocketChannelType.PUB_TRADE, self._handle_trade)

class WebsocketBindHandlerInterface(Generic[T], ABC):
    """Generic interface for binding handlers to channel types."""
    
    def __init__(self):
        self._bound_handlers: Dict[T, Callable[[Any], Awaitable[None]]] = {}
    
    def bind(self, channel: T, handler: Callable[[Any], Awaitable[None]]) -> None:
        """Bind a handler function to a WebSocket channel."""
        self._bound_handlers[channel] = handler
        
    async def _exec_bound_handler(self, channel: T, *args, **kwargs) -> None:
        """Execute the bound handler for a channel."""
        handler = self._get_bound_handler(channel)
        return await handler(*args, **kwargs)
```

### **Handler Binding Benefits**

1. **Explicit Channel Mapping** - Clear connection between channels and handler methods
2. **Type Safety** - Channels are typed enums preventing runtime errors
3. **Flexible Routing** - Easy to change handler mappings without code changes
4. **Testability** - Can bind different handlers for testing scenarios
5. **Performance** - Direct method dispatch without reflection overhead
6. **Debug Friendly** - Clear visibility of channel-to-handler relationships

## Exchange Implementation Examples

### **Generic Composite Implementation**

The system uses generic composite interfaces with exchange-specific REST and WebSocket implementations:

```python
# Using generic composites with exchange-specific components
from exchanges.interfaces.composite import (
    CompositePublicSpotExchange,
    CompositePrivateSpotExchange,
    CompositePublicFuturesExchange,
    CompositePrivateFuturesExchange
)

# MEXC example - using generic composite with MEXC-specific REST/WS
mexc_public = CompositePublicSpotExchange(
    config=mexc_config,
    rest_client=MexcPublicSpotRestInterface(mexc_config),
    websocket_client=MexcPublicSpotWebsocket(mexc_config)
)

# Gate.io example - using generic composite with Gate.io-specific REST/WS
gateio_private = CompositePrivateSpotExchange(
    config=gateio_config,
    rest_client=GateioPrivateSpotRestInterface(gateio_config),
    websocket_client=GateioPrivateSpotWebsocket(gateio_config)
)
```

### **Exchange-Specific Component Implementation**

Exchanges provide their own REST and WebSocket implementations:

```python
# MEXC REST implementation
class MexcPublicSpotRestInterface(BasePublicSpotRestInterface):
    """MEXC-specific public REST implementation with protobuf support."""
    pass

# Gate.io WebSocket implementation  
class GateioPrivateSpotWebsocket(BasePrivateSpotWebsocket):
    """Gate.io-specific private WebSocket with custom ping/pong handling."""
    pass
```

## HFT Performance Compliance

### **Domain-Specific Optimizations**

**Public Domain (Market Data)**:
- **Book Ticker Processing**: <500μs per update (HFT CRITICAL)
- **Orderbook Access**: <1ms per lookup with zero-copy access
- **Symbol Resolution**: 0.947μs per lookup (1M+ ops/second)
- **WebSocket Latency**: <10ms for market data updates

**Private Domain (Trading Operations)**:
- **Order Placement**: <50ms execution time (HFT TARGET)
- **Order Cancellation**: <50ms execution time (HFT TARGET)
- **Balance Queries**: Fresh API calls, no caching (HFT SAFETY)
- **Order Status**: Real-time WebSocket updates with fallback

### **HFT Safety Rules**

**NEVER Cache (Real-time Trading Data)**:
- Account balances (change with each trade)
- Order status (execution state)
- Position data (margin/futures)
- Recent trades (market movement)

**Safe to Cache (Static Configuration Data)**:
- Symbol mappings and SymbolInfo
- Exchange configuration and endpoints
- Trading rules and precision requirements
- Fee schedules and rate limits

## Extensibility

### **Adding New Exchanges**

To add a new exchange using the separated domain pattern:

1. **Create Exchange-Specific REST Implementations**:
```python
class NewExchangePublicSpotRestInterface(BasePublicSpotRestInterface):
    """Exchange-specific public REST implementation."""
    pass

class NewExchangePrivateSpotRestInterface(BasePrivateSpotRestInterface):
    """Exchange-specific private REST implementation."""
    pass
```

2. **Create Exchange-Specific WebSocket Implementations**:
```python
class NewExchangePublicSpotWebsocket(BasePublicSpotWebsocket):
    """Exchange-specific public WebSocket implementation."""
    pass

class NewExchangePrivateSpotWebsocket(BasePrivateSpotWebsocket):
    """Exchange-specific private WebSocket implementation."""
    pass
```

3. **Update Factory Mapping Tables**:
```python
EXCHANGE_REST_MAP.update({
    (ExchangeEnum.NEWEXCHANGE, False): NewExchangePublicSpotRestInterface,
    (ExchangeEnum.NEWEXCHANGE, True): NewExchangePrivateSpotRestInterface,
})

EXCHANGE_WS_MAP.update({
    (ExchangeEnum.NEWEXCHANGE, False): NewExchangePublicSpotWebsocket,
    (ExchangeEnum.NEWEXCHANGE, True): NewExchangePrivateSpotWebsocket,
})

# Generic composites are reused - no new composite classes needed!
```

### **Benefits of Separated Domain Extensibility**

1. **Independent Development** - Public and private domains developed separately
2. **Clear Patterns** - Constructor injection and handler binding patterns are consistent
3. **Minimal Code Changes** - Only update mapping tables to add new exchanges
4. **Type Safety** - Factory mappings prevent runtime configuration errors
5. **Domain Isolation** - Changes to public domain don't affect private domain

---

*This architecture documentation reflects the separated domain architecture with constructor injection patterns and generic composite interfaces (October 2025). The design uses generic CompositePublicSpotExchange and CompositePrivateSpotExchange classes with exchange-specific REST and WebSocket implementations, prioritizing complete domain isolation, explicit dependency management, and HFT performance while maintaining clear architectural boundaries between market data and trading operations.*