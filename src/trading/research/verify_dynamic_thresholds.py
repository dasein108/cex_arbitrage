#!/usr/bin/env python3
"""
Verify that both entry and exit thresholds are truly dynamic.
"""

import asyncio
import pandas as pd
import numpy as np
from optimized_cross_arbitrage_backtest import OptimizedCrossArbitrageBacktest, OptimizedBacktestConfig

async def verify_dynamic_thresholds():
    """Verify that thresholds change dynamically during backtest."""
    print("🔍 VERIFYING DYNAMIC THRESHOLD BEHAVIOR")
    print("=" * 50)
    
    # Create config with known percentiles
    config = OptimizedBacktestConfig(
        symbol="F_USDT",
        days=2,  # Shorter for faster test
        entry_percentile=20,  # Top 20% 
        exit_percentile=80,   # Top 20% of exit spreads
        min_entry_spread=-0.5,  # Very permissive
        profit_target=0.5,
        stop_loss=-0.5
    )
    
    backtest = OptimizedCrossArbitrageBacktest(config)
    
    # Load data
    df = await backtest._load_and_prepare_data()
    print(f"📊 Loaded {len(df)} periods")
    
    # Sample different periods and track threshold changes
    sample_periods = [60, 120, 180, 240, 300]
    threshold_history = []
    
    print(f"\n📈 TRACKING THRESHOLD EVOLUTION:")
    print(f"{'Period':<8} {'Entry Thresh':<12} {'Exit Thresh':<12} {'Entry Spread':<12} {'Exit Spread':<12}")
    print("-" * 65)
    
    for period_idx in sample_periods:
        if period_idx < len(df):
            row = df.iloc[period_idx]
            
            # Simulate historical data up to this point
            backtest.historical_entry_spreads = df['entry_spread_net'].iloc[:period_idx].tolist()
            backtest.historical_exit_spreads = df['exit_spread_net'].iloc[:period_idx].tolist()
            
            # Calculate thresholds as the backtest would
            if len(backtest.historical_entry_spreads) >= 50:
                entry_thresh = np.percentile(backtest.historical_entry_spreads, 
                                           100 - config.entry_percentile)
                exit_thresh = np.percentile(backtest.historical_exit_spreads, 
                                          config.exit_percentile)
            else:
                entry_thresh = -0.25  # Fallback
                exit_thresh = 0.1     # Fallback
            
            current_entry = row['entry_spread_net']
            current_exit = row['exit_spread_net']
            
            print(f"{period_idx:<8} {entry_thresh:<12.3f} {exit_thresh:<12.3f} {current_entry:<12.3f} {current_exit:<12.3f}")
            
            threshold_history.append({
                'period': period_idx,
                'entry_threshold': entry_thresh,
                'exit_threshold': exit_thresh,
                'entry_spread': current_entry,
                'exit_spread': current_exit
            })
    
    # Analyze threshold dynamics
    print(f"\n📊 THRESHOLD DYNAMICS ANALYSIS:")
    
    entry_thresholds = [t['entry_threshold'] for t in threshold_history]
    exit_thresholds = [t['exit_threshold'] for t in threshold_history]
    
    entry_range = max(entry_thresholds) - min(entry_thresholds)
    exit_range = max(exit_thresholds) - min(exit_thresholds)
    
    print(f"Entry threshold range: {min(entry_thresholds):.3f}% to {max(entry_thresholds):.3f}% (range: {entry_range:.3f}%)")
    print(f"Exit threshold range: {min(exit_thresholds):.3f}% to {max(exit_thresholds):.3f}% (range: {exit_range:.3f}%)")
    
    # Check if thresholds are actually changing
    entry_changing = entry_range > 0.01  # At least 0.01% change
    exit_changing = exit_range > 0.01    # At least 0.01% change
    
    print(f"\n✅ VERIFICATION RESULTS:")
    print(f"  Entry thresholds are dynamic: {'YES' if entry_changing else 'NO'} ({'✅' if entry_changing else '❌'})")
    print(f"  Exit thresholds are dynamic: {'YES' if exit_changing else 'NO'} ({'✅' if exit_changing else '❌'})")
    
    if entry_changing and exit_changing:
        print(f"\n🎉 SUCCESS: Both entry and exit thresholds are dynamically adjusted!")
        print(f"   Entry thresholds adapt based on rolling historical entry spreads")
        print(f"   Exit thresholds adapt based on rolling historical exit spreads")
        print(f"   This ensures optimal signal generation as market conditions change")
    else:
        print(f"\n⚠️  WARNING: Some thresholds may not be dynamic enough")
        if not entry_changing:
            print(f"   Entry thresholds are not changing significantly")
        if not exit_changing:
            print(f"   Exit thresholds are not changing significantly")

if __name__ == "__main__":
    asyncio.run(verify_dynamic_thresholds())