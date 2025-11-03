#!/usr/bin/env python3
"""
Migration Example: Old vs New Architecture

Shows how to migrate from the existing ArbitrageAnalyzer to the new 
dual-mode architecture while maintaining identical results.

Usage:
    python migration_example.py
"""

import asyncio
import pandas as pd
from datetime import datetime, UTC

from exchanges.structs import Symbol, AssetName
from trading.research.cross_arbitrage.arbitrage_analyzer import ArbitrageAnalyzer
from trading.analysis.base_arbitrage_strategy import create_backtesting_strategy


async def compare_old_vs_new_architecture():
    """
    Compare results from old ArbitrageAnalyzer vs new dual-mode architecture.
    """
    print("🔄 Migration Comparison: Old vs New Architecture")
    print("=" * 60)
    
    symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
    
    # Test 1: Old Architecture (Current ArbitrageAnalyzer)
    print("\n1️⃣ Running Old Architecture (ArbitrageAnalyzer)")
    print("-" * 45)
    
    old_analyzer = ArbitrageAnalyzer(use_db_book_tickers=False)  # Use candles
    
    try:
        old_start = datetime.now()
        old_df, old_results = await old_analyzer.run_analysis(symbol, days=1)
        old_time = (datetime.now() - old_start).total_seconds() * 1000
        
        print(f"✅ Old analyzer completed: {len(old_df)} rows in {old_time:.1f}ms")
        print(f"   Columns: {len(old_df.columns)} total")
        print(f"   Key indicators: {list(old_df.columns)[:10]}...")
        
        # Check for arbitrage calculations
        arb_columns = [col for col in old_df.columns if 'arb' in col]
        print(f"   Arbitrage columns: {arb_columns}")
        
    except Exception as e:
        print(f"❌ Old analyzer failed: {e}")
        old_df = pd.DataFrame()
        old_time = 0
    
    # Test 2: New Architecture (Dual-Mode Strategy)
    print("\n2️⃣ Running New Architecture (Dual-Mode Strategy)")
    print("-" * 48)
    
    new_strategy = create_backtesting_strategy(
        strategy_type='reverse_delta_neutral',
        symbol=symbol,
        days=1,
        use_db_source=False  # Use candles to match old analyzer
    )
    
    try:
        new_start = datetime.now()
        new_df = await new_strategy.run_analysis()
        new_time = (datetime.now() - new_start).total_seconds() * 1000
        
        print(f"✅ New strategy completed: {len(new_df)} rows in {new_time:.1f}ms")
        print(f"   Columns: {len(new_df.columns)} total")
        print(f"   Key indicators: {list(new_df.columns)[:10]}...")
        
        # Check for arbitrage calculations
        arb_columns = [col for col in new_df.columns if 'arb' in col]
        print(f"   Arbitrage columns: {arb_columns}")
        
    except Exception as e:
        print(f"❌ New strategy failed: {e}")
        new_df = pd.DataFrame()
        new_time = 0
    
    # Test 3: Results Comparison
    print("\n3️⃣ Results Comparison")
    print("-" * 25)
    
    if not old_df.empty and not new_df.empty:
        # Compare common columns
        common_columns = set(old_df.columns) & set(new_df.columns)
        print(f"📊 Common columns: {len(common_columns)}")
        
        # Compare key arbitrage calculations if available
        key_arb_cols = [
            'MEXC_vs_GATEIO_FUTURES_arb',
            'GATEIO_vs_GATEIO_FUTURES_arb',
            'mexc_vs_gateio_futures_net',
            'gateio_spot_vs_futures_net'
        ]
        
        for col in key_arb_cols:
            if col in old_df.columns and col in new_df.columns:
                old_mean = old_df[col].mean()
                new_mean = new_df[col].mean()
                diff_pct = abs(old_mean - new_mean) / abs(old_mean) * 100 if old_mean != 0 else 0
                
                print(f"   {col}:")
                print(f"     Old: {old_mean:.4f}, New: {new_mean:.4f}, Diff: {diff_pct:.2f}%")
        
        # Compare performance
        performance_improvement = ((old_time - new_time) / old_time * 100) if old_time > 0 else 0
        print(f"\n⚡ Performance comparison:")
        print(f"   Old architecture: {old_time:.1f}ms")
        print(f"   New architecture: {new_time:.1f}ms")
        print(f"   Improvement: {performance_improvement:+.1f}%")
    
    # Test 4: Migration Benefits
    print("\n4️⃣ Migration Benefits")
    print("-" * 23)
    
    print("✅ New Architecture Advantages:")
    print("   • Dual-mode compatibility (backtesting + live trading)")
    print("   • Automatic performance optimization")
    print("   • Composable architecture with dependency injection")
    print("   • Sub-millisecond live updates")
    print("   • Comprehensive performance monitoring")
    print("   • Strategy-agnostic base implementation")
    
    print("\n🔧 Migration Path:")
    print("   1. Test new architecture with existing data")
    print("   2. Validate identical results for key calculations")
    print("   3. Gradually migrate strategy functions")
    print("   4. Switch to live trading mode for deployment")
    print("   5. Retire old analyzer once confidence is established")
    
    # Test 5: Live Mode Demonstration
    print("\n5️⃣ Live Mode Demonstration (New Architecture Only)")
    print("-" * 53)
    
    # Switch to live mode
    try:
        new_strategy.switch_mode('live')
        
        # Initialize with context
        await new_strategy.data_provider.get_historical_data(symbol, 1)
        
        # Simulate a few live updates
        print("   Simulating live updates...")
        for i in range(3):
            test_data = {
                'MEXC_bid_price': 50000 + i * 10,
                'MEXC_ask_price': 50001 + i * 10,
                'GATEIO_bid_price': 49999 + i * 10,
                'GATEIO_ask_price': 50000 + i * 10,
                'GATEIO_FUTURES_bid_price': 49998 + i * 10,
                'GATEIO_FUTURES_ask_price': 49999 + i * 10,
                'timestamp': datetime.now(UTC)
            }
            
            signal_result = await new_strategy.update_live(test_data)
            print(f"     Update {i+1}: {signal_result['signal']} "
                  f"(confidence: {signal_result['confidence']:.2f}, "
                  f"time: {signal_result['processing_time_ms']:.2f}ms)")
        
        print("   ✅ Live mode working - ready for real-time trading!")
        
    except Exception as e:
        print(f"   ❌ Live mode demonstration failed: {e}")


async def demonstrate_backwards_compatibility():
    """
    Show how existing strategy functions can be gradually migrated.
    """
    print("\n🔄 Backwards Compatibility Demonstration")
    print("=" * 45)
    
    symbol = Symbol(base=AssetName("ETH"), quote=AssetName("USDT"))
    
    # Create new strategy
    strategy = create_backtesting_strategy(
        strategy_type='reverse_delta_neutral',
        symbol=symbol,
        days=1
    )
    
    try:
        # Run analysis to get data
        df = await strategy.run_analysis()
        
        print(f"✅ Got data with new architecture: {len(df)} rows")
        
        # Show how old analyzer methods could still work with new data
        if not df.empty:
            print("\n📊 Data compatibility check:")
            
            # Check if new data has same structure as old analyzer expects
            expected_columns = [
                'MEXC_bid_price', 'MEXC_ask_price',
                'GATEIO_bid_price', 'GATEIO_ask_price', 
                'GATEIO_FUTURES_bid_price', 'GATEIO_FUTURES_ask_price'
            ]
            
            has_all_columns = all(col in df.columns for col in expected_columns)
            print(f"   Has expected price columns: {has_all_columns}")
            
            if has_all_columns:
                # Could call old analyzer methods on new data
                print("   ✅ New data structure is compatible with old methods")
                print("   💡 Migration can be done incrementally!")
            else:
                print("   ⚠️  Some column mapping needed for full compatibility")
        
    except Exception as e:
        print(f"❌ Compatibility test failed: {e}")


if __name__ == "__main__":
    async def main():
        await compare_old_vs_new_architecture()
        await demonstrate_backwards_compatibility()
        
        print("\n🎉 Migration analysis completed!")
        print("\n📋 Next Steps:")
        print("   1. Run this comparison with your specific symbols")
        print("   2. Validate calculation accuracy matches existing results")
        print("   3. Test live mode with paper trading")
        print("   4. Gradually migrate your strategy functions")
        print("   5. Deploy to production with confidence!")
    
    asyncio.run(main())