# Mean Reversion Strategy

## Overview

The **Mean Reversion Strategy** is a statistical arbitrage approach that identifies when the price spread between MEXC and Gate.io deviates significantly from its historical mean, then positions to profit from the expected reversion to the mean. This strategy assumes that extreme spread deviations are temporary and will eventually normalize.

## Strategy Logic

### Core Concept
Price spreads between exchanges tend to fluctuate around a historical average. When spreads reach extreme values (measured by Z-score), they often revert back toward the mean. This strategy captures that reversion by taking positions when spreads are "stretched" and exiting when they normalize.

### Entry Conditions
```
1. Z-Score Threshold: |spread_z_score| > entry_z_threshold (default: 1.5)
2. Spread Velocity: spread_velocity < 0 (spread is contracting)
3. Correlation Check: rolling_correlation > 0.7 (exchanges still correlated)
4. Direction:
   - If spread > 0 (MEXC expensive): SHORT MEXC, LONG Gate.io  
   - If spread < 0 (Gate.io expensive): LONG MEXC, SHORT Gate.io
```

### Exit Conditions
```
1. Profit Target: |spread_z_score| < exit_z_threshold (default: 0.5)
2. Stop Loss: spread moved against position > stop_loss_pct (default: 0.5%)
3. Time Stop: hold_time > max_hold_minutes (default: 120 minutes)
4. Correlation Break: rolling_correlation < 0.6 (decorrelation)
```

## Technical Indicators

### Primary Indicators

**1. Z-Score Calculation:**
```python
spread_mean = mexc_vs_gateio_pct.rolling(20).mean()
spread_std = mexc_vs_gateio_pct.rolling(20).std()
spread_z_score = (current_spread - spread_mean) / spread_std
```

**2. Spread Velocity:**
```python
spread_velocity = mexc_vs_gateio_pct.diff()  # Rate of change
```

**3. Rolling Correlation:**
```python
rolling_corr = mexc_close.rolling(20).corr(gateio_close)
```

**4. Spread Percentage:**
```python
mexc_vs_gateio_pct = ((mexc_price - gateio_price) / gateio_price) * 100
```

### Statistical Foundation
- **Window Size**: 20 periods for mean/std calculation
- **Z-Score Interpretation**: 
  - Z > +1.5: Spread is 1.5 standard deviations above mean
  - Z < -1.5: Spread is 1.5 standard deviations below mean
- **Mean Reversion Assumption**: 68% of values fall within ±1σ, 95% within ±2σ

## Performance Analysis

### Recent Test Results (BTC_USDT - Real Order Book Data)
**Test Parameters:**
- Symbol: BTC_USDT
- Data Source: Real order book snapshots (6 hours)
- Timeframe: 5-minute aggregation
- Data Points: 10,772 snapshots

**Results:**
```
Total Trades: 184
Win Rate: 0.0%
Total P&L: -25.132%
Average P&L per Trade: -0.137%
Best Trade: -0.112%
Worst Trade: -0.151%
Average Hold Time: 9.1 minutes
Sharpe Ratio: -26.22
Maximum Drawdown: 24.994%
```

### Trade Analysis from CSV Data

**Exit Reason Distribution:**
- Profit Target: 160 trades (87.0%)
- Correlation Stop: 24 trades (13.0%)
- Stop Loss: 0 trades (0.0%)
- Time Stop: 0 trades (0.0%)

**Sample Trades:**
```
Trade #1: Short position, 10min hold, -0.138% net P&L
Trade #9: Short position, 6min hold, -0.136% net P&L  
Trade #17: Short position, 12min hold, -0.132% net P&L
```

**Key Observations:**
1. All trades resulted in losses despite hitting "profit targets"
2. Short holding times (average 9.1 minutes) suggest quick exits
3. 87% of trades exited on profit target, yet all were net losses
4. No stop losses triggered, indicating systematic issue rather than outliers

## Strategy Workflow

```mermaid
graph TD
    A[Calculate Technical Indicators] --> B{Window >= 20 periods?}
    B -->|No| A
    B -->|Yes| C[Calculate Z-Score]
    
    C --> D{|Z-Score| > Entry Threshold?}
    D -->|No| A
    D -->|Yes| E{Spread Velocity < 0?}
    E -->|No| A
    E -->|Yes| F{Correlation > 0.7?}
    F -->|No| A
    F -->|Yes| G[Determine Direction]
    
    G --> H{Spread > 0?}
    H -->|Yes| I[SHORT MEXC, LONG Gate.io]
    H -->|No| J[LONG MEXC, SHORT Gate.io]
    
    I --> K[Monitor Position]
    J --> K
    
    K --> L{Exit Condition Met?}
    L -->|Profit: Z < Exit Threshold| M[Close Position]
    L -->|Stop Loss: Spread Against| N[Close with Loss]
    L -->|Time Stop: > Max Hold| O[Close Neutral]
    L -->|Correlation < 0.6| P[Close Risk Management]
    L -->|No| K
    
    M --> A
    N --> A
    O --> A
    P --> A
```

## Profitability Analysis

### Why Strategy Shows Massive Losses

**1. Trading Cost Mismatch:**
```
Gross Edge Required: 0.14% (trading costs)
Actual Spread Range: -0.045% to 0.053% (0.098% total range)
Problem: Trading costs exceed the entire spread range
```

**2. Z-Score Threshold Issues:**
```
Entry Z-Score: 1.5σ
BTC_USDT typical std: ~0.02%
Entry threshold: 1.5 * 0.02% = 0.03%
Reality: Almost every minor fluctuation triggers entry
```

**3. Mean Reversion Failure:**
```
Assumption: Spreads revert to historical mean
BTC Reality: Tight spreads persist, no significant deviations
Result: "Reversion" profits smaller than transaction costs
```

**4. High-Frequency Noise:**
```
5-minute timeframe captures market microstructure noise
True mean reversion occurs over hours/days, not minutes
Result: Trading against random walk, not true inefficiencies
```

### When Strategy Could Be Profitable

**Favorable Market Conditions:**
1. **Higher Volatility Assets**: Altcoins with wider spreads
2. **Longer Timeframes**: Daily or hourly data for true mean reversion
3. **Market Stress**: During exchange outages or major news events
4. **Lower Costs**: Maker rebates or zero-fee promotional periods

**Historical Success Examples:**
- QUBIC_USDT: Previous tests showed positive returns
- During exchange maintenance windows
- Cryptocurrency market crashes (spread explosions)
- Low-liquidity pair arbitrage

## Pros and Cons

### ✅ Advantages

1. **Statistical Foundation**: Based on proven mean reversion principles
2. **Risk Management**: Multiple exit conditions prevent large losses
3. **Market Neutral**: Profits from inefficiencies, not price direction
4. **Scalable**: Can run across multiple symbols simultaneously
5. **Well-Documented**: Extensive academic research on mean reversion
6. **Correlation Monitoring**: Avoids trading during market disconnects

### ❌ Disadvantages

1. **High Transaction Costs**: Fixed costs overwhelm small edges
2. **Regime Changes**: Mean can shift, making historical stats irrelevant
3. **False Signals**: Noise triggers premature entries
4. **Holding Period Risk**: Longer holds increase adverse selection
5. **Correlation Risk**: Market stress can break exchange correlations
6. **Parameter Sensitivity**: Window size and thresholds need constant tuning

## Real-Time Market Differences

### Backtesting vs Live Trading

| Aspect | Backtesting | Live Trading |
|--------|-------------|--------------|
| **Data Quality** | Perfect 5-min snapshots | Missing ticks, gaps |
| **Execution** | Instant at mid-price | Slippage, partial fills |
| **Spread Calculation** | Based on close prices | Must use bid/ask reality |
| **Rolling Windows** | Precise 20-period calculation | Real-time updates, lag |
| **Correlation** | Backward-looking accuracy | Forward-looking uncertainty |
| **Costs** | Static 0.14% assumption | Dynamic fees, funding |

### Critical Live Trading Issues

**1. Look-Ahead Bias:**
```
Backtest: Z-score calculated with future data points
Reality: Must wait for window to complete before signal
Impact: Signals arrive 1-5 minutes after ideal entry
```

**2. Execution Timing:**
```
Backtest: Simultaneous entry on both exchanges
Reality: Sequential execution, spread can move mid-trade
Impact: Adverse selection, incomplete hedges
```

**3. Data Lag:**
```
Backtest: Perfect synchronization
Reality: Exchange feeds have different latencies
Impact: False spread signals from stale data
```

## Parameter Optimization

### Current Parameters Analysis

| Parameter | Current | Impact of BTC Test | Suggested Range |
|-----------|---------|-------------------|-----------------|
| entry_z_threshold | 1.5 | Too sensitive | 2.0 - 3.0 |
| exit_z_threshold | 0.5 | Too early exit | 0.2 - 0.8 |  
| stop_loss_pct | 0.5% | Never triggered | 0.3% - 1.0% |
| max_hold_minutes | 120 | Never reached | 30 - 240 |
| window_size | 20 | Too short for BTC | 50 - 100 |

### Symbol-Specific Optimization

**BTC_USDT (Major Pair):**
- Higher Z-score thresholds (2.5+)
- Longer rolling windows (50-100 periods)
- Hourly timeframes instead of 5-minute
- Lower position sizes

**Altcoin Pairs:**
- Standard thresholds (1.5-2.0)
- Shorter windows (20-40 periods)
- Higher position sizes
- Faster exit targets

## Implementation Notes

### Code Location
- **File**: `symbol_backtester.py`
- **Method**: `backtest_mean_reversion()`
- **Lines**: ~395-580

### Key Calculations
```python
# Core spread calculation
mexc_vs_gateio_pct = ((mexc_close - gateio_close) / gateio_close) * 100

# Z-score with rolling statistics
spread_mean = mexc_vs_gateio_pct.rolling(window=20).mean()
spread_std = mexc_vs_gateio_pct.rolling(window=20).std()
spread_z_score = (mexc_vs_gateio_pct - spread_mean) / spread_std

# Velocity for trend detection
spread_velocity = mexc_vs_gateio_pct.diff()

# Correlation for regime detection
rolling_corr = mexc_close.rolling(20).corr(gateio_close)
```

### Testing Commands
```bash
# Test mean reversion with real data
PYTHONPATH=src python symbol_backtester.py --symbol BTC_USDT --book-ticker

# Test with different parameters via direct call
# Modify symbol_backtester.py backtest_mean_reversion() call parameters

# Compare multiple strategies
PYTHONPATH=src python simple_all_strategies.py --symbol BTC_USDT --book-ticker
```

## Recommended Improvements

### Statistical Enhancements
1. **Adaptive Windows**: Dynamic window size based on volatility
2. **Outlier Handling**: Robust statistics instead of simple mean/std
3. **Regime Detection**: Switch parameters based on market conditions
4. **Multi-Timeframe**: Combine signals from different timeframes

### Risk Management
1. **Position Sizing**: Scale based on Z-score magnitude
2. **Portfolio Heat**: Limit total exposure across all symbols
3. **Drawdown Protection**: Reduce size after consecutive losses
4. **Correlation Clustering**: Avoid correlated symbol overexposure

### Execution Optimization
1. **Smart Entry**: Wait for spread stabilization before entry
2. **Partial Exits**: Scale out as spread approaches mean
3. **Spread Targeting**: Use limit orders at favorable spread levels
4. **Cross-Exchange**: Optimize order routing between exchanges

### Alternative Approaches
1. **Bollinger Bands**: Use standard deviation bands instead of Z-score
2. **Kalman Filters**: Dynamic mean estimation
3. **Machine Learning**: Train models to predict mean reversion
4. **Regime-Aware**: Different parameters for high/low volatility periods

---

*This strategy requires significant optimization for modern cryptocurrency markets. The classical mean reversion approach needs adaptation for the unique characteristics of crypto exchange spreads. Consider this a starting point for further research rather than a production-ready system.*