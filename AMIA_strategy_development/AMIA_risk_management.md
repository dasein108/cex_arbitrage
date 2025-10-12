# AMIA Risk Management Framework

## Table of Contents
1. [Risk Factor Identification](#risk-factor-identification)
2. [Quantitative Risk Models](#quantitative-risk-models)
3. [Risk Mitigation Strategies](#risk-mitigation-strategies)
4. [Position Sizing Framework](#position-sizing-framework)
5. [Stop-Loss Mechanisms](#stop-loss-mechanisms)
6. [Portfolio-Level Risk Controls](#portfolio-level-risk-controls)
7. [Real-Time Risk Monitoring](#real-time-risk-monitoring)
8. [Stress Testing Framework](#stress-testing-framework)

## Risk Factor Identification

### 1. Market Risk Factors

#### **Price Movement Risk**
- **Definition**: Risk of adverse price movements in either spot or futures legs
- **Impact**: Direct P&L impact through unfavorable position exits
- **Measurement**: Historical volatility, Value at Risk (VaR)
- **Mitigation**: Position sizing, diversification, stop-losses

#### **Basis Risk**
- **Definition**: Risk of spot-futures price relationship changes
- **Impact**: Convergence failure, unexpected spread movements
- **Measurement**: Basis volatility, correlation breakdown
- **Mitigation**: Shorter holding periods, basis monitoring

#### **Liquidity Risk**
- **Definition**: Risk of inability to exit positions at fair prices
- **Impact**: Wider spreads, slippage, delayed execution
- **Measurement**: Bid-ask spreads, order book depth
- **Mitigation**: Liquidity filters, position limits

### 2. Operational Risk Factors

#### **Execution Risk**
- **Definition**: Risk of orders not being executed as expected
- **Impact**: Partial fills, price slippage, failed arbitrage
- **Measurement**: Fill rates, execution latency
- **Mitigation**: Order management, latency optimization

#### **Technology Risk**
- **Definition**: Risk of system failures, connectivity issues
- **Impact**: Missed opportunities, unmanaged positions
- **Measurement**: System uptime, error rates
- **Mitigation**: Redundancy, fail-safes, monitoring

#### **Exchange Risk**
- **Definition**: Risk of exchange-specific issues or failures
- **Impact**: Frozen positions, delayed settlements
- **Measurement**: Exchange stability metrics
- **Mitigation**: Exchange diversification, position limits

### 3. Model Risk Factors

#### **Signal Degradation**
- **Definition**: Risk of strategy signals becoming less effective
- **Impact**: Reduced performance, increased drawdowns
- **Measurement**: Signal accuracy, hit rates
- **Mitigation**: Continuous monitoring, parameter adaptation

#### **Overfitting Risk**
- **Definition**: Risk of parameters being too specific to historical data
- **Impact**: Poor out-of-sample performance
- **Measurement**: Walk-forward analysis, stability tests
- **Mitigation**: Robust parameter selection, regularization

## Quantitative Risk Models

### 1. Value at Risk (VaR) Model

**Historical Simulation VaR**:
```python
def calculate_historical_var(returns: np.array, confidence_level: float = 0.05) -> float:
    """
    Calculate Historical Simulation VaR
    
    Args:
        returns: Array of historical returns
        confidence_level: VaR confidence level (0.05 for 95% VaR)
    
    Returns:
        VaR value (negative number representing potential loss)
    """
    return np.percentile(returns, confidence_level * 100)

# Example calculation
daily_returns = calculate_daily_strategy_returns(historical_trades)
var_95 = calculate_historical_var(daily_returns, 0.05)
```

**Parametric VaR**:
```python
def calculate_parametric_var(mu: float, sigma: float, confidence_level: float = 0.05) -> float:
    """
    Calculate Parametric VaR assuming normal distribution
    """
    from scipy.stats import norm
    z_score = norm.ppf(confidence_level)
    return mu + z_score * sigma
```

### 2. Expected Shortfall (ES) Model

```python
def calculate_expected_shortfall(returns: np.array, confidence_level: float = 0.05) -> float:
    """
    Calculate Expected Shortfall (Conditional VaR)
    """
    var_threshold = calculate_historical_var(returns, confidence_level)
    tail_returns = returns[returns <= var_threshold]
    return np.mean(tail_returns) if len(tail_returns) > 0 else var_threshold
```

### 3. Maximum Drawdown Model

```python
def calculate_max_drawdown(cumulative_returns: np.array) -> Dict[str, float]:
    """
    Calculate maximum drawdown and related metrics
    """
    peak = np.maximum.accumulate(cumulative_returns)
    drawdown = (cumulative_returns - peak) / peak
    
    max_dd = np.min(drawdown)
    max_dd_idx = np.argmin(drawdown)
    
    # Find peak before maximum drawdown
    peak_idx = np.argmax(cumulative_returns[:max_dd_idx + 1])
    
    # Calculate recovery (if any)
    recovery_idx = None
    if max_dd_idx < len(cumulative_returns) - 1:
        post_dd_values = cumulative_returns[max_dd_idx + 1:]
        recovery_mask = post_dd_values >= cumulative_returns[peak_idx]
        if np.any(recovery_mask):
            recovery_idx = max_dd_idx + 1 + np.argmax(recovery_mask)
    
    return {
        'max_drawdown': max_dd,
        'drawdown_start': peak_idx,
        'drawdown_end': max_dd_idx,
        'recovery_point': recovery_idx,
        'drawdown_duration': max_dd_idx - peak_idx,
        'recovery_duration': (recovery_idx - max_dd_idx) if recovery_idx else None
    }
```

### 4. Correlation Risk Model

```python
def calculate_correlation_risk(spot_returns: np.array, futures_returns: np.array, 
                              lookback_window: int = 252) -> Dict[str, float]:
    """
    Calculate correlation-based risk metrics
    """
    correlation = np.corrcoef(spot_returns, futures_returns)[0, 1]
    
    # Rolling correlation stability
    rolling_corr = []
    for i in range(lookback_window, len(spot_returns)):
        window_corr = np.corrcoef(
            spot_returns[i-lookback_window:i], 
            futures_returns[i-lookback_window:i]
        )[0, 1]
        rolling_corr.append(window_corr)
    
    corr_volatility = np.std(rolling_corr)
    
    return {
        'current_correlation': correlation,
        'correlation_volatility': corr_volatility,
        'correlation_stability': 1 - corr_volatility  # Higher is more stable
    }
```

## Risk Mitigation Strategies

### 1. Position Sizing Framework

#### **Kelly Criterion Adaptation**
```python
def calculate_optimal_position_size(win_rate: float, avg_win: float, avg_loss: float, 
                                   capital: float, max_allocation: float = 0.1) -> float:
    """
    Calculate optimal position size using modified Kelly Criterion
    
    Args:
        win_rate: Historical win rate (0-1)
        avg_win: Average winning trade amount
        avg_loss: Average losing trade amount (positive number)
        capital: Total available capital
        max_allocation: Maximum allocation per trade
    
    Returns:
        Optimal position size
    """
    if avg_loss <= 0:
        return 0
    
    # Kelly fraction calculation
    kelly_fraction = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_loss
    
    # Apply conservative factor and maximum allocation constraint
    conservative_factor = 0.25  # Use 25% of Kelly to reduce risk
    optimal_fraction = min(kelly_fraction * conservative_factor, max_allocation)
    
    return max(optimal_fraction * capital, 0)
```

#### **Volatility-Adjusted Position Sizing**
```python
def calculate_volatility_adjusted_size(target_volatility: float, strategy_volatility: float,
                                     base_position_size: float) -> float:
    """
    Adjust position size based on current volatility vs target
    """
    volatility_ratio = target_volatility / strategy_volatility
    adjusted_size = base_position_size * min(volatility_ratio, 2.0)  # Cap at 2x
    return max(adjusted_size, base_position_size * 0.5)  # Floor at 50%
```

### 2. Dynamic Risk Limits

#### **Adaptive VaR Limits**
```python
class AdaptiveRiskLimits:
    def __init__(self, base_var_limit: float = 0.02):
        self.base_var_limit = base_var_limit
        self.performance_multiplier = 1.0
        
    def update_limits(self, recent_performance: float, volatility_regime: str):
        """
        Update risk limits based on recent performance and market conditions
        """
        # Performance-based adjustment
        if recent_performance > 0:
            self.performance_multiplier = min(1.5, self.performance_multiplier * 1.1)
        else:
            self.performance_multiplier = max(0.5, self.performance_multiplier * 0.9)
        
        # Volatility regime adjustment
        volatility_multiplier = {
            'low': 1.2,
            'normal': 1.0,
            'high': 0.7,
            'extreme': 0.3
        }.get(volatility_regime, 1.0)
        
        return self.base_var_limit * self.performance_multiplier * volatility_multiplier
```

### 3. Stop-Loss Mechanisms

#### **Time-Based Stop-Loss**
```python
def check_time_stop_loss(entry_time: pd.Timestamp, current_time: pd.Timestamp,
                        max_hold_hours: float = 6) -> bool:
    """
    Check if position should be closed due to maximum holding time
    """
    hold_duration = (current_time - entry_time).total_seconds() / 3600
    return hold_duration >= max_hold_hours
```

#### **Adaptive Stop-Loss**
```python
def calculate_adaptive_stop_loss(entry_price: float, current_volatility: float,
                                confidence_level: float = 0.95) -> float:
    """
    Calculate adaptive stop-loss based on current market volatility
    """
    from scipy.stats import norm
    
    # Calculate stop-loss distance based on volatility
    z_score = norm.ppf(1 - confidence_level)
    stop_distance = current_volatility * abs(z_score)
    
    # Convert to price level
    stop_loss_price = entry_price * (1 - stop_distance)
    return stop_loss_price
```

#### **Correlation-Based Stop-Loss**
```python
def check_correlation_stop_loss(spot_returns: np.array, futures_returns: np.array,
                               min_correlation: float = 0.3) -> bool:
    """
    Check if position should be closed due to correlation breakdown
    """
    if len(spot_returns) < 10:  # Minimum samples needed
        return False
    
    current_correlation = np.corrcoef(spot_returns[-10:], futures_returns[-10:])[0, 1]
    return current_correlation < min_correlation
```

## Portfolio-Level Risk Controls

### 1. Risk Budget Allocation

```python
class RiskBudgetManager:
    def __init__(self, total_risk_budget: float):
        self.total_risk_budget = total_risk_budget
        self.allocated_risk = 0.0
        self.active_positions = {}
    
    def allocate_risk(self, position_id: str, position_risk: float) -> bool:
        """
        Check if new position can be allocated within risk budget
        """
        if self.allocated_risk + position_risk <= self.total_risk_budget:
            self.active_positions[position_id] = position_risk
            self.allocated_risk += position_risk
            return True
        return False
    
    def deallocate_risk(self, position_id: str):
        """
        Deallocate risk when position is closed
        """
        if position_id in self.active_positions:
            self.allocated_risk -= self.active_positions[position_id]
            del self.active_positions[position_id]
    
    def get_available_risk_budget(self) -> float:
        """
        Get remaining risk budget
        """
        return self.total_risk_budget - self.allocated_risk
```

### 2. Concentration Risk Management

```python
def calculate_concentration_risk(positions: Dict[str, float], 
                               max_single_position: float = 0.1,
                               max_exchange_exposure: float = 0.3) -> Dict[str, bool]:
    """
    Check for concentration risk violations
    """
    total_exposure = sum(abs(pos) for pos in positions.values())
    
    # Single position concentration
    max_position = max(abs(pos) for pos in positions.values()) if positions else 0
    single_position_risk = max_position / total_exposure if total_exposure > 0 else 0
    
    # Exchange concentration (assuming position keys contain exchange info)
    exchange_exposures = {}
    for pos_key, exposure in positions.items():
        exchange = pos_key.split('_')[0]  # Extract exchange from position key
        exchange_exposures[exchange] = exchange_exposures.get(exchange, 0) + abs(exposure)
    
    max_exchange_exposure_pct = max(exp / total_exposure for exp in exchange_exposures.values()) if exchange_exposures else 0
    
    return {
        'single_position_violation': single_position_risk > max_single_position,
        'exchange_concentration_violation': max_exchange_exposure_pct > max_exchange_exposure,
        'single_position_pct': single_position_risk,
        'max_exchange_exposure_pct': max_exchange_exposure_pct
    }
```

## Real-Time Risk Monitoring

### 1. Risk Dashboard Metrics

```python
class RealTimeRiskMonitor:
    def __init__(self):
        self.risk_metrics = {}
        self.alert_thresholds = {
            'var_breach': 0.02,
            'drawdown_alert': 0.05,
            'correlation_breakdown': 0.3,
            'volatility_spike': 2.0
        }
    
    def update_risk_metrics(self, portfolio_data: Dict) -> Dict[str, Any]:
        """
        Update real-time risk metrics
        """
        current_time = pd.Timestamp.now()
        
        # Calculate current metrics
        self.risk_metrics.update({
            'timestamp': current_time,
            'portfolio_value': portfolio_data['total_value'],
            'var_95': self.calculate_current_var(portfolio_data),
            'current_drawdown': self.calculate_current_drawdown(portfolio_data),
            'active_positions': len(portfolio_data['positions']),
            'leverage_ratio': self.calculate_leverage(portfolio_data),
            'correlation_score': self.calculate_portfolio_correlation(portfolio_data)
        })
        
        # Check for alerts
        alerts = self.check_risk_alerts()
        
        return {
            'metrics': self.risk_metrics,
            'alerts': alerts,
            'status': 'ALERT' if alerts else 'NORMAL'
        }
    
    def check_risk_alerts(self) -> List[Dict[str, Any]]:
        """
        Check for risk threshold breaches
        """
        alerts = []
        
        # VaR breach check
        if self.risk_metrics.get('var_95', 0) < -self.alert_thresholds['var_breach']:
            alerts.append({
                'type': 'VAR_BREACH',
                'severity': 'HIGH',
                'message': f"VaR exceeded threshold: {self.risk_metrics['var_95']:.4f}"
            })
        
        # Drawdown alert
        if self.risk_metrics.get('current_drawdown', 0) < -self.alert_thresholds['drawdown_alert']:
            alerts.append({
                'type': 'DRAWDOWN_ALERT',
                'severity': 'MEDIUM',
                'message': f"Drawdown alert: {self.risk_metrics['current_drawdown']:.4f}"
            })
        
        return alerts
```

### 2. Circuit Breakers

```python
class CircuitBreakerSystem:
    def __init__(self):
        self.breakers = {
            'loss_limit': {'threshold': -0.1, 'active': False},
            'volatility_spike': {'threshold': 3.0, 'active': False},
            'correlation_breakdown': {'threshold': 0.2, 'active': False}
        }
    
    def check_circuit_breakers(self, market_data: Dict) -> Dict[str, bool]:
        """
        Check if any circuit breakers should be triggered
        """
        triggered_breakers = {}
        
        # Daily loss limit
        daily_pnl = market_data.get('daily_pnl', 0)
        if daily_pnl < self.breakers['loss_limit']['threshold']:
            self.breakers['loss_limit']['active'] = True
            triggered_breakers['loss_limit'] = True
        
        # Volatility spike
        current_vol = market_data.get('volatility', 0)
        average_vol = market_data.get('average_volatility', current_vol)
        if current_vol > average_vol * self.breakers['volatility_spike']['threshold']:
            self.breakers['volatility_spike']['active'] = True
            triggered_breakers['volatility_spike'] = True
        
        # Correlation breakdown
        current_corr = market_data.get('correlation', 1.0)
        if current_corr < self.breakers['correlation_breakdown']['threshold']:
            self.breakers['correlation_breakdown']['active'] = True
            triggered_breakers['correlation_breakdown'] = True
        
        return triggered_breakers
    
    def reset_circuit_breaker(self, breaker_name: str):
        """
        Manually reset a circuit breaker
        """
        if breaker_name in self.breakers:
            self.breakers[breaker_name]['active'] = False
```

## Stress Testing Framework

### 1. Historical Stress Testing

```python
def historical_stress_test(strategy_returns: np.array, stress_scenarios: Dict[str, np.array]) -> Dict[str, Dict]:
    """
    Perform stress testing using historical scenarios
    """
    results = {}
    
    for scenario_name, scenario_shocks in stress_scenarios.items():
        # Apply shocks to strategy returns
        stressed_returns = strategy_returns + scenario_shocks[:len(strategy_returns)]
        
        # Calculate stress test metrics
        stressed_cumulative = np.cumprod(1 + stressed_returns)
        stressed_drawdown = calculate_max_drawdown(stressed_cumulative)
        
        results[scenario_name] = {
            'total_return': stressed_cumulative[-1] - 1,
            'volatility': np.std(stressed_returns) * np.sqrt(252),
            'sharpe_ratio': np.mean(stressed_returns) / np.std(stressed_returns) * np.sqrt(252),
            'max_drawdown': stressed_drawdown['max_drawdown'],
            'var_95': calculate_historical_var(stressed_returns, 0.05)
        }
    
    return results
```

### 2. Monte Carlo Stress Testing

```python
def monte_carlo_stress_test(portfolio_params: Dict, num_simulations: int = 1000,
                           time_horizon: int = 252) -> Dict[str, np.array]:
    """
    Perform Monte Carlo stress testing
    """
    results = {
        'final_values': [],
        'max_drawdowns': [],
        'var_95_values': []
    }
    
    for _ in range(num_simulations):
        # Generate random market scenario
        random_returns = np.random.multivariate_normal(
            portfolio_params['expected_returns'],
            portfolio_params['covariance_matrix'],
            time_horizon
        )
        
        # Calculate portfolio performance
        portfolio_returns = np.dot(random_returns, portfolio_params['weights'])
        cumulative_value = np.cumprod(1 + portfolio_returns)
        
        # Calculate metrics
        final_value = cumulative_value[-1]
        max_dd = calculate_max_drawdown(cumulative_value)['max_drawdown']
        var_95 = calculate_historical_var(portfolio_returns, 0.05)
        
        results['final_values'].append(final_value)
        results['max_drawdowns'].append(max_dd)
        results['var_95_values'].append(var_95)
    
    # Convert to numpy arrays for analysis
    for key in results:
        results[key] = np.array(results[key])
    
    return results
```

### 3. Scenario Analysis

```python
def scenario_analysis(base_parameters: Dict, scenario_changes: Dict[str, Dict]) -> pd.DataFrame:
    """
    Perform scenario analysis with parameter variations
    """
    results = []
    
    for scenario_name, parameter_changes in scenario_changes.items():
        # Create modified parameters
        modified_params = base_parameters.copy()
        modified_params.update(parameter_changes)
        
        # Run strategy simulation with modified parameters
        scenario_results = run_strategy_simulation(modified_params)
        
        results.append({
            'scenario': scenario_name,
            'total_return': scenario_results['total_return'],
            'sharpe_ratio': scenario_results['sharpe_ratio'],
            'max_drawdown': scenario_results['max_drawdown'],
            'hit_rate': scenario_results['hit_rate'],
            'profit_factor': scenario_results['profit_factor']
        })
    
    return pd.DataFrame(results)

# Example scenario definitions
stress_scenarios = {
    'market_crash': {
        'market_volatility_multiplier': 3.0,
        'correlation_change': -0.5,
        'liquidity_reduction': 0.5
    },
    'low_volatility': {
        'market_volatility_multiplier': 0.3,
        'spread_compression': 0.5,
        'signal_decay': 0.7
    },
    'high_correlation': {
        'correlation_increase': 0.3,
        'basis_risk_increase': 2.0,
        'execution_cost_increase': 1.5
    }
}
```

---

This comprehensive risk management framework provides the foundation for safe and effective deployment of the AMIA strategy. The combination of quantitative models, real-time monitoring, and stress testing ensures robust risk control across all market conditions.

**Next**: See [Related Strategies](AMIA_related_strategies.md) for delta-neutral variations and [Example Implementation](AMIA_example_implementation.py) for complete working code.