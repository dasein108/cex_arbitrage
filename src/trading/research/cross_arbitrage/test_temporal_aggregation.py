#!/usr/bin/env python3
"""
Test Script for Temporal Aggregation Strategy

Demonstrates the performance improvement from using temporal aggregation
with high-frequency book ticker data vs standard processing.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.append(str(project_root))

from exchanges.structs import Symbol
from temporal_backtester import TemporalAggregationBacktester

symbol = Symbol(base='FLK', quote='USDT')

async def test_temporal_aggregation_performance():
    """Test temporal aggregation vs standard processing"""
    
    print("🚀 Testing Temporal Aggregation Strategy")
    print("=" * 60)
    
    # Test configuration
    hours = 3  # 3 hours of data for quick test
    
    print(f"Symbol: {symbol}")
    print(f"Test period: {hours} hours")
    print()
    
    # Initialize backtester with temporal aggregation
    backtester = TemporalAggregationBacktester(
        use_temporal_aggregation=True,
        conservative_mode=False  # Start with conservative settings
    )
    
    try:
        # Load high-frequency data (targeting 5-second intervals)
        print("📊 Loading high-frequency book ticker data...")
        df = await backtester.load_high_frequency_data(
            symbol=symbol,
            hours=hours, 
            target_interval_seconds=5
        )
        df.fillna(method='ffill', inplace=True)  # Forward fill missing data
        if df is None or len(df) == 0:
            print("❌ No data available for testing")
            return
        
        print(f"✅ Loaded {len(df)} data points")
        print()
        
        # Test 1: Standard processing (expected poor performance)
        print("1️⃣ Testing Standard 5-Second Processing (Expected: Poor Performance)")
        print("-" * 50)
        
        backtester.use_temporal_aggregation = False
        standard_results = backtester.backtest_optimized_spike_capture(
            df, 
            symbol=symbol,
            save_report=False
        )
        
        print(f"   Trades: {standard_results.get('total_trades', 0)}")
        print(f"   Win Rate: {standard_results.get('win_rate', 0):.1f}%") 
        print(f"   Total P&L: {standard_results.get('total_pnl_pct', 0):.3f}%")
        print()
        
        # Test 2: Temporal aggregation processing
        print("2️⃣ Testing Temporal Aggregation (Expected: Improved Performance)")
        print("-" * 50)
        
        backtester.use_temporal_aggregation = True
        temporal_results = backtester.backtest_temporal_spike_capture(
            df,
            min_confidence=0.4,  # 40% minimum confidence
            max_hold_minutes=8,   # 8 minutes max hold
            symbol=symbol,
            save_report=False
        )
        
        print(f"   Trades: {temporal_results.get('total_trades', 0)}")
        print(f"   Win Rate: {temporal_results.get('win_rate', 0):.1f}%")
        print(f"   Total P&L: {temporal_results.get('total_pnl_pct', 0):.3f}%")
        print(f"   Signals Generated: {temporal_results.get('signals_generated', 0)}")
        print(f"   Signals Acted On: {temporal_results.get('signals_acted_on', 0)}")
        print()
        
        # Test 3: Baseline comparison with 1-minute data
        print("3️⃣ Baseline: 1-Minute Data Processing")
        print("-" * 50)
        
        baseline_df = await backtester.load_book_ticker_data(
            symbol=symbol,
            hours=hours,
            timeframe=60  # 1 minute
        )
        
        baseline_results = backtester.backtest_optimized_spike_capture(
            baseline_df,
            symbol=symbol, 
            save_report=False
        )
        
        print(f"   Data Points: {len(baseline_df)}")
        print(f"   Trades: {baseline_results.get('total_trades', 0)}")
        print(f"   Win Rate: {baseline_results.get('win_rate', 0):.1f}%")
        print(f"   Total P&L: {baseline_results.get('total_pnl_pct', 0):.3f}%")
        print()
        
        # Performance comparison
        print("📊 PERFORMANCE COMPARISON")
        print("=" * 60)
        
        print(f"{'Method':<25} {'Trades':<8} {'Win Rate':<10} {'Total P&L':<12} {'Data Points'}")
        print("-" * 65)
        
        print(f"{'Standard 5s':<25} {standard_results.get('total_trades', 0):<8} "
              f"{standard_results.get('win_rate', 0):<10.1f} "
              f"{standard_results.get('total_pnl_pct', 0):<12.3f} {len(df)}")
        
        print(f"{'Temporal Aggregation':<25} {temporal_results.get('total_trades', 0):<8} "
              f"{temporal_results.get('win_rate', 0):<10.1f} "
              f"{temporal_results.get('total_pnl_pct', 0):<12.3f} {len(df)}")
        
        print(f"{'1-Minute Baseline':<25} {baseline_results.get('total_trades', 0):<8} "
              f"{baseline_results.get('win_rate', 0):<10.1f} "
              f"{baseline_results.get('total_pnl_pct', 0):<12.3f} {len(baseline_df)}")
        
        print()
        
        # Calculate improvements
        win_rate_improvement = temporal_results.get('win_rate', 0) - standard_results.get('win_rate', 0)
        pnl_improvement = temporal_results.get('total_pnl_pct', 0) - standard_results.get('total_pnl_pct', 0)
        
        print("🎯 KEY IMPROVEMENTS")
        print("-" * 30)
        print(f"Win Rate Improvement: +{win_rate_improvement:.1f}%")
        print(f"P&L Improvement: +{pnl_improvement:.3f}%")
        
        if temporal_results.get('win_rate', 0) > standard_results.get('win_rate', 0):
            print("✅ Temporal aggregation shows improved performance!")
        else:
            print("⚠️ Temporal aggregation needs tuning")
        
        # Show temporal aggregation specific metrics
        agg_stats = temporal_results.get('aggregator_stats', {})
        if agg_stats:
            print("\n📈 TEMPORAL AGGREGATION METRICS")
            print("-" * 35)
            print(f"Total Updates Processed: {agg_stats.get('total_updates', 0)}")
            print(f"Signals Filtered (noise): {agg_stats.get('filtered_signals', 0)}")
            print(f"Filter Rate: {agg_stats.get('filter_rate', 0):.1%}")
            print(f"Signal Generation Rate: {agg_stats.get('signal_rate', 0):.1%}")
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()


async def test_different_confidence_levels():
    """Test performance with different confidence thresholds"""
    
    print("\n🔬 Testing Different Confidence Levels")
    print("=" * 50)
    

    backtester = TemporalAggregationBacktester(use_temporal_aggregation=True)
    df = await backtester.load_high_frequency_data(symbol, hours=2)
    
    confidence_levels = [0.2, 0.4, 0.6, 0.8]
    
    print(f"{'Confidence':<12} {'Trades':<8} {'Win Rate':<10} {'P&L':<8}")
    print("-" * 40)
    
    for confidence in confidence_levels:
        results = backtester.backtest_temporal_spike_capture(
            df,
            min_confidence=confidence,
            symbol=symbol,
            save_report=False
        )
        
        print(f"{confidence:<12.1f} {results.get('total_trades', 0):<8} "
              f"{results.get('win_rate', 0):<10.1f} "
              f"{results.get('total_pnl_pct', 0):<8.3f}")


if __name__ == "__main__":
    print("🧪 Temporal Aggregation Testing Suite")
    print("=" * 50)
    
    # Run main test
    asyncio.run(test_temporal_aggregation_performance())
    
    # Run confidence level test
    asyncio.run(test_different_confidence_levels())
    
    print("\n✅ Testing complete!")
    print("\n💡 Next Steps:")
    print("1. If temporal aggregation shows improvement, integrate into production")
    print("2. Tune confidence thresholds based on desired trade frequency")
    print("3. Test with different symbols and market conditions")
    print("4. Consider implementing real-time version for live trading")