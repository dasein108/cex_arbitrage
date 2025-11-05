#!/usr/bin/env python3
"""
Debug Cross-Exchange P&L Issues

Investigates why cross-exchange trading returns 0% P&L.
"""

import asyncio
from datetime import datetime, timezone
from trading.signals.backtesting.position_tracker import PositionTracker
from trading.signals.implementations.inventory_spot_strategy_signal_v2 import InventorySpotStrategySignalV2
from trading.signals.types.signal_types import Signal
from exchanges.structs import Symbol, AssetName

async def debug_cross_exchange_pnl():
    """Debug cross-exchange P&L calculation step by step."""
    
    print("🔍 Debugging Cross-Exchange P&L Issues")
    print("=" * 50)
    
    # Create components
    tracker = PositionTracker(initial_capital=10000.0)
    strategy = InventorySpotStrategySignalV2(
        symbol=Symbol(base=AssetName('FLK'), quote=AssetName('USDT')),
        position_size_usd=1000.0,
        min_execution_confidence=0.7,
        safe_offset_percentile=25.0
    )
    
    print(f"✅ Components created")
    
    # Test cross-exchange scenario step by step
    print(f"\n1️⃣ Testing Cross-Exchange Entry")
    print("-" * 40)
    
    tracker.reset()
    
    # Entry with clear arbitrage opportunity
    entry_market_data = {
        'mexc_bid': 0.05445,
        'mexc_ask': 0.05450,
        'gateio_bid': 0.05460,  # Higher than MEXC ask - arbitrage opportunity
        'gateio_ask': 0.05465,
        'gateio_futures_bid': 0.05440,
        'gateio_futures_ask': 0.05445
    }
    
    print(f"📊 Entry market data:")
    print(f"   MEXC: {entry_market_data['mexc_bid']} / {entry_market_data['mexc_ask']}")
    print(f"   Gate.io: {entry_market_data['gateio_bid']} / {entry_market_data['gateio_ask']}")
    print(f"   Arbitrage spread: {(entry_market_data['gateio_bid'] - entry_market_data['mexc_ask']) / entry_market_data['mexc_ask'] * 10000:.1f} bps")
    
    # Open cross-exchange position
    trade_result = tracker.update_position_realtime(
        signal=Signal.ENTER,
        strategy=strategy,
        market_data=entry_market_data,
        cross_exchange=True,
        buy_exchange='MEXC_SPOT',
        sell_exchange='GATEIO_SPOT',
        position_size_usd=1000.0
    )
    
    if tracker.current_position:
        print(f"✅ Cross-exchange position opened")
        entry_data = tracker.current_position.entry_data
        print(f"   Entry data keys: {list(entry_data.keys())}")
        print(f"   Entry buy price: {entry_data.get('buy_price')}")
        print(f"   Entry sell price: {entry_data.get('sell_price')}")
        print(f"   Entry action: {entry_data.get('action')}")
        print(f"   Opportunity type: {entry_data.get('opportunity_type')}")
        print(f"   Buy exchange: {entry_data.get('buy_exchange')}")
        print(f"   Sell exchange: {entry_data.get('sell_exchange')}")
        
        # Test direct close_position call to debug calculation
        print(f"\n🔬 Direct close_position debug:")
        
        exit_market_data = {
            'mexc_bid': 0.05450,   # Prices converged
            'mexc_ask': 0.05455,
            'gateio_bid': 0.05455,
            'gateio_ask': 0.05460,
            'gateio_futures_bid': 0.05445,
            'gateio_futures_ask': 0.05450
        }
        
        print(f"   Exit market data:")
        print(f"     MEXC: {exit_market_data['mexc_bid']} / {exit_market_data['mexc_ask']}")
        print(f"     Gate.io: {exit_market_data['gateio_bid']} / {exit_market_data['gateio_ask']}")
        
        # Debug the close_position method directly
        close_result = strategy.close_position(
            position=entry_data,
            market_data=exit_market_data,
            cross_exchange=True
        )
        
        print(f"   Close result:")
        print(f"     Strategy type: {close_result.get('strategy_type')}")
        print(f"     Gross P&L: ${close_result.get('gross_pnl_usd', 0):.6f}")
        print(f"     Fees: ${close_result.get('fees_usd', 0):.6f}")
        print(f"     Net P&L: ${close_result.get('pnl_usd', 0):.6f}")
        print(f"     P&L %: {close_result.get('pnl_pct', 0):.6f}%")
        
        # Debug specific calculation values
        print(f"\n🔍 Debugging calculation details:")
        
        entry_buy_price = entry_data.get('buy_price', 0)
        entry_sell_price = entry_data.get('sell_price', 0)
        action = entry_data.get('action', '')
        opportunity_type = entry_data.get('opportunity_type', '')
        
        print(f"   Entry buy price: {entry_buy_price}")
        print(f"   Entry sell price: {entry_sell_price}")
        print(f"   Action: '{action}'")
        print(f"   Opportunity type: '{opportunity_type}'")
        
        # Check if we're hitting the early return
        mexc_bid, mexc_ask, gateio_bid, gateio_ask = strategy._extract_current_prices(exit_market_data)
        print(f"   Extracted exit prices:")
        print(f"     MEXC: {mexc_bid} / {mexc_ask}")
        print(f"     Gate.io: {gateio_bid} / {gateio_ask}")
        print(f"   All prices valid: {all([mexc_bid, mexc_ask, gateio_bid, gateio_ask])}")
        
        if not all([mexc_bid, mexc_ask, gateio_bid, gateio_ask]):
            print(f"   ❌ ISSUE: Missing price data causing early return with 0 P&L!")
            print(f"     This explains the 0% P&L issue")
        
        # Check action string matching
        if opportunity_type != 'same_exchange' and opportunity_type != 'direct_price':
            print(f"   Action string checks:")
            print(f"     'gateio_bid_spike' in action: {'gateio_bid_spike' in action}")
            print(f"     'mexc_bid_spike' in action: {'mexc_bid_spike' in action}")
            
            if 'gateio_bid_spike' not in action and 'mexc_bid_spike' not in action:
                print(f"   ❌ ISSUE: Action string doesn't match expected patterns!")
                print(f"   This causes default exit logic which might be incorrect")
        
        # Close position through tracker
        print(f"\n📊 Closing position through tracker:")
        trade_result = tracker.update_position_realtime(
            signal=Signal.EXIT,
            strategy=strategy,
            market_data=exit_market_data,
            cross_exchange=True
        )
        
        if trade_result:
            print(f"   ✅ Position closed successfully")
            print(f"   Trade P&L: ${trade_result.pnl_usd:.6f}")
            print(f"   Trade P&L %: {trade_result.pnl_pct:.6f}%")
        else:
            print(f"   ❌ No trade result returned")
    else:
        print(f"❌ Cross-exchange position not opened")
    
    print(f"\n🎯 Summary:")
    if tracker.completed_trades:
        trade = tracker.completed_trades[0]
        if trade.pnl_usd == 0:
            print(f"   ❌ Confirmed: Trade has 0 P&L")
            print(f"   This indicates a systematic issue in cross-exchange P&L calculation")
        else:
            print(f"   ✅ Trade has non-zero P&L: ${trade.pnl_usd:.6f}")
    else:
        print(f"   ❌ No completed trades found")

if __name__ == "__main__":
    asyncio.run(debug_cross_exchange_pnl())