# Exchange Factory - Simple Implementation

## Overview

The CEX Arbitrage Engine uses a simplified factory pattern based on direct mapping dictionaries. The factory (`src/exchanges/exchange_factory.py`) provides straightforward functions to create exchange components with constructor injection.

## Architecture

### Simple Mapping-Based Factory

The factory uses direct dictionary mappings for component creation:

```python
# Simple mapping dictionaries
EXCHANGE_REST_MAP = {
    (ExchangeEnum.MEXC, False): MexcPublicSpotRestInterface,
    (ExchangeEnum.MEXC, True): MexcPrivateSpotRestInterface,
    # ... more mappings
}

EXCHANGE_WS_MAP = {
    (ExchangeEnum.MEXC, False): MexcPublicSpotWebsocket,
    (ExchangeEnum.MEXC, True): MexcPrivateSpotWebsocket,
    # ... more mappings
}
```

### Factory Functions

**Core Functions**:
- `get_rest_implementation(config, is_private)` - Creates REST clients
- `get_ws_implementation(config, is_private)` - Creates WebSocket clients  
- `get_composite_implementation(config, is_private)` - Creates composite exchanges with injected dependencies

**Compatibility Functions**:
- `create_rest_client()` - Wrapper for backward compatibility
- `create_websocket_client()` - Wrapper for backward compatibility

## Constructor Injection Pattern

The factory creates composite exchanges with dependency injection:

```python
def get_composite_implementation(exchange_config: ExchangeConfig, is_private: bool):
    # Create dependencies
    ws_client = get_ws_implementation(exchange_config, is_private)
    rest_client = get_rest_implementation(exchange_config, is_private)
    
    # Inject via constructor
    return composite_class(exchange_config, rest_client, ws_client)
```

## Supported Exchanges

| Exchange | REST | WebSocket | Composite |
|----------|------|-----------|-----------|
| MEXC | ✅ | ✅ | ✅ |
| GATEIO | ✅ | ✅ | ✅ |
| GATEIO_FUTURES | ✅ | ✅ | ✅ |

## Usage Examples

### Basic Usage
```python
from exchanges.exchange_factory import get_composite_implementation
from config.structs import ExchangeConfig
from exchanges.structs.enums import ExchangeEnum

# Create composite exchange
config = ExchangeConfig(exchange_enum=ExchangeEnum.MEXC)
exchange = get_composite_implementation(config, is_private=False)
```

### Compatibility Usage
```python
from exchanges.exchange_factory import create_rest_client

# Legacy compatibility
rest_client = create_rest_client(ExchangeEnum.MEXC, config, is_private=False)
```

## Key Benefits

- **Simplicity**: 92 lines total, easy to understand
- **Direct Mapping**: No complex logic, just dictionary lookups
- **Constructor Injection**: Dependencies injected at creation time
- **Type Safety**: Clear mapping prevents runtime errors
- **Performance**: Minimal overhead, sub-millisecond creation

## Implementation File

See `src/exchanges/exchange_factory.py` for the complete implementation.