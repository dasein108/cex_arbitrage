#!/usr/bin/env python3
"""
Test script to verify the percentile calculation fix
"""

import numpy as np

def test_percentile_calculation():
    """Test the corrected percentile calculation logic"""
    print("🧪 Testing Corrected Percentile Calculation")
    print("=" * 50)
    
    # Create test data based on user's actual analysis results
    # MEXC to Futures: range -147.23 to +81.78 bps, 80th percentile at -1.29 bps
    # Generate realistic distribution around these values
    np.random.seed(42)
    mexc_to_fut_history = np.concatenate([
        np.random.normal(-50, 20, 200),  # Mostly negative spreads  
        np.random.uniform(-147.23, 81.78, 179)  # Full range
    ])
    
    # Futures to MEXC: range +8.83 to +237.79 bps, 80th percentile at +145.00 bps
    fut_to_mexc_history = np.concatenate([
        np.random.normal(100, 30, 200),  # Mostly positive spreads
        np.random.uniform(8.83, 237.79, 179)  # Full range  
    ])
    
    print(f"MEXC to Futures history: {mexc_to_fut_history}")
    print(f"Range: {mexc_to_fut_history.min():.4f} to {mexc_to_fut_history.max():.4f} bps")
    
    print(f"\nFutures to MEXC history: {fut_to_mexc_history}")  
    print(f"Range: {fut_to_mexc_history.min():.4f} to {fut_to_mexc_history.max():.4f} bps")
    
    # Test current spread values from user's data
    mexc_to_fut_current = -1.29  # User's 80th percentile value (bps)
    fut_to_mexc_current = 145.0   # User's 80th percentile value (bps)
    
    print(f"\n🔍 Testing Current Spread Values:")
    print(f"MEXC to Futures current: {mexc_to_fut_current:.4f} bps")
    print(f"Futures to MEXC current: {fut_to_mexc_current:.4f} bps")
    
    # Calculate percentiles using corrected logic
    mexc_percentile = (
        np.searchsorted(np.sort(mexc_to_fut_history), mexc_to_fut_current) / 
        len(mexc_to_fut_history) * 100
    )
    
    fut_percentile = (
        np.searchsorted(np.sort(fut_to_mexc_history), fut_to_mexc_current) /
        len(fut_to_mexc_history) * 100
    )
    
    print(f"\n📊 Calculated Percentiles:")
    print(f"MEXC to Futures: {mexc_percentile:.1f}th percentile")
    print(f"Futures to MEXC: {fut_percentile:.1f}th percentile")
    
    # Test entry signal conditions (UPDATED THRESHOLDS)
    entry_threshold = 70.0  # 70th percentile (more permissive)
    min_spread_threshold = -50.0  # -50 bps = -0.05% (more realistic)
    
    print(f"\n🎯 Entry Signal Conditions:")
    print(f"Entry threshold: {entry_threshold}th percentile")
    print(f"Min spread threshold: {min_spread_threshold} bps")
    
    # CORRECTED ARBITRAGE LOGIC:
    # MEXC to Futures: More negative = more profitable (low percentile)
    # Futures to MEXC: More positive = more profitable (high percentile)
    mexc_entry_signal = (
        mexc_percentile <= (100 - entry_threshold) and 
        mexc_to_fut_current < (min_spread_threshold / 10)  # -100 bps / 10 = -10 bps threshold
    )
    
    fut_entry_signal = (
        fut_percentile >= entry_threshold and 
        fut_to_mexc_current > abs(min_spread_threshold / 10)   # +10 bps threshold
    )
    
    print(f"\nMEXC to Futures Entry Signal (CORRECTED):")
    print(f"  Percentile check: {mexc_percentile:.1f} <= {100 - entry_threshold} = {mexc_percentile <= (100 - entry_threshold)}")
    print(f"  Spread check: {mexc_to_fut_current:.4f} < {min_spread_threshold / 10:.1f} = {mexc_to_fut_current < (min_spread_threshold / 10)}")
    print(f"  → Entry signal: {mexc_entry_signal}")
    
    print(f"\nFutures to MEXC Entry Signal:")
    print(f"  Percentile check: {fut_percentile:.1f} >= {entry_threshold} = {fut_percentile >= entry_threshold}")  
    print(f"  Spread check: {fut_to_mexc_current:.4f} > {abs(min_spread_threshold / 10):.1f} = {fut_to_mexc_current > abs(min_spread_threshold / 10)}")
    print(f"  → Entry signal: {fut_entry_signal}")
    
    overall_entry = mexc_entry_signal or fut_entry_signal
    print(f"\n🏆 Overall Entry Signal: {overall_entry}")
    
    if overall_entry:
        print("✅ SUCCESS: Entry signals should now be generated!")
    else:
        print("❌ ISSUE: Still no entry signals - need further investigation")
    
    return overall_entry

if __name__ == "__main__":
    test_percentile_calculation()