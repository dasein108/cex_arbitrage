#!/usr/bin/env python3
"""
Debug script to isolate position tracker issues.
"""

import asyncio
from datetime import datetime, timezone
from trading.signals.backtesting.position_tracker import PositionTracker
from trading.signals.implementations.inventory_spot_strategy_signal_v2 import InventorySpotStrategySignalV2
from trading.signals.types.signal_types import Signal
from exchanges.structs import Symbol, AssetName

async def debug_open_position():
    """Debug the open_position method directly."""
    
    print("🔍 Debugging Position Opening")
    print("=" * 40)
    
    # Create strategy
    strategy = InventorySpotStrategySignalV2(
        symbol=Symbol(base=AssetName('FLK'), quote=AssetName('USDT')),
        position_size_usd=1000.0,
        min_execution_confidence=0.7,
        safe_offset_percentile=25.0
    )
    
    # Test market data
    market_data = {
        'gateio_spot_bid': 0.05450,
        'gateio_spot_ask': 0.05455,
        'entry_buy_price': 0.05455,
        'entry_sell_price': 0.05450,
    }
    
    # Test parameters
    params = {
        'same_exchange': True,
        'exchange': 'GATEIO_SPOT',
        'rotating_amount': 1.5,
        'position_size_usd': 1000.0
    }
    
    print(f"📊 Input market_data: {market_data}")
    print(f"📊 Input params: {params}")
    
    # Call open_position directly
    try:
        position_details = strategy.open_position(
            signal=Signal.ENTER,
            market_data=market_data,
            **params
        )
        
        print(f"✅ open_position returned: {type(position_details)}")
        print(f"📦 Position details: {position_details}")
        
        if isinstance(position_details, dict):
            print(f"🔑 Keys in position_details: {list(position_details.keys())}")
            if 'buy_price' in position_details:
                print(f"💰 Buy price: {position_details['buy_price']}")
            if 'sell_price' in position_details:
                print(f"💰 Sell price: {position_details['sell_price']}")
        else:
            print(f"❌ Position details is not a dict: {position_details}")
            
    except Exception as e:
        print(f"❌ Error in open_position: {e}")
        import traceback
        traceback.print_exc()
    
    # Now test with position tracker
    print(f"\n🔧 Testing with Position Tracker")
    print("-" * 40)
    
    tracker = PositionTracker(initial_capital=10000.0)
    
    try:
        trade_result = tracker.update_position_realtime(
            signal=Signal.ENTER,
            strategy=strategy,
            market_data=market_data,
            **params
        )
        
        print(f"✅ Position tracker completed")
        print(f"📦 Current position: {tracker.current_position}")
        
        if tracker.current_position:
            print(f"🔑 Entry data keys: {list(tracker.current_position.entry_data.keys()) if tracker.current_position.entry_data else 'Empty!'}")
            print(f"📊 Entry data: {tracker.current_position.entry_data}")
        else:
            print(f"❌ No current position created")
            
    except Exception as e:
        print(f"❌ Error in position tracker: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_open_position())