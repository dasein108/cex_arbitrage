#!/usr/bin/env python3
"""
Debug script to trace the exact flow of indicator calculation
and find why 'mexc_vs_gateio_futures_net' is missing.
"""

import asyncio
import pandas as pd
from datetime import datetime
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / 'src'
sys.path.insert(0, str(src_path))

from exchanges.structs import Symbol, AssetName, BookTicker
from trading.analysis.arbitrage_signal_strategy import ArbitrageSignalStrategy
from trading.analysis.arbitrage_indicators import ArbitrageIndicators, IndicatorConfig
from trading.analysis.arbitrage_data_loader import ArbitrageDataLoader


def debug_indicator_calculation_flow():
    """Debug the exact flow of indicator calculations."""
    print("🔍 DEBUGGING INDICATOR CALCULATION FLOW")
    print("=" * 60)
    
    # Create mock data
    symbol = Symbol(base=AssetName('TEST'), quote=AssetName('USDT'))
    
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
    
    print("📋 Step 1: Create DataLoader and process live data")
    data_loader = ArbitrageDataLoader(symbol, is_live_mode=True)
    current_data = data_loader.update_live_data(
        spot_book_tickers=spot_book_tickers,
        futures_book_ticker=futures_book_ticker
    )
    
    print(f"✅ Current data structure created:")
    for key in current_data.keys():
        print(f"   • {key}: {type(current_data[key])}")
    
    print(f"\n📊 Spot exchanges data:")
    for exchange, data in current_data['spot_exchanges'].items():
        print(f"   {exchange}: bid={data['bid_price']}, ask={data['ask_price']}")
    
    print(f"\n📊 Futures exchange data:")
    futures_data = current_data['futures_exchange']
    print(f"   Futures: bid={futures_data['bid_price']}, ask={futures_data['ask_price']}")
    
    print("\n📋 Step 2: Calculate indicators using ArbitrageIndicators")
    indicators = ArbitrageIndicators(IndicatorConfig())
    
    # Test the calculate_single_row_indicators method directly
    current_indicators = indicators.calculate_single_row_indicators(
        current_data, 
        strategy_type='reverse_delta_neutral'
    )
    
    print(f"\n✅ Indicators calculated: {len(current_indicators)} total")
    print(f"📊 Key indicators present:")
    
    # Check for the critical indicators
    critical_indicators = [
        'mexc_vs_gateio_futures_net',
        'gateio_spot_vs_futures_net', 
        'MEXC_vs_GATEIO_FUTURES_arb',
        'GATEIO_vs_GATEIO_FUTURES_arb',
        'entry_threshold',
        'exit_threshold'
    ]
    
    for indicator in critical_indicators:
        if indicator in current_indicators.index:
            print(f"   ✅ {indicator}: {current_indicators[indicator]:.4f}")
        else:
            print(f"   ❌ {indicator}: MISSING!")
    
    print(f"\n📊 All available indicators:")
    for idx in current_indicators.index[:20]:  # Show first 20
        value = current_indicators[idx]
        if pd.notna(value):
            if isinstance(value, (int, float)):
                print(f"   • {idx}: {value:.4f}")
            else:
                print(f"   • {idx}: {value}")
    
    print("\n📋 Step 3: Test signal generation")
    from trading.analysis.arbitrage_signal_generator import ArbitrageSignalGenerator
    
    signal_generator = ArbitrageSignalGenerator('reverse_delta_neutral')
    
    # Create minimal historical context
    historical_context = pd.DataFrame()
    
    try:
        signal = signal_generator.generate_signal(
            strategy_type='reverse_delta_neutral',
            current_indicators=current_indicators,
            historical_context=historical_context
        )
        print(f"✅ Signal generated: {signal.value}")
    except Exception as e:
        print(f"❌ Signal generation failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n🔍 DIAGNOSIS:")
    print("-" * 40)
    
    if 'mexc_vs_gateio_futures_net' not in current_indicators.index:
        print("❌ PROBLEM: 'mexc_vs_gateio_futures_net' is not being calculated!")
        print("   This is why signal generation fails.")
        
        print("\n🔍 Checking raw DataFrame columns...")
        # Create a DataFrame to see what columns are actually created
        row_data = {}
        
        # This mimics what calculate_single_row_indicators does
        from trading.analysis.arbitrage_indicators import AnalyzerKeys
        
        if 'spot_exchanges' in current_data:
            for exchange_name, data in current_data['spot_exchanges'].items():
                if exchange_name.upper() == 'MEXC':
                    row_data[AnalyzerKeys.mexc_bid] = data['bid_price']
                    row_data[AnalyzerKeys.mexc_ask] = data['ask_price']
                elif exchange_name.upper() == 'GATEIO':
                    row_data[AnalyzerKeys.gateio_spot_bid] = data['bid_price']
                    row_data[AnalyzerKeys.gateio_spot_ask] = data['ask_price']
        
        if 'futures_exchange' in current_data:
            futures_data = current_data['futures_exchange']
            row_data[AnalyzerKeys.gateio_futures_bid] = futures_data['bid_price']
            row_data[AnalyzerKeys.gateio_futures_ask] = futures_data['ask_price']
        
        print(f"\n📊 Row data being created:")
        for key, value in row_data.items():
            print(f"   • {key}: {value}")
        
        # Now let's see if the indicators are calculated
        df_test = pd.DataFrame([row_data])
        print(f"\n📊 DataFrame columns: {list(df_test.columns)}")
        
        # Test calculate_all_indicators directly
        df_with_indicators = indicators.calculate_all_indicators(df_test)
        print(f"\n✅ After calculate_all_indicators:")
        print(f"   Columns: {list(df_with_indicators.columns)}")
        
        if 'mexc_vs_gateio_futures_net' in df_with_indicators.columns:
            print(f"   ✅ 'mexc_vs_gateio_futures_net' = {df_with_indicators['mexc_vs_gateio_futures_net'].iloc[0]:.4f}")
        else:
            print(f"   ❌ 'mexc_vs_gateio_futures_net' still missing!")
    else:
        print("✅ All indicators are being calculated correctly!")


if __name__ == "__main__":
    debug_indicator_calculation_flow()