# CompositePublicFuturesExchange Interface Specification

## Overview

The `CompositePublicFuturesExchange` interface extends `CompositePublicExchange` with futures-specific market data operations. It adds funding rates, open interest, mark prices, and index prices to the standard spot market data capabilities.

## Interface Purpose and Responsibilities

### Primary Purpose
- Provide complete futures market data orchestration
- Manage futures-specific data alongside standard orderbooks
- Track funding rates for arbitrage calculations
- Monitor open interest and price indices

### Core Responsibilities
1. **Inherited Market Data**: All spot public functionality
2. **Funding Rate Management**: Track and update funding rates
3. **Price Indices**: Maintain mark and index prices
4. **Open Interest Tracking**: Monitor contract open interest
5. **Futures Data Loading**: Initialize futures-specific data

## Architectural Position

```
CompositePublicExchange (parent - inherits all public spot)
    └── CompositePublicFuturesExchange (adds futures data)
            └── Implementations:
                    ├── GateioPublicFuturesExchange
                    ├── BinancePublicFuturesExchange
                    └── [Other futures exchanges]
```

## Futures-Specific State

### Additional State Management
```python
# Futures-specific data structures
self._funding_rates: Dict[Symbol, Dict] = {}
self._open_interest: Dict[Symbol, Dict] = {}
self._mark_prices: Dict[Symbol, Decimal] = {}
self._index_prices: Dict[Symbol, Decimal] = {}

# Tag override for identification
self._tag = f'{config.name}_public_futures'
```

### Funding Rate Structure
```python
{
    "rate": Decimal("0.0001"),      # Current funding rate
    "next_funding_time": 1234567890,  # Next payment timestamp
    "interval_hours": 8,             # Payment interval
    "timestamp": 1234567880          # Last update time
}
```

### Open Interest Structure
```python
{
    "open_interest": Decimal("1234.56"),  # Total contracts
    "open_interest_value": Decimal("61728000"),  # USD value
    "timestamp": 1234567890            # Update timestamp
}
```

## Abstract Properties

### Futures Data Properties
```python
@property
@abstractmethod
def funding_rates(self) -> Dict[Symbol, Dict]:
    """Get current funding rates for all symbols"""
    pass

@property
@abstractmethod
def open_interest(self) -> Dict[Symbol, Dict]:
    """Get open interest data for all symbols"""
    pass

@property
@abstractmethod
def mark_prices(self) -> Dict[Symbol, Decimal]:
    """Get mark prices for liquidation calculations"""
    pass

@property
@abstractmethod
def index_prices(self) -> Dict[Symbol, Decimal]:
    """Get underlying index prices"""
    pass
```

## Abstract Loading Methods

### Futures Data Loading
```python
@abstractmethod
async def _load_funding_rates(self, symbols: List[Symbol]) -> None:
    """Load funding rates from REST API"""
    for symbol in symbols:
        rate_data = await self._public_rest.get_funding_rate(symbol)
        self._funding_rates[symbol] = rate_data

@abstractmethod
async def _load_open_interest(self, symbols: List[Symbol]) -> None:
    """Load open interest from REST API"""
    for symbol in symbols:
        oi_data = await self._public_rest.get_open_interest(symbol)
        self._open_interest[symbol] = oi_data

@abstractmethod
async def _load_mark_prices(self, symbols: List[Symbol]) -> None:
    """Load mark prices from REST API"""
    for symbol in symbols:
        mark_price = await self._public_rest.get_mark_price(symbol)
        self._mark_prices[symbol] = Decimal(mark_price)

@abstractmethod
async def _load_index_prices(self, symbols: List[Symbol]) -> None:
    """Load index prices from REST API"""
    for symbol in symbols:
        index_price = await self._public_rest.get_index_price(symbol)
        self._index_prices[symbol] = Decimal(index_price)
```

## Enhanced Initialization

### Extended Initialization Flow
```python
async def initialize(self, symbols: List[Symbol] = None) -> None:
    """Initialize with futures-specific data"""
    # Initialize base public functionality
    await super().initialize(symbols)
    
    if symbols:
        try:
            # Load futures-specific data (parallel)
            await asyncio.gather(
                self._load_funding_rates(symbols),
                self._load_open_interest(symbols),
                self._load_mark_prices(symbols),
                self._load_index_prices(symbols),
                return_exceptions=True
            )
            
            self.logger.info(
                f"{self._tag} futures data initialized",
                symbols=len(symbols),
                funding_rates=len(self._funding_rates),
                open_interest=len(self._open_interest)
            )
            
        except Exception as e:
            self.logger.error(f"Futures data init failed: {e}")
            raise
```

## Data Refresh Operations

### Enhanced Refresh for Reconnection
```python
async def _refresh_exchange_data(self) -> None:
    """Refresh all data including futures-specific"""
    # Refresh base market data
    await super()._refresh_exchange_data()
    
    if self.active_symbols:
        symbols_list = list(self.active_symbols)
        
        # Refresh futures data
        await asyncio.gather(
            self._load_funding_rates(symbols_list),
            self._load_open_interest(symbols_list),
            self._load_mark_prices(symbols_list),
            self._load_index_prices(symbols_list),
            return_exceptions=True
        )
```

## Update Methods

### Futures Data Updates
```python
def _update_funding_rate(self, symbol: Symbol, funding_rate: Dict) -> None:
    """Update funding rate with validation"""
    # Validate data freshness
    if self._is_stale_data(funding_rate.get('timestamp')):
        self.logger.warning(f"Stale funding rate ignored: {symbol}")
        return
    
    self._funding_rates[symbol] = funding_rate
    
    # Notify arbitrage layer if rate significant
    if abs(funding_rate['rate']) > Decimal('0.001'):
        self.logger.info(
            "High funding rate",
            symbol=symbol,
            rate=funding_rate['rate']
        )

def _update_mark_price(self, symbol: Symbol, mark_price: Decimal) -> None:
    """Update mark price for liquidation monitoring"""
    self._mark_prices[symbol] = mark_price
    
    # Check deviation from index
    if symbol in self._index_prices:
        deviation = abs(mark_price - self._index_prices[symbol]) / self._index_prices[symbol]
        if deviation > Decimal('0.01'):  # 1% deviation
            self.logger.warning(
                "Mark/Index deviation",
                symbol=symbol,
                deviation=deviation
            )
```

## Futures-Specific Queries

### Historical Data Access
```python
async def get_funding_rate_history(
    self,
    symbol: Symbol,
    limit: int = 100
) -> List[Dict]:
    """Get historical funding rates"""
    if not self._public_rest:
        raise RuntimeError("REST client not initialized")
    
    return await self._public_rest.get_funding_rate_history(symbol, limit)
```

## Monitoring and Statistics

### Enhanced Statistics
```python
def get_futures_stats(self) -> Dict[str, Any]:
    """Get futures-specific statistics"""
    base_stats = self.get_orderbook_stats()
    
    futures_stats = {
        'tracked_funding_rates': len(self._funding_rates),
        'tracked_open_interest': len(self._open_interest),
        'tracked_mark_prices': len(self._mark_prices),
        'tracked_index_prices': len(self._index_prices),
        'avg_funding_rate': self._calculate_avg_funding_rate(),
        'total_open_interest_usd': self._calculate_total_oi()
    }
    
    return {**base_stats, **futures_stats}

def _calculate_avg_funding_rate(self) -> Decimal:
    """Calculate average funding rate across symbols"""
    if not self._funding_rates:
        return Decimal('0')
    
    total = sum(
        fr['rate'] for fr in self._funding_rates.values()
    )
    return total / len(self._funding_rates)
```

## Implementation Pattern

### Minimal Futures Implementation
```python
class GateioPublicFuturesExchange(CompositePublicFuturesExchange):
    # Inherit factory methods from spot implementation
    async def _create_public_rest(self) -> PublicFuturesRest:
        return GateioFuturesPublicRest(self.config, self.logger)
    
    async def _create_public_ws_with_handlers(
        self,
        handlers: PublicWebsocketHandlers
    ) -> PublicFuturesWebsocket:
        return GateioFuturesPublicWebsocket(
            self.config,
            handlers,
            self.logger
        )
    
    # Implement futures-specific loaders
    async def _load_funding_rates(self, symbols: List[Symbol]) -> None:
        for symbol in symbols:
            rate = await self._public_rest.get_funding_rate(symbol)
            self._funding_rates[symbol] = rate
    
    # ... other loading methods
```

## Dependencies and Relationships

### External Dependencies
- All CompositePublicExchange dependencies
- Futures-specific data structures (when defined)

### Internal Relationships
- **Parent**: CompositePublicExchange (inherits all)
- **Uses**: PublicFuturesRest, PublicFuturesWebsocket
- **Sibling**: CompositePrivateFuturesExchange

## Implementation Checklist

When implementing futures public composite:

- [ ] Extend CompositePublicFuturesExchange
- [ ] Implement funding rate loading
- [ ] Implement open interest loading
- [ ] Implement mark price loading
- [ ] Implement index price loading
- [ ] Override factory methods if needed
- [ ] Test initialization with futures symbols
- [ ] Verify funding rate updates
- [ ] Check mark/index price accuracy
- [ ] Monitor performance metrics

## Futures Arbitrage Support

### Funding Arbitrage Data
```python
def get_funding_arbitrage_data(self, symbol: Symbol) -> Dict:
    """Get data for funding rate arbitrage"""
    return {
        'funding_rate': self._funding_rates.get(symbol),
        'mark_price': self._mark_prices.get(symbol),
        'index_price': self._index_prices.get(symbol),
        'orderbook': self._orderbooks.get(symbol),
        'next_funding': self._get_next_funding_time(symbol)
    }
```

### Cross-Exchange Comparison
```python
def compare_funding_rates(self, other_exchange: 'CompositePublicFuturesExchange') -> Dict:
    """Compare funding rates with another exchange"""
    comparison = {}
    for symbol in self._funding_rates:
        if symbol in other_exchange._funding_rates:
            our_rate = self._funding_rates[symbol]['rate']
            their_rate = other_exchange._funding_rates[symbol]['rate']
            comparison[symbol] = {
                'our_rate': our_rate,
                'their_rate': their_rate,
                'spread': our_rate - their_rate
            }
    return comparison
```

## Future Enhancements

1. **Funding Payment Calculator**: Calculate actual payment amounts
2. **Liquidation Monitor**: Track liquidation events
3. **Basis Tracking**: Spot-futures basis monitoring
4. **Term Structure**: Multiple expiry tracking
5. **Greeks Calculation**: Options-like risk metrics