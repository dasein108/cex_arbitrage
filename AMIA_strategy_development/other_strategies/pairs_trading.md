# Pairs Trading Strategy - Comprehensive Guide

## Table of Contents
1. [Strategy Overview](#strategy-overview)
2. [Mathematical Framework](#mathematical-framework)
3. [Implementation Details](#implementation-details)
4. [Market Requirements](#market-requirements)
5. [Risk Analysis](#risk-analysis)
6. [Performance Characteristics](#performance-characteristics)
7. [Operational Considerations](#operational-considerations)
8. [Advanced Variations](#advanced-variations)

## Strategy Overview

**Pairs Trading** is a market-neutral statistical arbitrage strategy that exploits temporary price divergences between two highly correlated securities. The strategy assumes that correlated assets will revert to their historical relationship, profiting from mean reversion while maintaining market neutrality.

### Core Principle

The fundamental concept involves:
1. **Identifying** pairs of historically correlated securities
2. **Monitoring** their price relationship (spread)
3. **Trading** when the spread deviates significantly from its mean
4. **Profiting** from the convergence back to the historical relationship

### Strategy Classification
- **Type**: Statistical Arbitrage / Mean Reversion
- **Risk Profile**: Medium
- **Return Potential**: Medium (10-25% annually)
- **Complexity**: Medium
- **Capital Intensity**: Medium

### Key Assumptions
- **Mean reversion**: Price relationships return to historical norms
- **Stationarity**: The spread has consistent statistical properties
- **Cointegration**: Long-term equilibrium relationship exists
- **Sufficient liquidity**: Can execute both legs efficiently

## Mathematical Framework

### 1. Cointegration Analysis

**Augmented Dickey-Fuller Test**:
```
Δy_t = α + βt + γy_{t-1} + Σδ_i Δy_{t-i} + ε_t
```

**Null Hypothesis**: γ = 0 (unit root exists, no cointegration)
**Alternative**: γ < 0 (stationary, cointegrated)

**Engle-Granger Two-Step Method**:
```
Step 1: y_t = α + βx_t + u_t
Step 2: Δu_t = γu_{t-1} + Σδ_i Δu_{t-i} + ε_t
```

**Johansen Test** (for multiple series):
```
Δy_t = Πy_{t-1} + Σ_{i=1}^{k-1} Γ_i Δy_{t-i} + ε_t
```

### 2. Spread Calculation

**Simple Spread**:
```
Spread_t = P1_t - β × P2_t
```

**Log Spread** (for different price levels):
```
Spread_t = ln(P1_t) - β × ln(P2_t)
```

**Optimal Hedge Ratio** (OLS):
```
β = Cov(P1, P2) / Var(P2)
```

**Kalman Filter Dynamic Beta**:
```
β_t = β_{t-1} + K_t(P1_t - β_{t-1} × P2_t)
```

### 3. Signal Generation

**Z-Score Calculation**:
```
Z_t = (Spread_t - μ_{spread}) / σ_{spread}
```

**Entry Signals**:
```
Long Signal: Z_t < -threshold (spread below mean)
Short Signal: Z_t > +threshold (spread above mean)
```

**Exit Signals**:
```
Exit: |Z_t| < exit_threshold or Z_t crosses zero
```

### 4. Position Sizing

**Equal Dollar Allocation**:
```
Position1 = Capital / (2 × P1)
Position2 = -β × Capital / (2 × P2)
```

**Risk Parity**:
```
Position1 = Capital × σ2 / (σ1 + σ2) / P1
Position2 = -Capital × σ1 / (σ1 + σ2) / P2
```

## Implementation Details

### 1. Basic Pairs Trading Implementation

```python
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from statsmodels.tsa.stattools import coint, adfuller
from statsmodels.regression.linear_model import OLS
import logging

@dataclass
class PairsTrade:
    """Pairs trading position data structure"""
    symbol1: str
    symbol2: str
    entry_time: pd.Timestamp
    entry_price1: float
    entry_price2: float
    quantity1: float
    quantity2: float
    hedge_ratio: float
    entry_zscore: float
    exit_time: Optional[pd.Timestamp] = None
    exit_price1: Optional[float] = None
    exit_price2: Optional[float] = None
    pnl: Optional[float] = None
    status: str = "open"

class PairsTrading:
    def __init__(self, 
                 entry_threshold: float = 2.0,
                 exit_threshold: float = 0.5,
                 lookback_period: int = 252,
                 min_correlation: float = 0.7,
                 cointegration_pvalue: float = 0.05):
        
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold
        self.lookback_period = lookback_period
        self.min_correlation = min_correlation
        self.cointegration_pvalue = cointegration_pvalue
        
        self.active_trades = []
        self.closed_trades = []
        self.pair_stats = {}
        self.logger = logging.getLogger(__name__)
    
    def test_cointegration(self, series1: pd.Series, series2: pd.Series) -> Dict:
        """Test for cointegration between two price series"""
        
        # Ensure series are aligned
        aligned_data = pd.concat([series1, series2], axis=1).dropna()
        s1, s2 = aligned_data.iloc[:, 0], aligned_data.iloc[:, 1]
        
        # Correlation test
        correlation = s1.corr(s2)
        
        if correlation < self.min_correlation:
            return {
                'cointegrated': False,
                'reason': 'insufficient_correlation',
                'correlation': correlation
            }
        
        # Cointegration test
        try:
            score, p_value, _ = coint(s1, s2)
            
            # Additional stationarity check on residuals
            ols_result = OLS(s1, s2).fit()
            residuals = ols_result.resid
            adf_stat, adf_p_value, _, _, _, _ = adfuller(residuals)
            
            cointegrated = p_value < self.cointegration_pvalue
            
            return {
                'cointegrated': cointegrated,
                'coint_p_value': p_value,
                'coint_score': score,
                'correlation': correlation,
                'hedge_ratio': ols_result.params[0],
                'adf_stat': adf_stat,
                'adf_p_value': adf_p_value,
                'residuals_stationary': adf_p_value < 0.05
            }
            
        except Exception as e:
            self.logger.error(f"Cointegration test failed: {e}")
            return {
                'cointegrated': False,
                'reason': 'test_failed',
                'error': str(e)
            }
    
    def calculate_spread_statistics(self, series1: pd.Series, series2: pd.Series,
                                  hedge_ratio: float) -> Dict:
        """Calculate spread statistics for signal generation"""
        
        # Calculate spread
        spread = series1 - hedge_ratio * series2
        
        # Rolling statistics
        spread_mean = spread.rolling(self.lookback_period).mean()
        spread_std = spread.rolling(self.lookback_period).std()
        
        # Z-score
        z_score = (spread - spread_mean) / spread_std
        
        # Half-life of mean reversion (Ornstein-Uhlenbeck process)
        spread_lag = spread.shift(1)
        delta_spread = spread.diff()
        
        # Regression: Δspread_t = α + β × spread_{t-1} + ε
        valid_data = pd.concat([delta_spread, spread_lag], axis=1).dropna()
        if len(valid_data) > 10:
            ols_result = OLS(valid_data.iloc[:, 0], valid_data.iloc[:, 1]).fit()
            mean_reversion_coef = ols_result.params[0]
            half_life = -np.log(2) / mean_reversion_coef if mean_reversion_coef < 0 else np.inf
        else:
            half_life = np.inf
        
        return {
            'spread': spread,
            'spread_mean': spread_mean,
            'spread_std': spread_std,
            'z_score': z_score,
            'half_life': half_life,
            'current_zscore': z_score.iloc[-1] if not z_score.empty else 0,
            'spread_volatility': spread_std.iloc[-1] if not spread_std.empty else 0
        }
    
    def generate_trading_signals(self, symbol1: str, symbol2: str,
                               prices1: pd.Series, prices2: pd.Series) -> Dict:
        """Generate pairs trading signals_v2"""
        
        # Test cointegration
        coint_result = self.test_cointegration(prices1, prices2)
        
        if not coint_result['cointegrated']:
            return {
                'signal_type': 'no_signal',
                'reason': coint_result.get('reason', 'not_cointegrated'),
                'cointegration_result': coint_result
            }
        
        hedge_ratio = coint_result['hedge_ratio']
        
        # Calculate spread statistics
        spread_stats = self.calculate_spread_statistics(prices1, prices2, hedge_ratio)
        current_zscore = spread_stats['current_zscore']
        
        # Generate signals_v2
        signal_type = 'no_signal'
        signal_details = {}
        
        if current_zscore > self.entry_threshold:
            # Spread is high - short spread (short asset1, long asset2)
            signal_type = 'short_spread'
            signal_details = {
                'action1': 'short',
                'action2': 'long',
                'rationale': 'spread_above_threshold'
            }
        elif current_zscore < -self.entry_threshold:
            # Spread is low - long spread (long asset1, short asset2)
            signal_type = 'long_spread'
            signal_details = {
                'action1': 'long',
                'action2': 'short',
                'rationale': 'spread_below_threshold'
            }
        
        return {
            'signal_type': signal_type,
            'signal_details': signal_details,
            'hedge_ratio': hedge_ratio,
            'current_zscore': current_zscore,
            'spread_stats': spread_stats,
            'cointegration_result': coint_result
        }
    
    def calculate_position_sizes(self, capital: float, price1: float, price2: float,
                               hedge_ratio: float, allocation_method: str = 'equal_dollar') -> Tuple[float, float]:
        """Calculate optimal position sizes"""
        
        if allocation_method == 'equal_dollar':
            # Equal dollar allocation
            half_capital = capital / 2
            quantity1 = half_capital / price1
            quantity2 = half_capital / price2
            
        elif allocation_method == 'hedge_ratio':
            # Use hedge ratio for sizing
            total_weight = 1 + abs(hedge_ratio)
            weight1 = 1 / total_weight
            weight2 = abs(hedge_ratio) / total_weight
            
            quantity1 = (capital * weight1) / price1
            quantity2 = (capital * weight2) / price2
            
        else:
            raise ValueError(f"Unknown allocation method: {allocation_method}")
        
        return quantity1, quantity2
    
    def execute_pairs_trade(self, signal: Dict, symbol1: str, symbol2: str,
                          price1: float, price2: float, capital: float) -> Optional[PairsTrade]:
        """Execute pairs trading signal"""
        
        if signal['signal_type'] == 'no_signal':
            return None
        
        hedge_ratio = signal['hedge_ratio']
        current_zscore = signal['current_zscore']
        
        # Calculate position sizes
        base_qty1, base_qty2 = self.calculate_position_sizes(
            capital, price1, price2, hedge_ratio
        )
        
        # Adjust for signal direction
        if signal['signal_type'] == 'long_spread':
            # Long asset1, short asset2
            quantity1 = base_qty1
            quantity2 = -base_qty2 * hedge_ratio
        else:  # short_spread
            # Short asset1, long asset2
            quantity1 = -base_qty1
            quantity2 = base_qty2 * hedge_ratio
        
        # Create trade
        trade = PairsTrade(
            symbol1=symbol1,
            symbol2=symbol2,
            entry_time=pd.Timestamp.now(),
            entry_price1=price1,
            entry_price2=price2,
            quantity1=quantity1,
            quantity2=quantity2,
            hedge_ratio=hedge_ratio,
            entry_zscore=current_zscore
        )
        
        self.active_trades.append(trade)
        
        self.logger.info(f"Executed pairs trade: {signal['signal_type']} "
                        f"{symbol1}/{symbol2}, Z-score: {current_zscore:.2f}")
        
        return trade
    
    def check_exit_signals(self, trade: PairsTrade, current_price1: float,
                         current_price2: float, current_zscore: float) -> bool:
        """Check if trade should be exited"""
        
        # Z-score reversal exit
        if abs(current_zscore) < self.exit_threshold:
            return True
        
        # Zero-crossing exit
        if (trade.entry_zscore > 0 and current_zscore < 0) or \
           (trade.entry_zscore < 0 and current_zscore > 0):
            return True
        
        # Time-based exit (optional)
        days_open = (pd.Timestamp.now() - trade.entry_time).days
        if days_open > 30:  # Maximum 30 days
            return True
        
        return False
    
    def close_pairs_trade(self, trade: PairsTrade, exit_price1: float,
                        exit_price2: float, current_zscore: float) -> float:
        """Close pairs trade and calculate P&L"""
        
        # Calculate P&L for each leg
        pnl1 = trade.quantity1 * (exit_price1 - trade.entry_price1)
        pnl2 = trade.quantity2 * (exit_price2 - trade.entry_price2)
        total_pnl = pnl1 + pnl2
        
        # Update trade
        trade.exit_time = pd.Timestamp.now()
        trade.exit_price1 = exit_price1
        trade.exit_price2 = exit_price2
        trade.pnl = total_pnl
        trade.status = "closed"
        
        # Move to closed trades
        self.active_trades.remove(trade)
        self.closed_trades.append(trade)
        
        self.logger.info(f"Closed pairs trade: {trade.symbol1}/{trade.symbol2}, "
                        f"P&L: {total_pnl:.4f}, Exit Z-score: {current_zscore:.2f}")
        
        return total_pnl
```

### 2. Advanced Statistical Analysis

```python
class AdvancedPairsTrading(PairsTrading):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.kalman_filters = {}
    
    def fit_kalman_filter_hedge_ratio(self, series1: pd.Series, series2: pd.Series) -> Dict:
        """Fit Kalman filter for dynamic hedge ratio estimation"""
        from pykalman import KalmanFilter
        
        # State space model: spread_t = [1, P2_t] × [intercept, beta]'
        # Observation model
        obs_mat = np.column_stack([np.ones(len(series2)), series2.values])
        
        # Kalman filter setup
        kf = KalmanFilter(
            n_dim_state=2,
            n_dim_obs=1,
            initial_state_mean=np.array([0, 1]),
            initial_state_covariance=np.eye(2) * 1000,
            transition_matrices=np.eye(2),
            observation_matrices=obs_mat,
            transition_covariance=np.eye(2) * 0.001,
            observation_covariance=np.array([[1]])
        )
        
        # Fit and extract states
        state_means, state_covariances = kf.em(series1.values).smooth()[0]
        
        # Extract dynamic hedge ratios
        intercepts = state_means[:, 0]
        hedge_ratios = state_means[:, 1]
        
        return {
            'dynamic_hedge_ratios': pd.Series(hedge_ratios, index=series1.index),
            'dynamic_intercepts': pd.Series(intercepts, index=series1.index),
            'state_covariances': state_covariances
        }
    
    def calculate_hurst_exponent(self, spread: pd.Series) -> float:
        """Calculate Hurst exponent to measure mean reversion strength"""
        
        # Remove NaN values
        spread_clean = spread.dropna()
        
        if len(spread_clean) < 100:
            return 0.5  # Random walk default
        
        lags = range(2, min(100, len(spread_clean) // 4))
        tau = [np.sqrt(np.std(np.subtract(spread_clean[lag:], spread_clean[:-lag]))) 
               for lag in lags]
        
        # Linear regression on log scale
        log_lags = np.log(lags)
        log_tau = np.log(tau)
        
        # Hurst = slope of log(tau) vs log(lag)
        slope = np.polyfit(log_lags, log_tau, 1)[0]
        hurst = slope
        
        return hurst
    
    def enhanced_signal_generation(self, symbol1: str, symbol2: str,
                                 prices1: pd.Series, prices2: pd.Series) -> Dict:
        """Enhanced signal generation with additional statistical tests"""
        
        # Basic signal generation
        basic_signal = self.generate_trading_signals(symbol1, symbol2, prices1, prices2)
        
        if basic_signal['signal_type'] == 'no_signal':
            return basic_signal
        
        # Additional analysis
        hedge_ratio = basic_signal['hedge_ratio']
        spread = prices1 - hedge_ratio * prices2
        
        # Hurst exponent analysis
        hurst = self.calculate_hurst_exponent(spread)
        mean_reverting = hurst < 0.5
        
        # Volatility regime detection
        spread_vol = spread.rolling(30).std()
        current_vol = spread_vol.iloc[-1]
        avg_vol = spread_vol.mean()
        vol_regime = 'high' if current_vol > avg_vol * 1.5 else 'normal'
        
        # Half-life analysis
        half_life = basic_signal['spread_stats']['half_life']
        suitable_half_life = 1 < half_life < 30  # 1-30 days
        
        # Enhanced signal filtering
        enhanced_signal = basic_signal.copy()
        enhanced_signal.update({
            'hurst_exponent': hurst,
            'mean_reverting': mean_reverting,
            'volatility_regime': vol_regime,
            'half_life': half_life,
            'suitable_half_life': suitable_half_life,
            'signal_quality': 'good' if (mean_reverting and suitable_half_life) else 'poor'
        })
        
        # Filter signals_v2 based on quality
        if not mean_reverting or not suitable_half_life:
            enhanced_signal['signal_type'] = 'no_signal'
            enhanced_signal['reason'] = 'poor_signal_quality'
        
        return enhanced_signal
```

## Market Requirements

### 1. Essential Market Conditions

#### **High Correlation Assets**
- **Historical correlation**: >0.7 consistently over time
- **Economic relationship**: Fundamental business connection
- **Sector similarity**: Same industry or related sectors
- **Market capitalization**: Similar size companies preferred

#### **Liquid Markets**
- **Daily volume**: >$1M average daily volume for each asset
- **Bid-ask spreads**: <0.1% for major assets
- **Market depth**: Sufficient size at multiple price levels
- **Trading hours**: Synchronized trading sessions

#### **Statistical Properties**
- **Cointegration**: Statistically significant long-term relationship
- **Stationarity**: Spread exhibits mean-reverting properties
- **Half-life**: Mean reversion occurs within reasonable timeframe (1-30 days)
- **Volatility**: Sufficient spread volatility for profitable opportunities

### 2. Optimal Market Environments

#### **Mean-Reverting Markets**
- ✅ **Ideal**: Markets without strong trends
- ✅ **Benefit**: Spread deviations more likely to revert
- ✅ **Performance**: Higher success rate for convergence trades

#### **Normal Volatility Regimes**
- ✅ **Ideal**: Moderate volatility (15-30% annualized)
- ❌ **Risk**: Very low volatility reduces opportunities
- ❌ **Risk**: Extremely high volatility breaks relationships

#### **Stable Economic Conditions**
- ✅ **Ideal**: Normal market functioning
- ❌ **Risk**: Economic shocks disrupt correlations
- ❌ **Risk**: Sector rotations break relationships

### 3. Asset Selection Criteria

#### **Quantitative Filters**
```python
def screen_pairs(price_data: pd.DataFrame, min_correlation: float = 0.7,
                min_cointegration_conf: float = 0.05) -> List[Tuple[str, str]]:
    """Screen for suitable pairs trading candidates"""
    
    assets = price_data.columns
    suitable_pairs = []
    
    for i, asset1 in enumerate(assets):
        for asset2 in assets[i+1:]:
            series1 = price_data[asset1].dropna()
            series2 = price_data[asset2].dropna()
            
            # Align series
            aligned = pd.concat([series1, series2], axis=1).dropna()
            if len(aligned) < 252:  # Need at least 1 year of data
                continue
            
            s1, s2 = aligned.iloc[:, 0], aligned.iloc[:, 1]
            
            # Correlation test
            correlation = s1.corr(s2)
            if correlation < min_correlation:
                continue
            
            # Cointegration test
            try:
                score, p_value, _ = coint(s1, s2)
                if p_value < min_cointegration_conf:
                    suitable_pairs.append((asset1, asset2))
            except:
                continue
    
    return suitable_pairs
```

#### **Fundamental Considerations**
- **Business model similarity**: Similar revenue streams
- **Market exposure**: Geographic and sector overlap
- **Competitive dynamics**: Not direct competitors (merger risk)
- **Corporate actions**: Minimal dividend/split differences

## Risk Analysis

### 1. Primary Risk Factors

#### **Correlation Breakdown**
- **Temporary divergence**: Short-term relationship failure
- **Permanent breakdown**: Fundamental business changes
- **Market regime change**: Different correlation during stress
- **Mitigation**: Continuous monitoring, position limits, stop-losses

#### **Mean Reversion Failure**
- **Trending behavior**: Spread continues in one direction
- **Structural breaks**: Permanent level shifts
- **Extended divergence**: Longer than expected reversion time
- **Mitigation**: Half-life monitoring, time-based exits, trend filters

#### **Execution Risk**
- **Leg risk**: Unable to execute both sides simultaneously
- **Slippage**: Market impact during trade execution
- **Liquidity gaps**: Reduced trading during market stress
- **Mitigation**: Algorithmic execution, liquidity checks, position sizing

#### **Model Risk**
- **Parameter instability**: Changing statistical relationships
- **Lookback period**: Optimal historical period selection
- **Regime changes**: Different market behavior periods
- **Mitigation**: Walk-forward testing, adaptive parameters, regime detection

### 2. Risk Metrics and Monitoring

#### **Spread Risk Metrics**
```python
def calculate_spread_risk_metrics(spread: pd.Series) -> Dict:
    """Calculate comprehensive spread risk metrics"""
    
    # Volatility metrics
    current_vol = spread.rolling(30).std().iloc[-1]
    historical_vol = spread.std()
    vol_ratio = current_vol / historical_vol
    
    # Extreme movement analysis
    spread_standardized = (spread - spread.mean()) / spread.std()
    max_deviation = spread_standardized.abs().max()
    var_95 = np.percentile(spread, 5)
    var_99 = np.percentile(spread, 1)
    
    # Autocorrelation analysis
    autocorr_1 = spread.autocorr(lag=1)
    autocorr_5 = spread.autocorr(lag=5)
    
    return {
        'current_volatility': current_vol,
        'volatility_ratio': vol_ratio,
        'max_deviation': max_deviation,
        'var_95': var_95,
        'var_99': var_99,
        'autocorr_1day': autocorr_1,
        'autocorr_5day': autocorr_5,
        'mean_reversion_strength': -autocorr_1  # Stronger mean reversion = more negative
    }
```

#### **Portfolio Risk Controls**
```python
def implement_risk_controls(trades: List[PairsTrade], 
                          max_pairs: int = 10,
                          max_correlation: float = 0.5) -> Dict:
    """Implement portfolio-level risk controls"""
    
    # Position limits
    active_pairs = len([t for t in trades if t.status == 'open'])
    can_add_position = active_pairs < max_pairs
    
    # Correlation limits between pairs
    if len(trades) > 1:
        # Calculate correlation between pair spreads
        # This would require spread data for each pair
        pass
    
    # Sector concentration
    sectors = {}
    for trade in trades:
        sector1 = get_sector(trade.symbol1)  # Would need sector mapping
        sector2 = get_sector(trade.symbol2)
        sectors[sector1] = sectors.get(sector1, 0) + 0.5
        sectors[sector2] = sectors.get(sector2, 0) + 0.5
    
    max_sector_exposure = max(sectors.values()) if sectors else 0
    
    return {
        'can_add_position': can_add_position,
        'active_pairs': active_pairs,
        'max_sector_exposure': max_sector_exposure,
        'sector_diversification': len(sectors) / max(1, len(trades))
    }
```

### 3. Risk Mitigation Strategies

#### **Position Sizing**
- **Kelly criterion**: Optimal position size based on win rate
- **Volatility targeting**: Size based on spread volatility
- **Correlation adjustment**: Reduce size for highly correlated pairs
- **Maximum allocation**: Limit per pair (typically 5-10% of capital)

#### **Exit Rules**
- **Z-score reversal**: Exit when |Z| < exit_threshold
- **Time-based**: Maximum holding period (30-60 days)
- **Stop-loss**: Maximum loss per trade (2-5% of capital)
- **Correlation breakdown**: Exit if correlation drops below threshold

## Performance Characteristics

### 1. Expected Returns

#### **Conservative Implementation**
- **Annual return**: 8-15%
- **Sharpe ratio**: 1.0-1.5
- **Maximum drawdown**: 3-8%
- **Win rate**: 55-65%
- **Average trade duration**: 10-20 days

#### **Moderate Implementation**
- **Annual return**: 12-20%
- **Sharpe ratio**: 1.2-2.0
- **Maximum drawdown**: 5-12%
- **Win rate**: 50-60%
- **Average trade duration**: 5-15 days

#### **Aggressive Implementation**
- **Annual return**: 15-25%
- **Sharpe ratio**: 1.0-1.8
- **Maximum drawdown**: 8-18%
- **Win rate**: 45-55%
- **Average trade duration**: 3-10 days

### 2. Performance Attribution

```python
def analyze_pairs_performance(closed_trades: List[PairsTrade]) -> Dict:
    """Comprehensive performance analysis"""
    
    if not closed_trades:
        return {}
    
    # Basic metrics
    pnls = [trade.pnl for trade in closed_trades]
    total_pnl = sum(pnls)
    win_rate = len([p for p in pnls if p > 0]) / len(pnls)
    
    # Return statistics
    avg_return = np.mean(pnls)
    return_vol = np.std(pnls)
    sharpe = avg_return / return_vol if return_vol > 0 else 0
    
    # Drawdown analysis
    cumulative_pnl = np.cumsum(pnls)
    running_max = np.maximum.accumulate(cumulative_pnl)
    drawdowns = cumulative_pnl - running_max
    max_drawdown = np.min(drawdowns)
    
    # Trade duration analysis
    durations = [(trade.exit_time - trade.entry_time).days 
                for trade in closed_trades if trade.exit_time]
    avg_duration = np.mean(durations) if durations else 0
    
    # Win/loss analysis
    winning_trades = [p for p in pnls if p > 0]
    losing_trades = [p for p in pnls if p <= 0]
    
    profit_factor = (sum(winning_trades) / abs(sum(losing_trades))) \
                   if losing_trades else float('inf')
    
    return {
        'total_trades': len(closed_trades),
        'total_pnl': total_pnl,
        'win_rate': win_rate,
        'average_return': avg_return,
        'sharpe_ratio': sharpe,
        'max_drawdown': max_drawdown,
        'profit_factor': profit_factor,
        'average_duration_days': avg_duration,
        'best_trade': max(pnls),
        'worst_trade': min(pnls)
    }
```

### 3. Market Regime Performance

#### **Normal Markets**
- ✅ **Best performance**: Stable relationships, predictable mean reversion
- ✅ **High win rates**: 60-70% success rate
- ✅ **Consistent returns**: Lower volatility, steady profits

#### **Volatile Markets**
- ⚠️ **Mixed performance**: Higher profits but more risk
- ⚠️ **Lower win rates**: 45-55% success rate
- ⚠️ **Higher drawdowns**: Larger losses when relationships break

#### **Crisis Periods**
- ❌ **Poor performance**: Correlations break down
- ❌ **High losses**: Mean reversion fails
- ❌ **Liquidity issues**: Difficulty exiting positions

## Operational Considerations

### 1. Implementation Timeline

#### **Phase 1: Research & Development** (4-6 weeks)
- Historical data collection and cleaning
- Pair identification and screening
- Cointegration analysis and validation
- Strategy backtesting and optimization

#### **Phase 2: System Development** (4-8 weeks)
- Real-time data feed integration
- Signal generation system
- Order management and execution
- Risk monitoring and alerts

#### **Phase 3: Testing & Validation** (6-8 weeks)
- Paper trading implementation
- Live market testing with small positions
- Performance monitoring and validation
- Parameter fine-tuning

#### **Phase 4: Production Deployment** (2-4 weeks)
- Full capital allocation
- Automated execution
- Real-time monitoring
- Performance reporting

### 2. Technology Requirements

#### **Data Infrastructure**
- **Market data**: Real-time price feeds for all traded assets
- **Historical data**: At least 3 years of daily price history
- **Corporate actions**: Dividend, split, and merger adjustments
- **Alternative data**: Economic indicators, news sentiment

#### **Execution Platform**
- **Order management**: Multi-asset order routing
- **Risk controls**: Real-time position monitoring
- **Latency**: <500ms for signal generation and execution
- **Reliability**: 99.9% uptime requirements

#### **Analytics Platform**
- **Statistical computing**: R/Python with specialized libraries
- **Backtesting engine**: Historical simulation capabilities
- **Performance monitoring**: Real-time P&L and risk metrics
- **Reporting**: Automated performance reports

### 3. Operational Workflow

#### **Daily Operations**
- **Pre-market**: Overnight gap analysis and position adjustments
- **Market hours**: Signal monitoring and trade execution
- **Post-market**: Performance reconciliation and risk review
- **End-of-day**: Portfolio rebalancing and reporting

#### **Weekly Operations**
- **Pair review**: Cointegration relationship monitoring
- **Performance analysis**: Strategy and pair-level attribution
- **Risk assessment**: Correlation and concentration analysis
- **Parameter review**: Statistical model validation

#### **Monthly Operations**
- **Strategy review**: Overall performance evaluation
- **Pair universe update**: Add/remove trading pairs
- **Risk model update**: Parameter recalibration
- **Research**: New pair identification and validation

## Advanced Variations

### 1. Dynamic Pairs Trading

```python
class DynamicPairsTrading(AdvancedPairsTrading):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.regime_detector = None
        self.dynamic_thresholds = {}
    
    def detect_market_regime(self, market_data: pd.DataFrame) -> str:
        """Detect current market regime"""
        
        # Calculate market volatility
        market_returns = market_data.pct_change().mean(axis=1)
        current_vol = market_returns.rolling(30).std().iloc[-1] * np.sqrt(252)
        
        # Volatility regime classification
        if current_vol < 0.15:
            return 'low_volatility'
        elif current_vol > 0.3:
            return 'high_volatility'
        else:
            return 'normal'
    
    def adjust_parameters_for_regime(self, regime: str):
        """Adjust strategy parameters based on market regime"""
        
        regime_params = {
            'low_volatility': {
                'entry_threshold': 1.5,
                'exit_threshold': 0.3,
                'lookback_period': 200
            },
            'normal': {
                'entry_threshold': 2.0,
                'exit_threshold': 0.5,
                'lookback_period': 252
            },
            'high_volatility': {
                'entry_threshold': 2.5,
                'exit_threshold': 0.8,
                'lookback_period': 100
            }
        }
        
        params = regime_params.get(regime, regime_params['normal'])
        self.entry_threshold = params['entry_threshold']
        self.exit_threshold = params['exit_threshold']
        self.lookback_period = params['lookback_period']
```

### 2. Multi-Asset Pairs Trading

```python
class MultiAssetPairsTrading(PairsTrading):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.asset_universe = []
        self.correlation_matrix = None
    
    def build_correlation_matrix(self, price_data: pd.DataFrame) -> pd.DataFrame:
        """Build correlation matrix for asset universe"""
        returns = price_data.pct_change().dropna()
        correlation_matrix = returns.corr()
        self.correlation_matrix = correlation_matrix
        return correlation_matrix
    
    def find_optimal_pairs(self, price_data: pd.DataFrame, 
                          max_pairs: int = 20) -> List[Tuple[str, str]]:
        """Find optimal pairs based on multiple criteria"""
        
        correlation_matrix = self.build_correlation_matrix(price_data)
        assets = correlation_matrix.columns
        
        # Score all possible pairs
        pair_scores = []
        
        for i, asset1 in enumerate(assets):
            for asset2 in assets[i+1:]:
                
                # Correlation score
                correlation = abs(correlation_matrix.loc[asset1, asset2])
                
                # Cointegration test
                series1 = price_data[asset1].dropna()
                series2 = price_data[asset2].dropna()
                coint_result = self.test_cointegration(series1, series2)
                
                if coint_result['cointegrated']:
                    # Combined score
                    score = correlation * (1 - coint_result['coint_p_value'])
                    
                    pair_scores.append({
                        'pair': (asset1, asset2),
                        'score': score,
                        'correlation': correlation,
                        'coint_p_value': coint_result['coint_p_value']
                    })
        
        # Sort by score and return top pairs
        pair_scores.sort(key=lambda x: x['score'], reverse=True)
        return [p['pair'] for p in pair_scores[:max_pairs]]
```

## Conclusion

Pairs trading represents a sophisticated statistical arbitrage strategy that can provide consistent returns with controlled risk. Success requires:

1. **Rigorous pair selection** using statistical tests
2. **Robust signal generation** with multiple confirmation criteria
3. **Effective risk management** at position and portfolio levels
4. **Continuous monitoring** of relationship stability
5. **Adaptive parameters** for changing market conditions

The strategy works best in stable market environments with mean-reverting price relationships. While offering attractive risk-adjusted returns, it requires significant statistical expertise and robust technology infrastructure for successful implementation.

---

**Next**: See [Cross-Exchange Market Making](cross_exchange_market_making.md) for liquidity provision strategies and [Mean Reversion Strategies](mean_reversion_strategies.md) for related approaches.