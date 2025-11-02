"""
Visualization and Analysis Utilities

Helper functions for analyzing backtest results and generating insights
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime


class BacktestAnalyzer:
    """Analysis utilities for backtest results"""
    
    @staticmethod
    def analyze_trade_timing(trades_df: pd.DataFrame) -> Dict:
        """Analyze optimal entry timing patterns"""
        
        if len(trades_df) == 0:
            return {'message': 'No trades to analyze'}
        
        # Group by hour if timestamps available
        if 'entry_time' in trades_df.columns:
            try:
                trades_df['hour'] = pd.to_datetime(trades_df['entry_time']).dt.hour
                hourly_pnl = trades_df.groupby('hour')['net_pnl_pct'].agg(['mean', 'count', 'sum'])
                best_hours = hourly_pnl.nlargest(3, 'mean').index.tolist()
                worst_hours = hourly_pnl.nsmallest(3, 'mean').index.tolist()
            except:
                best_hours = []
                worst_hours = []
        else:
            best_hours = []
            worst_hours = []
        
        # Hold time vs P&L analysis
        hold_time_bins = [0, 5, 15, 30, 60, 120, float('inf')]
        hold_time_labels = ['<5min', '5-15min', '15-30min', '30-60min', '1-2h', '>2h']
        trades_df['hold_time_bin'] = pd.cut(trades_df['hold_time'], 
                                             bins=hold_time_bins, 
                                             labels=hold_time_labels)
        
        hold_time_analysis = trades_df.groupby('hold_time_bin')['net_pnl_pct'].agg([
            'mean', 'count', 'std'
        ])
        
        return {
            'best_trading_hours': best_hours,
            'worst_trading_hours': worst_hours,
            'hold_time_analysis': hold_time_analysis,
            'optimal_hold_time': hold_time_analysis['mean'].idxmax(),
        }
    
    @staticmethod
    def calculate_risk_adjusted_metrics(trades_df: pd.DataFrame) -> Dict:
        """Calculate advanced risk-adjusted performance metrics"""
        
        if len(trades_df) == 0:
            return {}
        
        returns = trades_df['net_pnl_pct'].values
        
        # Sortino Ratio (only penalize downside volatility)
        downside_returns = returns[returns < 0]
        downside_std = np.std(downside_returns) if len(downside_returns) > 0 else 0.001
        sortino_ratio = (np.mean(returns) / downside_std * np.sqrt(252)) if downside_std > 0 else 0
        
        # Calmar Ratio (return / max drawdown)
        cumulative_returns = np.cumsum(returns)
        running_max = np.maximum.accumulate(cumulative_returns)
        drawdown = cumulative_returns - running_max
        max_drawdown = np.min(drawdown) if len(drawdown) > 0 else 0.001
        calmar_ratio = np.mean(returns) / abs(max_drawdown) if max_drawdown != 0 else 0
        
        # Omega Ratio (probability weighted gains/losses)
        threshold = 0
        gains = returns[returns > threshold]
        losses = returns[returns <= threshold]
        omega_ratio = (np.sum(gains - threshold) / -np.sum(losses - threshold) 
                      if len(losses) > 0 and np.sum(losses) != 0 else float('inf'))
        
        # Expected Shortfall (CVaR at 95%)
        var_95 = np.percentile(returns, 5)
        cvar_95 = np.mean(returns[returns <= var_95]) if len(returns[returns <= var_95]) > 0 else 0
        
        # Recovery factor
        total_return = np.sum(returns)
        recovery_factor = total_return / abs(max_drawdown) if max_drawdown != 0 else 0
        
        return {
            'sortino_ratio': sortino_ratio,
            'calmar_ratio': calmar_ratio,
            'omega_ratio': omega_ratio,
            'var_95': var_95,
            'cvar_95': cvar_95,
            'max_drawdown': max_drawdown,
            'recovery_factor': recovery_factor,
        }
    
    @staticmethod
    def find_optimal_parameters(df: pd.DataFrame, 
                               backtester,
                               strategy_func: str = 'backtest_spike_capture') -> pd.DataFrame:
        """
        Parameter optimization through grid search
        
        WARNING: This can be slow - consider using fewer iterations
        """
        
        # Parameter grids for different strategies
        param_grids = {
            'backtest_spike_capture': {
                'volatility_threshold': [1.2, 1.3, 1.5, 1.7],
                'z_score_threshold': [1.5, 2.0, 2.5],
                'profit_target_pct': [0.2, 0.3, 0.4],
                'stop_loss_pct': [0.3, 0.4, 0.5],
            },
            'backtest_triangular_arbitrage': {
                'edge_threshold': [0.3, 0.5, 0.7],
                'max_hold_time': [20, 30, 45],
            }
        }
        
        if strategy_func not in param_grids:
            return pd.DataFrame()
        
        grid = param_grids[strategy_func]
        results = []
        
        # Generate all combinations
        from itertools import product
        param_names = list(grid.keys())
        param_values = list(grid.values())
        
        print(f"Testing {np.prod([len(v) for v in param_values])} parameter combinations...")
        
        for combination in product(*param_values):
            params = dict(zip(param_names, combination))
            
            # Run backtest with these parameters
            try:
                if strategy_func == 'backtest_spike_capture':
                    result = backtester.backtest_spike_capture(df, **params)
                elif strategy_func == 'backtest_triangular_arbitrage':
                    result = backtester.backtest_triangular_arbitrage(df, **params)
                else:
                    continue
                
                if result['total_trades'] > 0:
                    results.append({
                        **params,
                        'total_trades': result['total_trades'],
                        'win_rate': result['win_rate'],
                        'total_pnl': result['total_pnl_pct'],
                        'sharpe_ratio': result['sharpe_ratio'],
                        'max_drawdown': result['max_drawdown_pct'],
                        'profit_factor': result['profit_factor'],
                    })
            except Exception as e:
                print(f"Error with params {params}: {e}")
                continue
        
        results_df = pd.DataFrame(results)
        
        if len(results_df) > 0:
            # Rank by Sharpe ratio
            results_df = results_df.sort_values('sharpe_ratio', ascending=False)
        
        return results_df
    
    @staticmethod
    def monte_carlo_simulation(trades_df: pd.DataFrame, 
                              num_simulations: int = 1000,
                              confidence_level: float = 0.95) -> Dict:
        """
        Monte Carlo simulation of trade sequence randomization
        
        Helps understand if results are due to skill or luck
        """
        
        if len(trades_df) == 0:
            return {}
        
        returns = trades_df['net_pnl_pct'].values
        actual_total_return = np.sum(returns)
        actual_sharpe = np.mean(returns) / np.std(returns) if np.std(returns) > 0 else 0
        
        # Run simulations
        simulated_returns = []
        simulated_sharpes = []
        
        for _ in range(num_simulations):
            # Randomly shuffle trade order
            shuffled = np.random.choice(returns, size=len(returns), replace=True)
            sim_return = np.sum(shuffled)
            sim_sharpe = np.mean(shuffled) / np.std(shuffled) if np.std(shuffled) > 0 else 0
            
            simulated_returns.append(sim_return)
            simulated_sharpes.append(sim_sharpe)
        
        # Calculate percentiles
        return_percentile = np.percentile(simulated_returns, 
                                         [100 - confidence_level*100, confidence_level*100])
        sharpe_percentile = np.percentile(simulated_sharpes,
                                         [100 - confidence_level*100, confidence_level*100])
        
        # P-value: probability of achieving actual result by chance
        p_value_return = np.mean(np.array(simulated_returns) >= actual_total_return)
        p_value_sharpe = np.mean(np.array(simulated_sharpes) >= actual_sharpe)
        
        return {
            'actual_return': actual_total_return,
            'simulated_mean_return': np.mean(simulated_returns),
            'return_confidence_interval': return_percentile,
            'p_value_return': p_value_return,
            'actual_sharpe': actual_sharpe,
            'simulated_mean_sharpe': np.mean(simulated_sharpes),
            'sharpe_confidence_interval': sharpe_percentile,
            'p_value_sharpe': p_value_sharpe,
            'statistically_significant': p_value_sharpe < 0.05,
        }
    
    @staticmethod
    def analyze_correlation_impact(df: pd.DataFrame, trades_df: pd.DataFrame) -> Dict:
        """Analyze how correlation affects trade profitability"""
        
        if len(trades_df) == 0:
            return {}
        
        # Merge trade entry correlation with outcomes
        trades_with_corr = trades_df.copy()
        
        # Bin correlation levels
        corr_bins = [0, 0.6, 0.75, 0.85, 0.95, 1.0]
        corr_labels = ['<0.6', '0.6-0.75', '0.75-0.85', '0.85-0.95', '>0.95']
        
        # This would need actual correlation at entry time
        # For now, just show the concept
        
        return {
            'message': 'Correlation impact analysis - need entry correlation data',
            'recommendation': 'Trade only when correlation > 0.75 for safety'
        }
    
    @staticmethod
    def analyze_spread_persistence(df: pd.DataFrame, 
                                   lookback_periods: List[int] = [5, 10, 20]) -> Dict:
        """
        Analyze spread mean reversion speed
        
        Helps determine optimal hold times
        """
        
        if 'mexc_vs_gateio_pct' not in df.columns:
            return {}
        
        spread = df['mexc_vs_gateio_pct']
        
        # Calculate autocorrelation at different lags
        autocorr_results = {}
        for lag in lookback_periods:
            autocorr = spread.autocorr(lag=lag)
            autocorr_results[f'lag_{lag}'] = autocorr
        
        # Half-life calculation (simple AR(1) estimate)
        spread_change = spread.diff().dropna()
        spread_lagged = spread.shift(1).dropna()
        
        # Align indices
        common_idx = spread_change.index.intersection(spread_lagged.index)
        spread_change = spread_change.loc[common_idx]
        spread_lagged = spread_lagged.loc[common_idx]
        
        if len(spread_change) > 10:
            # Simple OLS regression
            mean_change = np.mean(spread_change)
            mean_lagged = np.mean(spread_lagged)
            
            numerator = np.sum((spread_lagged - mean_lagged) * (spread_change - mean_change))
            denominator = np.sum((spread_lagged - mean_lagged) ** 2)
            
            if denominator != 0:
                beta = numerator / denominator
                half_life = -np.log(2) / np.log(1 + beta) if beta < 0 else float('inf')
            else:
                half_life = float('inf')
        else:
            half_life = float('inf')
        
        return {
            'autocorrelation': autocorr_results,
            'half_life_minutes': half_life if half_life != float('inf') else None,
            'interpretation': (
                f"Spread mean-reverts with half-life of {half_life:.1f} minutes"
                if half_life != float('inf') 
                else "Spread does not show clear mean reversion"
            )
        }


def print_advanced_analysis(trades_df: pd.DataFrame, df: pd.DataFrame = None):
    """Print comprehensive analysis of backtest results"""
    
    analyzer = BacktestAnalyzer()
    
    print("\n" + "="*80)
    print("🔬 ADVANCED ANALYSIS")
    print("="*80)
    
    # Risk-adjusted metrics
    print("\n📊 Risk-Adjusted Metrics:")
    risk_metrics = analyzer.calculate_risk_adjusted_metrics(trades_df)
    for metric, value in risk_metrics.items():
        if isinstance(value, float):
            if value == float('inf'):
                print(f"  {metric:20s} ∞")
            else:
                print(f"  {metric:20s} {value:>10.3f}")
    
    # Trade timing
    print("\n⏰ Trade Timing Analysis:")
    timing = analyzer.analyze_trade_timing(trades_df)
    if 'best_trading_hours' in timing and timing['best_trading_hours']:
        print(f"  Best hours:     {timing['best_trading_hours']}")
        print(f"  Worst hours:    {timing['worst_trading_hours']}")
    if 'optimal_hold_time' in timing:
        print(f"  Optimal hold:   {timing['optimal_hold_time']}")
    
    # Monte Carlo
    print("\n🎲 Monte Carlo Simulation (1000 runs):")
    mc_results = analyzer.monte_carlo_simulation(trades_df, num_simulations=1000)
    if mc_results:
        print(f"  Actual Sharpe:       {mc_results['actual_sharpe']:.3f}")
        print(f"  Simulated Mean:      {mc_results['simulated_mean_sharpe']:.3f}")
        print(f"  P-value:             {mc_results['p_value_sharpe']:.3f}")
        print(f"  Significant:         {'✓ Yes' if mc_results['statistically_significant'] else '✗ No'}")
    
    # Spread persistence
    if df is not None:
        print("\n🔄 Spread Mean Reversion:")
        persistence = analyzer.analyze_spread_persistence(df)
        if 'half_life_minutes' in persistence and persistence['half_life_minutes']:
            print(f"  Half-life:           {persistence['half_life_minutes']:.1f} minutes")
            print(f"  {persistence['interpretation']}")
    
    print("="*80)
