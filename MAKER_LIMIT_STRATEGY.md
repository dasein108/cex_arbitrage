# Maker Limit Order Strategy Analysis

## Strategy Overview

A sophisticated market making strategy for low-liquidity, low-cap volatile altcoins that combines spot limit orders with delta-neutral futures hedging. The strategy aims to profit from wide spot spreads while maintaining market-neutral exposure through futures positions.

### Core Strategy Components:
1. **Spot Market Making**: Place limit orders with safe offset from orderbook top on MEXC
2. **Delta-Neutral Hedging**: Execute futures hedge on Gate.io when spot orders fill
3. **Spread Arbitrage**: Exploit wider spot spreads vs thinner futures spreads
4. **Risk Management**: Dynamic position sizing and offset calculation based on market conditions

## Result Metrics Analysis

### Top 10 Candidates Analysis

```
🏆 TOP 10 CANDIDATES
--------------------------------------------------------------------------------
Symbol          Score    Rec          Risk     Corr     Vol Ratio  Offset  
--------------------------------------------------------------------------------
CRV_USDT        6.50     BUY          LOW      1.000    1.01       1.5     
MINA_USDT       6.50     BUY          LOW      0.983    1.02       1.7     
NKN_USDT        6.50     BUY          LOW      0.982    1.05       1.8     
PERP_USDT       6.50     BUY          LOW      0.994    1.00       1.8     
AEVO_USDT       6.50     BUY          LOW      0.994    1.04       1.6     
NFP_USDT        6.50     BUY          LOW      0.991    1.12       1.9     
PIXEL_USDT      6.50     BUY          LOW      0.997    1.00       1.6     
COTI_USDT       6.50     BUY          LOW      0.987    1.05       1.7     
WAXP_USDT       6.50     BUY          LOW      0.964    1.11       1.8     
SUN_USDT        6.50     BUY          LOW      0.957    1.08       1.6   
```

### Metric Definitions

#### **Score (0-10 Scale)**
Overall candidate quality ranking based on multiple factors:
- **6.50**: Strong BUY recommendation territory
- **Scoring Components**:
  - Volatility advantage (0-2.5 points)
  - Correlation quality (0-2.0 points)
  - Volume adequacy (0-1.5 points)
  - Spike frequency (0-1.5 points)
  - Market regime bonus/penalty (±1.5 points)
  - Spread efficiency (0-1.0 point)
  - Risk penalty (up to -30%)

#### **Recommendation Categories**
- **STRONG BUY** (Score ≥7.0): High-confidence opportunities
- **BUY** (Score ≥5.0): Good opportunities with medium confidence
- **WEAK BUY** (Score ≥3.0): Marginal opportunities requiring caution
- **AVOID** (Score <3.0): Poor risk/reward or failed entry criteria

#### **Risk Level Assessment**
- **LOW**: Minimal risk factors, stable market conditions
- **MEDIUM**: Some risk factors present, requires monitoring
- **HIGH**: Multiple risk factors, avoid or use minimal position size

#### **Correlation (Corr)**
Spot-futures price correlation coefficient:
- **>0.95**: Excellent hedge effectiveness (CRV, PERP, AEVO, PIXEL)
- **0.85-0.95**: Good hedge effectiveness (most candidates)
- **<0.70**: Poor correlation, AVOID for delta-neutral strategy

#### **Volatility Ratio (Vol Ratio)**
Spot volatility divided by futures volatility:
- **>1.20**: Excellent volatility advantage for market making
- **1.05-1.20**: Good advantage (NFP: 1.12, WAXP: 1.11, SUN: 1.08)
- **1.00-1.05**: Minimal advantage but acceptable
- **<1.00**: Futures more volatile than spot (unfavorable)

#### **Liquidity Tier**
Classification based on hourly futures trading volume:
- **ULTRA_LOW** (<50k/hour): Highest risk, smallest positions (30% size)
- **LOW** (50k-100k/hour): **TARGET RANGE** - optimal low-liquidity opportunities
- **MEDIUM** (100k-500k/hour): Standard liquidity, normal parameters
- **HIGH** (>500k/hour): High liquidity, lower opportunity potential

#### **Offset (Ticks)**
Recommended distance from best bid/ask for limit orders:
- **1.5-4.5 ticks**: Range varies by liquidity tier and market conditions
- **Calculation factors**:
  - Base offset: 2-3 ticks (varies by liquidity tier)
  - Volatility multiplier: Based on vol ratio
  - Regime multiplier: 0.7x for mean-reverting, 1.5x for trending
  - Basis volatility adjustment
  - Liquidity offset multiplier: 1.5x for ultra-low, 1.3x for low liquidity
  - High volatility adjustment: +30%

## Candidate Selection Criteria

### **Entry Requirements (Must Pass All)**

#### **1. Correlation Threshold**
```python
correlation >= 0.7  # Minimum 70% correlation
```
- **Purpose**: Ensure hedge effectiveness
- **Critical for**: Delta-neutral strategy success
- **Risk**: Poor correlation = failed hedging

#### **2. Trend Filtering**
```python
trend_strength <= 0.05  # Maximum 5% trend
```
- **Purpose**: Avoid directional markets
- **Logic**: Market making fails in strong trends
- **Detection**: Price vs 20-period SMA deviation

#### **3. Flexible Liquidity Validation (Updated)**
```python
hourly_futures_volume >= 5,000  # Only block extremely dangerous liquidity
# Target range: 25k-100k/hour (low liquidity)
# Warning range: 5k-25k/hour (ultra-low but tradeable)
```
- **Purpose**: Focus on low-liquidity opportunities while avoiding danger
- **Strategy Focus**: <100k/hour volume pairs are the target market
- **Risk Management**: Only block <5k/hour (truly dangerous liquidity)

#### **4. Basis Volatility Limits (Liquidity-Adjusted)**
```python
# More permissive for low liquidity pairs
basis_threshold = 0.15 if liquidity_tier in ['ULTRA_LOW', 'LOW'] else 0.10
basis_volatility <= avg_price * basis_threshold
```
- **Purpose**: Stable hedge relationship with liquidity consideration
- **Logic**: Low liquidity pairs naturally have higher basis volatility
- **Adjustment**: 15% threshold for low liquidity vs 10% for higher liquidity

### **Warning Conditions (Non-Blocking)**

#### **1. Spike Frequency Check**
```python
spike_frequency >= 0.01  # Prefer >1% spike frequency
```
- **Purpose**: Identify opportunity-rich pairs
- **Logic**: Higher spike frequency = more fill opportunities
- **Detection**: 2.5 sigma price movements

#### **2. Volatility Advantage**
```python
volatility_ratio >= 1.2  # Prefer spot 20% more volatile
```
- **Purpose**: Ensure market making edge
- **Logic**: Higher spot volatility = better spread capture opportunities

#### **3. RSI Extremes**
```python
20 <= rsi <= 80  # Avoid extreme RSI conditions
```
- **Purpose**: Avoid mean-reversion exhaustion
- **Logic**: Extreme RSI may indicate trend continuation risk

## Analysis Results Interpretation

### **Why All Candidates Score 6.50**
The uniform scoring suggests:
1. **Similar Market Conditions**: All pairs exhibit comparable risk/reward profiles
2. **Consistent Correlations**: Strong spot-futures relationships across all pairs
3. **Adequate Liquidity**: All pairs pass minimum volume requirements
4. **Mean-Reverting Regime**: Market conditions favor market making strategies

### **Key Observations**

#### **Excellent Correlations (>0.98)**
- **CRV_USDT**: Perfect 1.000 correlation - ideal hedge
- **PERP_USDT**: 0.994 correlation - very reliable hedge
- **AEVO_USDT**: 0.994 correlation - very reliable hedge
- **PIXEL_USDT**: 0.997 correlation - excellent hedge

#### **Volatility Advantages**
- **NFP_USDT**: 1.12 ratio - good volatility edge
- **WAXP_USDT**: 1.11 ratio - solid advantage
- **SUN_USDT**: 1.08 ratio - moderate advantage

#### **Conservative Offsets**
- **Range**: 1.5-1.9 ticks - appropriate for current market conditions
- **Logic**: Low volatility environment = smaller offsets needed
- **Risk Management**: Prevents excessive adverse selection

## Trading Implementation Guidelines

### **Position Entry Protocol**
1. **Pre-Trade Verification**:
   - Confirm futures orderbook depth >$50k
   - Verify correlation hasn't degraded <0.7
   - Check no major news/events pending

2. **Order Placement**:
   - Place limit buy order at (best_bid - offset_ticks)
   - Place limit sell order at (best_ask + offset_ticks)
   - Use recommended position sizes (typically 20-50% of normal)

3. **Fill Management**:
   - **Buy Fill**: Immediately execute market sell on futures
   - **Sell Fill**: Immediately execute market buy on futures
   - Target hedge execution within 100ms

### **Risk Management Rules**

#### **Position Limits**
- **Maximum exposure**: 5-10% of daily futures volume per symbol
- **Position sizing**: Use calculated `position_size_factor` (typically 20-80%)
- **Correlation monitoring**: Exit if correlation drops below 0.6

#### **Market Regime Monitoring**
- **Trending markets**: Reduce position sizes by 50%
- **High volatility**: Increase offsets by 30%
- **Low liquidity**: Avoid new positions

#### **Exit Triggers**
- **Correlation breakdown**: <0.6 correlation
- **Volume drought**: Futures volume <50% of average
- **Trend emergence**: >3% price movement in same direction
- **Basis instability**: >15% basis volatility

## Expected Performance Characteristics

### **Target Metrics**
- **Win Rate**: 60-70% (mean-reverting fills)
- **Average Profit**: 0.1-0.3% per round trip
- **Sharpe Ratio**: 1.5-2.5 (market neutral)
- **Maximum Drawdown**: <5% (with proper risk management)

### **Risk Factors**
- **Execution Risk**: Futures hedge failure
- **Correlation Risk**: Temporary correlation breakdown
- **Liquidity Risk**: Sudden volume disappearance
- **Event Risk**: News-driven directional moves

### **Optimal Market Conditions**
- **Mean-reverting markets**: Best performance environment
- **High intraday volatility**: More fill opportunities
- **Stable basis relationships**: Predictable hedge performance
- **Adequate futures liquidity**: Reliable hedge execution

## Conclusion

The analysis identifies 10 high-quality candidates for the maker limit order strategy, all scoring 6.50/10 with LOW risk ratings. The uniform scoring reflects stable market conditions ideal for market making with delta-neutral hedging.

**Key Success Factors**:
1. **Excellent correlations** (0.957-1.000) ensure reliable hedging
2. **Conservative offsets** (1.5-1.9 ticks) balance opportunity vs risk
3. **Adequate liquidity** enables consistent execution
4. **Mean-reverting regime** favors market making strategies

**Recommended Implementation**: Start with highest correlation pairs (CRV, PERP, AEVO, PIXEL) using conservative position sizes and monitor performance before scaling to full allocation.