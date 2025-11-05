#!/usr/bin/env python3
"""
Debug P&L Calculation Issues

Investigates why inventory spot strategy shows 0% P&L for 6 trades.
"""

import asyncio
from datetime import datetime, timezone
from trading.signals.backtesting.position_tracker import PositionTracker
from trading.signals.implementations.inventory_spot_strategy_signal_v2 import InventorySpotStrategySignalV2
from trading.signals.types.signal_types import Signal
from exchanges.structs import Symbol, AssetName

async def debug_pnl_calculation():
    """Debug P&L calculation step by step."""
    
    print("🔍 Debugging P&L Calculation Issues")
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
    print(f"   Strategy: {strategy.strategy_type}")
    print(f"   Position size: ${strategy.position_size_usd}")
    
    # Test scenario 1: Same-exchange trading with realistic price movement
    print(f"\n1️⃣ Testing Same-Exchange Trading P&L")
    print("-" * 40)
    
    tracker.reset()
    
    # Entry with clear spread
    entry_market_data = {
        'gateio_bid': 0.05450,  # Sell at bid
        'gateio_ask': 0.05455,  # Buy at ask
        'mexc_bid': 0.05445,
        'mexc_ask': 0.05450
    }
    
    print(f"📊 Entry market data:")
    print(f"   Gate.io: {entry_market_data['gateio_bid']} / {entry_market_data['gateio_ask']}")
    print(f"   Spread: {(entry_market_data['gateio_ask'] - entry_market_data['gateio_bid']) / entry_market_data['gateio_bid'] * 10000:.1f} bps")
    
    # Open position
    trade_result = tracker.update_position_realtime(
        signal=Signal.ENTER,
        strategy=strategy,
        market_data=entry_market_data,
        same_exchange=True,
        exchange='GATEIO_SPOT',
        rotating_amount=1.5,
        position_size_usd=1000.0
    )
    
    if tracker.current_position:
        print(f"✅ Position opened successfully")
        entry_data = tracker.current_position.entry_data
        print(f"   Entry buy price: {entry_data.get('buy_price')}")
        print(f"   Entry sell price: {entry_data.get('sell_price')}")
        print(f"   Entry spread: {entry_data.get('spread_bps', 0):.1f} bps")
        print(f"   Rotating amount: {entry_data.get('rotating_amount')}")
        
        # Exit with favorable price movement
        exit_market_data = {
            'gateio_bid': 0.05465,  # Higher bid (favorable for sells)
            'gateio_ask': 0.05470,  # Higher ask  
            'mexc_bid': 0.05460,
            'mexc_ask': 0.05465
        }
        
        print(f"\n📊 Exit market data:")
        print(f"   Gate.io: {exit_market_data['gateio_bid']} / {exit_market_data['gateio_ask']}")
        print(f"   Price movement: +{(exit_market_data['gateio_bid'] - entry_market_data['gateio_bid']) / entry_market_data['gateio_bid'] * 100:.3f}%")
        
        # Debug: Call close_position directly to see calculation details
        print(f"\n🔬 Direct close_position calculation:")
        close_result = strategy.close_position(
            position=entry_data,
            market_data=exit_market_data,
            same_exchange=True
        )
        
        print(f"   Close result keys: {list(close_result.keys())}")
        print(f"   Gross P&L: ${close_result.get('gross_pnl_usd', 0):.4f}")
        print(f"   Fees: ${close_result.get('fees_usd', 0):.4f}")
        print(f"   Net P&L: ${close_result.get('pnl_usd', 0):.4f}")
        print(f"   P&L %: {close_result.get('pnl_pct', 0):.4f}%")
        
        # Close position through tracker
        trade_result = tracker.update_position_realtime(
            signal=Signal.EXIT,
            strategy=strategy,
            market_data=exit_market_data,
            same_exchange=True
        )
        
        if trade_result:
            print(f"\n✅ Position closed through tracker")
            print(f"   Trade P&L: ${trade_result.pnl_usd:.4f}")
            print(f"   Trade P&L %: {trade_result.pnl_pct:.4f}%")
            print(f"   Hold time: {trade_result.hold_time_minutes:.1f} minutes")
        else:
            print(f"\n❌ No trade result returned from tracker")
    else:
        print(f"❌ Position not opened")
    
    # Test scenario 2: Direct manual P&L calculation
    print(f"\n2️⃣ Manual P&L Verification")
    print("-" * 40)
    
    entry_buy = 0.05455 * 1.5  # Gate.io ask * rotating_amount
    entry_sell = 0.05450 * 0.5  # Gate.io bid * (2.0 - rotating_amount)
    
    exit_buy = 0.05470 * 1.5   # New prices
    exit_sell = 0.05465 * 0.5
    
    entry_spread = entry_sell - entry_buy
    exit_spread = exit_sell - exit_buy
    spread_change = exit_spread - entry_spread
    
    position_size = 1000.0
    avg_price = (entry_buy + entry_sell) / 2
    units = position_size / avg_price
    gross_pnl = spread_change * units
    
    print(f"📊 Manual calculation:")
    print(f"   Entry: buy={entry_buy:.6f}, sell={entry_sell:.6f}, spread={entry_spread:.6f}")
    print(f"   Exit:  buy={exit_buy:.6f}, sell={exit_sell:.6f}, spread={exit_spread:.6f}")
    print(f"   Spread change: {spread_change:.6f}")
    print(f"   Units: {units:.2f}")
    print(f"   Gross P&L: ${gross_pnl:.4f}")
    
    # Test scenario 3: Check for edge cases
    print(f"\n3️⃣ Checking for Edge Cases")
    print("-" * 40)
    
    if entry_buy == 0 or entry_sell == 0:
        print(f"❌ ISSUE: Zero entry prices detected")
        print(f"   Entry buy: {entry_buy}")
        print(f"   Entry sell: {entry_sell}")
    
    if abs(spread_change) < 0.000001:
        print(f"❌ ISSUE: Spread change too small: {spread_change}")
    
    if units == 0:
        print(f"❌ ISSUE: Zero units calculated")
    
    print(f"\n🎯 Analysis Summary:")
    if tracker.completed_trades:
        total_pnl = sum(t.pnl_usd for t in tracker.completed_trades)
        print(f"   Completed trades: {len(tracker.completed_trades)}")
        print(f"   Total P&L: ${total_pnl:.4f}")
        print(f"   First trade details:")
        first_trade = tracker.completed_trades[0]
        print(f"     P&L USD: ${first_trade.pnl_usd:.6f}")
        print(f"     P&L %: {first_trade.pnl_pct:.6f}%")
        print(f"     Fees: ${first_trade.fees_usd:.6f}")
    else:
        print(f"   No completed trades found")

if __name__ == "__main__":
    asyncio.run(debug_pnl_calculation())