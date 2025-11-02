# Spread Volatility Harvesting Strategy Documentation

## 📚 Table of Contents
- [Strategy Overview](#strategy-overview)
- [How It Works](#how-it-works)
- [Market Regime Classification](#market-regime-classification)
- [Key Indicators](#key-indicators)
- [Workflow Diagram](#workflow-diagram)
- [Position Management](#position-management)
- [Entry and Exit Conditions](#entry-and-exit-conditions)
- [Risk Management](#risk-management)
- [Real-World Example](#real-world-example)
- [Pros and Cons](#pros-and-cons)

---

## 🎯 Strategy Overview

**Spread Volatility Harvesting** is an advanced multi-tier trading strategy that profits from volatility in negative spread environments by running multiple concurrent positions across different market regimes.

### **Simple Explanation**
Think of this like being a farmer who plants different crops based on weather conditions:
- **Extreme weather** (deep negative spreads): Plant hardy crops (larger positions)
- **Moderate weather** (normal negative spreads): Plant regular crops (medium positions)  
- **Good weather** (positive spreads): Plant premium crops (small positions)
- **Harvest** when conditions improve (spread compression)

You maintain multiple "fields" (positions) simultaneously, each responding to different market conditions.

### **Key Innovation: Multi-Tier Approach**
Unlike single-position strategies, this approach:
- **Runs up to 3 positions simultaneously**
- **Adapts position size** to market regime severity
- **Diversifies entry points** across different volatility levels
- **Scales exposure** based on opportunity quality

---

## 🔧 How It Works

### **The Multi-Tier System**

1. **Classify Market Regime**
   - Analyze current spread levels and volatility
   - Categorize into: EXTREME, DEEP, MODERATE, NORMAL, or POSITIVE
   - Determine appropriate position tier

2. **Scale Position Size**
   - **Tier 1 (Extreme)**: $2,000 positions (highest confidence)
   - **Tier 2 (Deep)**: $1,500 positions (high confidence)
   - **Tier 3 (Moderate)**: $1,000 positions (moderate confidence)

3. **Manage Multiple Positions**
   - Track up to 3 concurrent positions
   - Each position has unique entry conditions and targets
   - Independent exit triggers for each position

4. **Dynamic Exit Strategy**
   - Monitor spread compression for each position
   - Apply time-based and volatility-based exits
   - Calculate tail hedging costs for risk management

### **Position Lifecycle**
```
MONITOR → CLASSIFY → ENTER → TRACK → EXIT → REPEAT
    ↑                                    ↓
    └────────── CONTINUOUS CYCLE ───────┘
```

---

## 🏛️ Market Regime Classification

### **Regime Definitions**

**1. EXTREME_NEGATIVE (Spread < -5.0%)**
- **Characteristics**: Massive market dislocation, panic selling
- **Position Tier**: Tier 1 ($2,000)
- **Confidence**: Highest - these spreads almost always compress
- **Historical Frequency**: 1-5% of time
- **Example**: Major exchange issues, liquidity crises

**2. DEEP_NEGATIVE (Spread < -2.0%)**  
- **Characteristics**: Significant market stress, high volatility
- **Position Tier**: Tier 2 ($1,500)
- **Confidence**: High - strong mean reversion expected
- **Historical Frequency**: 5-15% of time
- **Example**: Market downturns, news-driven selling

**3. MODERATE_NEGATIVE (Spread < -0.5%)**
- **Characteristics**: Normal negative carrying cost, mild stress
- **Position Tier**: Tier 3 ($1,000) 
- **Confidence**: Moderate - gradual compression expected
- **Historical Frequency**: 40-60% of time
- **Example**: Regular futures/spot basis, funding effects

**4. NORMAL (Spread -0.5% to +0.5%)**
- **Characteristics**: Fair value range, efficient markets
- **Action**: No new positions, monitor existing
- **Historical Frequency**: 20-40% of time
- **Example**: Stable market conditions, low volatility

**5. POSITIVE (Spread > +0.5%)**
- **Characteristics**: Potential reverse opportunities
- **Action**: Consider reverse arbitrage (not implemented)
- **Historical Frequency**: 1-10% of time
- **Example**: Futures premium, backwardation

### **Regime Transition Patterns**
```
EXTREME ──► DEEP ──► MODERATE ──► NORMAL ──► POSITIVE
   ↑                                           ↓
   └──── Market Cycle Reversal ──────────────┘
```

---

## 📊 Key Indicators

### **1. Combined Spread (%)**
**What it measures**: Primary signal for regime classification
- **Formula**: `(Futures Price - Spot Price) / Spot Price × 100`
- **Why important**: Determines which tier to activate
- **Typical values**: -5% (extreme) to +1% (positive)

### **2. Spread Volatility**
**What it measures**: How much the spread fluctuates
- **Formula**: 20-period rolling standard deviation of spreads
- **Why important**: Higher volatility = better harvest opportunities
- **Threshold**: Must be > 1.0% for position entry

### **3. Spread Z-Score**
**What it measures**: How unusual current spread is vs. history
- **Formula**: `(Current Spread - Mean) / Standard Deviation`
- **Why important**: Confirms extreme conditions
- **Typical values**: -3.0 (very extreme) to +2.0 (unusual positive)

### **4. Position Tier**
**What it measures**: Risk/reward classification of current opportunity
- **Values**: 1 (extreme), 2 (deep), 3 (moderate)
- **Why important**: Determines position size and confidence level
- **Assignment**: Based on spread thresholds and volatility

### **5. Active Positions Counter**
**What it measures**: Number of current open positions
- **Range**: 0 to 3 maximum
- **Why important**: Prevents over-leverage and manages risk
- **Logic**: New positions only if under maximum

### **6. Tail Hedge Cost (%)**
**What it measures**: Monthly insurance cost against extreme losses
- **Default**: 1% per month (0.033% per day)
- **Why important**: Realistic cost of hedging tail risk
- **Application**: Reduces net returns to account for protection costs

### **7. Position P&L Tracking**
**What it measures**: Individual profit/loss for each position
- **Calculation**: Mark-to-market based on current vs. entry spreads
- **Why important**: Determines exit timing for each position
- **Resolution**: Independent P&L for each tier/position

---

## 🔄 Workflow Diagram

```
START: Monitor Market Continuously
  |
  v
┌─────────────────────────────────────────┐
│         Collect Market Data            │
│                                         │
│ • Spot prices (MEXC, Gate.io)         │
│ • Futures prices (Gate.io)            │
│ • Calculate combined spread            │
│ • Update volatility measures          │
└─────────────────────────────────────────┘
  |
  v
┌─────────────────────────────────────────┐
│        Classify Market Regime          │
│                                         │
│ IF spread < -5.0%: EXTREME_NEGATIVE    │
│ IF spread < -2.0%: DEEP_NEGATIVE       │
│ IF spread < -0.5%: MODERATE_NEGATIVE   │
│ IF spread ±0.5%:   NORMAL              │
│ IF spread > +0.5%: POSITIVE            │
└─────────────────────────────────────────┘
  |
  v
┌─────────────────────────────────────────┐
│       Check Entry Conditions           │
│                                         │
│ 1. Volatility > 1.0%?                 │
│ 2. Active positions < 3?              │
│ 3. Regime = EXTREME/DEEP/MODERATE?     │
│ 4. Z-score indicates extreme?         │
└─────────────────────────────────────────┘
  |
  ├── NO ENTRY ─────────────────┐
  |                             |
  ENTRY CONDITIONS MET          |
  |                             |
  v                             |
┌─────────────────────────────────────────┐
│        Determine Position Tier         │
│                                         │
│ EXTREME_NEGATIVE → Tier 1 ($2,000)    │
│ DEEP_NEGATIVE    → Tier 2 ($1,500)    │
│ MODERATE_NEGATIVE → Tier 3 ($1,000)   │
│                                         │
│ Assign unique position ID              │
│ Record entry spread and time           │
└─────────────────────────────────────────┘
  |
  v
┌─────────────────────────────────────────┐
│         Execute Entry Trade             │
│                                         │
│ • Long futures position               │
│ • Short spot position                 │
│ • Record entry prices                 │
│ • Increment active position counter   │
└─────────────────────────────────────────┘
  |
  v
┌─────────────────────────────────────────┐
│        Monitor All Positions           │
│                                         │
│ For each active position:              │
│ • Calculate current P&L                │
│ • Check exit conditions               │
│ • Update position metrics             │
│ • Apply tail hedge costs              │
└─────────────────────────────────────────┘
  |
  v
┌─────────────────────────────────────────┐
│        Check Exit Conditions           │
│                                         │
│ For each position, check:              │
│ 1. Spread compression (> -0.5%)?      │
│ 2. Time limit exceeded (48 hours)?    │
│ 3. Volatility declined (< 0.5%)?      │
│ 4. Stop loss triggered (-10%)?        │
└─────────────────────────────────────────┘
  |
  ├── NO EXIT ──────────────────┐
  |                             |
  EXIT TRIGGERED                |
  |                             |
  v                             |
┌─────────────────────────────────────────┐
│         Execute Exit Trade              │
│                                         │
│ • Close futures position              │
│ • Close spot position                 │
│ • Calculate final P&L                 │
│ • Decrement active position counter   │
│ • Record exit reason                  │
└─────────────────────────────────────────┘
  |                             |
  v                             |
┌─────────────────────────────────────────┐
│        Update Strategy Metrics         │
│                                         │
│ • Add position P&L to cumulative      │
│ • Update success/failure statistics   │
│ • Recalculate risk metrics            │
│ • Log trade details for analysis      │
└─────────────────────────────────────────┘
  |                             |
  └─────────────────────────────┘
  |
  v
CONTINUE MONITORING (every 5 minutes)

┌─────────────────────────────────────────┐
│          Risk Management Loop           │
│                                         │
│ • Monitor maximum position count (3)   │
│ • Apply tail hedge costs (1%/month)    │
│ • Track regime transition patterns     │
│ • Adjust position sizing if needed     │
│ • Emergency exit if market breakdown   │
└─────────────────────────────────────────┘
```

---

## 🎪 Position Management

### **Multi-Position Tracking System**

**Position ID Assignment**:
- Each position gets unique ID (1.0, 2.0, 3.0, etc.)
- ID increments with each new position entry
- Allows tracking multiple concurrent positions

**Position State Variables**:
```
Position_1: {
  ID: 1.0,
  Tier: EXTREME (1),
  Size: $2,000,
  Entry_Spread: -5.2%,
  Entry_Time: "2025-10-31 18:35:00",
  Current_PnL: +$45.50
}

Position_2: {
  ID: 2.0, 
  Tier: DEEP (2),
  Size: $1,500,
  Entry_Spread: -2.8%,
  Entry_Time: "2025-10-31 19:15:00", 
  Current_PnL: +$12.30
}
```

### **Position Sizing Logic**

**Tier-Based Sizing**:
- **Tier 1 (Extreme)**: $2,000 - highest confidence, largest size
- **Tier 2 (Deep)**: $1,500 - high confidence, medium size  
- **Tier 3 (Moderate)**: $1,000 - moderate confidence, smaller size

**Dynamic Adjustment**:
- Position size may adjust based on available capital
- Never exceed 20% of total portfolio per position
- Scale down if multiple positions would exceed risk limits

### **Portfolio-Level Risk Control**

**Maximum Exposure**:
- **Total positions**: 3 maximum concurrent
- **Total exposure**: $4,500 maximum ($2,000 + $1,500 + $1,000)
- **Portfolio allocation**: Maximum 30% of total capital

**Diversification Benefits**:
- **Time diversification**: Positions entered at different times
- **Regime diversification**: Different tiers respond to different conditions
- **Exit independence**: Each position can exit independently

---

## 🎯 Entry and Exit Conditions

### **Entry Conditions (ALL must be true)**

**Global Entry Requirements**:
1. **Spread volatility > 1.0%**: Market showing significant movement
2. **Active positions < 3**: Room for additional position
3. **Negative regime active**: EXTREME, DEEP, or MODERATE classification

**Tier-Specific Entries**:

**Tier 1 (Extreme) Entry**:
- Spread < -5.0% (extreme dislocation)
- Z-score < -2.5 (very unusual)
- Volatility > 1.5% (high movement)
- Position size: $2,000

**Tier 2 (Deep) Entry**:
- Spread < -2.0% (significant negative)
- Z-score < -2.0 (unusual)
- Volatility > 1.2% (elevated movement)
- Position size: $1,500

**Tier 3 (Moderate) Entry**:
- Spread < -0.5% (moderate negative)
- Z-score < -1.5 (below average)
- Volatility > 1.0% (minimum movement)
- Position size: $1,000

### **Exit Conditions (ANY triggers exit for individual position)**

**Success Exits**:
1. **Spread Compression**: Spread > -0.5% (return to normal)
2. **Target Profit**: Position P&L > 2% (strong performance)

**Risk Management Exits**:
3. **Time Limit**: Position held > 48 hours (prevent indefinite exposure)
4. **Volatility Decline**: Spread volatility < 0.5% (opportunity fading)
5. **Stop Loss**: Position P&L < -10% (limit downside)

**Market Condition Exits**:
6. **Regime Change**: Market transitions to POSITIVE (reversal signal)
7. **Emergency**: Exchange issues or extreme market breakdown

---

## 🛡️ Risk Management

### **Multi-Layer Protection System**

**Position-Level Risk Control**:
- **Individual stop losses**: -10% maximum loss per position
- **Time limits**: 48-hour maximum holding period
- **Size limits**: Tier-based position sizing
- **Entry discipline**: Strict volatility and regime requirements

**Portfolio-Level Risk Control**:
- **Position count limit**: Maximum 3 concurrent positions
- **Total exposure limit**: Maximum $4,500 across all positions
- **Capital allocation**: Maximum 30% of total portfolio
- **Regime diversification**: Positions across different market conditions

**Strategy-Level Risk Control**:
- **Tail hedge cost**: 1% monthly cost for extreme loss protection
- **Volatility monitoring**: Exit when opportunities fade
- **Market regime tracking**: Adapt to changing conditions
- **Emergency protocols**: Immediate exit procedures for system failures

### **Cost Accounting**

**Direct Trading Costs**:
- **Entry/exit fees**: Standard trading commissions
- **Slippage**: Execution price impact
- **Funding costs**: Futures position financing

**Tail Hedge Cost Modeling**:
- **Monthly cost**: 1% of position value (realistic hedge cost)
- **Daily application**: 0.033% applied to each position daily
- **Purpose**: Models cost of purchasing tail risk protection
- **Effect**: Reduces net returns by realistic hedge expense

### **Risk Factors and Mitigation**

**Concentration Risk**:
- **Risk**: All positions in same market/regime
- **Mitigation**: Time and tier diversification

**Liquidity Risk**:
- **Risk**: Cannot exit positions when needed
- **Mitigation**: Position size limits, exchange diversification

**Model Risk**:
- **Risk**: Regime classification fails
- **Mitigation**: Multiple exit triggers, time limits

**Tail Risk**:
- **Risk**: Extreme market events beyond modeling
- **Mitigation**: Explicit tail hedge cost accounting

---

## 💡 Real-World Example

Let's walk through a multi-position scenario:

### **Day 1: Extreme Market Stress**

**Market Conditions**:
- **Combined spread**: -5.2% (EXTREME_NEGATIVE)
- **Volatility**: 1.8% (very high)
- **Z-score**: -3.1 (extremely unusual)

**Position Entry**:
- **Tier 1 position**: $2,000 (highest confidence)
- **Position ID**: 1.0
- **Entry spread**: -5.2%
- **Active positions**: 1/3

### **Day 1 Evening: Market Still Stressed**

**Market Conditions**:
- **Combined spread**: -2.8% (DEEP_NEGATIVE)
- **Volatility**: 1.3% (high)
- **Z-score**: -2.2 (unusual)

**Position Entry**:
- **Tier 2 position**: $1,500 (high confidence)
- **Position ID**: 2.0
- **Entry spread**: -2.8%
- **Active positions**: 2/3

### **Day 2: Partial Recovery**

**Market Conditions**:
- **Combined spread**: -0.8% (MODERATE_NEGATIVE)
- **Volatility**: 1.1% (moderate)

**Position Status**:
- **Position 1.0**: Spread compressed from -5.2% to -0.8% = +4.4% compression
- **Position 2.0**: Spread compressed from -2.8% to -0.8% = +2.0% compression
- **Both positions profitable**, but monitoring for exit signals

### **Day 2 Afternoon: Normal Conditions Return**

**Market Conditions**:
- **Combined spread**: -0.3% (NORMAL)
- **Volatility**: 0.6% (declining)

**Exit Triggers**:
- **Position 1.0**: Spread > -0.5% → EXIT (success!)
- **Position 2.0**: Spread > -0.5% → EXIT (success!)

**Results**:
- **Position 1.0**: +$156 profit (7.8% return)
- **Position 2.0**: +$78 profit (5.2% return)
- **Total profit**: +$234
- **Less tail hedge costs**: -$12 (2 days × $6/day)
- **Net profit**: +$222

---

## ✅ Pros and Cons

### **Advantages**
✅ **Diversified Approach**: Multiple positions across different regimes
✅ **Adaptive Sizing**: Position size matches confidence level
✅ **Risk-Managed**: Multiple exit triggers and position limits
✅ **Scalable**: Can handle varying market conditions
✅ **Regime-Aware**: Responds appropriately to different market states
✅ **Independent Exits**: Each position can exit independently
✅ **Tail-Risk Aware**: Explicit modeling of extreme loss protection

### **Disadvantages**
❌ **Complex Management**: Tracking multiple concurrent positions
❌ **Capital Intensive**: Requires larger capital base for full implementation
❌ **Higher Costs**: Multiple positions increase trading costs
❌ **Model Dependent**: Relies heavily on regime classification accuracy
❌ **Correlation Risk**: Positions may be more correlated than expected
❌ **Monitoring Intensive**: Requires constant attention to multiple positions
❌ **Tail Hedge Drag**: Monthly hedge costs reduce net returns

### **Best Market Conditions**
- **High volatility periods**: Creates multiple tier opportunities
- **Market transitions**: Regime changes provide entry/exit signals
- **Stress events**: Multiple negative regimes create tier diversity
- **Inefficient markets**: Sustained spread dislocations

### **Avoid During**
- **Ultra-low volatility**: Insufficient movement for tier classification
- **Extreme trending markets**: May overwhelm risk management
- **Exchange issues**: Execution difficulties with multiple positions
- **Limited capital**: Strategy requires substantial capital base

---

## 📈 Performance Expectations

### **Realistic Targets**
- **Win Rate**: 70-85% (some positions will lose)
- **Average Winning Position**: 3-8% profit
- **Average Losing Position**: -5-10% loss  
- **Monthly Return**: 8-25% (highly variable based on regimes)
- **Maximum Drawdown**: 10-20% (multiple positions can lose simultaneously)
- **Position Duration**: 12-48 hours average

### **Key Success Factors**
1. **Accurate Regime Classification**: Proper tier assignment crucial
2. **Disciplined Position Sizing**: Stick to tier-based sizing rules
3. **Independent Exit Execution**: Don't hold losing positions too long
4. **Volatility Monitoring**: Enter only during sufficient movement periods
5. **Risk Management**: Respect position limits and stop losses
6. **Cost Management**: Minimize trading costs and factor in tail hedge expenses

### **Performance Drivers**
- **Market volatility**: Higher volatility = more opportunities
- **Regime frequency**: More extreme/deep regimes = better returns
- **Execution quality**: Fast, accurate order execution critical
- **Risk management**: Avoiding large losses preserves capital for next opportunities

---

## 🔧 Implementation Guidelines

### **Capital Requirements**
- **Minimum capital**: $15,000 (for full 3-position implementation)
- **Recommended capital**: $25,000-50,000 (for proper diversification)
- **Reserve requirements**: Keep 70% cash for new opportunities

### **Technology Requirements**
- **Real-time data**: Sub-second price feeds from multiple exchanges
- **Fast execution**: Low-latency order submission and management
- **Position tracking**: Multi-position P&L and risk monitoring
- **Regime classification**: Automated market condition analysis

### **Operational Requirements**
- **24/7 monitoring**: Market conditions can change rapidly
- **Risk oversight**: Continuous position and portfolio risk management
- **Performance tracking**: Detailed analysis of each position's performance
- **Emergency procedures**: Clear protocols for system failures or extreme events

---

*This documentation provides a comprehensive guide to the Spread Volatility Harvesting strategy. This is the most complex of the three reverse arbitrage strategies and requires significant capital, technology infrastructure, and risk management capabilities. Proper implementation demands careful attention to regime classification, position management, and multi-tier risk control.*