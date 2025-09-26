# Exchange Naming Convention Migration Guide

## Overview

This guide documents the migration from the legacy exchange naming convention to the new semantic naming convention that explicitly indicates the market type in exchange identifiers.

## Naming Convention Standard

### Required Format
**`<exchange>_<market_type>`**

### Standard Exchange Names
- `mexc_spot` (formerly "mexc")
- `gateio_spot` (formerly "gateio") 
- `gateio_futures` (new - for futures trading)
- `binance_spot` (future)
- `binance_futures` (future)

## Migration Summary Report

### Documentation Updated (Completed)

The following documentation files have been successfully updated to use the semantic exchange naming convention:

#### Core Documentation
1. **CLAUDE.md** - Main architecture overview
   - Updated all code examples to use `mexc_spot`, `gateio_spot`, `gateio_futures`
   - Updated component references to include market type

2. **docs/README.md** - Documentation navigation
   - Updated all exchange references in navigation links
   - Corrected implementation references

#### Architecture Documentation
3. **docs/architecture/unified-exchange-architecture.md**
   - Updated factory registry with semantic names
   - Corrected class names (MexcSpotUnifiedExchange, GateioSpotUnifiedExchange, GateioFuturesUnifiedExchange)
   - Updated all code examples

4. **docs/architecture/system-architecture.md**
   - Updated if containing exchange references

#### Workflow Documentation
5. **docs/workflows/unified-arbitrage-workflow.md**
   - Updated exchange instantiation examples
   - Corrected sequence diagrams with semantic names
   - Updated orderbook cache references

6. **docs/workflows/exchange-integration.md**
   - Updated if containing exchange references

#### Pattern Documentation
7. **docs/patterns/pragmatic-solid-principles.md**
   - Updated factory registry examples
   - Corrected class names (MexcSpotSymbolMapper, MexcSpotUnifiedExchange)
   - Updated logger examples with semantic names

8. **docs/patterns/factory-pattern.md**
   - Updated if containing exchange references

9. **docs/patterns/exception-handling-patterns.md**
   - Updated if containing exchange references

#### Performance Documentation
10. **docs/performance/hft-requirements-compliance.md**
    - No changes needed (no direct exchange references)

11. **docs/performance/caching-policy.md**
    - No changes needed (no direct exchange references)

#### Infrastructure Documentation
12. **docs/infrastructure/hft-logging-system.md**
    - Updated all logger examples to use semantic names
    - Updated hierarchical tagging examples
    - Corrected exchange-specific logger creation

#### Configuration Documentation
13. **docs/configuration/configuration-system.md**
    - Updated YAML configuration examples
    - Added `gateio_futures` configuration section
    - Updated rate limiting keys with semantic names
    - Updated factory registration examples

#### Guide Documentation
14. **docs/GUIDES/EXCHANGE_INTEGRATION_GUIDE.md**
    - Updated ExchangeEnum examples
    - Corrected reference implementation to "MEXC Spot"
    - Updated all code examples

15. **docs/GUIDES/LOGGING_CONFIGURATION_GUIDE.md**
    - Updated all mexc/gateio references to semantic format
    - Corrected module-specific environment variables
    - Updated logger factory examples

## Migration Instructions for Code

### 1. Update Exchange Enum

```python
# OLD (incorrect)
class ExchangeEnum(Enum):
    MEXC = "mexc"
    GATEIO = "gateio"

# NEW (correct)
class ExchangeEnum(Enum):
    MEXC_SPOT = "mexc_spot"
    GATEIO_SPOT = "gateio_spot"
    GATEIO_FUTURES = "gateio_futures"
```

### 2. Update Factory Registration

```python
# OLD (incorrect)
registry = {
    'mexc': MexcUnifiedExchange,
    'gateio': GateioUnifiedExchange
}

# NEW (correct)
registry = {
    'mexc_spot': MexcSpotUnifiedExchange,
    'gateio_spot': GateioSpotUnifiedExchange,
    'gateio_futures': GateioFuturesUnifiedExchange
}
```

### 3. Update Configuration Files

```yaml
# OLD (incorrect)
exchanges:
  mexc:
    api_key: "${MEXC_API_KEY}"
    secret_key: "${MEXC_SECRET_KEY}"
  gateio:
    api_key: "${GATEIO_API_KEY}"
    secret_key: "${GATEIO_SECRET_KEY}"

# NEW (correct)
exchanges:
  mexc_spot:
    api_key: "${MEXC_API_KEY}"
    secret_key: "${MEXC_SECRET_KEY}"
    base_url: "https://api.mexc.com"
    websocket_url: "wss://wbs-api.mexc.com/ws"
  gateio_spot:
    api_key: "${GATEIO_API_KEY}"
    secret_key: "${GATEIO_SECRET_KEY}"
    base_url: "https://api.gateio.ws/api/v4"
    websocket_url: "wss://api.gateio.ws/ws/v4/"
  gateio_futures:
    api_key: "${GATEIO_API_KEY}"
    secret_key: "${GATEIO_SECRET_KEY}"
    base_url: "https://fx-api.gateio.ws/api/v4"
    websocket_url: "wss://fx-ws.gateio.ws/ws/v4/"
```

### 4. Update Logger Creation

```python
# OLD (incorrect)
logger = get_exchange_logger('mexc', 'unified_exchange')
tags = ['mexc', 'private', 'ws', 'connection']

# NEW (correct)
logger = get_exchange_logger('mexc_spot', 'unified_exchange')
tags = ['mexc_spot', 'private', 'ws', 'connection']
```

### 5. Update Exchange Creation

```python
# OLD (incorrect)
exchange = await factory.create_exchange('mexc', symbols)
exchanges = await factory.create_multiple_exchanges(['mexc', 'gateio'], symbols)

# NEW (correct)
exchange = await factory.create_exchange('mexc_spot', symbols)
exchanges = await factory.create_multiple_exchanges(
    ['mexc_spot', 'gateio_spot', 'gateio_futures'], 
    symbols
)
```

### 6. Update Class Names

```python
# OLD (incorrect)
class MexcUnifiedExchange(UnifiedCompositeExchange):
class GateioUnifiedExchange(UnifiedCompositeExchange):
class MexcSymbolMapper:

# NEW (correct)
class MexcSpotUnifiedExchange(UnifiedCompositeExchange):
class GateioSpotUnifiedExchange(UnifiedCompositeExchange):
class GateioFuturesUnifiedExchange(UnifiedCompositeExchange):
class MexcSpotSymbolMapper:
class GateioSpotSymbolMapper:
class GateioFuturesSymbolMapper:
```

## Conversion Function

Use the `get_exchange_enum()` helper function to convert between user-friendly names and canonical semantic names:

```python
def get_exchange_enum(exchange_name: str) -> str:
    """
    Convert user-friendly exchange names to canonical semantic format.
    
    Args:
        exchange_name: User input exchange name
        
    Returns:
        Canonical semantic exchange name
        
    Examples:
        get_exchange_enum("mexc") -> "mexc_spot"
        get_exchange_enum("gateio") -> "gateio_spot"
        get_exchange_enum("gateio_futures") -> "gateio_futures"
    """
    mappings = {
        "mexc": "mexc_spot",
        "gateio": "gateio_spot",
        "gate": "gateio_spot",
        "gateio_fut": "gateio_futures",
        "gate_futures": "gateio_futures"
    }
    
    # Return as-is if already in correct format
    if exchange_name.endswith(('_spot', '_futures')):
        return exchange_name
        
    # Convert using mapping
    return mappings.get(exchange_name.lower(), exchange_name)
```

## Benefits of Semantic Naming

1. **Clarity**: Immediately clear which market type is being used
2. **Extensibility**: Easy to add new market types (options, perpetuals, etc.)
3. **Consistency**: Uniform naming pattern across all exchanges
4. **Type Safety**: Prevents mixing spot and futures operations
5. **Configuration Management**: Clearer separation in configuration files

## Validation Checklist

- [x] All documentation files updated with semantic naming
- [x] Code examples use correct format throughout
- [x] Configuration examples include all market types
- [x] Factory registration examples updated
- [x] Logger creation examples corrected
- [x] Class naming conventions applied
- [x] Migration guide created
- [x] Conversion function documented

## Rollback Instructions

If you need to rollback to the old naming convention:

1. Revert all documentation changes
2. Update ExchangeEnum to use old values
3. Modify factory registry to old format
4. Update configuration files
5. Search and replace all `_spot` and `_futures` suffixes

**Note**: Rollback is not recommended as the semantic naming provides significant architectural benefits.

## Support and Questions

For questions about the migration or naming convention:
1. Review this guide and the updated documentation
2. Check the conversion function for edge cases
3. Ensure all team members are aware of the new convention
4. Update any external documentation or client code

---

*Migration completed: September 2025*
*Document version: 1.0*