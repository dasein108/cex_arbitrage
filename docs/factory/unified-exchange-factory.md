# Unified Exchange Factory - Single Entry Point for All Exchange Components

## Overview

The Unified Exchange Factory provides a single, clear interface for creating all exchange-related components. This eliminates confusion between multiple factory patterns and provides a clear decision path for developers.

## Factory Philosophy

### **Before: Multiple Confusing Factories**
```python
# Confusion: Which factory to use?
from exchanges.factory.transport_factory import create_rest_client      # Option A
from exchanges.factory.composite_exchange_factory import create_composite_exchange  # Option B

# Problem: Overlapping responsibilities, unclear choice
```

### **After: Single Unified Factory**
```python
# Clear: One factory, explicit component selection
from exchanges.factory import create_exchange_component

# Explicit component type selection eliminates confusion
rest_client = create_exchange_component(exchange, config, 'rest')
websocket_client = create_exchange_component(exchange, config, 'websocket', handlers=handlers)
composite_exchange = create_exchange_component(exchange, config, 'composite')
```

## Component Types

The unified factory supports four explicit component types:

### **1. REST (`'rest'`)** - Direct API Integration
```python
# For custom REST API integration
rest_client = create_exchange_component(
    exchange=ExchangeEnum.MEXC,
    config=mexc_config,
    component_type='rest',
    is_private=False
)

# Use case: Custom data pipelines, specific API endpoints
await rest_client.get_orderbook(symbol)
await rest_client.get_ticker(symbol)
```

### **2. WebSocket (`'websocket'`)** - Real-time Streaming
```python
# For custom WebSocket message handling
handlers = create_public_handlers(
    orderbook_handler=my_orderbook_handler,
    trades_handler=my_trade_handler
)

ws_client = create_exchange_component(
    exchange=ExchangeEnum.MEXC,
    config=mexc_config,
    component_type='websocket',
    is_private=False,
    handlers=handlers
)

# Use case: Custom message processing, specialized streaming
await ws_client.initialize(symbols=[Symbol('BTC', 'USDT')])
```

### **3. Composite (`'composite'`)** - Full Exchange Interface
```python
# For complete exchange functionality
exchange = create_exchange_component(
    exchange=ExchangeEnum.MEXC,
    config=mexc_config,
    component_type='composite',
    is_private=True
)

# Use case: Standard trading, arbitrage systems, portfolio management
await exchange.initialize()
balance = await exchange.get_balance()
order = await exchange.place_order(symbol, side, quantity, price)
```

### **4. Pair (`'pair'`)** - Separated Domain Architecture
```python
# For HFT systems with separated market data and trading
public_exchange, private_exchange = create_exchange_component(
    exchange=ExchangeEnum.MEXC,
    config=mexc_config,
    component_type='pair'
)

# Use case: HFT arbitrage with complete domain separation
# public_exchange: market data only (no credentials needed)
# private_exchange: trading operations only (requires credentials)
```

## Factory Decision Matrix

| Use Case | Component Type | When to Use | Example |
|----------|----------------|-------------|---------|
| **Custom REST Integration** | `'rest'` | Building custom data pipelines, specific API calls | Historical data collection, custom indicators |
| **Custom WebSocket Handling** | `'websocket'` | Custom message processing, specialized streaming | Real-time analytics, custom data transformations |
| **Standard Trading Operations** | `'composite'` | Full exchange integration for trading | Arbitrage bots, portfolio management, order execution |
| **Market Data Analysis** | `'composite'` | Full market data interface | Price monitoring, market analysis, backtesting |
| **HFT Separated Domain** | `'pair'` | High-frequency systems with domain separation | Professional arbitrage, institutional trading |

## Convenience Functions

For backward compatibility and ease of use, the unified factory provides convenience functions:

```python
# Convenience functions (equivalent to create_exchange_component)
rest_client = create_rest_client(exchange, config, is_private=False)
ws_client = create_websocket_client(exchange, config, handlers, is_private=False)
composite = create_composite_exchange(exchange, config, is_private=False)
public, private = create_exchange_pair(exchange, config)

# Handler creation
public_handlers = create_public_handlers(
    orderbook_handler=handle_orderbook,
    trades_handler=handle_trades,
    book_ticker_handler=handle_book_ticker
)

private_handlers = create_private_handlers(
    order_handler=handle_orders,
    balance_handler=handle_balance,
    execution_handler=handle_executions
)
```

## Complete Usage Examples

### **Example 1: Custom Data Pipeline (REST)**
```python
from exchanges.factory import create_exchange_component
from exchanges.structs.enums import ExchangeEnum
from config.config_manager import HftConfig

# Create configuration
config = HftConfig().get_exchange_config('mexc')

# Create REST client for data collection
rest_client = create_exchange_component(
    exchange=ExchangeEnum.MEXC,
    config=config,
    component_type='rest',
    is_private=False
)

# Custom data pipeline
async def collect_market_data():
    symbols_info = await rest_client.get_symbols_info()
    for symbol in symbols_info.symbols:
        orderbook = await rest_client.get_orderbook(symbol)
        ticker = await rest_client.get_ticker(symbol)
        # Process data...
```

### **Example 2: Real-time Analysis (WebSocket)**
```python
from exchanges.factory import create_exchange_component, create_public_handlers

# Custom message handlers
async def analyze_orderbook(orderbook):
    # Custom orderbook analysis
    spread = orderbook.asks[0].price - orderbook.bids[0].price
    print(f"Spread: {spread}")

async def detect_arbitrage(trade):
    # Custom trade analysis
    print(f"Large trade detected: {trade.quantity}")

# Create handlers
handlers = create_public_handlers(
    orderbook_handler=analyze_orderbook,
    trades_handler=detect_arbitrage
)

# Create WebSocket client
ws_client = create_exchange_component(
    exchange=ExchangeEnum.MEXC,
    config=config,
    component_type='websocket',
    is_private=False,
    handlers=handlers
)

# Start streaming
await ws_client.initialize(symbols=[Symbol('BTC', 'USDT')])
```

### **Example 3: Trading System (Composite)**
```python
# Complete trading system
trading_exchange = create_exchange_component(
    exchange=ExchangeEnum.MEXC,
    config=config,
    component_type='composite',
    is_private=True  # Requires credentials
)

# Full trading functionality
async def trading_strategy():
    await trading_exchange.initialize()
    
    # Get account information
    balance = await trading_exchange.get_balance()
    print(f"Available balance: {balance}")
    
    # Place order
    order = await trading_exchange.place_order(
        symbol=Symbol('BTC', 'USDT'),
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=0.001,
        price=50000.0
    )
    
    # Monitor order status
    order_status = await trading_exchange.get_order_status(order.order_id)
```

### **Example 4: HFT Arbitrage (Pair)**
```python
# Separated domain architecture for HFT
public_exchange, private_exchange = create_exchange_component(
    exchange=ExchangeEnum.MEXC,
    config=config,
    component_type='pair'
)

# HFT arbitrage system
async def hft_arbitrage_system():
    # Initialize both domains
    await public_exchange.initialize(symbols=[Symbol('BTC', 'USDT')])
    await private_exchange.initialize()
    
    # Market data domain (no credentials)
    public_exchange.add_orderbook_update_handler(detect_arbitrage_opportunity)
    
    # Trading domain (requires credentials)
    async def detect_arbitrage_opportunity(symbol, orderbook, update_type):
        # Analyze arbitrage opportunity
        if is_profitable_arbitrage(orderbook):
            # Execute trade via private exchange
            await private_exchange.place_order(...)
```

## Validation and Error Handling

The unified factory provides comprehensive validation:

```python
# Validate component request before creation
validation = validate_component_request(
    exchange=ExchangeEnum.MEXC,
    component_type='websocket',
    is_private=True
)

if validation['is_valid']:
    component = create_exchange_component(...)
else:
    print(f"Validation failed: {validation}")

# Built-in validation errors:
# - Unsupported exchange
# - Missing credentials for private components
# - Invalid handler types for WebSocket components
# - Unsupported component types
```

## Caching and Performance

The unified factory includes intelligent caching:

```python
# Automatic caching (enabled by default)
client1 = create_exchange_component(ExchangeEnum.MEXC, config, 'rest')
client2 = create_exchange_component(ExchangeEnum.MEXC, config, 'rest')  # Returns cached instance

# Disable caching for specific use cases
client = create_exchange_component(
    ExchangeEnum.MEXC, config, 'rest', use_cache=False
)

# Cache management
from exchanges.factory import clear_cache, get_cache_stats

# Clear all cached components
clear_cache()

# Get cache statistics
stats = get_cache_stats()
print(f"Cached components: {stats['cached_components']}")
```

## Utility Functions

```python
from exchanges.factory import (
    get_supported_exchanges,
    is_exchange_supported,
    get_supported_component_types,
    get_component_decision_matrix
)

# Check support
supported_exchanges = get_supported_exchanges()
# Returns: [ExchangeEnum.MEXC, ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES]

mexc_supported = is_exchange_supported(ExchangeEnum.MEXC)  # True

component_types = get_supported_component_types()
# Returns: ['rest', 'websocket', 'composite', 'pair']

# Get decision matrix for component selection
decision_matrix = get_component_decision_matrix()
# Returns detailed mapping of use cases to component types
```

## Migration from Legacy Factories

### **Old Pattern (Deprecated)**
```python
# Old: transport_factory
from exchanges.factory.transport_factory import create_rest_client, create_websocket_client

# Old: composite_exchange_factory  
from exchanges.factory.composite_exchange_factory import create_composite_exchange

# Problem: Unclear which factory to use, overlapping responsibilities
```

### **New Pattern (Recommended)**
```python
# New: unified factory
from exchanges.factory import create_exchange_component

# Or use convenience functions
from exchanges.factory import create_rest_client, create_websocket_client, create_composite_exchange

# Benefit: Single entry point, explicit component selection, clear decision path
```

## HFT Performance Characteristics

The unified factory maintains all HFT performance targets:

- **Component Creation**: <1ms overhead
- **Cache Lookup**: <0.1ms for repeated requests  
- **Memory Efficiency**: Shared instances reduce memory footprint
- **Type Safety**: Full type annotations prevent runtime errors
- **Error Handling**: Fast validation prevents expensive failure scenarios

## Best Practices

### **1. Use Explicit Component Types**
```python
# Good: Clear intent
create_exchange_component(exchange, config, 'composite', is_private=True)

# Avoid: Implicit assumptions
create_composite_exchange(exchange, config, is_private=True)  # What type of composite?
```

### **2. Leverage Validation**
```python
# Validate before creating expensive components
if validate_component_request(exchange, 'websocket', is_private=True)['is_valid']:
    ws_client = create_exchange_component(...)
```

### **3. Use Appropriate Component Types**
```python
# Custom data processing: use 'rest'
rest_client = create_exchange_component(exchange, config, 'rest')

# Standard trading: use 'composite' 
trading_exchange = create_exchange_component(exchange, config, 'composite', is_private=True)

# HFT systems: use 'pair'
public, private = create_exchange_component(exchange, config, 'pair')
```

### **4. Handler Injection for WebSocket**
```python
# Always provide handlers for WebSocket components
handlers = create_public_handlers(orderbook_handler=my_handler)
ws_client = create_exchange_component(exchange, config, 'websocket', handlers=handlers)
```

The unified factory eliminates the confusion of multiple factory patterns while maintaining all performance and functionality benefits of the separated domain architecture.