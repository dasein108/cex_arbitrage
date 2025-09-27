# PublicSpotRest Interface Specification

## Overview

The `PublicSpotRest` interface defines the contract for public spot market data operations via REST API. This is the foundational interface for all unauthenticated market data retrieval operations in the HFT arbitrage engine.

## Interface Purpose and Responsibilities

### Primary Purpose
- Provide standardized access to public spot market data across all exchanges
- Enable retrieval of market information without authentication
- Ensure HFT-compliant data fetching with sub-50ms latency targets

### Core Responsibilities
1. **Symbol Information Management**: Retrieve and parse exchange trading rules
2. **Market Data Retrieval**: Fetch orderbooks, trades, tickers, and klines
3. **Server Health Monitoring**: Ping and time synchronization
4. **Historical Data Access**: Retrieve historical trade and kline data

## Architectural Position

```
BaseRestInterface (parent)
    └── PublicSpotRest (abstract)
            ├── MexcPublicRest (concrete)
            ├── GateioPublicRest (concrete)
            └── [Other exchange implementations]
```

## Key Abstract Methods

### 1. `get_symbols_info() -> Dict[Symbol, SymbolInfo]`
**Purpose**: Retrieve complete trading rules and symbol specifications
**HFT Requirements**: 
- Must complete within 1000ms (initialization phase)
- Results cached as static configuration (HFT-safe)
**Returns**: Dictionary mapping Symbol to SymbolInfo with precision, limits, etc.

### 2. `get_orderbook(symbol: Symbol, limit: int = 100) -> OrderBook`
**Purpose**: Fetch current orderbook snapshot
**HFT Requirements**: 
- Must complete within 50ms for arbitrage detection
- No caching of real-time data (HFT safety rule)
**Returns**: OrderBook struct with bids, asks, and metadata

### 3. `get_recent_trades(symbol: Symbol, limit: int = 500) -> List[Trade]`
**Purpose**: Retrieve recent executed trades
**HFT Requirements**: 
- Must complete within 50ms
- Used for market direction analysis
**Returns**: List of Trade structs sorted by timestamp

### 4. `get_klines(symbol: Symbol, timeframe: KlineInterval, date_from: Optional[datetime], date_to: Optional[datetime]) -> List[Kline]`
**Purpose**: Fetch candlestick/kline data for technical analysis
**HFT Requirements**: 
- Latency not critical (used for analysis, not execution)
**Returns**: List of Kline structs with OHLCV data

### 5. `get_klines_batch(symbol: Symbol, timeframe: KlineInterval, date_from: Optional[datetime], date_to: Optional[datetime]) -> List[Kline]`
**Purpose**: Batch retrieval of kline data for efficiency
**HFT Requirements**: 
- Optimized for bulk data loading
**Returns**: List of Kline structs

### 6. `get_server_time() -> int`
**Purpose**: Get exchange server timestamp for synchronization
**HFT Requirements**: 
- Critical for time-sensitive operations
- Must complete within 10ms
**Returns**: Server timestamp in milliseconds

### 7. `ping() -> bool`
**Purpose**: Test exchange connectivity
**HFT Requirements**: 
- Must complete within 10ms
- Used for health monitoring
**Returns**: True if connection successful

### 8. `get_historical_trades(symbol: Symbol, limit: int = 500, timestamp_from: Optional[int] = None, timestamp_to: Optional[int] = None) -> List[Trade]`
**Purpose**: Retrieve historical trade data with time range filtering
**HFT Requirements**: 
- Latency not critical (historical analysis)
**Returns**: List of Trade structs

### 9. `get_ticker_info(symbol: Optional[Symbol] = None) -> Dict[Symbol, Ticker]`
**Purpose**: Get 24hr price change statistics
**HFT Requirements**: 
- Must complete within 100ms
- Used for market overview
**Returns**: Dictionary mapping Symbol to Ticker stats

## Data Flow Patterns

### Initialization Flow
```
1. Exchange initialization triggered
2. PublicSpotRest.get_symbols_info() called
3. Symbol mappings cached (static data - HFT safe)
4. Initial orderbook snapshots loaded
```

### Market Data Flow
```
1. Orderbook request initiated
2. REST call to exchange endpoint
3. Response parsed to OrderBook struct (msgspec)
4. Returned to composite layer (no caching)
```

## HFT Performance Requirements

### Latency Targets
- **Critical Operations** (orderbook, trades): <50ms
- **Server Operations** (ping, time): <10ms  
- **Initialization** (symbols info): <1000ms
- **Non-Critical** (klines, historical): <500ms

### Throughput Requirements
- Support 100+ concurrent requests
- Handle 1000+ requests/second aggregate
- Connection pooling mandatory

### Memory Requirements
- Zero-copy message parsing (msgspec.Struct)
- No caching of real-time data
- Minimal memory footprint per request

## Dependencies and Relationships

### External Dependencies
- `exchanges.structs.common`: Data structures (Symbol, OrderBook, etc.)
- `exchanges.structs.enums`: KlineInterval enumeration
- `config.structs`: ExchangeConfig
- `infrastructure.logging`: HFTLoggerInterface

### Internal Relationships
- **Parent**: BaseRestInterface (provides transport management)
- **Used By**: CompositePublicExchange (orchestration layer)
- **Siblings**: PublicFuturesRest (extends for futures)

## Implementation Guidelines

### 1. Transport Management
```python
# Inherited from BaseRestInterface
self._transport_manager  # REST client with connection pooling
self.logger  # HFT logger instance
self.config  # Exchange configuration
```

### 2. Error Handling Pattern
```python
async def get_orderbook(self, symbol: Symbol, limit: int = 100) -> OrderBook:
    try:
        response = await self._transport_manager.get(
            endpoint=f"/depth",
            params={"symbol": self._format_symbol(symbol), "limit": limit}
        )
        return self._parse_orderbook(response)
    except Exception as e:
        self.logger.error(f"Orderbook fetch failed: {e}")
        raise ExchangeRestError(f"Failed to get orderbook: {e}")
```

### 3. Data Parsing Requirements
- Use msgspec.Struct for all return types
- Implement exchange-specific parsing methods
- Handle exchange quirks in implementation

### 4. Connection Management
- Leverage BaseRestInterface transport manager
- Implement retry logic for transient failures
- Respect rate limits per exchange

## Implementation Checklist

When implementing PublicSpotRest for a new exchange:

- [ ] Extend PublicSpotRest abstract class
- [ ] Implement all 9 abstract methods
- [ ] Use msgspec.Struct for data structures
- [ ] Add exchange-specific symbol formatting
- [ ] Implement proper error handling
- [ ] Add performance logging for HFT monitoring
- [ ] Test latency compliance (<50ms for critical)
- [ ] Verify no caching of real-time data
- [ ] Document exchange-specific quirks
- [ ] Add integration tests

## Security Considerations

- No authentication required (public endpoints only)
- Validate all response data before parsing
- Handle rate limit responses gracefully
- Log suspicious response patterns

## Monitoring and Observability

### Key Metrics
- Request latency per endpoint
- Success/failure rates
- Rate limit hits
- Connection pool utilization

### Logging Requirements
- Log all errors with context
- Track slow requests (>50ms for critical)
- Monitor connection health
- Record rate limit warnings

## Future Enhancements

1. **Batch Operations**: Enhanced batching for multiple symbols
2. **Compression**: Support for compressed responses
3. **Caching Layer**: Smart caching for static data only
4. **Circuit Breaker**: Automatic failure detection and recovery