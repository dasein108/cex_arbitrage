#!/usr/bin/env python3
"""
Debug version of optimized backtest to identify signal generation issues.
"""

import asyncio
import pandas as pd
import numpy as np
from optimized_cross_arbitrage_backtest import OptimizedCrossArbitrageBacktest, OptimizedBacktestConfig

async def debug_backtest():
    """Run debug version of backtest with detailed logging."""
    print("🔍 DEBUG BACKTEST - Investigating Signal Generation")
    print("=" * 60)
    
    # Create debug config with very relaxed thresholds
    config = OptimizedBacktestConfig(
        symbol="F_USDT",
        days=3,
        profit_target=0.3,      # Lower target
        stop_loss=-0.5,         # Higher stop loss
        min_transfer_time_minutes=5,  # Shorter transfer
        max_position_hours=8,   # Longer hold time
        entry_percentile=50,    # Much more relaxed (median)
        min_entry_spread=-0.2,  # Very low minimum
        position_size_usd=1000
    )
    
    backtest = OptimizedCrossArbitrageBacktest(config)
    
    # Load data
    df = await backtest._load_and_prepare_data()
    
    print(f"\n📊 DATA ANALYSIS:")
    print(f"Total periods: {len(df)}")
    print(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    
    # Analyze spreads
    print(f"\n📈 ENTRY SPREAD ANALYSIS:")
    print(f"Entry spread range: {df['entry_spread_net'].min():.3f}% to {df['entry_spread_net'].max():.3f}%")
    print(f"Entry spread mean: {df['entry_spread_net'].mean():.3f}%")
    print(f"Entry spread median: {df['entry_spread_net'].median():.3f}%")
    print(f"Positive entry spreads: {(df['entry_spread_net'] > 0).sum()} / {len(df)} ({(df['entry_spread_net'] > 0).mean()*100:.1f}%)")
    print(f"Entry spreads > -0.1%: {(df['entry_spread_net'] > -0.1).sum()} / {len(df)} ({(df['entry_spread_net'] > -0.1).mean()*100:.1f}%)")
    
    print(f"\n📉 EXIT SPREAD ANALYSIS:")
    print(f"Exit spread range: {df['exit_spread_net'].min():.3f}% to {df['exit_spread_net'].max():.3f}%")
    print(f"Exit spread mean: {df['exit_spread_net'].mean():.3f}%")
    print(f"Positive exit spreads: {(df['exit_spread_net'] > 0).sum()} / {len(df)} ({(df['exit_spread_net'] > 0).mean()*100:.1f}%)")
    
    # Test signal generation on sample periods
    print(f"\n🔍 SIGNAL GENERATION TEST:")
    backtest.historical_entry_spreads = df['entry_spread_net'].tolist()[:100]  # Pre-populate history
    
    test_periods = [50, 100, 200, 300, 400]  # Test different periods
    
    for i in test_periods:
        if i < len(df):
            row = df.iloc[i]
            signal, reason = backtest._generate_optimized_signal(row)
            
            print(f"\nPeriod {i} ({row['timestamp']}):")
            print(f"  Entry spread: {row['entry_spread_net']:.3f}%")
            print(f"  Exit spread: {row['exit_spread_net']:.3f}%")
            print(f"  Signal: {signal}")
            print(f"  Reason: {reason}")
    
    # Calculate thresholds manually
    historical_positive = [s for s in df['entry_spread_net'] if s > -0.5]
    if historical_positive:
        threshold_90 = np.percentile(historical_positive, 90)
        threshold_75 = np.percentile(historical_positive, 75)
        threshold_50 = np.percentile(historical_positive, 50)
        
        print(f"\n📊 THRESHOLD ANALYSIS:")
        print(f"Historical positive spreads count: {len(historical_positive)}")
        print(f"90th percentile threshold: {threshold_90:.3f}%")
        print(f"75th percentile threshold: {threshold_75:.3f}%")
        print(f"50th percentile threshold: {threshold_50:.3f}%")
        
        # Test how many periods would trigger at different thresholds
        print(f"\nPeriods that would trigger at different thresholds:")
        for thresh in [-0.5, -0.3, -0.1, 0.0, 0.1]:
            count = (df['entry_spread_net'] > thresh).sum()
            print(f"  > {thresh:.1f}%: {count} periods ({count/len(df)*100:.1f}%)")
    
    # Try running backtest with relaxed config
    print(f"\n🚀 RUNNING RELAXED BACKTEST:")
    
    # Override signal generation to be very permissive
    def debug_signal_generation(self, row):
        current_entry_spread = row['entry_spread_net']
        # Very permissive entry condition
        if (current_entry_spread > -0.2 and 
            len(self.open_positions) < self.config.max_concurrent_positions):
            return 'ENTER', f'DEBUG: Entry spread {current_entry_spread:.3f}% > -0.2%'
        return 'HOLD', f'Entry: {current_entry_spread:.3f}%'
    
    # Temporarily replace the method
    original_method = backtest._generate_optimized_signal
    backtest._generate_optimized_signal = lambda row: debug_signal_generation(backtest, row)
    
    # Run simulation
    results = await backtest.run_backtest()
    
    # Restore original method
    backtest._generate_optimized_signal = original_method
    
    print(backtest.format_report(results))

if __name__ == "__main__":
    asyncio.run(debug_backtest())