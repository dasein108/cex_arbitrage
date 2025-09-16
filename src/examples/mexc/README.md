# MEXC Exchange Demos

This directory contains demonstration scripts showcasing the MEXC exchange implementation and the hybrid architecture integration.

## Demo Scripts

### 1. `architecture_showcase_demo.py` ⭐
**Comprehensive hybrid architecture overview**

Shows the complete hybrid architecture implementation without requiring network connectivity or API credentials.

```bash
PYTHONPATH=src python src/examples/mexc/architecture_showcase_demo.py
```

**Features demonstrated:**
- Inheritance hierarchy and base class methods
- Configuration structure and components  
- Usage patterns for exchange initialization
- Arbitrage layer integration patterns
- Multi-exchange coordination

**Best for:** Understanding the overall architecture and integration patterns.

### 2. `base_class_features_demo.py` 🏗️
**Focused base class functionality showcase**

Deep dive into the BaseExchangeInterface features available through hybrid architecture.

```bash
PYTHONPATH=src python src/examples/mexc/base_class_features_demo.py
```

**Features demonstrated:**
- Update handler system for arbitrage integration
- Statistics and monitoring capabilities
- Connection management and reconnection
- Orderbook access patterns
- Initialization sequence
- Graceful shutdown handling

**Best for:** Understanding base class capabilities and arbitrage integration.

### 3. `hybrid_architecture_demo.py` 🚀
**Full async demonstration (requires setup)**

Complete async demo showing real initialization and update handling patterns.

```bash
PYTHONPATH=src python src/examples/mexc/hybrid_architecture_demo.py
```

**Features demonstrated:**
- Full async initialization sequence
- Real-time update handler registration
- Symbol management (add/remove)
- Statistics monitoring
- Connection state changes
- Graceful shutdown

**Requirements:** Proper REST strategy registration and WebSocket configuration.

### 4. `public_exchange_basic_demo.py` 🔧
**Basic usage patterns**

Simple demonstration focusing on instantiation and basic API exploration.

```bash
PYTHONPATH=src python src/examples/mexc/public_exchange_demo.py
```

**Features demonstrated:**
- Exchange instantiation patterns
- Method availability checking
- Configuration structure
- Basic property access
- Async method signatures

**Best for:** Quick verification of setup and basic functionality.

## Architecture Overview

### Hybrid Architecture Benefits

The MEXC exchange implementation uses the hybrid architecture pattern where:

- **BaseExchangeInterface** handles common functionality:
  - Orderbook management and storage
  - REST API initialization sequence  
  - Reconnection handling with exponential backoff
  - Update notification system for arbitrage layer
  - Statistics and monitoring
  - Graceful shutdown coordination

- **MexcPublicExchange** implements exchange-specific details:
  - MEXC REST API integration
  - MEXC WebSocket message handling
  - Exchange-specific data parsing
  - Symbol mapping and configuration

### Key Features

1. **Update Handler System**
   - Arbitrage engines register handlers with exchanges
   - Base class coordinates notifications to all handlers
   - Consistent OrderBook and Symbol formats across exchanges

2. **Connection Management**
   - Automatic reconnection with exponential backoff
   - REST snapshot reload on reconnection
   - Connection health monitoring

3. **Statistics and Monitoring**
   - Real-time performance metrics
   - Connection status tracking
   - Update processing statistics

4. **Thread-Safe Operations**
   - Copy-on-read orderbook access
   - Safe concurrent access to exchange data
   - Proper resource cleanup

## Integration Patterns

### Arbitrage Layer Integration

```python
# Register update handler
async def arbitrage_handler(symbol, orderbook, update_type):
    if update_type == OrderbookUpdateType.DIFF:
        process_arbitrage_opportunity(symbol, orderbook)
    elif update_type == OrderbookUpdateType.SNAPSHOT:
        initialize_symbol_state(symbol, orderbook)

exchange.add_orderbook_update_handler(arbitrage_handler)
await exchange.initialize(symbols)
```

### Multi-Exchange Coordination

```python
# Unified handler for multiple exchanges
exchanges = [mexc_exchange, gateio_exchange]
for exchange in exchanges:
    exchange.add_orderbook_update_handler(unified_handler)
    await exchange.initialize(common_symbols)
```

## Running the Demos

All demos are designed to be safe to run without:
- Real API credentials
- Network connectivity  
- Complex configuration setup

Simply run any demo with:
```bash
PYTHONPATH=src python src/examples/mexc/<demo_name>.py
```

## Next Steps

After exploring the demos:

1. **Set up real configuration** for live testing
2. **Integrate with arbitrage components** using the handler patterns
3. **Extend to additional exchanges** using the same hybrid architecture
4. **Implement custom monitoring** using the statistics API

## Architecture Documentation

For more details on the hybrid architecture, see:
- `/Users/dasein/dev/cex_arbitrage/src/core/cex/base/base_exchange.py` - Base class implementation
- `/Users/dasein/dev/cex_arbitrage/src/cex/mexc/public_exchange.py` - MEXC implementation  
- `/Users/dasein/dev/cex_arbitrage/CLAUDE.md` - Overall system architecture