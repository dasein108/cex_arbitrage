import pandas as pd
import numpy as np
from typing import Tuple, Dict, List
from trading.research.trading_utlis import DEFAULT_FEES_PER_TRADE
from trading.research.delta_neutral_research import get_trading_signals, simple_delta_neutral_backtest


def optimize_thresholds_grid_search(df: pd.DataFrame, min_trades: int = 5) -> Tuple[float, float, Dict]:
    """
    Option 1: Grid Search Optimization
    
    Tests different combinations of entry/exit thresholds to find optimal balance
    between trade frequency and profitability.
    
    Args:
        df: DataFrame with normalized_spread column
        min_trades: Minimum number of trades required for valid result
        
    Returns:
        best_entry_threshold, best_exit_threshold, results_summary
    """
    # Minimum threshold must cover round-trip fees
    min_threshold = DEFAULT_FEES_PER_TRADE * 2  # 0.002 = 0.2%
    
    # Define search ranges
    entry_thresholds = np.arange(min_threshold, 0.08, 0.005)  # 0.2% to 8% in 0.5% steps
    exit_thresholds = np.arange(min_threshold * 0.5, 0.04, 0.002)  # 0.1% to 4% in 0.2% steps
    
    best_score = -np.inf
    best_entry = min_threshold
    best_exit = min_threshold * 0.5
    results = []
    
    print(f"🔍 Grid Search: Testing {len(entry_thresholds)} × {len(exit_thresholds)} combinations...")
    
    for entry_thresh in entry_thresholds:
        for exit_thresh in exit_thresholds:
            # Skip invalid combinations
            if exit_thresh >= entry_thresh:
                continue
                
            # Generate signals and backtest
            entry_signal, exit_signal = get_trading_signals(df, entry_thresh, exit_thresh)
            trades = simple_delta_neutral_backtest(df, entry_signal, exit_signal)
            
            if len(trades) < min_trades:
                continue
                
            # Calculate performance metrics
            total_pnl = sum(t['pnl'] for t in trades)
            avg_pnl = total_pnl / len(trades)
            win_rate = sum(1 for t in trades if t['pnl'] > 0) / len(trades)
            
            # Composite score: balance profitability and frequency
            # Higher weight on profitability, but reward reasonable trade frequency
            frequency_bonus = min(len(trades) / 20, 1.0)  # Bonus for up to 20 trades
            score = total_pnl * 0.7 + avg_pnl * 0.2 + frequency_bonus * 0.1
            
            results.append({
                'entry_thresh': entry_thresh,
                'exit_thresh': exit_thresh,
                'total_pnl': total_pnl,
                'avg_pnl': avg_pnl,
                'trade_count': len(trades),
                'win_rate': win_rate,
                'score': score
            })
            
            if score > best_score:
                best_score = score
                best_entry = entry_thresh
                best_exit = exit_thresh
    
    # Summary of best result
    summary = {
        'method': 'Grid Search',
        'best_entry_threshold': best_entry,
        'best_exit_threshold': best_exit,
        'best_score': best_score,
        'total_combinations_tested': len(results),
        'min_fees_constraint': min_threshold
    }
    
    return best_entry, best_exit, summary


def optimize_thresholds_statistical(df: pd.DataFrame, confidence_level: float = 0.75) -> Tuple[float, float, Dict]:
    """
    Option 2: Statistical Distribution Optimization
    
    Uses statistical properties of normalized_spread distribution to set thresholds.
    Sets thresholds based on percentiles to capture meaningful deviations.
    
    Args:
        df: DataFrame with normalized_spread column
        confidence_level: Confidence level for threshold setting (0.75 = capture 75% of opportunities)
        
    Returns:
        entry_threshold, exit_threshold, results_summary
    """
    # Clean data - remove NaN values
    spread_data = df['normalized_spread'].dropna()
    
    if len(spread_data) < 100:
        raise ValueError("Insufficient data for statistical analysis")
    
    # Minimum threshold constraint
    min_threshold = DEFAULT_FEES_PER_TRADE * 2  # 0.002 = 0.2%
    
    # Analyze spread distribution
    spread_mean = spread_data.mean()
    spread_std = spread_data.std()
    
    # Calculate percentiles for negative spreads (entry opportunities)
    negative_spreads = spread_data[spread_data < 0]
    
    if len(negative_spreads) < 20:
        # Fallback to standard deviation approach
        entry_threshold = max(abs(spread_mean - 2 * spread_std), min_threshold)
    else:
        # Use percentile approach for entry (when futures underperform)
        percentile = (1 - confidence_level) * 100  # e.g., 25th percentile for 75% confidence
        entry_threshold = max(abs(np.percentile(negative_spreads, percentile)), min_threshold)
    
    # Exit threshold: should be smaller than entry for convergence arbitrage
    # For normalized spread: enter at -entry_threshold, exit at -exit_threshold (closer to zero)
    exit_threshold = max(entry_threshold * 0.3, min_threshold * 0.5)
    
    # Validate thresholds with backtest
    entry_signal, exit_signal = get_trading_signals(df, entry_threshold, exit_threshold)
    trades = simple_delta_neutral_backtest(df, entry_signal, exit_signal)
    
    # Calculate validation metrics
    if len(trades) > 0:
        total_pnl = sum(t['pnl'] for t in trades)
        avg_pnl = total_pnl / len(trades)
        win_rate = sum(1 for t in trades if t['pnl'] > 0) / len(trades)
    else:
        total_pnl = avg_pnl = win_rate = 0
    
    # Summary with statistical insights
    summary = {
        'method': 'Statistical Distribution',
        'entry_threshold': entry_threshold,
        'exit_threshold': exit_threshold,
        'spread_mean': spread_mean,
        'spread_std': spread_std,
        'confidence_level': confidence_level,
        'negative_spread_count': len(negative_spreads),
        'backtest_trades': len(trades),
        'backtest_total_pnl': total_pnl,
        'backtest_avg_pnl': avg_pnl,
        'backtest_win_rate': win_rate,
        'min_fees_constraint': min_threshold
    }
    
    return entry_threshold, exit_threshold, summary


def compare_optimization_methods(df: pd.DataFrame) -> Dict:
    """
    Compare both optimization methods and recommend the best approach.
    
    Args:
        df: DataFrame with normalized_spread and required price columns
        
    Returns:
        Dictionary with comparison results and recommendation
    """
    print("🚀 Optimizing Delta-Neutral Thresholds - Comparing Methods")
    print("=" * 70)
    
    # Method 1: Grid Search
    print("\n1️⃣ Grid Search Optimization...")
    grid_entry, grid_exit, grid_summary = optimize_thresholds_grid_search(df)
    
    # Method 2: Statistical
    print("\n2️⃣ Statistical Distribution Optimization...")
    stat_entry, stat_exit, stat_summary = optimize_thresholds_statistical(df)
    
    # Test both methods
    methods_comparison = []
    
    for method_name, entry_thresh, exit_thresh in [
        ("Grid Search", grid_entry, grid_exit),
        ("Statistical", stat_entry, stat_exit)
    ]:
        entry_signal, exit_signal = get_trading_signals(df, entry_thresh, exit_thresh)
        trades = simple_delta_neutral_backtest(df, entry_signal, exit_signal)
        
        if len(trades) > 0:
            total_pnl = sum(t['pnl'] for t in trades)
            avg_pnl = total_pnl / len(trades)
            win_rate = sum(1 for t in trades if t['pnl'] > 0) / len(trades)
            avg_hold_hours = sum(t['hours'] for t in trades) / len(trades)
        else:
            total_pnl = avg_pnl = win_rate = avg_hold_hours = 0
        
        methods_comparison.append({
            'method': method_name,
            'entry_threshold': entry_thresh,
            'exit_threshold': exit_thresh,
            'trade_count': len(trades),
            'total_pnl': total_pnl,
            'avg_pnl_per_trade': avg_pnl,
            'win_rate': win_rate,
            'avg_hold_hours': avg_hold_hours,
            'sharpe_proxy': total_pnl / max(0.01, np.std([t['pnl'] for t in trades])) if len(trades) > 1 else 0
        })
    
    # Determine recommendation
    if len(methods_comparison) >= 2:
        grid_result = methods_comparison[0]
        stat_result = methods_comparison[1]
        
        # Recommend based on total PnL and trade count balance
        if grid_result['total_pnl'] > stat_result['total_pnl'] and grid_result['trade_count'] >= 3:
            recommended = 'Grid Search'
            recommended_entry = grid_entry
            recommended_exit = grid_exit
        else:
            recommended = 'Statistical'
            recommended_entry = stat_entry
            recommended_exit = stat_exit
    else:
        recommended = 'Statistical'  # Fallback
        recommended_entry = stat_entry
        recommended_exit = stat_exit
    
    return {
        'grid_search_results': grid_summary,
        'statistical_results': stat_summary,
        'methods_comparison': methods_comparison,
        'recommendation': {
            'method': recommended,
            'entry_threshold': recommended_entry,
            'exit_threshold': recommended_exit,
            'reasoning': f"Recommended {recommended} method based on performance comparison"
        }
    }


def print_optimization_results(comparison_results: Dict):
    """Print formatted optimization results."""
    print("\n📊 THRESHOLD OPTIMIZATION RESULTS")
    print("=" * 80)
    
    # Print method comparison
    for method_data in comparison_results['methods_comparison']:
        print(f"\n{method_data['method']} Method:")
        print(f"  Entry Threshold: {method_data['entry_threshold']:.3f} ({method_data['entry_threshold']*100:.1f}%)")
        print(f"  Exit Threshold:  {method_data['exit_threshold']:.3f} ({method_data['exit_threshold']*100:.1f}%)")
        print(f"  Trade Count:     {method_data['trade_count']}")
        print(f"  Total PnL:       {method_data['total_pnl']:.4f}%")
        print(f"  Avg PnL/Trade:   {method_data['avg_pnl_per_trade']:.4f}%")
        print(f"  Win Rate:        {method_data['win_rate']:.1%}")
        print(f"  Avg Hold Time:   {method_data['avg_hold_hours']:.2f} hours")
    
    # Print recommendation
    rec = comparison_results['recommendation']
    print(f"\n🎯 RECOMMENDATION: {rec['method']}")
    print(f"   Entry Threshold: {rec['entry_threshold']:.3f} ({rec['entry_threshold']*100:.1f}%)")
    print(f"   Exit Threshold:  {rec['exit_threshold']:.3f} ({rec['exit_threshold']*100:.1f}%)")
    print(f"   Reasoning: {rec['reasoning']}")
    
    print(f"\n💡 Note: Minimum threshold constraint = {DEFAULT_FEES_PER_TRADE * 2:.3f} ({DEFAULT_FEES_PER_TRADE * 2 * 100:.1f}%) for round-trip fees")
    print("=" * 80)