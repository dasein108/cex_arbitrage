# Simplified Spot-Futures Task Strategy

A minimalistic arbitrage strategy focused on market-market order execution between 1 spot exchange and 1 futures exchange using dynamic threshold optimization.

## Overview

This strategy is designed as a simplified alternative to the complex `inventory_spot_strategy`, focusing on:

- **Simple Execution**: Market-market orders only (no limit orders)
- **Optimal Thresholds**: Fee-adjusted quantile-based entry/exit points
- **Minimal Configuration**: Essential parameters only
- **Clean Architecture**: Extends `BaseMultiSpotFuturesArbitrageTask` patterns

## Key Features

### 🎯 Simplified Trading Logic
- **Market Orders Only**: No complex limit order management
- **Dual Direction Support**: Spot→Futures and Futures→Spot arbitrage
- **Fee-Adjusted Spreads**: Comprehensive cost modeling including trading fees
- **Quantile-Based Thresholds**: Entry at 75th percentile, exit at 25th percentile

### 📊 Integrated Signal Logic
- **Dynamic Threshold Calculation**: Integrated from `mexc_gateio_futures_arbitrage_signal.py`
- **Volatility Adjustment**: Adaptive thresholds based on spread volatility
- **Historical Window**: Configurable lookback period for quantile calculations
- **Risk Management**: Daily trade limits and minimum spread requirements

### 🏗️ Architectural Benefits
- **Base Class Integration**: Reuses `BaseMultiSpotFuturesArbitrageTask` infrastructure
- **Delta Hedge Management**: Automatic futures position rebalancing
- **Separated Domain Compliance**: Follows project's domain separation patterns
- **HFT Performance**: Optimized for sub-millisecond execution requirements

## Configuration

### Basic Configuration

```python
from db.models import Symbol
from exchanges.structs import ExchangeEnum
from trading.strategies.implementations.spot_futures_task import create_spot_futures_strategy_task

# Create BTC arbitrage strategy
strategy = create_spot_futures_strategy_task(
    symbol=Symbol(base="BTC", quote="USDT"),
    spot_exchange=ExchangeEnum.MEXC,
    futures_exchange=ExchangeEnum.GATEIO_FUTURES,
    order_qty=0.01,           # 0.01 BTC per trade
    total_quantity=0.1,       # Maximum 0.1 BTC position
    entry_quantile=0.75,      # Enter at 75th percentile
    exit_quantile=0.25        # Exit at 25th percentile
)
```

### Advanced Configuration

```python
strategy = create_spot_futures_strategy_task(
    # Basic parameters
    symbol=Symbol(base="ETH", quote="USDT"),
    spot_exchange=ExchangeEnum.MEXC,
    futures_exchange=ExchangeEnum.GATEIO_FUTURES,
    order_qty=0.1,
    total_quantity=1.0,
    
    # Threshold optimization
    entry_quantile=0.80,                    # More selective entry
    exit_quantile=0.20,                     # Earlier exit
    min_spread_threshold=0.003,             # Require 0.3% spread above fees
    
    # Fee structure customization  
    spot_taker_fee=0.0005,                  # 0.05% MEXC spot
    futures_taker_fee=0.0006,               # 0.06% Gate.io futures
    
    # Risk management
    max_daily_trades=15,                    # Conservative trade frequency
    historical_window_hours=24,             # Full day of spread history
    volatility_adjustment=True              # Enable adaptive thresholds
)
```

## Signal Integration

The strategy integrates core logic from `mexc_gateio_futures_arbitrage_signal.py`:

### Fee-Adjusted Spread Calculation
- **Spot→Futures**: `(futures_bid - spot_ask) / spot_ask - total_fees`
- **Futures→Spot**: `(spot_bid - futures_ask) / futures_ask - total_fees`
- **Total Fees**: Spot taker fee + Futures taker fee

### Quantile-Based Thresholds
- **Entry Logic**: Spread percentile >= entry_quantile AND spread > min_threshold
- **Exit Logic**: Spread percentile <= exit_quantile
- **Volatility Adjustment**: `entry_threshold *= (1 + volatility * 10)` in volatile periods

### Historical Window Management
- **Rolling Buffer**: Maintains spread history for quantile calculations
- **Minimum History**: Requires 50+ data points before generating signals
- **Window Size**: `historical_window_hours * 12` (5-minute intervals)

## Execution Flow

### 1. Market Data Processing
```python
# Calculate fee-adjusted spreads for both directions
spreads = self.calculate_fee_adjusted_spreads()

# Update spread history and calculate percentiles
percentile_info = self.update_spread_history(spreads)
```

### 2. Signal Generation
```python
# Determine entry conditions with fee-adjusted profitability
entry_decision = self.should_enter_arbitrage(spreads, percentile_info)

# Check exit conditions for existing positions
should_exit = self.should_exit_arbitrage(percentile_info)
```

### 3. Market Execution
```python
# Execute both legs simultaneously (market-market only)
if entry_decision['should_enter']:
    await self.execute_market_arbitrage(entry_decision['direction'])

# Maintain delta hedge
await self.manage_delta_hedge()
```

## Comparison with Inventory Strategy

| Feature | Inventory Strategy | Spot-Futures Task |
|---------|-------------------|-------------------|
| **Order Types** | Limit + Market orders | Market orders only |
| **Complexity** | ~500 lines complex logic | ~300 lines simplified |
| **Setup Management** | Complex ArbitrageSetup classes | Simple direction strings |
| **Signal Integration** | InventorySpotStrategySignal | Direct signal logic integration |
| **Position Tracking** | Multiple position balances | Single spot + futures positions |
| **Execution Logic** | Conditional limit/market execution | Always market execution |

## Performance Characteristics

### Latency Targets
- **Signal Generation**: <1ms per calculation
- **Market Execution**: <50ms for dual-leg orders
- **Delta Hedge**: <100ms for position rebalancing
- **Spread Calculation**: <0.1ms with efficient numpy operations

### Memory Usage
- **Spread History**: ~288KB for 24-hour window (12 hours * 12 intervals/hour * 8 bytes)
- **Position State**: Minimal state in context classes
- **Signal Buffer**: Fixed-size rolling arrays for optimal performance

### Risk Management
- **Daily Trade Limits**: Configurable maximum trades per day
- **Position Limits**: Enforced total_quantity constraints
- **Minimum Spreads**: Prevents execution below profitability thresholds
- **Exception Handling**: Robust error handling with detailed logging

## Integration Examples

### With Existing Demo Framework
```python
# In your demo/example scripts
from trading.strategies.implementations.spot_futures_task import create_spot_futures_strategy_task

strategy = create_spot_futures_strategy_task(
    symbol=your_symbol,
    spot_exchange=ExchangeEnum.MEXC,
    futures_exchange=ExchangeEnum.GATEIO_FUTURES,
    order_qty=your_order_size,
    total_quantity=your_max_position
)

# Use with existing strategy runner infrastructure
await strategy.start()
while strategy_running:
    await strategy.step()
```

### With Backtesting Framework
The strategy's dynamic column keys and fee-adjusted logic are compatible with the backtesting framework patterns established in the signal implementation.

## Architecture Compliance

### Separated Domain Architecture ✅
- **Public Domain**: Market data access via `book_ticker` interfaces
- **Private Domain**: Trading operations via `place_market_order` methods
- **No Cross-Domain Inheritance**: Extends base class without violating domain separation

### HFT Requirements ✅
- **Sub-millisecond Targets**: Optimized spread calculations and signal logic
- **No Real-time Caching**: Follows HFT caching policy (no orderbook/balance caching)
- **Minimal Configuration**: Fast initialization and context loading

### Project Patterns ✅
- **Struct-First Policy**: Uses msgspec.Struct for all data modeling
- **Exception Propagation**: Proper error handling without function-level suppression
- **LEAN Development**: Implements necessity, avoids speculation
- **Pragmatic SOLID**: Balanced application prioritizing value over dogma

This simplified strategy provides a clean, maintainable foundation for spot-futures arbitrage while integrating the sophisticated threshold optimization logic from the signal framework.