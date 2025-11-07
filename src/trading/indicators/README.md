# Trading Indicators - Adaptive Spike Detection

## Overview

This module implements an advanced adaptive spike detection system for cryptocurrency trading across multiple exchanges. The system uses volatility-adjusted technical analysis to identify price anomalies and potential arbitrage opportunities in real-time market data.

## Technical Analysis Methodology

### Core Algorithm: Adaptive Quantile-Based Outlier Detection

The `CandlesSpikeIndicator` employs a sophisticated statistical approach that combines:

1. **Adaptive Smoothing** - Dynamic exponential moving average with volatility adjustment
2. **Rolling Quantile Analysis** - Dynamic thresholds based on recent price behavior
3. **Multi-Exchange Comparison** - Cross-exchange spike analysis for arbitrage detection

### Mathematical Foundation

#### 1. True Price Calculation (Adaptive EMA)

```python
# Short-term volatility normalization
vol = price.rolling(window).std()
vol_norm = vol / vol.mean()

# Adaptive alpha: faster smoothing in low volatility periods
alpha = (1 / window) * (1 / (1 + vol_norm))
true_price = price.ewm(alpha=alpha.mean()).mean()
```

**Purpose**: Creates a volatility-adjusted baseline price that adapts to market conditions:
- **Low volatility**: Faster adaptation (higher alpha) for precise tracking
- **High volatility**: Slower adaptation (lower alpha) to avoid noise

#### 2. Deviation Analysis

```python
deviation = price - true_price
deviation_pct = (deviation / true_price) * 100
```

**Purpose**: Measures how far current price deviates from the "fair value" (true price):
- **Positive deviation**: Price above fair value (potential sell opportunity)
- **Negative deviation**: Price below fair value (potential buy opportunity)

#### 3. Dynamic Quantile Thresholds

```python
upper_q = deviation_pct.rolling(window).quantile(0.99)  # 99th percentile
lower_q = deviation_pct.rolling(window).quantile(0.01)  # 1st percentile
```

**Purpose**: Creates adaptive boundaries based on recent price behavior:
- **Not fixed thresholds**: Adapts to changing market volatility
- **Percentile-based**: Captures extreme movements relative to recent history

#### 4. Spike Detection Logic

```python
is_spike = (deviation_pct > upper_q) | (deviation_pct < lower_q)
```

**Purpose**: Identifies statistical outliers that represent significant price anomalies:
- **Upper spikes**: Potential overvaluation (sell signals)
- **Lower spikes**: Potential undervaluation (buy signals)

## Key Metrics Explained

### Primary Indicators

| Metric | Formula | Trading Significance |
|--------|---------|---------------------|
| `true_price` | Adaptive EMA | Fair value baseline for comparison |
| `deviation` | `price - true_price` | Absolute price displacement |
| `deviation_pct` | `(deviation / true_price) * 100` | Relative price displacement (%) |
| `volatility` | Rolling std of deviation_pct | Market uncertainty measure |
| `is_spike` | Boolean flag | Trade signal indicator |

### Statistical Boundaries

| Metric | Purpose | Trading Application |
|--------|---------|-------------------|
| `upper_q` | 99th percentile threshold | Sell signal boundary |
| `lower_q` | 1st percentile threshold | Buy signal boundary |
| Dynamic range | `upper_q - lower_q` | Market volatility gauge |

### Summary Statistics

| Statistic | Description | Arbitrage Relevance |
|-----------|-------------|-------------------|
| `volatility_std` | Standard deviation of price deviations | Risk assessment |
| `mean_abs_dev` | Average absolute deviation | Typical price displacement |
| `spike_count` | Total number of detected spikes | Market anomaly frequency |
| `max_spike_dev_pct` | Largest spike magnitude | Maximum opportunity size |
| `most_common_up_spike` | Most frequent upward spike size | Typical sell opportunity |
| `most_common_down_spike` | Most frequent downward spike size | Typical buy opportunity |

## Trading Applications

### 1. Single Exchange Spike Trading

**Strategy**: Place limit orders to catch mean reversion after spikes
- **Upward spike detected**: Place sell limit order at current price
- **Downward spike detected**: Place buy limit order at current price
- **Exit**: When price returns toward `true_price`

### 2. Cross-Exchange Arbitrage

**Strategy**: Exploit price discrepancies between exchanges
- **Exchange A spikes up, Exchange B normal**: Sell A, Buy B
- **Exchange A spikes down, Exchange B normal**: Buy A, Sell B
- **Profit**: Capture spread when prices converge

### 3. Volatility-Based Position Sizing

**Risk Management**: Adjust position size based on spike characteristics
- **Low volatility spikes**: Larger positions (more predictable)
- **High volatility spikes**: Smaller positions (higher risk)
- **Frequent spikes**: Reduced exposure (unstable market)

## Advantages Over Traditional Methods

### 1. Adaptive Nature
- **Traditional**: Fixed thresholds (e.g., ±2 standard deviations)
- **This system**: Dynamic thresholds based on recent market behavior

### 2. Volatility Adjustment
- **Traditional**: Static moving averages
- **This system**: Volatility-adjusted smoothing for better responsiveness

### 3. Multi-Exchange Awareness
- **Traditional**: Single exchange analysis
- **This system**: Cross-exchange comparison for arbitrage detection

### 4. Statistical Robustness
- **Traditional**: Normal distribution assumptions
- **This system**: Quantile-based approach (distribution-agnostic)

## Implementation Notes

### Window Size Selection
- **Default: 50 periods** - Balances responsiveness vs. stability
- **Shorter windows**: More sensitive, higher false positives
- **Longer windows**: More stable, slower reaction time

### Quantile Range Configuration
- **Default: (0.01, 0.99)** - Captures extreme 1% movements
- **Tighter range**: More frequent signals, smaller opportunities
- **Wider range**: Fewer signals, larger opportunities

### Performance Considerations
- **Real-time processing**: Optimized for streaming market data
- **Memory efficiency**: Rolling calculations minimize memory footprint
- **Low latency**: Vectorized operations for fast execution

## Risk Warnings

1. **Spike Continuation Risk**: Spikes may continue rather than revert
2. **Liquidity Risk**: Large spikes may indicate poor market depth
3. **Execution Risk**: Fast markets may prevent optimal order fills
4. **Model Risk**: Statistical assumptions may not hold in extreme markets

## Configuration Examples

```python
# Conservative configuration (fewer, higher-quality signals)
indicator = CandlesSpikeIndicator(
    exchanges=exchanges,
    symbol=symbol,
    timeframe=KlineInterval.MINUTE_5,  # Longer timeframe
    lookback_period_hours=48           # More data for stability
)

# Aggressive configuration (more frequent signals)
indicator = CandlesSpikeIndicator(
    exchanges=exchanges,
    symbol=symbol,
    timeframe=KlineInterval.MINUTE_1,  # Shorter timeframe
    lookback_period_hours=12           # Less data for responsiveness
)
```

## Future Enhancements

1. **Machine Learning Integration**: Train models on historical spike patterns
2. **Multi-Timeframe Analysis**: Combine signals from different timeframes
3. **Order Book Integration**: Consider market depth for signal validation
4. **Real-time Alerts**: WebSocket integration for immediate notifications
5. **Backtesting Framework**: Systematic validation of signal performance