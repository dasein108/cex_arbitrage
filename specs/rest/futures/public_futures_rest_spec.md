# PublicFuturesRest Interface Specification

## Overview

The `PublicFuturesRest` interface extends `PublicSpotRest` with futures-specific public market data operations. This interface provides access to funding rates, mark prices, and other futures-specific data without authentication.

## Interface Purpose and Responsibilities

### Primary Purpose
- Extend spot market data capabilities for futures markets
- Provide futures-specific data like funding rates and mark prices
- Maintain HFT compliance for futures arbitrage opportunities

### Core Responsibilities
1. **Funding Rate Data**: Current and historical funding rates
2. **Mark Price Information**: Real-time mark price for liquidation calculations
3. **Inherited Spot Operations**: All PublicSpotRest functionality

## Architectural Position

```
PublicSpotRest (parent - inherits all spot methods)
    └── PublicFuturesRest (adds futures-specific)
            ├── GateioFuturesPublicRest (concrete)
            ├── BinanceFuturesPublicRest (concrete)
            └── [Other futures implementations]
```

## Key Abstract Methods (Futures-Specific)

### 1. `get_funding_rate(symbol: Symbol) -> Dict`
**Purpose**: Retrieve current funding rate for perpetual futures
**HFT Requirements**: 
- Must complete within 50ms
- Critical for futures-spot arbitrage
**Returns**: Dictionary with funding rate and next payment time
```python
{
    "symbol": Symbol,
    "funding_rate": Decimal,
    "funding_time": int,  # Next funding timestamp
    "interval_hours": int  # Funding interval (typically 8)
}
```

### 2. `get_mark_price(symbol: Symbol) -> float`
**Purpose**: Get current mark price for liquidation calculations
**HFT Requirements**: 
- Must complete within 50ms
- Critical for risk management
**Returns**: Current mark price as float

## Inherited Methods from PublicSpotRest

All methods from PublicSpotRest are available:
- `get_symbols_info()` - Trading rules (futures-specific)
- `get_orderbook()` - Futures orderbook data
- `get_recent_trades()` - Futures trades
- `get_klines()` - Futures candlestick data
- `get_ticker_info()` - 24hr futures statistics
- `get_server_time()` - Server synchronization
- `ping()` - Connectivity test

## Data Flow Patterns

### Funding Rate Flow
```
1. Funding rate request initiated
2. REST call to futures endpoint
3. Parse funding rate and schedule
4. Return for arbitrage calculations
5. No caching (real-time data)
```

### Mark Price Flow
```
1. Mark price requested for position
2. REST call to mark price endpoint
3. Parse current mark price
4. Use for liquidation calculations
5. Return without caching
```

## Futures-Specific Considerations

### Contract Types
```python
# Different handling for perpetual vs dated futures
def _format_futures_symbol(self, symbol: Symbol) -> str:
    if symbol.is_perpetual:
        return f"{symbol.base}{symbol.quote}_PERP"
    else:
        # Dated futures with expiry
        return f"{symbol.base}{symbol.quote}_{symbol.expiry}"
```

### Funding Rate Calculations
```python
# Funding rate impact on arbitrage
def calculate_funding_cost(
    funding_rate: Decimal, 
    position_size: Decimal,
    hours_held: int
) -> Decimal:
    # Funding typically every 8 hours
    payments = hours_held / 8
    return position_size * funding_rate * payments
```

## HFT Performance Requirements

### Latency Targets
- **Funding Rate**: <50ms (arbitrage critical)
- **Mark Price**: <50ms (risk critical)
- **Inherited Operations**: Same as PublicSpotRest

### Update Frequency
- Funding rates: Every 1-5 minutes
- Mark prices: Real-time via WebSocket preferred
- Orderbooks: Continuous streaming required

## Implementation Guidelines

### 1. Funding Rate Implementation
```python
async def get_funding_rate(self, symbol: Symbol) -> Dict:
    response = await self._transport_manager.get(
        endpoint="/futures/funding_rate",
        params={"symbol": self._format_futures_symbol(symbol)}
    )
    
    return {
        "symbol": symbol,
        "funding_rate": Decimal(response["rate"]),
        "funding_time": int(response["next_funding_time"]),
        "interval_hours": 8
    }
```

### 2. Mark Price Implementation
```python
async def get_mark_price(self, symbol: Symbol) -> float:
    response = await self._transport_manager.get(
        endpoint="/futures/mark_price",
        params={"symbol": self._format_futures_symbol(symbol)}
    )
    
    # Return as float for compatibility
    return float(response["mark_price"])
```

### 3. Symbol Info Override
```python
async def get_symbols_info(self) -> Dict[Symbol, SymbolInfo]:
    # Get futures-specific symbol info
    info = await super().get_symbols_info()
    
    # Add futures-specific fields
    for symbol, symbol_info in info.items():
        symbol_info.contract_size = self._get_contract_size(symbol)
        symbol_info.is_perpetual = self._is_perpetual(symbol)
        
    return info
```

## Dependencies and Relationships

### External Dependencies
- All PublicSpotRest dependencies
- Futures-specific data structures (when added)

### Internal Relationships
- **Parent**: PublicSpotRest (inherits all methods)
- **Used By**: CompositePublicFuturesExchange
- **Siblings**: PrivateFuturesRest (authenticated operations)

## Futures Market Specifics

### Contract Specifications
- **Perpetual**: No expiry, funding rate mechanism
- **Dated Futures**: Fixed expiry, no funding
- **Contract Size**: Notional value per contract
- **Margin Requirements**: Initial and maintenance

### Risk Parameters
- **Liquidation Price**: Calculated from mark price
- **Max Leverage**: Exchange-specific limits
- **Position Limits**: Maximum position sizes
- **Funding Cap**: Maximum funding rate limits

## Implementation Checklist

When implementing PublicFuturesRest:

- [ ] Extend PublicFuturesRest class
- [ ] Implement get_funding_rate()
- [ ] Implement get_mark_price()
- [ ] Override get_symbols_info() for futures
- [ ] Add futures symbol formatting
- [ ] Handle perpetual vs dated contracts
- [ ] Test funding rate accuracy
- [ ] Verify mark price updates
- [ ] Document contract specifications
- [ ] Add futures-specific error handling

## Monitoring and Observability

### Futures-Specific Metrics
- Funding rate fetch latency
- Mark price update frequency
- Funding payment accuracy
- Contract rollover handling

### Critical Alerts
- Funding rate unavailable
- Mark price stale (>1 second)
- Contract specification changes
- Unusual funding rate spikes

## Future Enhancements

1. **Index Price**: Add index price retrieval
2. **Open Interest**: Track open interest data
3. **Liquidation Feed**: Monitor liquidations
4. **Insurance Fund**: Track insurance fund size
5. **Predicted Funding**: Calculate predicted rates