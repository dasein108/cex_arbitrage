#!/usr/bin/env python3
"""
Simple debug analysis of the backtest data.
"""

import pandas as pd
import numpy as np

def analyze_backtest_data():
    """Analyze the backtest CSV data to understand why no trades occurred."""
    
    # Read the backtest results
    df = pd.read_csv('/Users/dasein/dev/cex_arbitrage/src/trading/research/cache/optimized_arbitrage_backtest_F_USDT_3d_20251020_172629.csv')
    
    print("🔍 BACKTEST DATA ANALYSIS")
    print("=" * 50)
    
    print(f"📊 Basic Stats:")
    print(f"Total periods: {len(df)}")
    print(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    
    print(f"\n📈 Entry Spread Analysis:")
    entry_spreads = df['entry_spread_net']
    print(f"Range: {entry_spreads.min():.3f}% to {entry_spreads.max():.3f}%")
    print(f"Mean: {entry_spreads.mean():.3f}%")
    print(f"Median: {entry_spreads.median():.3f}%")
    print(f"Std: {entry_spreads.std():.3f}%")
    
    # Count periods by spread ranges
    ranges = [
        (entry_spreads > 0.3, "> 0.3% (original target)"),
        (entry_spreads > 0.1, "> 0.1%"),
        (entry_spreads > 0.0, "> 0.0% (positive)"),
        (entry_spreads > -0.1, "> -0.1%"),
        (entry_spreads > -0.2, "> -0.2%"),
        (entry_spreads > -0.3, "> -0.3%"),
    ]
    
    print(f"\n📊 Entry Spread Distribution:")
    for condition, label in ranges:
        count = condition.sum()
        pct = count / len(df) * 100
        print(f"  {label}: {count} periods ({pct:.1f}%)")
    
    print(f"\n📉 Exit Spread Analysis:")
    exit_spreads = df['exit_spread_net']
    print(f"Range: {exit_spreads.min():.3f}% to {exit_spreads.max():.3f}%")
    print(f"Mean: {exit_spreads.mean():.3f}%")
    print(f"Positive exits: {(exit_spreads > 0).sum()} / {len(df)} ({(exit_spreads > 0).mean()*100:.1f}%)")
    
    # Find best opportunities
    print(f"\n🎯 Best Entry Opportunities:")
    best_entries = df.nlargest(10, 'entry_spread_net')[['timestamp', 'entry_spread_net', 'exit_spread_net']]
    for _, row in best_entries.iterrows():
        print(f"  {row['timestamp']}: Entry {row['entry_spread_net']:.3f}%, Exit {row['exit_spread_net']:.3f}%")
    
    # Calculate realistic thresholds
    print(f"\n📊 Threshold Analysis:")
    
    # Use all data for percentiles
    all_spreads = entry_spreads.dropna()
    thresholds = {
        '95th': np.percentile(all_spreads, 95),
        '90th': np.percentile(all_spreads, 90),
        '75th': np.percentile(all_spreads, 75),
        '50th': np.percentile(all_spreads, 50),
    }
    
    for name, threshold in thresholds.items():
        count = (all_spreads > threshold).sum()
        pct = count / len(all_spreads) * 100
        print(f"  {name} percentile: {threshold:.3f}% ({count} periods, {pct:.1f}%)")
    
    # Test signal logic with different thresholds
    print(f"\n🔍 Signal Testing:")
    test_thresholds = [-0.5, -0.3, -0.2, -0.1, 0.0, 0.1]
    
    for thresh in test_thresholds:
        triggered = (entry_spreads > thresh).sum()
        pct = triggered / len(df) * 100
        print(f"  Threshold {thresh:5.1f}%: {triggered:3d} signals ({pct:5.1f}%)")
    
    # Recommend fixes
    print(f"\n💡 RECOMMENDATIONS:")
    
    if (entry_spreads > 0).sum() < 10:
        print("  ❌ Very few positive spreads - data may have issues")
        print("  ✅ Consider using relative thresholds instead of absolute")
    
    best_threshold = np.percentile(all_spreads, 85)  # Top 15%
    realistic_signals = (entry_spreads > best_threshold).sum()
    
    print(f"  ✅ Recommended entry threshold: {best_threshold:.3f}% (85th percentile)")
    print(f"  ✅ This would generate ~{realistic_signals} signals ({realistic_signals/len(df)*100:.1f}% of periods)")
    
    if realistic_signals > 5:
        print(f"  ✅ Use threshold: {best_threshold:.3f}% for meaningful backtest")
    else:
        print(f"  ⚠️  Even 85th percentile gives few signals - check data quality")

if __name__ == "__main__":
    analyze_backtest_data()