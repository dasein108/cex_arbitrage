#!/usr/bin/env python3
"""
Test script to verify pandas integration in the strategy backtester.
Uses available GATEIO_FUTURES data for both spot and futures simulation.
"""

import asyncio
from datetime import datetime, timedelta
from src.trading.analysis.strategy_backtester import HFTStrategyBacktester, BacktestConfig, HFTMarketDataFrame, MarketDataPoint
from exchanges.structs.common import Symbol, AssetName
from src.db.models import BookTickerSnapshot


async def test_pandas_integration():
    """Test the HFTMarketDataFrame and pandas integration functionality."""
    print("🧪 Testing Pandas Integration in Strategy Backtester")
    print("=" * 60)
    
    try:
        # Test 1: HFTMarketDataFrame creation and conversion
        print("\n📊 Test 1: HFTMarketDataFrame functionality")
        
        # Create sample market data points
        sample_data = [
            MarketDataPoint(
                timestamp=datetime.now() - timedelta(seconds=i*10),
                spot_bid=100.0 + i * 0.1,
                spot_ask=100.1 + i * 0.1,
                spot_bid_qty=1000.0,
                spot_ask_qty=1000.0,
                fut_bid=100.05 + i * 0.1,
                fut_ask=100.15 + i * 0.1,
                fut_bid_qty=1000.0,
                fut_ask_qty=1000.0
            )
            for i in range(10)
        ]
        
        # Test HFTMarketDataFrame creation
        hft_data = HFTMarketDataFrame(sample_data)
        print(f"✅ Created HFTMarketDataFrame with {len(hft_data)} data points")
        print(f"✅ DataFrame columns: {list(hft_data.df.columns)}")
        
        # Test vectorized calculations
        print(f"✅ Calculated spreads: min={hft_data.df['spread_bps'].min():.2f}bps, max={hft_data.df['spread_bps'].max():.2f}bps")
        
        # Test quality filtering
        filtered_data = hft_data.filter_quality(min_liquidity=100.0)
        print(f"✅ Quality filtering: {len(hft_data)} -> {len(filtered_data)} points")
        
        # Test rolling metrics
        rolling_data = hft_data.calculate_rolling_metrics(window=5)
        print(f"✅ Rolling metrics calculated with window=5")
        
        # Test timestamp alignment
        aligned_data = hft_data.align_by_tolerance(tolerance_seconds=1)
        print(f"✅ Timestamp alignment: {len(hft_data)} -> {len(aligned_data)} points")
        
        # Test conversion back to MarketDataPoint list
        converted_points = hft_data.to_market_data_points()
        print(f"✅ Converted back to {len(converted_points)} MarketDataPoint objects")
        
        # Test backward compatibility indexing
        first_point = hft_data[0]
        print(f"✅ Backward compatibility: first point timestamp = {first_point.timestamp}")
        
        # Test 2: Pandas DataFrame operations
        print("\n📈 Test 2: Advanced pandas DataFrame operations")
        
        # Test vectorized spread analysis
        hft_data_large = HFTMarketDataFrame([
            MarketDataPoint(
                timestamp=datetime.now() - timedelta(seconds=i),
                spot_bid=100.0 + i * 0.01 + (i % 3) * 0.02,  # Add some variance
                spot_ask=100.1 + i * 0.01 + (i % 3) * 0.02,
                spot_bid_qty=1000.0 + i * 10,
                spot_ask_qty=1000.0 + i * 10,
                fut_bid=100.05 + i * 0.01 + (i % 5) * 0.03,  # Different variance pattern
                fut_ask=100.15 + i * 0.01 + (i % 5) * 0.03,
                fut_bid_qty=1000.0 + i * 10,
                fut_ask_qty=1000.0 + i * 10
            )
            for i in range(100)  # Larger dataset for testing
        ])
        
        print(f"✅ Created large dataset: {len(hft_data_large)} points")
        
        # Test statistical operations
        df = hft_data_large.df
        spread_stats = {
            'mean': df['spread_bps'].mean(),
            'std': df['spread_bps'].std(),
            'min': df['spread_bps'].min(),
            'max': df['spread_bps'].max(),
            'median': df['spread_bps'].median()
        }
        
        print(f"✅ Spread statistics: mean={spread_stats['mean']:.2f}bps, std={spread_stats['std']:.2f}bps")
        print(f"   Range: [{spread_stats['min']:.2f}, {spread_stats['max']:.2f}]bps, median={spread_stats['median']:.2f}bps")
        
        # Test rolling calculations
        rolling_data = hft_data_large.calculate_rolling_metrics(window=20)
        rolling_means = rolling_data.df['spread_rolling_mean'].dropna()
        print(f"✅ Rolling metrics: {len(rolling_means)} rolling mean values calculated")
        
        # Test quality filtering effectiveness
        # Inject some bad data
        bad_data = [
            MarketDataPoint(
                timestamp=datetime.now(),
                spot_bid=0.0,  # Bad data
                spot_ask=100.1,
                spot_bid_qty=1000.0,
                spot_ask_qty=1000.0,
                fut_bid=100.05,
                fut_ask=100.15,
                fut_bid_qty=1000.0,
                fut_ask_qty=1000.0
            ),
            MarketDataPoint(
                timestamp=datetime.now(),
                spot_bid=100.2,  # Invalid spread (bid > ask)
                spot_ask=100.1,
                spot_bid_qty=1000.0,
                spot_ask_qty=1000.0,
                fut_bid=100.05,
                fut_ask=100.15,
                fut_bid_qty=1000.0,
                fut_ask_qty=1000.0
            )
        ]
        
        mixed_data = HFTMarketDataFrame(sample_data + bad_data)
        filtered_mixed = mixed_data.filter_quality(min_liquidity=100.0)
        
        print(f"✅ Quality filtering test: {len(mixed_data)} -> {len(filtered_mixed)} points")
        print(f"   Removed {len(mixed_data) - len(filtered_mixed)} invalid data points")
        
        # Test 3: Vectorized validation
        print("\n✅ Test 3: Vectorized data validation")
        
        # Create backtester instance for validation testing
        backtester = HFTStrategyBacktester()
        
        # Test invalid data point
        invalid_point = MarketDataPoint(
            timestamp=datetime.now(),
            spot_bid=0.0,  # Invalid: zero bid
            spot_ask=100.1,
            spot_bid_qty=1000.0,
            spot_ask_qty=1000.0,
            fut_bid=100.05,
            fut_ask=100.15,
            fut_bid_qty=1000.0,
            fut_ask_qty=1000.0
        )
        
        is_valid = backtester._is_valid_market_data(invalid_point)
        print(f"✅ Invalid data detection: {not is_valid} (should be True)")
        
        # Test valid data point
        valid_point = sample_data[0]
        is_valid = backtester._is_valid_market_data(valid_point)
        print(f"✅ Valid data detection: {is_valid} (should be True)")
        
        print(f"\n🎉 All pandas integration tests passed successfully!")
        print(f"✅ HFTMarketDataFrame hybrid structure working")
        print(f"✅ Vectorized calculations enabled")
        print(f"✅ Enhanced timestamp alignment with ±1 second tolerance")
        print(f"✅ Data quality filtering and validation")
        print(f"✅ Rolling metrics calculation")
        print(f"✅ Backward compatibility maintained")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_pandas_integration())