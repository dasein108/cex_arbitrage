#!/usr/bin/env python3
"""
Test the fixed optimized backtest with realistic thresholds.
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.append('/Users/dasein/dev/cex_arbitrage/src')

from trading.research.optimized_cross_arbitrage_backtest import OptimizedCrossArbitrageBacktest, OptimizedBacktestConfig

async def test_fixed_backtest():
    """Test the corrected backtest with realistic parameters."""
    print("🚀 TESTING FIXED OPTIMIZED BACKTEST")
    print("=" * 50)
    
    # Create realistic config based on data analysis
    config = OptimizedBacktestConfig(
        symbol="F_USDT",
        days=3,
        
        # Realistic thresholds based on data analysis
        entry_percentile=15,    # Top 15% (should give ~87 signals)
        min_entry_spread=-0.25, # 85th percentile from analysis
        
        # Conservative profit targets
        profit_target=0.3,      # Lower profit target
        stop_loss=-0.3,         # Reasonable stop loss
        
        # Faster execution
        min_transfer_time_minutes=5,
        max_position_hours=6,
        
        # Trading parameters
        position_size_usd=1000,
        max_concurrent_positions=3
    )
    
    print(f"📊 Config Summary:")
    print(f"  Entry percentile: {config.entry_percentile}% (top {config.entry_percentile}%)")
    print(f"  Exit percentile: {config.exit_percentile}% (dynamic threshold)")
    print(f"  Min entry spread: {config.min_entry_spread:.3f}%")
    print(f"  Profit target: {config.profit_target:.1f}%")
    print(f"  Stop loss: {config.stop_loss:.1f}%")
    
    backtest = OptimizedCrossArbitrageBacktest(config)
    
    try:
        # Run the corrected backtest
        results = await backtest.run_backtest()
        
        # Print results
        print(backtest.format_report(results))
        
        # Additional analysis
        perf = results['performance']
        if perf.total_trades > 0:
            print(f"\n🎯 DETAILED RESULTS:")
            print(f"  Entry signals worked: YES")
            print(f"  Average holding time: {perf.avg_holding_period_minutes:.1f} minutes")
            print(f"  Profit targets hit: {perf.profit_target_hits}")
            print(f"  Stop losses hit: {perf.stop_loss_hits}")
            print(f"  Time limit exits: {perf.time_limit_exits}")
            
            # Show some positions
            if backtest.positions:
                print(f"\n📋 SAMPLE POSITIONS:")
                for i, pos in enumerate(backtest.positions[:5]):
                    print(f"  {i+1}. Entry: {pos.entry_spread:.3f}% → Exit: {pos.exit_spread:.3f}% → P&L: ${pos.pnl:.2f}")
        else:
            print(f"\n❌ Still no trades generated")
            print(f"  Check if entry_percentile={config.entry_percentile}% is correct")
            print(f"  Check if min_entry_spread={config.min_entry_spread:.3f}% is correct")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_fixed_backtest())