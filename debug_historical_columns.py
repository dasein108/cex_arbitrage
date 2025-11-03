#!/usr/bin/env python3
"""
Debug script to check what columns are in the historical data
and why 'mexc_vs_gateio_futures_net' error occurs.
"""

import asyncio
import pandas as pd
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / 'src'
sys.path.insert(0, str(src_path))

from exchanges.structs import Symbol, AssetName, BookTicker
from trading.analysis.arbitrage_signal_strategy import ArbitrageSignalStrategy


async def debug_historical_data_columns():
    """Check what columns are in the historical data."""
    print("🔍 DEBUGGING HISTORICAL DATA COLUMNS")
    print("=" * 60)
    
    symbol = Symbol(base=AssetName('FLK'), quote=AssetName('USDT'))
    
    # Test with each strategy type
    strategy_types = ['reverse_delta_neutral', 'inventory_spot', 'volatility_harvesting']
    
    for strategy_type in strategy_types:
        print(f"\n📊 Testing {strategy_type} strategy")
        print("-" * 40)
        
        try:
            strategy = ArbitrageSignalStrategy(
                symbol=symbol,
                strategy_type=strategy_type,
                is_live_mode=False  # Backtesting mode
            )
            
            # Try to initialize
            await strategy.initialize(days=1)
            
            # Get historical data
            historical_df = strategy.get_historical_data()
            
            if historical_df.empty:
                print(f"❌ No historical data loaded")
                continue
            
            print(f"✅ Loaded {len(historical_df)} rows")
            print(f"📊 Columns in historical data ({len(historical_df.columns)} total):")
            
            # Group columns by type
            price_columns = [col for col in historical_df.columns if 'price' in col.lower()]
            spread_columns = [col for col in historical_df.columns if 'spread' in col.lower()]
            net_columns = [col for col in historical_df.columns if 'net' in col.lower()]
            threshold_columns = [col for col in historical_df.columns if 'threshold' in col.lower()]
            
            print(f"\n   Price columns ({len(price_columns)}):")
            for col in price_columns[:10]:  # Show first 10
                print(f"      • {col}")
            
            print(f"\n   Spread columns ({len(spread_columns)}):")
            for col in spread_columns[:10]:
                print(f"      • {col}")
            
            print(f"\n   Net columns ({len(net_columns)}):")
            for col in net_columns:
                print(f"      • {col}")
            
            print(f"\n   Threshold columns ({len(threshold_columns)}):")
            for col in threshold_columns:
                print(f"      • {col}")
            
            # Check for critical columns
            print(f"\n   ❓ Critical columns check:")
            critical_cols = ['mexc_vs_gateio_futures_net', 'gateio_spot_vs_futures_net']
            for col in critical_cols:
                if col in historical_df.columns:
                    print(f"      ✅ {col} present")
                else:
                    print(f"      ❌ {col} MISSING!")
            
            # Check sample row for accessing in demo
            if not historical_df.empty:
                sample_row = historical_df.iloc[0]
                print(f"\n   📋 Sample row access test:")
                
                # Try to access columns the way demo does
                try:
                    if 'MEXC_bid_price' in sample_row.index:
                        print(f"      ✅ MEXC_bid_price: {sample_row['MEXC_bid_price']}")
                    else:
                        print(f"      ❌ MEXC_bid_price not in index")
                except Exception as e:
                    print(f"      ❌ Error accessing MEXC_bid_price: {e}")
                
                try:
                    if 'mexc_vs_gateio_futures_net' in sample_row.index:
                        print(f"      ✅ mexc_vs_gateio_futures_net: {sample_row['mexc_vs_gateio_futures_net']}")
                    else:
                        print(f"      ❌ mexc_vs_gateio_futures_net not in index")
                except Exception as e:
                    print(f"      ❌ Error accessing mexc_vs_gateio_futures_net: {e}")
                
        except Exception as e:
            print(f"❌ Error with {strategy_type}: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("🔍 DIAGNOSIS:")
    print("The issue is likely that historical data columns don't match")
    print("what the demo expects when creating BookTicker objects.")


async def test_update_with_mock_data():
    """Test update_with_live_data with mock data to find the exact error."""
    print("\n🧪 TESTING UPDATE WITH MOCK DATA")
    print("=" * 60)
    
    symbol = Symbol(base=AssetName('TEST'), quote=AssetName('USDT'))
    
    # Create strategy
    strategy = ArbitrageSignalStrategy(
        symbol=symbol,
        strategy_type='reverse_delta_neutral',
        is_live_mode=True  # Live mode
    )
    
    # Don't initialize (to avoid database dependency)
    strategy.context_ready = True  # Force ready
    strategy.historical_df = pd.DataFrame()  # Empty historical
    
    # Create mock BookTickers
    spot_book_tickers = {
        'MEXC': BookTicker(
            symbol=symbol,
            bid_price=100.0,
            ask_price=100.1,
            bid_quantity=1000.0,
            ask_quantity=1000.0,
            timestamp=int(pd.Timestamp.now().timestamp() * 1000)
        ),
        'GATEIO': BookTicker(
            symbol=symbol,
            bid_price=99.9,
            ask_price=100.0,
            bid_quantity=1000.0,
            ask_quantity=1000.0,
            timestamp=int(pd.Timestamp.now().timestamp() * 1000)
        )
    }
    
    futures_book_ticker = BookTicker(
        symbol=symbol,
        bid_price=99.8,
        ask_price=99.9,
        bid_quantity=1000.0,
        ask_quantity=1000.0,
        timestamp=int(pd.Timestamp.now().timestamp() * 1000)
    )
    
    print("📊 Testing update_with_live_data...")
    try:
        signal = strategy.update_with_live_data(
            spot_book_tickers=spot_book_tickers,
            futures_book_ticker=futures_book_ticker
        )
        print(f"✅ Signal generated: {signal.value}")
    except KeyError as e:
        print(f"❌ KeyError: {e}")
        print(f"   This is the 'mexc_vs_gateio_futures_net' error!")
    except Exception as e:
        print(f"❌ Other error: {e}")
        import traceback
        traceback.print_exc()


async def main():
    await debug_historical_data_columns()
    await test_update_with_mock_data()


if __name__ == "__main__":
    asyncio.run(main())