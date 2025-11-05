#!/usr/bin/env python3
"""
Test the exit flow specifically to isolate the close_position issue.
"""

import asyncio
from datetime import datetime, timezone
from trading.signals.backtesting.position_tracker import PositionTracker
from trading.signals.implementations.inventory_spot_strategy_signal_v2 import InventorySpotStrategySignalV2
from trading.signals.types.signal_types import Signal
from exchanges.structs import Symbol, AssetName

async def test_exit_flow():
    """Test the exit flow specifically."""
    
    print("🔍 Testing Exit Flow")
    print("=" * 40)
    
    # Create components
    tracker = PositionTracker(initial_capital=10000.0)
    strategy = InventorySpotStrategySignalV2(
        symbol=Symbol(base=AssetName('FLK'), quote=AssetName('USDT')),
        position_size_usd=1000.0,
        min_execution_confidence=0.7,
        safe_offset_percentile=25.0
    )
    
    # Entry
    entry_market_data = {
        'gateio_spot_bid': 0.05450,
        'gateio_spot_ask': 0.05455,
        'entry_buy_price': 0.05455,
        'entry_sell_price': 0.05450,
    }
    
    params = {
        'same_exchange': True,
        'exchange': 'GATEIO_SPOT',
        'rotating_amount': 1.5,
        'position_size_usd': 1000.0
    }
    
    print("📊 Opening position...")
    trade_result = tracker.update_position_realtime(
        signal=Signal.ENTER,
        strategy=strategy,
        market_data=entry_market_data,
        **params
    )
    
    print(f"✅ Position opened: {tracker.current_position.strategy_type}")
    print(f"📦 Entry data keys: {list(tracker.current_position.entry_data.keys())}")
    
    # Exit
    exit_market_data = {
        'gateio_spot_bid': 0.05465,
        'gateio_spot_ask': 0.05470,
        'exit_buy_price': 0.05470,
        'exit_sell_price': 0.05465,
    }
    
    print(f"\n📊 Closing position...")
    print(f"🔍 About to call close_position with entry_data: {list(tracker.current_position.entry_data.keys())}")
    
    try:
        trade_result = tracker.update_position_realtime(
            signal=Signal.EXIT,
            strategy=strategy,
            market_data=exit_market_data,
            **params
        )
        
        if trade_result:
            print(f"✅ Position closed successfully")
            print(f"   P&L: ${trade_result.pnl_usd:.2f} ({trade_result.pnl_pct:.3f}%)")
        else:
            print(f"❌ No trade result returned")
            
    except Exception as e:
        print(f"❌ Error during close: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_exit_flow())