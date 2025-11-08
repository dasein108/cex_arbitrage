#!/usr/bin/env python3
"""
Spike Catching Strategy Parameter Optimization Script

This script runs comprehensive parameter optimization for the spike catching strategy
using systematic grid search with train/validation splits.
"""

import asyncio
from trading.signals_v2.signal_backtester import SignalBacktester
from exchanges.structs import Symbol, AssetName
from exchanges.structs.enums import KlineInterval

async def main():
    """
    Run parameter optimization for spike catching strategy.
    """
    print("🚀 Spike Catching Strategy Parameter Optimization")
    print("=" * 60)
    
    # Initialize backtester
    backtester = SignalBacktester(
        initial_capital_usdt=1000.0,
        position_size_usdt=100.0,
        candles_timeframe=KlineInterval.MINUTE_1,
        snapshot_seconds=60
    )

    # Test symbol (can be changed to any supported symbol)
    asset_name = 'AIA'
    symbol = Symbol(base=AssetName(asset_name), quote=AssetName('USDT'))
    
    print(f"📊 Optimizing parameters for {symbol}")
    print(f"💰 Capital: $1000 | Position Size: $100")
    print(f"⏰ Data Source: 1-minute candles | Period: 48 hours")
    print()
    
    # Run optimization
    try:
        optimization_results = await backtester.optimize_strategy_parameters(
            symbol=symbol,
            data_source='candles',
            hours=48  # Use 48 hours for robust optimization
        )
        
        if 'error' in optimization_results:
            print(f"❌ Optimization failed: {optimization_results['error']}")
            return
        
        # Display comprehensive results
        print(f"\n" + "=" * 60)
        print(f"📈 PARAMETER OPTIMIZATION RESULTS")
        print(f"=" * 60)
        
        print(f"🔢 Total combinations tested: {optimization_results['total_combinations_tested']}")
        print(f"📊 Data split: {optimization_results['data_split']['train_samples']} train, {optimization_results['data_split']['validation_samples']} validation")
        
        best = optimization_results['best_params']
        validation = optimization_results['validation_performance']
        
        print(f"\n🏆 OPTIMAL PARAMETERS DISCOVERED:")
        print(f"   📈 Spike Offset Multiplier: {best['spike_offset_multiplier']}")
        print(f"   🎯 Stabilization Threshold: {best['stabilization_threshold']}%")
        print(f"   ⏱️  Max Position Time: {best['max_position_time_minutes']} minutes")
        print(f"   🏅 Training Score: {best['composite_score']:.2f}")
        
        print(f"\n🧪 OUT-OF-SAMPLE VALIDATION PERFORMANCE:")
        print(f"   💰 P&L: {validation['total_pnl_pct']:.2f}%")
        print(f"   📊 Total Trades: {validation['total_trades']}")
        print(f"   🎯 Win Rate: {validation['win_rate']:.1f}%")
        print(f"   📉 Sharpe Ratio: {validation['sharpe_ratio']:.2f}")
        
        # Performance analysis
        if validation['total_pnl_pct'] > 0:
            print(f"   ✅ Strategy shows positive returns on validation data")
        else:
            print(f"   ⚠️  Strategy shows negative returns on validation data")
            
        if validation['win_rate'] > 50:
            print(f"   ✅ Win rate above 50% indicates good signal quality")
        else:
            print(f"   ⚠️  Win rate below 50% suggests challenging market conditions")
        
        print(f"\n🎯 TOP 10 PARAMETER COMBINATIONS:")
        print(f"{'Rank':<4} {'Offset':<6} {'Threshold':<9} {'Time':<8} {'P&L%':<8} {'Trades':<6} {'WinRate':<7} {'Score':<8}")
        print(f"{'-'*4} {'-'*6} {'-'*9} {'-'*8} {'-'*8} {'-'*6} {'-'*7} {'-'*8}")
        
        for i, result in enumerate(optimization_results['top_10_results'][:10], 1):
            print(f"{i:<4} {result['spike_offset_multiplier']:<6.1f} "
                  f"{result['stabilization_threshold']:<9.1f}% "
                  f"{result['max_position_time_minutes']:<8}min "
                  f"{result['total_pnl_pct']:<8.2f}% "
                  f"{result['total_trades']:<6} "
                  f"{result['win_rate']:<7.1f}% "
                  f"{result['composite_score']:<8.2f}")
        
        # Strategy recommendations
        print(f"\n💡 STRATEGY RECOMMENDATIONS:")
        
        if best['spike_offset_multiplier'] >= 4.0:
            print(f"   🔥 High spike offset suggests volatile market conditions")
            print(f"   📈 Strategy adapted to capture larger price movements")
        
        if best['stabilization_threshold'] >= 2.0:
            print(f"   ⚖️  High stabilization threshold indicates need for strong reversal signals")
            print(f"   🎯 Strategy prioritizes quality exits over quick profits")
        
        if best['max_position_time_minutes'] <= 15:
            print(f"   ⚡ Short position time suggests high-frequency opportunities")
            print(f"   🔄 Strategy optimized for quick turnaround trades")
        
        # Implementation guide
        print(f"\n🛠️  IMPLEMENTATION GUIDE:")
        print(f"   1. Update signal_backtester.py with optimal parameters:")
        print(f"      spike_offset_multiplier={best['spike_offset_multiplier']}")
        print(f"      stabilization_threshold={best['stabilization_threshold']}")
        print(f"      max_position_time_minutes={best['max_position_time_minutes']}")
        print(f"   2. Test on additional symbols to validate robustness")
        print(f"   3. Consider implementing adaptive parameters based on market volatility")
        print(f"   4. Monitor performance in live trading with smaller position sizes")
        
        print(f"\n✅ Parameter optimization completed successfully!")
        
    except Exception as e:
        print(f"❌ Optimization failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())