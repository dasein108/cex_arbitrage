# Portfolio Rebalancer for Volatile Crypto Assets

A simple, robust portfolio rebalancing system designed for highly volatile cryptocurrency assets on MEXC spot exchange.

## Overview

This rebalancer implements a **Threshold-Based Cascade Strategy** optimized for crypto assets that can move -30% to +200% daily. It maintains equal portfolio weights across a basket of assets through systematic rebalancing when deviations exceed configured thresholds.

## Key Features

- **Simple Threshold Logic**: Rebalances when assets deviate >40% from mean portfolio value
- **Cooldown Protection**: Prevents over-trading during extreme volatility  
- **USDT Reserve Management**: Maintains 30% reserve for market opportunities
- **Backtesting Framework**: Historical performance validation using MEXC kline data
- **Live Trading Support**: Real-time execution via DualExchange interface

## Strategy Rules

### Upside Rebalancing (Asset +40% above mean)
1. Sell 20% of the outperforming asset to USDT
2. Keep 30% of proceeds as USDT reserve
3. Redistribute 70% equally to other assets

### Downside Rebalancing (Asset -35% below mean)  
1. Check USDT reserves first
2. If insufficient, sell from outperforming assets (max 25% each)
3. Buy underperforming asset to restore equal weights

## Configuration

Default settings optimized for volatile markets:
```python
RebalanceConfig(
    upside_threshold=0.40,      # 40% above mean triggers sell
    downside_threshold=0.35,    # 35% below mean triggers buy
    sell_percentage=0.20,       # Sell 20% of outperformer
    usdt_reserve=0.30,         # Keep 30% as USDT reserve
    min_order_value=15.0,      # Minimum $15 orders
    cooldown_minutes=30        # 30min between rebalances per asset
)
```

## Project Structure

```
portfolio_rebalancer/
├── README.md                   # This file
├── __init__.py                # Package initialization
├── config.py                  # Configuration dataclasses
├── rebalancer.py             # Core rebalancing logic
├── backtester.py             # Backtesting framework
├── live_trader.py            # Live trading implementation
├── portfolio_tracker.py      # Portfolio state management
├── utils.py                  # Helper functions
└── examples/
    ├── backtest_example.py   # Backtesting demonstration
    └── live_example.py       # Live trading example
```

## Quick Start

### Backtesting

```python
from src.applications.portfolio_rebalancer import BacktestEngine, RebalanceConfig

# Configure strategy
config = RebalanceConfig(
    upside_threshold=0.40,
    downside_threshold=0.35,
    sell_percentage=0.20,
    usdt_reserve=0.30
)

# Run backtest
engine = BacktestEngine(
    assets=['HANA', 'AIA', 'XAN'],
    initial_capital=10000,
    config=config
)

results = await engine.run_backtest(
    start_date=datetime(2024, 1, 1),
    end_date=datetime(2024, 12, 31)
)

print(results.summary())
```

### Live Trading

```python
from src.applications.portfolio_rebalancer import LiveRebalancer
from src.exchanges.dual_exchange import DualExchange

# Initialize exchange
exchange = DualExchange.get_instance(mexc_config)
await exchange.initialize(symbols)

# Create rebalancer
rebalancer = LiveRebalancer(
    exchange=exchange,
    assets=['HANA', 'AIA', 'XAN'],
    config=config
)

# Run rebalancing loop
await rebalancer.run_forever()
```

## Performance Metrics

The backtester tracks:
- **Total Return**: Overall portfolio performance
- **Sharpe Ratio**: Risk-adjusted returns
- **Max Drawdown**: Largest peak-to-trough decline
- **Rebalance Count**: Number of rebalancing events
- **Win Rate**: Percentage of profitable rebalances
- **Fees Paid**: Total transaction costs

## Risk Management

- **Position Limits**: No single asset >40% of portfolio
- **Minimum Order Size**: $15 to ensure profitability after fees
- **Cooldown Periods**: 30-minute minimum between rebalances
- **USDT Buffer**: Always maintain minimum reserve for opportunities
- **Error Recovery**: Automatic retry with exponential backoff

## Dependencies

- `msgspec`: Fast serialization
- `numpy`: Statistical calculations
- `pandas`: Data analysis (optional)
- MEXC REST API via `DualExchange`

## Testing

Run the test suite:
```bash
python -m pytest src/applications/portfolio_rebalancer/tests/
```

## Important Considerations

### For Volatile Assets (-30% to +200% daily)

1. **Higher Thresholds**: 40% upside, 35% downside (vs standard 25%)
2. **Smaller Sells**: Only 20% of position (vs 25%) to avoid missing rallies
3. **Larger Reserve**: 30% USDT reserve (vs 20%) for volatility
4. **Longer Cooldowns**: 30 minutes minimum between trades

### Exchange Considerations

- MEXC rate limits: 20 requests/second
- Minimum trade sizes vary by asset
- Market orders used for immediate execution
- Slippage expected during high volatility

## License

Proprietary - Internal Use Only