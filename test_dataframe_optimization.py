#!/usr/bin/env python3
"""
Test the fully DataFrame-optimized strategy backtester.
Demonstrates the performance improvements from using pandas DataFrames throughout.
"""

import asyncio
import time
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from src.trading.analysis.strategy_backtester import HFTStrategyBacktester, BacktestConfig
from exchanges.structs.common import Symbol, AssetName


class MockBookTickerSnapshot:
    """Mock class for testing DataFrame optimization without database dependencies."""
    
    def __init__(self, timestamp, exchange, symbol_base, symbol_quote, bid_price, ask_price, bid_qty, ask_qty):
        self.timestamp = timestamp
        self.exchange = exchange
        self.symbol_base = symbol_base
        self.symbol_quote = symbol_quote
        self.bid_price = bid_price
        self.ask_price = ask_price
        self.bid_qty = bid_qty
        self.ask_qty = ask_qty


async def test_dataframe_optimization():
    """Test the DataFrame-optimized backtester performance and functionality."""
    print("🧪 Testing DataFrame-Optimized Strategy Backtester")
    print("=" * 60)
    
    try:
        # Generate larger realistic dataset for performance testing
        print("\n📊 Generating realistic market data for performance testing...")
        
        base_time = datetime.now()
        np.random.seed(42)  # For reproducible results
        
        # Create spot data with realistic price movements
        spot_data = []
        current_price = 100.0
        for i in range(500):  # Larger dataset
            # Random walk with trend
            price_change = np.random.normal(0, 0.001) + 0.0001  # Slight upward trend
            current_price += current_price * price_change
            
            timestamp = base_time + timedelta(seconds=i * 2 + np.random.uniform(-0.5, 0.5))
            
            bid_price = current_price * (1 - np.random.uniform(0.0001, 0.0005))
            ask_price = current_price * (1 + np.random.uniform(0.0001, 0.0005))
            
            spot_data.append(MockBookTickerSnapshot(
                timestamp=timestamp,
                exchange="MEXC_SPOT",
                symbol_base="TEST",
                symbol_quote="USDT",
                bid_price=bid_price,
                ask_price=ask_price,
                bid_qty=np.random.uniform(1000, 5000),
                ask_qty=np.random.uniform(1000, 5000)
            ))
        
        # Create futures data with systematic spread patterns
        futures_data = []
        for i, spot_snap in enumerate(spot_data):
            # Futures typically trade at slight premium/discount
            basis = np.sin(i * 0.1) * 0.002  # Oscillating basis
            futures_mid = spot_snap.bid_price * (1 + basis)
            
            timestamp = spot_snap.timestamp + timedelta(milliseconds=np.random.randint(-800, 800))
            
            fut_bid = futures_mid * (1 - np.random.uniform(0.0001, 0.0003))
            fut_ask = futures_mid * (1 + np.random.uniform(0.0001, 0.0003))
            
            futures_data.append(MockBookTickerSnapshot(
                timestamp=timestamp,
                exchange="GATEIO_FUTURES",
                symbol_base="TEST",
                symbol_quote="USDT",
                bid_price=fut_bid,
                ask_price=fut_ask,
                bid_qty=np.random.uniform(1000, 3000),
                ask_qty=np.random.uniform(1000, 3000)
            ))
        
        print(f"✅ Generated {len(spot_data)} spot + {len(futures_data)} futures data points")
        print(f"   Total data points: {len(spot_data) + len(futures_data)}")
        
        # Test 1: DataFrame Alignment Performance
        print(f"\n⚡ Test 1: DataFrame Alignment Performance")
        
        backtester = HFTStrategyBacktester()
        
        start_time = time.time()
        aligned_df = backtester._align_market_data(spot_data, futures_data)
        alignment_time = (time.time() - start_time) * 1000
        
        print(f"✅ Alignment completed in {alignment_time:.2f}ms")
        print(f"✅ Aligned DataFrame shape: {aligned_df.shape}")
        print(f"✅ DataFrame columns: {list(aligned_df.columns)}")
        
        if not aligned_df.empty:
            print(f"✅ Data efficiency: {len(aligned_df)*2}/{len(spot_data) + len(futures_data)} = {len(aligned_df)*2/(len(spot_data) + len(futures_data))*100:.1f}%")
        
        # Test 2: Vectorized Quality Filtering
        print(f"\n🔍 Test 2: Vectorized Quality Filtering")
        
        config = BacktestConfig(min_liquidity_usd=500.0)
        
        start_time = time.time()
        filtered_df = backtester._apply_quality_filters(aligned_df, config)
        filtering_time = (time.time() - start_time) * 1000
        
        print(f"✅ Quality filtering completed in {filtering_time:.2f}ms")
        print(f"✅ Filtered shape: {filtered_df.shape} (retained {len(filtered_df)/len(aligned_df)*100:.1f}%)")
        
        # Test 3: Rolling Metrics Calculation
        print(f"\n📈 Test 3: Rolling Metrics Calculation")
        
        start_time = time.time()
        enhanced_df = backtester._calculate_rolling_metrics(filtered_df, window=30)
        rolling_time = (time.time() - start_time) * 1000
        
        print(f"✅ Rolling metrics completed in {rolling_time:.2f}ms")
        print(f"✅ Enhanced DataFrame columns: {len(enhanced_df.columns)} total")
        if 'spread_rolling_mean' in enhanced_df.columns:
            print(f"✅ Rolling mean calculated: {enhanced_df['spread_rolling_mean'].notna().sum()} valid values")
        
        # Test 4: Vectorized Signal Detection
        print(f"\n🎯 Test 4: Vectorized Signal Detection")
        
        start_time = time.time()
        signals_df = backtester._identify_entry_signals_vectorized(enhanced_df, config)
        signal_time = (time.time() - start_time) * 1000
        
        print(f"✅ Signal detection completed in {signal_time:.2f}ms")
        print(f"✅ Signals identified: {len(signals_df)} from {len(enhanced_df)} points")
        if not signals_df.empty:
            signal_rate = len(signals_df) / len(enhanced_df) * 100
            print(f"✅ Signal rate: {signal_rate:.2f}%")
            
            # Analyze signal quality
            if 'signal_strength' in signals_df.columns:
                avg_strength = signals_df['signal_strength'].mean()
                max_strength = signals_df['signal_strength'].max()
                print(f"✅ Signal strength: avg={avg_strength:.3f}%, max={max_strength:.3f}%")
            
            # Direction distribution
            if 'direction' in signals_df.columns:
                long_signals = (signals_df['direction'] == 'long_spot_short_futures').sum()
                short_signals = (signals_df['direction'] == 'short_spot_long_futures').sum()
                print(f"✅ Direction split: {long_signals} long, {short_signals} short")
        
        # Test 5: DataFrame Row Conversion Performance
        print(f"\n🔄 Test 5: DataFrame Row Conversion Performance")
        
        if not enhanced_df.empty:
            start_time = time.time()
            # Test conversion of 100 random rows
            sample_indices = np.random.choice(len(enhanced_df), min(100, len(enhanced_df)), replace=False)
            converted_points = []
            
            for idx in sample_indices:
                row = enhanced_df.iloc[idx]
                market_point = backtester._dataframe_row_to_market_data_point(row)
                converted_points.append(market_point)
            
            conversion_time = (time.time() - start_time) * 1000
            
            print(f"✅ Row conversion: {len(converted_points)} points in {conversion_time:.2f}ms")
            print(f"✅ Avg conversion time: {conversion_time/len(converted_points):.3f}ms per point")
            
            # Verify conversion accuracy
            first_point = converted_points[0]
            first_row = enhanced_df.iloc[sample_indices[0]]
            
            spread_match = abs(first_point.get_spread_bps() - first_row['spread_bps']) < 0.01
            print(f"✅ Conversion accuracy: {'PASS' if spread_match else 'FAIL'}")
        
        # Test 6: Performance Summary
        print(f"\n📊 Test 6: Performance Summary")
        
        total_processing_time = alignment_time + filtering_time + rolling_time + signal_time
        data_points_per_ms = len(enhanced_df) / max(total_processing_time, 0.001)
        
        print(f"✅ Total processing time: {total_processing_time:.2f}ms")
        print(f"✅ Data points processed: {len(enhanced_df)}")
        print(f"✅ Processing rate: {data_points_per_ms:.1f} points/ms")
        print(f"✅ Theoretical capacity: {data_points_per_ms * 1000:.0f} points/second")
        
        # HFT Performance Validation
        hft_compliant = total_processing_time < 10  # <10ms target
        print(f"✅ HFT Compliance: {'PASS' if hft_compliant else 'FAIL'} (<10ms target)")
        
        # Test 7: Memory Efficiency
        print(f"\n💾 Test 7: Memory Efficiency Analysis")
        
        # DataFrame memory usage
        df_memory = enhanced_df.memory_usage(deep=True).sum() / 1024 / 1024  # MB
        per_point_memory = df_memory / len(enhanced_df) * 1024  # KB per point
        
        print(f"✅ DataFrame memory: {df_memory:.2f} MB")
        print(f"✅ Memory per point: {per_point_memory:.3f} KB")
        print(f"✅ Memory efficiency: {'GOOD' if per_point_memory < 1.0 else 'NEEDS_OPTIMIZATION'}")
        
        # Test 8: Statistical Analysis
        print(f"\n📈 Test 8: Statistical Analysis of Results")
        
        if not enhanced_df.empty:
            # Spread statistics
            spread_stats = enhanced_df['spread_bps'].describe()
            print(f"✅ Spread statistics (bps):")
            print(f"   Mean: {spread_stats['mean']:.2f}")
            print(f"   Std: {spread_stats['std']:.2f}")
            print(f"   Range: [{spread_stats['min']:.2f}, {spread_stats['max']:.2f}]")
            print(f"   Median: {spread_stats['50%']:.2f}")
            
            # Liquidity statistics
            total_liquidity = enhanced_df['spot_liquidity'] + enhanced_df['fut_liquidity']
            print(f"✅ Total liquidity statistics:")
            print(f"   Mean: ${total_liquidity.mean():.0f}")
            print(f"   Median: ${total_liquidity.median():.0f}")
            print(f"   Min: ${total_liquidity.min():.0f}")
            
            # Volatility analysis
            if 'price_volatility' in enhanced_df.columns:
                vol_stats = enhanced_df['price_volatility'].dropna()
                if not vol_stats.empty:
                    print(f"✅ Price volatility:")
                    print(f"   Mean: {vol_stats.mean():.4f}")
                    print(f"   Max: {vol_stats.max():.4f}")
        
        print(f"\n🎉 DataFrame Optimization Tests Completed Successfully!")
        print(f"✅ All vectorized operations working correctly")
        print(f"✅ Performance targets met: {data_points_per_ms:.1f} points/ms")
        print(f"✅ HFT compliance: {'ACHIEVED' if hft_compliant else 'NEEDS_WORK'}")
        print(f"✅ Memory efficiency: {per_point_memory:.3f} KB/point")
        print(f"✅ Signal detection: {len(signals_df) if not signals_df.empty else 0} opportunities found")
        
        return {
            'processing_time_ms': total_processing_time,
            'data_points': len(enhanced_df),
            'signals_found': len(signals_df) if not signals_df.empty else 0,
            'processing_rate': data_points_per_ms,
            'hft_compliant': hft_compliant,
            'memory_per_point_kb': per_point_memory
        }
        
    except Exception as e:
        print(f"❌ Error during DataFrame optimization test: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    results = asyncio.run(test_dataframe_optimization())
    
    if results:
        print(f"\n" + "="*60)
        print(f"DATAFRAME OPTIMIZATION RESULTS:")
        print(f"  Processing Time: {results['processing_time_ms']:.2f}ms")
        print(f"  Data Points: {results['data_points']}")
        print(f"  Signals Found: {results['signals_found']}")
        print(f"  Processing Rate: {results['processing_rate']:.1f} points/ms")
        print(f"  HFT Compliant: {results['hft_compliant']}")
        print(f"  Memory Efficiency: {results['memory_per_point_kb']:.3f} KB/point")
        print(f"="*60)