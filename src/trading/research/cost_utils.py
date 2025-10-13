"""
Delta-Neutral Arbitrage Parameter Optimization Utilities

This module provides quantitative methods for optimizing entry and exit parameters
in delta-neutral arbitrage strategies. Two main approaches are implemented:

1. Statistical Approach: Based on historical spread distribution analysis
2. Risk-Adjusted Approach: Optimized for risk-adjusted returns and drawdown control

Theoretical Foundation:
====================

Delta-neutral arbitrage profits from temporary price discrepancies between 
correlated instruments (spot vs futures) while remaining hedged against 
directional price movements. The key challenge is optimizing:

- Entry Threshold (max_entry_cost_pct): The spread cost threshold for entering positions
- Exit Target (min_profit_pct): The profit target for closing positions

Entry Threshold Theory:
- Lower thresholds = fewer but higher quality trades
- Must exceed transaction costs: 2 * (spot_fee + futures_fee) + bid_ask_spread
- Should be based on spread distribution percentiles (typically 10th-25th percentile)
- Accounts for spread volatility and mean reversion characteristics

Exit Target Theory:
- Must provide positive expected value after all transaction costs
- Balance between holding time risk and profit realization
- Consider spread mean reversion speed and volatility clustering
- Optimal target often 2-3x transaction costs for adequate risk premium

Risk Considerations:
- Delta-neutral strategies have limited directional risk but face basis risk
- Spread widening during market stress can cause losses
- Optimal parameters balance trade frequency vs trade quality
- Risk-adjusted optimization considers Sharpe ratio and maximum drawdown
"""

import pandas as pd
import numpy as np
from typing import Tuple, Dict, List, Optional
from dataclasses import dataclass
import warnings


@dataclass
class ParameterRecommendation:
    """Container for parameter optimization results"""
    max_entry_cost_pct: float
    min_profit_pct: float
    expected_trades_per_day: float
    expected_win_rate: float
    expected_avg_profit: float
    confidence_score: float
    reasoning: str


@dataclass
class SpreadStatistics:
    """Container for spread analysis results"""
    mean_entry_cost: float
    std_entry_cost: float
    percentiles: Dict[int, float]
    mean_reversion_speed: float
    volatility_clustering: float
    transaction_cost_floor: float


def calculate_spread_statistics(df: pd.DataFrame, 
                              spot_fee: float = 0.0005, 
                              fut_fee: float = 0.0005) -> SpreadStatistics:
    """
    Calculate comprehensive spread statistics for parameter optimization.
    
    Args:
        df: DataFrame with spot_ask_price, fut_bid_price, spot_bid_price, fut_ask_price columns
        spot_fee: Spot market transaction fee (default 0.05%)
        fut_fee: Futures market transaction fee (default 0.05%)
    
    Returns:
        SpreadStatistics object with key metrics
    
    Theory:
        Analyzes the statistical properties of spreads to inform parameter selection.
        Entry cost distribution helps set selective entry thresholds.
        Mean reversion metrics inform exit timing strategies.
    """
    # Calculate entry and exit costs
    df = df.copy()
    df['entry_cost_pct'] = ((df['spot_ask_price'] - df['fut_bid_price']) / 
                           df['spot_ask_price']) * 100
    df['exit_cost_pct'] = ((df['fut_ask_price'] - df['spot_bid_price']) / 
                          df['fut_ask_price']) * 100
    
    # Basic statistics
    entry_costs = df['entry_cost_pct'].dropna()
    mean_entry = entry_costs.mean()
    std_entry = entry_costs.std()
    
    # Percentile analysis for threshold setting
    percentiles = {
        p: entry_costs.quantile(p/100) 
        for p in [5, 10, 15, 20, 25, 30, 50, 75, 90, 95]
    }
    
    # Mean reversion analysis
    # Calculate spread changes to measure mean reversion speed
    df['spread_change'] = df['entry_cost_pct'].diff()
    mean_reversion_speed = abs(df['spread_change'].autocorr(lag=1))
    
    # Volatility clustering (GARCH-like effect)
    volatility_clustering = abs(df['spread_change'].rolling(10).std().autocorr(lag=1))
    
    # Transaction cost floor (minimum profitable spread)
    transaction_cost_floor = 2 * (spot_fee + fut_fee) * 100  # Convert to percentage
    
    return SpreadStatistics(
        mean_entry_cost=mean_entry,
        std_entry_cost=std_entry,
        percentiles=percentiles,
        mean_reversion_speed=mean_reversion_speed,
        volatility_clustering=volatility_clustering,
        transaction_cost_floor=transaction_cost_floor
    )


def optimize_parameters_statistical(df: pd.DataFrame,
                                  spot_fee: float = 0.0005,
                                  fut_fee: float = 0.0005,
                                  target_trades_per_day: Optional[float] = None,
                                  conservatism_level: str = 'moderate') -> ParameterRecommendation:
    """
    Statistical approach to parameter optimization based on historical spread distribution.
    
    Args:
        df: Historical market data DataFrame
        spot_fee: Spot market transaction fee
        fut_fee: Futures market transaction fee  
        target_trades_per_day: Desired trade frequency (None for optimal balance)
        conservatism_level: 'conservative', 'moderate', or 'aggressive'
    
    Returns:
        ParameterRecommendation with optimal parameters
    
    Theory:
        Uses historical spread distribution to set entry thresholds at statistically
        favorable levels. Entry threshold based on percentiles ensures selectivity
        while maintaining reasonable trade frequency. Exit target optimized for
        risk-adjusted returns considering transaction costs and mean reversion.
        
        Conservative: Lower trade frequency, higher profit margins (10th percentile entry)
        Moderate: Balanced approach (20th percentile entry)  
        Aggressive: Higher frequency, lower margins (30th percentile entry)
    """
    # Calculate entry_cost_pct for trade frequency estimation
    df_with_costs = df.copy()
    df_with_costs['entry_cost_pct'] = ((df_with_costs['spot_ask_price'] - df_with_costs['fut_bid_price']) / 
                                       df_with_costs['spot_ask_price']) * 100
    
    stats = calculate_spread_statistics(df, spot_fee, fut_fee)
    
    # Set conservatism parameters
    conservatism_params = {
        'conservative': {'entry_percentile': 10, 'profit_multiplier': 3.0, 'confidence': 0.9},
        'moderate': {'entry_percentile': 20, 'profit_multiplier': 2.5, 'confidence': 0.8},
        'aggressive': {'entry_percentile': 30, 'profit_multiplier': 2.0, 'confidence': 0.7}
    }
    
    params = conservatism_params[conservatism_level]
    
    # Entry threshold: Use percentile of favorable spreads
    max_entry_cost_pct = stats.percentiles[params['entry_percentile']]
    
    # Ensure entry threshold is above transaction cost floor
    max_entry_cost_pct = max(max_entry_cost_pct, stats.transaction_cost_floor * 1.1)
    
    # Exit target: Multiple of transaction costs with risk premium
    min_profit_pct = stats.transaction_cost_floor * params['profit_multiplier']
    
    # Estimate trade frequency and performance
    favorable_entries = (df_with_costs['entry_cost_pct'] <= max_entry_cost_pct).sum()
    hours_in_data = len(df) / (24 * 60 / 5)  # Assuming 5-minute bars
    expected_trades_per_day = favorable_entries / (hours_in_data / 24) if hours_in_data > 0 else 0
    
    # Estimate win rate based on mean reversion strength
    expected_win_rate = 0.6 + (stats.mean_reversion_speed * 0.3)  # 60-90% range
    expected_win_rate = min(0.9, max(0.5, expected_win_rate))
    
    # Expected average profit (simplified estimate)
    expected_avg_profit = min_profit_pct * 0.8  # Account for early exits
    
    reasoning = f"""
    Statistical Analysis Results:
    - Entry threshold: {max_entry_cost_pct:.4f}% ({params['entry_percentile']}th percentile)
    - Exit target: {min_profit_pct:.4f}% ({params['profit_multiplier']}x transaction costs)
    - Mean reversion strength: {stats.mean_reversion_speed:.3f}
    - Transaction cost floor: {stats.transaction_cost_floor:.4f}%
    - Conservatism level: {conservatism_level}
    """
    
    return ParameterRecommendation(
        max_entry_cost_pct=max_entry_cost_pct,
        min_profit_pct=min_profit_pct,
        expected_trades_per_day=expected_trades_per_day,
        expected_win_rate=expected_win_rate,
        expected_avg_profit=expected_avg_profit,
        confidence_score=params['confidence'],
        reasoning=reasoning
    )


def optimize_parameters_risk_adjusted(df: pd.DataFrame,
                                    spot_fee: float = 0.0005,
                                    fut_fee: float = 0.0005,
                                    max_drawdown_tolerance: float = 0.02,
                                    min_sharpe_target: float = 1.5) -> ParameterRecommendation:
    """
    Risk-adjusted approach optimizing for Sharpe ratio and drawdown control.
    
    Args:
        df: Historical market data DataFrame
        spot_fee: Spot market transaction fee
        fut_fee: Futures market transaction fee
        max_drawdown_tolerance: Maximum acceptable drawdown (default 2%)
        min_sharpe_target: Minimum target Sharpe ratio (default 1.5)
    
    Returns:
        ParameterRecommendation with risk-optimized parameters
    
    Theory:
        Optimizes parameters for risk-adjusted returns rather than raw profitability.
        Uses historical simulation to find parameter combinations that maximize
        Sharpe ratio while controlling maximum drawdown. This approach is more
        robust to market regime changes and provides better long-term performance.
        
        Key principles:
        - Higher entry selectivity reduces drawdown risk
        - Exit targets balanced for frequency vs profit per trade
        - Considers volatility clustering and regime changes
        - Optimizes for consistent performance rather than peak returns
    """
    from .backtesting_direct_arbitrage import delta_neutral_backtest
    
    # Calculate entry_cost_pct for backtesting (required by delta_neutral_backtest)
    df_with_costs = df.copy()
    df_with_costs['entry_cost_pct'] = ((df_with_costs['spot_ask_price'] - df_with_costs['fut_bid_price']) / 
                                       df_with_costs['spot_ask_price']) * 100
    
    stats = calculate_spread_statistics(df, spot_fee, fut_fee)
    
    # Parameter search grid (focused on realistic ranges)
    entry_thresholds = np.arange(
        stats.transaction_cost_floor * 1.1,
        stats.percentiles[50],
        (stats.percentiles[50] - stats.transaction_cost_floor * 1.1) / 10
    )
    
    exit_targets = np.arange(
        stats.transaction_cost_floor * 1.5,
        stats.transaction_cost_floor * 4.0,
        stats.transaction_cost_floor * 0.25
    )
    
    best_params = None
    best_score = -np.inf
    results = []
    
    # Grid search for optimal risk-adjusted parameters
    for entry_thresh in entry_thresholds:
        for exit_target in exit_targets:
            try:
                # Run backtest with current parameters
                trades = delta_neutral_backtest(
                    df_with_costs.copy(),
                    max_entry_cost_pct=entry_thresh,
                    min_profit_pct=exit_target,
                    max_hours=6,
                    spot_fee=spot_fee,
                    fut_fee=fut_fee
                )
                
                if len(trades) < 5:  # Need minimum trades for meaningful statistics
                    continue
                
                # Calculate risk metrics
                returns = [t['net_pnl_pct'] for t in trades]
                mean_return = np.mean(returns)
                std_return = np.std(returns) if len(returns) > 1 else 0.01
                
                # Calculate drawdown
                cumulative_returns = np.cumsum(returns)
                running_max = np.maximum.accumulate(cumulative_returns)
                drawdowns = running_max - cumulative_returns
                max_drawdown = np.max(drawdowns) if len(drawdowns) > 0 else 0
                
                # Sharpe ratio (annualized, assuming daily trading)
                sharpe_ratio = (mean_return * 252) / (std_return * np.sqrt(252)) if std_return > 0 else 0
                
                # Win rate
                win_rate = sum(1 for r in returns if r > 0) / len(returns)
                
                # Combined score (Sharpe ratio penalized by drawdown)
                if max_drawdown <= max_drawdown_tolerance and sharpe_ratio >= min_sharpe_target:
                    score = sharpe_ratio * win_rate * (1 - max_drawdown / max_drawdown_tolerance)
                else:
                    score = sharpe_ratio * win_rate * 0.5  # Penalty for not meeting constraints
                
                results.append({
                    'entry_thresh': entry_thresh,
                    'exit_target': exit_target,
                    'sharpe_ratio': sharpe_ratio,
                    'max_drawdown': max_drawdown,
                    'win_rate': win_rate,
                    'mean_return': mean_return,
                    'num_trades': len(trades),
                    'score': score
                })
                
                if score > best_score:
                    best_score = score
                    best_params = {
                        'max_entry_cost_pct': entry_thresh,
                        'min_profit_pct': exit_target,
                        'sharpe_ratio': sharpe_ratio,
                        'max_drawdown': max_drawdown,
                        'win_rate': win_rate,
                        'mean_return': mean_return,
                        'num_trades': len(trades)
                    }
                    
            except Exception as e:
                warnings.warn(f"Error in parameter optimization: {e}")
                continue
    
    if best_params is None:
        # Fallback to conservative statistical approach
        return optimize_parameters_statistical(df, spot_fee, fut_fee, 
                                             conservatism_level='conservative')
    
    # Estimate daily trade frequency
    hours_in_data = len(df) / (24 * 60 / 5)  # Assuming 5-minute bars
    expected_trades_per_day = best_params['num_trades'] / (hours_in_data / 24) if hours_in_data > 0 else 0
    
    confidence_score = min(1.0, best_params['sharpe_ratio'] / 2.0)  # Higher Sharpe = higher confidence
    
    reasoning = f"""
    Risk-Adjusted Optimization Results:
    - Entry threshold: {best_params['max_entry_cost_pct']:.4f}%
    - Exit target: {best_params['min_profit_pct']:.4f}%
    - Sharpe ratio: {best_params['sharpe_ratio']:.3f}
    - Maximum drawdown: {best_params['max_drawdown']:.4f}%
    - Win rate: {best_params['win_rate']:.3f}
    - Evaluated {len(results)} parameter combinations
    """
    
    return ParameterRecommendation(
        max_entry_cost_pct=best_params['max_entry_cost_pct'],
        min_profit_pct=best_params['min_profit_pct'],
        expected_trades_per_day=expected_trades_per_day,
        expected_win_rate=best_params['win_rate'],
        expected_avg_profit=best_params['mean_return'],
        confidence_score=confidence_score,
        reasoning=reasoning
    )


def compare_parameter_approaches(df: pd.DataFrame,
                               spot_fee: float = 0.0005,
                               fut_fee: float = 0.0005) -> Dict[str, ParameterRecommendation]:
    """
    Compare both optimization approaches and return results for analysis.
    
    Args:
        df: Historical market data DataFrame
        spot_fee: Spot market transaction fee
        fut_fee: Futures market transaction fee
    
    Returns:
        Dictionary with results from both approaches
    
    Usage:
        results = compare_parameter_approaches(df)
        print("Statistical Approach:", results['statistical'])
        print("Risk-Adjusted Approach:", results['risk_adjusted'])
    """
    statistical_result = optimize_parameters_statistical(df, spot_fee, fut_fee)
    risk_adjusted_result = optimize_parameters_risk_adjusted(df, spot_fee, fut_fee)
    
    return {
        'statistical': statistical_result,
        'risk_adjusted': risk_adjusted_result,
        'spread_stats': calculate_spread_statistics(df, spot_fee, fut_fee)
    }


def print_optimization_summary(results: Dict[str, ParameterRecommendation]) -> None:
    """
    Print a comprehensive summary of parameter optimization results.
    
    Args:
        results: Dictionary from compare_parameter_approaches()
    """
    print("=" * 80)
    print("DELTA-NEUTRAL ARBITRAGE PARAMETER OPTIMIZATION SUMMARY")
    print("=" * 80)
    
    for approach_name, result in results.items():
        if isinstance(result, ParameterRecommendation):
            print(f"\n{approach_name.upper()} APPROACH:")
            print(f"{'Entry Threshold:':<25} {result.max_entry_cost_pct:.4f}%")
            print(f"{'Exit Target:':<25} {result.min_profit_pct:.4f}%")
            print(f"{'Expected Trades/Day:':<25} {result.expected_trades_per_day:.2f}")
            print(f"{'Expected Win Rate:':<25} {result.expected_win_rate:.1%}")
            print(f"{'Expected Avg Profit:':<25} {result.expected_avg_profit:.4f}%")
            print(f"{'Confidence Score:':<25} {result.confidence_score:.2f}")
            print(f"\nReasoning: {result.reasoning}")
            print("-" * 60)