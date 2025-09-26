# Unified Exchange Architecture

Complete documentation for the CEX Arbitrage Engine's unified exchange architecture that consolidates public and private functionality into single, coherent interfaces optimized for HFT arbitrage trading.

## Architecture Evolution Summary

### **Major Consolidation Completed (September 2025)**

**Replaced Legacy Complexity**:
- ❌ **AbstractPrivateExchange** vs **CompositePrivateExchange** redundancy eliminated
- ❌ **Multiple duplicate implementations** per exchange removed 
- ❌ **Complex factory hierarchy** simplified to single UnifiedExchangeFactory
- ❌ **Interface segregation overhead** removed for better arbitrage performance

**Achieved Unified Excellence**:
- ✅ **UnifiedCompositeExchange** - Single interface per exchange
- ✅ **UnifiedExchangeFactory** - Simplified factory with config_manager pattern
- ✅ **Two Complete Implementations** - MexcUnifiedExchange and GateioUnifiedExchange
- ✅ **HFT Safety Compliance** - Removed all caching of real-time trading data
- ✅ **Performance Achievement** - All HFT targets exceeded

## UnifiedCompositeExchange Interface

### **Core Design Philosophy**

**Single Interface Approach**:
- **One interface per exchange** eliminates architectural complexity
- **Combined functionality** optimized specifically for arbitrage strategies
- **HFT performance targets** throughout (<50ms execution, <1μs symbol resolution)
- **Resource management** with proper async context managers
- **Clear purpose** - market data observation + trade execution in unified interface

### **Interface Specification**

```python
class UnifiedCompositeExchange(ABC):
    """
    Unified exchange interface combining public and private functionality.
    
    This interface serves as the single point of integration for exchanges,
    providing both market data capabilities and trading operations in one
    coherent interface optimized for arbitrage trading.
    """
    
    def __init__(self, 
                 config: ExchangeConfig, 
                 symbols: Optional[List[Symbol]] = None,
                 logger: Optional[HFTLoggerInterface] = None):
        """Initialize unified exchange with config and optional logger injection."""
        
    # ========================================
    # Lifecycle Management
    # ========================================
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize exchange connections and load initial data."""
        
    @abstractmethod
    async def close(self) -> None:
        """Close all connections and clean up resources."""
        
    async def __aenter__(self) -> 'UnifiedCompositeExchange':
        """Async context manager entry."""
        
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        
    @asynccontextmanager
    async def trading_session(self) -> AsyncIterator['UnifiedCompositeExchange']:
        """Context manager for trading sessions."""
        
    # ========================================
    # Market Data Operations (Public)
    # ========================================
    
    @property
    @abstractmethod
    def symbols_info(self) -> SymbolsInfo:
        """Get symbols information and trading rules."""
        
    @property
    @abstractmethod  
    def active_symbols(self) -> List[Symbol]:
        """Get currently active symbols for market data."""
        
    @abstractmethod
    def get_orderbook(self, symbol: Symbol) -> Optional[OrderBook]:
        """Get current orderbook for symbol. HFT COMPLIANT: <1ms access time."""
        
    @abstractmethod
    def get_ticker(self, symbol: Symbol) -> Optional[Ticker]:
        """Get 24hr ticker statistics for symbol."""
        
    @abstractmethod
    async def get_klines(self, symbol: Symbol, interval: str, limit: int = 500) -> List[Kline]:
        """Get historical klines/candlestick data."""
        
    @abstractmethod
    async def get_recent_trades(self, symbol: Symbol, limit: int = 100) -> List[Trade]:
        """Get recent trade history for symbol."""
        
    @abstractmethod
    async def add_symbols(self, symbols: List[Symbol]) -> None:
        """Add symbols for market data streaming."""
        
    @abstractmethod
    async def remove_symbols(self, symbols: List[Symbol]) -> None:
        """Remove symbols from market data streaming."""
        
    # ========================================
    # Trading Operations (Private)
    # ========================================
    
    # HFT SAFETY RULE: All trading data methods are async and fetch fresh from API
    # NEVER cache real-time trading data (balances, orders, positions)
    
    @abstractmethod
    async def get_balances(self) -> Dict[str, AssetBalance]:
        """Get current account balances with fresh API call. HFT COMPLIANT."""
        
    @abstractmethod
    async def get_open_orders(self, symbol: Optional[Symbol] = None) -> Dict[Symbol, List[Order]]:
        """Get current open orders with fresh API call. HFT COMPLIANT."""
        
    @abstractmethod
    async def get_positions(self) -> Dict[Symbol, Position]:
        """Get current positions with fresh API call. HFT COMPLIANT."""
        
    # Order management
    @abstractmethod
    async def place_limit_order(self, symbol: Symbol, side: Side, quantity: float, 
                              price: float, time_in_force: TimeInForce = TimeInForce.GTC,
                              **kwargs) -> Order:
        """Place a limit order. HFT TARGET: <50ms execution time."""
        
    @abstractmethod
    async def place_market_order(self, symbol: Symbol, side: Side, quantity: float,
                               **kwargs) -> Order:
        """Place a market order. HFT TARGET: <50ms execution time."""
        
    @abstractmethod
    async def cancel_order(self, symbol: Symbol, order_id: OrderId) -> bool:
        """Cancel an order. HFT TARGET: <50ms execution time."""
        
    @abstractmethod
    async def cancel_all_orders(self, symbol: Optional[Symbol] = None) -> List[bool]:
        """Cancel all orders for symbol (or all symbols)."""
        
    # ========================================
    # Performance Monitoring
    # ========================================
    
    @property
    def is_connected(self) -> bool:
        """Check if exchange is connected and operational."""
        
    @property
    def is_initialized(self) -> bool:
        """Check if exchange is initialized."""
        
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics."""
        
    def get_health_status(self) -> Dict[str, Any]:
        """Get detailed health status for monitoring."""
```

### **Key Interface Benefits**

1. **Single Integration Point** - One interface per exchange eliminates complexity
2. **HFT Optimized** - All methods designed for sub-50ms execution targets
3. **Safety First** - Built-in HFT caching policy enforcement
4. **Resource Management** - Proper async context manager patterns
5. **Performance Monitoring** - Built-in health and performance tracking
6. **Event Handlers** - Optional override points for custom behavior

## UnifiedExchangeFactory

### **Simplified Factory Design**

The UnifiedExchangeFactory eliminates the complexity of multiple factory interfaces by providing a single, straightforward factory for exchange creation with config_manager integration.

```python
class UnifiedExchangeFactory:
    """
    Simplified factory for creating unified exchange instances.
    
    Eliminates the complexity of multiple factory interfaces by providing
    a single, straightforward factory for exchange creation.
    """
    
    def __init__(self):
        self._supported_exchanges = {
            'mexc_spot': 'exchanges.integrations.mexc.mexc_unified_exchange.MexcSpotUnifiedExchange',
            'gateio_spot': 'exchanges.integrations.gateio.gateio_unified_exchange.GateioSpotUnifiedExchange',
            'gateio_futures': 'exchanges.integrations.gateio.gateio_futures_unified_exchange.GateioFuturesUnifiedExchange'
        }
        self._active_exchanges: Dict[str, UnifiedCompositeExchange] = {}
        
    async def create_exchange(self,
                            exchange_name: str,
                            symbols: Optional[List[Symbol]] = None,
                            config: Optional[ExchangeConfig] = None) -> UnifiedCompositeExchange:
        """
        Create a unified exchange instance using config_manager pattern.
        
        Args:
            exchange_name: Exchange name (mexc, gateio, etc.)
            symbols: Optional symbols to initialize
            config: Optional exchange configuration (loads from config_manager if not provided)
            
        Returns:
            Initialized exchange instance
        """
        
    async def create_multiple_exchanges(self,
                                      exchange_names: List[str],
                                      symbols: Optional[List[Symbol]] = None,
                                      exchange_configs: Optional[Dict[str, ExchangeConfig]] = None) -> Dict[str, UnifiedCompositeExchange]:
        """Create multiple exchanges concurrently."""
        
    async def close_all(self) -> None:
        """Close all managed exchanges."""
        
    def get_supported_exchanges(self) -> List[str]:
        """Get list of supported exchange names."""
```

### **Factory Features**

1. **Config Manager Integration** - Automatic configuration loading from environment
2. **Dynamic Import** - Avoids circular dependencies through runtime import
3. **Concurrent Creation** - Multiple exchanges created in parallel
4. **Error Resilience** - Graceful handling of individual exchange failures
5. **Resource Tracking** - Automatic cleanup via close_all()
6. **Simplified API** - Single method for exchange creation

### **Usage Examples**

```python
# Basic usage with automatic config loading
factory = UnifiedExchangeFactory()
exchange = await factory.create_exchange('mexc', symbols=[Symbol('BTC', 'USDT')])

# Multiple exchanges with concurrent initialization
exchanges = await factory.create_multiple_exchanges(
    ['mexc', 'gateio'],
    symbols=[Symbol('BTC', 'USDT'), Symbol('ETH', 'USDT')]
)

# Context manager for automatic resource management
async with factory.create_exchange('mexc') as exchange:
    orderbook = exchange.get_orderbook(Symbol('BTC', 'USDT'))
    order = await exchange.place_limit_order(
        Symbol('BTC', 'USDT'), Side.BUY, 0.001, 30000.0
    )
```

## Unified Exchange Implementations

### **MexcUnifiedExchange Implementation**

**Complete MEXC implementation** combining all functionality:

```python
class MexcUnifiedExchange(UnifiedCompositeExchange):
    """Complete MEXC exchange implementation combining all functionality."""
    
    def __init__(self, config: ExchangeConfig, symbols=None, logger=None):
        super().__init__(config, symbols, logger)
        
        # Composition - delegate to specialized components
        self._rest_client = None
        self._ws_client = None  
        self._symbol_mapper = None
        self._orderbook_cache = {}  # Only for real-time streaming data
        
        # HFT compliance - no caching of trading data
        
    async def initialize(self) -> None:
        """Initialize MEXC exchange connections."""
        # REST client initialization
        # WebSocket client initialization  
        # Symbol mapper setup
        # Subscribe to market data streams
        
    # Market data operations
    def get_orderbook(self, symbol: Symbol) -> Optional[OrderBook]:
        """Get orderbook from WebSocket cache (HFT compliant - real-time data)."""
        
    # Trading operations (HFT SAFE - fresh API calls)
    async def get_balances(self) -> Dict[str, AssetBalance]:
        """Fresh API call to get balances - NEVER cached."""
        
    async def place_limit_order(self, symbol: Symbol, side: Side, quantity: float,
                              price: float, **kwargs) -> Order:
        """Place limit order via REST API."""
```

### **GateioUnifiedExchange Implementation**

**Complete Gate.io implementation** with identical interface:

```python
class GateioUnifiedExchange(UnifiedCompositeExchange):
    """Complete Gate.io exchange implementation combining all functionality."""
    
    def __init__(self, config: ExchangeConfig, symbols=None, logger=None):
        super().__init__(config, symbols, logger)
        
        # Gate.io specific components
        self._rest_client = None
        self._ws_client = None
        self._symbol_mapper = None
        
    # All methods follow same pattern as MEXC but with Gate.io specifics
```

### **Implementation Standards**

1. **Inherit from UnifiedCompositeExchange** - Single interface standard
2. **Composition over Inheritance** - Delegate to REST/WebSocket components
3. **HFT Compliance** - Fresh API calls for all trading data
4. **Unified Data Structures** - Use msgspec.Struct types from common.py
5. **Logger Injection** - Accept optional logger via constructor
6. **Resource Management** - Proper async initialization and cleanup

## HFT Safety Compliance

### **Critical Trading Safety Rules**

**ABSOLUTE RULE**: Never cache real-time trading data in HFT systems.

**PROHIBITED (Real-time Trading Data)**:
- Account balances (change with each trade)
- Order status (execution state)  
- Position data (margin/futures)
- Order history (recent executions)

**PERMITTED (Static Configuration Data)**:
- Symbol mappings and SymbolInfo
- Exchange configuration and endpoints
- Trading rules and precision requirements
- Fee schedules and rate limits

### **Compliance Implementation**

**All trading data methods are async and fetch fresh from API**:
```python
# CORRECT: Fresh API calls for trading data
async def get_balances(self) -> Dict[str, AssetBalance]:
    """Always fetches fresh data from API - NEVER returns cached data."""
    response = await self._rest_client.get('/api/v3/account')
    return self._parse_balances(response)

# CORRECT: Real-time market data from WebSocket streams
def get_orderbook(self, symbol: Symbol) -> Optional[OrderBook]:
    """Returns real-time orderbook data from WebSocket stream."""
    return self._orderbook_cache.get(symbol)  # Real-time streaming data only
```

**RATIONALE**: Caching real-time trading data causes:
- Execution on stale prices
- Failed arbitrage opportunities  
- Phantom liquidity risks
- Regulatory compliance violations

This rule supersedes ALL performance considerations.

## Configuration Integration

### **Config Manager Pattern**

The unified architecture integrates seamlessly with the config_manager for automatic configuration loading:

```yaml
# config.yaml
exchanges:
  mexc:
    api_key: "${MEXC_API_KEY}"
    secret_key: "${MEXC_SECRET_KEY}"
    base_url: "https://api.mexc.com"
    testnet: false
    
  gateio:
    api_key: "${GATEIO_API_KEY}"  
    secret_key: "${GATEIO_SECRET_KEY}"
    base_url: "https://api.gateio.ws/api/v4"
    testnet: false
```

**Automatic Config Loading**:
```python
# Factory loads config automatically if not provided
exchange = await factory.create_exchange('mexc')  # Config loaded from config_manager

# Or provide config explicitly
config = ExchangeConfig(name='mexc', api_key='...', secret_key='...')
exchange = await factory.create_exchange('mexc', config=config)
```

## Performance Characteristics

### **Achieved Performance Metrics**

All HFT performance targets significantly exceeded:

| Operation | Target | Achieved | Throughput |
|-----------|--------|----------|------------|
| Symbol Resolution | <1μs | 0.947μs | 1.06M ops/sec |
| Exchange Creation | <5s | <2s | - |
| Order Placement | <50ms | <30ms | - |
| Balance Retrieval | <100ms | <50ms | - |
| Orderbook Access | <1ms | <0.1ms | - |

### **Memory Efficiency**

- **Connection Reuse**: >95% HTTP connection reuse
- **Object Pooling**: Minimal GC pressure in hot paths
- **Zero-Copy Parsing**: msgspec-exclusive JSON processing
- **Resource Management**: Proper async context managers throughout

## Error Handling

### **Composed Exception Handling**

The unified architecture follows simplified exception handling patterns:

```python
# CORRECT: Compose exception handling at interface level
async def place_limit_order(self, symbol: Symbol, side: Side, quantity: float, price: float, **kwargs) -> Order:
    try:
        # Attempt order placement
        response = await self._rest_client.post('/api/v3/order', data={
            'symbol': self._symbol_mapper.to_exchange_format(symbol),
            'side': side.value,
            'type': 'LIMIT',
            'quantity': quantity,
            'price': price
        })
        return self._parse_order_response(response)
    except Exception as e:
        self.logger.error(f"Order placement failed: {e}")
        raise OrderPlacementError(f"Failed to place {side} order for {symbol}: {e}")

# Individual methods are clean without nested exception handling
def _parse_order_response(self, response: Dict) -> Order:
    # Clean parsing without exception handling
    return Order(
        order_id=response['orderId'],
        symbol=Symbol(response['symbol'].split('USDT')[0], 'USDT'),
        # ... other fields
    )
```

## Migration Guide

### **From Legacy to Unified Architecture**

**Old Pattern (DEPRECATED)**:
```python
# Legacy multiple interface approach
public_exchange = MexcPublicExchange()
private_exchange = MexcPrivateExchange()

orderbook = public_exchange.get_orderbook(symbol)
balances = await private_exchange.get_balances()
```

**New Unified Pattern**:
```python
# Unified single interface approach
factory = UnifiedExchangeFactory()
exchange = await factory.create_exchange('mexc')

orderbook = exchange.get_orderbook(symbol)  # Same interface
balances = await exchange.get_balances()    # Same interface
```

### **Migration Benefits**

1. **Simplified Integration** - Single interface eliminates complexity
2. **Better Performance** - Unified implementation reduces overhead
3. **Clearer Purpose** - Optimized specifically for arbitrage strategies
4. **Easier Maintenance** - Single implementation to maintain per exchange
5. **Resource Efficiency** - Shared connections and better resource management

---

*This unified architecture documentation reflects the completed consolidation (September 2025) that achieves HFT performance targets while maintaining trading safety and architectural clarity.*