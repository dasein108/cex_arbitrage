# Cross-Exchange Spot-Futures Arbitrage Strategy

A delta-neutral arbitrage strategy that captures basis spread opportunities between spot and futures markets across different exchanges. Optimized for high-profit scenarios like MEXC spot vs Gate.io futures.

## Overview

This strategy implements cross-exchange spot-futures arbitrage, enabling traders to capture basis spread opportunities between different exchanges. The most profitable setups involve spot markets on one exchange (e.g., MEXC, Binance) and futures markets on another (e.g., Gate.io futures), where pricing inefficiencies create arbitrage opportunities.

**Key Examples:**
- **MEXC Spot vs Gate.io Futures**: Often the most profitable due to different market dynamics
- **Binance Spot vs Gate.io Futures**: High liquidity spot paired with efficient futures pricing
- **Same-exchange arbitrage**: Traditional basis trading (lower profits but simpler execution)

## Key Features

### 🎯 **Cross-Exchange Delta-Neutral Position Management**
- Simultaneous spot positions on one exchange and futures positions on another
- Automatic cross-exchange asset transfers for position management
- Automatic position rebalancing to maintain delta neutrality
- Support for both entry (long spot + short futures) and exit modes

### 📊 **Advanced Signal Generation**
- Historical candle data analysis using ArbitrageAnalyzer
- Dynamic threshold calculation with ArbStats (25th percentiles)
- Real-time spread monitoring and validation
- Entry/exit specific validation logic

### ⚡ **High-Performance Execution**
- HFT-optimized order management
- Parallel exchange initialization
- Efficient spread calculation and monitoring
- Sub-millisecond logging integration

### 💰 **Comprehensive PnL Tracking**
- Real-time position tracking with average price calculation
- Separate tracking for realized and unrealized PnL
- Fee accounting and net profit calculation
- Position mode support (accumulate, release, hedge)

## Architecture

### Core Components

1. **SpotFuturesArbitrageTask**: Main strategy execution engine
2. **SpotFuturesArbitrageTaskContext**: Strategy configuration and state
3. **Position**: Unified position tracking with PnL calculation
4. **MarketData**: Exchange-specific configuration

### Key Differences from Cross-Exchange Strategy

| Feature | Original Cross-Exchange | Cross-Exchange Spot-Futures |
|---------|-------------------------|---------------------------|
| Markets | 3 exchanges (source/dest/hedge) | 2 exchanges (spot/futures) |
| Asset Transfer | Inter-exchange transfers required | Inter-exchange transfers for cross-exchange setups |
| Position Types | Source, Dest, Hedge | Spot, Futures |
| Complexity | High (3-way transfer management) | Medium (2-way transfer management) |
| Opportunity | Price differences across 3 exchanges | Basis spread between spot and futures |
| Profit Potential | Medium-High | **High** (especially cross-exchange) |

## Usage

### Basic Configuration

```python
from trading.strategies.implementations.spot_futures_spread_arbitrage_strategy import SpotFuturesArbitrageTaskContext
from exchanges.structs import Symbol, AssetName, ExchangeEnum

# Cross-exchange setup (MEXC spot vs Gate.io futures)
context = SpotFuturesArbitrageTaskContext(
    symbol=Symbol(base=AssetName('BTC'), quote=AssetName('USDT')),
    total_quantity=100.0,
    order_qty=10.0,
    current_mode='enter',
    min_profit_margin=0.15,  # 0.15% (higher for cross-exchange)
    max_acceptable_spread=0.3,  # 0.3% (more tolerance for cross-exchange)
    settings={
        'spot': MarketData(exchange=ExchangeEnum.MEXC),  # MEXC spot
        'futures': MarketData(exchange=ExchangeEnum.GATEIO_FUTURES)  # Gate.io futures
    }
)

# Initialize and run strategy (includes automatic asset transfers)
task = SpotFuturesArbitrageTask(context)
await task.start()
```

### Pre-configured Examples

```python
from .example_config import (
    create_mexc_spot_gateio_futures_config,
    create_binance_spot_gateio_futures_config,
    create_aggressive_cross_exchange_config
)

# MEXC spot vs Gate.io futures (recommended for highest profits)
config = create_mexc_spot_gateio_futures_config('BTC', 'USDT')

# Binance spot vs Gate.io futures (high liquidity setup)
config = create_binance_spot_gateio_futures_config('ETH', 'USDT')

# Aggressive cross-exchange with market orders
config = create_aggressive_cross_exchange_config('SOL', 'USDT')
```

## Signal Generation

### Cross-Exchange Basis Spread Calculation

```python
# Cross-exchange spot vs futures spread (MEXC spot vs Gate.io futures)
spread = (futures_bid - spot_ask) / futures_bid * 100

# Positive spread = Arbitrage opportunity:
#   - Buy on spot exchange (MEXC)
#   - Sell on futures exchange (Gate.io)
# Negative spread = Wait or reverse opportunity
```

### Entry/Exit Logic

- **Entry Signals**: Generated when basis spread exceeds historical thresholds
- **Exit Signals**: Generated when spread normalizes or reverses
- **Dynamic Thresholds**: Based on 25th percentile of historical spread data
- **Spread Validation**: Ensures profitability after fees and execution costs

## Position Management

### Delta-Neutral Rebalancing

```python
delta = spot_qty + futures_qty  # futures_qty is negative for shorts

if delta > min_threshold:
    # Too much long exposure - increase futures short
    place_futures_sell_order(abs(delta))
elif delta < -min_threshold:
    # Too much short exposure - decrease futures short  
    place_futures_buy_order(abs(delta))
```

### Position Modes

- **Accumulate**: Building long spot position
- **Release**: Closing spot position (selling)
- **Hedge**: Managing futures position (typically short)

## Risk Management

### Spread Validation

- **Entry Validation**: Net edge > min_profit_margin after all costs
- **Exit Validation**: 50% more permissive than entry (capital preservation)
- **Execution Costs**: Real-time bid-ask spread monitoring
- **Fee Integration**: Actual exchange fees from configuration

### Position Limits

- Configurable total_quantity and order_qty limits
- Minimum quantity thresholds to prevent dust trades
- Automatic position rebalancing to maintain delta neutrality

## Performance Considerations

### HFT Optimizations

- Parallel exchange initialization
- Efficient numpy array operations for signal calculation
- Sub-millisecond logging with structured tags
- Connection pooling and persistent WebSocket connections

### Memory Efficiency

- Rolling window for historical spread data (7 days max)
- Efficient position tracking with msgspec.Struct
- Minimal object allocation in hot paths

## Monitoring and Debugging

### Comprehensive Logging

```
📊 Current prices: spot_bid=50000, futures_ask=49950
🎯 Spot-futures arbitrage signal: ENTER (basis=0.1%)
✅ Entry validation passed: net_edge=0.05% > required=0.1%
⚖️ Position rebalancing: delta=0.1 BTC
```

### Key Metrics

- Spread validation success/rejection rates
- Position delta and rebalancing frequency
- PnL tracking (gross, net, fees)
- Signal generation statistics

## Files Structure

```
spot_futures_spread_arbitrage_strategy/
├── __init__.py                 # Module exports
├── spot_futures_arbitrage_task.py  # Main strategy implementation
├── unified_position.py         # Position tracking and PnL
├── example_config.py          # Configuration examples
└── README.md                  # This documentation
```

## Integration with Existing Systems

This strategy leverages the existing CEX arbitrage infrastructure:

- **ArbitrageAnalyzer**: Historical candle data and signal generation
- **DualExchange**: Unified public/private exchange interfaces  
- **BaseStrategyTask**: Common strategy lifecycle management
- **HFT Logging**: High-performance structured logging
- **Signal Analysis**: Proven signal calculation from cross-exchange backtests

## Next Steps

1. **Backtesting**: Integrate with existing backtest infrastructure
2. **Paper Trading**: Test with live data but no real trades
3. **Risk Limits**: Add position size and drawdown limits
4. **Multi-Symbol**: Support for multiple trading pairs
5. **Advanced Signals**: ML-based signal enhancement

---

*This strategy represents a complete adaptation of the cross-exchange arbitrage patterns to spot-futures arbitrage, maintaining the same level of sophistication while simplifying the execution model.*