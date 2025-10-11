#!/usr/bin/env python3
"""
Simple test to demonstrate the enhanced get_best_spread_bins function
with synthetic data to validate the arbitrage logic.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd

# Mock the imports for demonstration
DEFAULT_FEES_FOR_LEGS_TRADE = 0.1  # 0.1% total fees (0.05% spot + 0.05% futures)

def group_spread_bins(series, step=0.02, threshold=50):
    """Mock implementation of group_spread_bins for testing."""
    bins = np.arange(series.min(), series.max() + step, step)
    counts, bin_edges = np.histogram(series, bins=bins)
    
    mask = counts > 0
    values = bin_edges[:-1][mask]
    counts = counts[mask]
    
    grouped_values = []
    grouped_counts = []
    
    i = 0
    while i < len(values):
        if counts[i] < threshold:
            group_vals = [values[i]]
            group_cnts = [counts[i]]
            
            j = i + 1
            while j < len(values) and counts[j] < threshold:
                group_vals.append(values[j])
                group_cnts.append(counts[j])
                j += 1
            
            grouped_values.append(np.mean(group_vals))
            grouped_counts.append(sum(group_cnts))
            i = j
        else:
            grouped_values.append(values[i])
            grouped_counts.append(counts[i])
            i += 1
    
    return np.array(grouped_values), np.array(grouped_counts)


def get_best_spread_bins(df: pd.DataFrame, step=0.02, threshold=50, min_profit_pct=0.01):
    """
    Enhanced arbitrage bin analysis function.
    """
    # Get binned spread distributions for entry and exit
    spot_fut_vals, spot_fut_cnts = group_spread_bins(df['spot_fut_spread_prc'], step=step, threshold=threshold)
    fut_spot_vals, fut_spot_cnts = group_spread_bins(df['fut_spot_spread_prc'], step=step, threshold=threshold)
    
    # Calculate total fee threshold (round-trip fees + minimum profit)
    profit_threshold = DEFAULT_FEES_FOR_LEGS_TRADE + min_profit_pct
    
    # Initialize results list for profitable bin combinations
    profitable_opportunities = []
    
    # Analyze all possible entry-exit bin combinations
    for i, entry_spread in enumerate(spot_fut_vals):
        for j, exit_spread in enumerate(fut_spot_vals):
            # Calculate theoretical profit for this bin pair
            # Profit = Entry Spread - Exit Spread - Total Fees
            max_profit = entry_spread - exit_spread - DEFAULT_FEES_FOR_LEGS_TRADE
            
            # Filter by profitability threshold
            if max_profit >= min_profit_pct:
                # Calculate combined frequency weight
                count_weight = np.sqrt(spot_fut_cnts[i] * fut_spot_cnts[j])
                
                profitable_opportunities.append([
                    entry_spread,      # Entry spread value (spot_fut_val)
                    exit_spread,       # Exit spread value (fut_spot_val)
                    max_profit,        # Maximum profit potential
                    count_weight       # Statistical confidence weight
                ])
    
    # Convert to numpy array and sort by profit potential
    if profitable_opportunities:
        result = np.array(profitable_opportunities)
        # Sort by maximum profit (descending)
        result = result[result[:, 2].argsort()[::-1]]
        
        print(f"\n📊 Arbitrage Analysis Results:")
        print(f"  • Entry bins analyzed: {len(spot_fut_vals)}")
        print(f"  • Exit bins analyzed: {len(fut_spot_vals)}")
        print(f"  • Profitable opportunities: {len(result)}")
        if len(result) > 0:
            print(f"  • Best opportunity: Entry={result[0,0]:.3f}%, Exit={result[0,1]:.3f}%, Profit={result[0,2]:.3f}%")
            print(f"  • Profit range: {result[-1,2]:.3f}% to {result[0,2]:.3f}%")
            print(f"  • Required fees threshold: {DEFAULT_FEES_FOR_LEGS_TRADE:.3f}%")
        
        return result
    else:
        print(f"⚠️ No profitable opportunities found with threshold {profit_threshold:.3f}%")
        return np.array([])


def create_synthetic_arbitrage_data():
    """Create synthetic market data with known arbitrage opportunities."""
    np.random.seed(42)
    n_samples = 10000
    
    # Scenario 1: Clear arbitrage opportunity
    # Entry spread (spot > futures): centered around 0.5% with noise
    entry_spreads_1 = np.random.normal(0.5, 0.1, n_samples // 3)
    
    # Exit spread (futures > spot): centered around -0.2% with noise
    exit_spreads_1 = np.random.normal(-0.2, 0.1, n_samples // 3)
    
    # Scenario 2: Marginal opportunity
    entry_spreads_2 = np.random.normal(0.15, 0.05, n_samples // 3)
    exit_spreads_2 = np.random.normal(-0.03, 0.05, n_samples // 3)
    
    # Scenario 3: No opportunity (negative spreads)
    entry_spreads_3 = np.random.normal(-0.1, 0.05, n_samples - 2 * (n_samples // 3))
    exit_spreads_3 = np.random.normal(0.1, 0.05, n_samples - 2 * (n_samples // 3))
    
    # Combine scenarios
    all_entry = np.concatenate([entry_spreads_1, entry_spreads_2, entry_spreads_3])
    all_exit = np.concatenate([exit_spreads_1, exit_spreads_2, exit_spreads_3])
    
    # Shuffle to mix scenarios
    indices = np.random.permutation(len(all_entry))
    
    return pd.DataFrame({
        'spot_fut_spread_prc': all_entry[indices],
        'fut_spot_spread_prc': all_exit[indices]
    })


def main():
    """Run the arbitrage analysis demonstration."""
    
    print("="*80)
    print("SPOT/FUTURES ARBITRAGE BIN ANALYSIS - ENHANCED VERSION")
    print("="*80)
    
    print("\n📋 System Design:")
    print("  • Entry: Sell Spot (bid), Buy Futures (ask)")
    print("  • Exit: Buy Spot (ask), Sell Futures (bid)")
    print("  • Profit = Entry Spread - Exit Spread - Fees")
    print(f"  • Total Fees: {DEFAULT_FEES_FOR_LEGS_TRADE:.2f}%")
    
    # Create synthetic data
    print("\n🔬 Creating synthetic market data with known arbitrage patterns...")
    df = create_synthetic_arbitrage_data()
    
    print(f"\n📊 Data Statistics:")
    print(f"  • Total samples: {len(df):,}")
    print(f"  • Entry spread range: {df['spot_fut_spread_prc'].min():.2f}% to {df['spot_fut_spread_prc'].max():.2f}%")
    print(f"  • Entry spread mean: {df['spot_fut_spread_prc'].mean():.3f}%")
    print(f"  • Exit spread range: {df['fut_spot_spread_prc'].min():.2f}% to {df['fut_spot_spread_prc'].max():.2f}%")
    print(f"  • Exit spread mean: {df['fut_spot_spread_prc'].mean():.3f}%")
    
    print("\n" + "="*80)
    print("TEST 1: Standard Parameters (1bp minimum profit)")
    print("="*80)
    
    opportunities = get_best_spread_bins(
        df, 
        step=0.02,
        threshold=50,
        min_profit_pct=0.01  # 1% minimum profit
    )
    
    if len(opportunities) > 0:
        print("\n📈 Top 10 Arbitrage Opportunities:")
        print("-"*60)
        print(f"{'#':>3} {'Entry %':>10} {'Exit %':>10} {'Profit %':>10} {'Weight':>12}")
        print("-"*60)
        for i, opp in enumerate(opportunities[:10], 1):
            print(f"{i:3d} {opp[0]:10.3f} {opp[1]:10.3f} {opp[2]:10.3f} {opp[3]:12.0f}")
        
        # Calculate strategy metrics
        avg_profit = opportunities[:, 2].mean()
        max_profit = opportunities[:, 2].max()
        weighted_profit = np.average(opportunities[:, 2], weights=opportunities[:, 3])
        
        print("\n📊 Strategy Performance Metrics:")
        print(f"  • Total opportunities: {len(opportunities)}")
        print(f"  • Average profit: {avg_profit:.3f}%")
        print(f"  • Weighted profit: {weighted_profit:.3f}%")
        print(f"  • Maximum profit: {max_profit:.3f}%")
        print(f"  • Minimum profit: {opportunities[-1, 2]:.3f}%")
    
    print("\n" + "="*80)
    print("TEST 2: Aggressive Parameters (0.5bp minimum)")
    print("="*80)
    
    opportunities_aggressive = get_best_spread_bins(
        df, 
        step=0.01,  # Finer bins
        threshold=25,  # Lower threshold
        min_profit_pct=0.005  # 0.5% minimum profit
    )
    
    if len(opportunities_aggressive) > 0:
        print(f"\n📈 Found {len(opportunities_aggressive)} opportunities (vs {len(opportunities)} with standard params)")
    
    print("\n" + "="*80)
    print("TEST 3: Conservative Parameters (2bp minimum)")
    print("="*80)
    
    opportunities_conservative = get_best_spread_bins(
        df, 
        step=0.05,  # Wider bins
        threshold=100,  # Higher threshold
        min_profit_pct=0.02  # 2% minimum profit
    )
    
    if len(opportunities_conservative) > 0:
        print(f"\n📈 Found {len(opportunities_conservative)} high-quality opportunities")
    
    # Trading recommendations
    print("\n" + "="*80)
    print("💡 TRADING RECOMMENDATIONS")
    print("="*80)
    
    if len(opportunities) > 0:
        best = opportunities[0]
        print(f"\n🎯 Optimal Entry/Exit Points:")
        print(f"  • Enter when spot-futures spread ≥ {best[0]:.3f}%")
        print(f"  • Exit when futures-spot spread ≤ {best[1]:.3f}%")
        print(f"  • Expected profit per cycle: {best[2]:.3f}%")
        
        # Calculate daily profit potential
        position_size = 100000  # $100k position
        trades_per_day = 10  # Conservative estimate
        daily_profit = position_size * (weighted_profit / 100) * trades_per_day
        
        print(f"\n💰 Profit Potential (with $100k capital):")
        print(f"  • Per trade: ${position_size * (weighted_profit / 100):.2f}")
        print(f"  • Daily (10 trades): ${daily_profit:.2f}")
        print(f"  • Monthly (200 trades): ${daily_profit * 20:.2f}")
        print(f"  • Annual return: {(daily_profit * 250 / position_size * 100):.1f}%")
    else:
        print("\n⚠️ No profitable opportunities found")
        print("  Consider adjusting parameters or waiting for better market conditions")
    
    print("\n" + "="*80)
    print("✅ ANALYSIS COMPLETE")
    print("="*80)


if __name__ == "__main__":
    main()