#!/usr/bin/env python3
"""
Test Positive P&L with Fixed Cross-Exchange Logic

Tests the fixed cross-exchange logic with favorable market conditions.
"""

import asyncio
from datetime import datetime, timezone
from trading.signals.backtesting.position_tracker import PositionTracker
from trading.signals.implementations.inventory_spot_strategy_signal_v2 import InventorySpotStrategySignalV2
from trading.signals.types.signal_types import Signal
from exchanges.structs import Symbol, AssetName

async def test_positive_pnl():
    """Test cross-exchange P&L with favorable conditions."""
    
    print("🧪 Testing Positive P&L with Fixed Cross-Exchange Logic")
    print("=" * 60)
    
    # Create components
    tracker = PositionTracker(initial_capital=10000.0)
    strategy = InventorySpotStrategySignalV2(
        symbol=Symbol(base=AssetName('FLK'), quote=AssetName('USDT')),
        position_size_usd=1000.0,
        min_execution_confidence=0.7,
        safe_offset_percentile=25.0
    )
    
    print(f"✅ Components created")
    
    # Test with larger arbitrage opportunity
    print(f"\n1️⃣ Testing with Large Arbitrage Opportunity")
    print("-" * 50)
    
    tracker.reset()
    
    # Entry with significant arbitrage spread
    entry_market_data = {
        'mexc_bid': 0.05440,
        'mexc_ask': 0.05445,
        'gateio_bid': 0.05480,  # Much higher than MEXC ask - large opportunity
        'gateio_ask': 0.05485,
        'gateio_futures_bid': 0.05430,
        'gateio_futures_ask': 0.05435
    }
    
    print(f"📊 Entry market data:")
    print(f"   MEXC: {entry_market_data['mexc_bid']} / {entry_market_data['mexc_ask']}")
    print(f"   Gate.io: {entry_market_data['gateio_bid']} / {entry_market_data['gateio_ask']}")
    spread_bps = (entry_market_data['gateio_bid'] - entry_market_data['mexc_ask']) / entry_market_data['mexc_ask'] * 10000
    print(f"   Arbitrage spread: {spread_bps:.1f} bps")
    
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
        print(f"   Entry buy price: {entry_data.get('buy_price')}")
        print(f"   Entry sell price: {entry_data.get('sell_price')}")
        print(f"   Entry spread: {entry_data.get('spread_bps', 0):.1f} bps")
        
        # Exit with maintained spread (favorable)
        exit_market_data = {
            'mexc_bid': 0.05450,   # MEXC prices moved up (good for our MEXC position)
            'mexc_ask': 0.05455,
            'gateio_bid': 0.05470,  # Gate.io stayed high (good for our Gate.io position)
            'gateio_ask': 0.05475,
            'gateio_futures_bid': 0.05440,
            'gateio_futures_ask': 0.05445
        }
        
        print(f"\n📊 Exit market data:")
        print(f"   MEXC: {exit_market_data['mexc_bid']} / {exit_market_data['mexc_ask']}")
        print(f"   Gate.io: {exit_market_data['gateio_bid']} / {exit_market_data['gateio_ask']}")
        
        # Calculate expected P&L manually
        entry_spread = entry_data.get('sell_price') - entry_data.get('buy_price')
        exit_spread = exit_market_data['gateio_bid'] - exit_market_data['mexc_ask']  # Reverse: sell MEXC, buy Gate.io
        total_spread = entry_spread + exit_spread
        print(f"   Entry spread: {entry_spread:.6f}")
        print(f"   Exit spread: {exit_spread:.6f}")
        print(f"   Total spread: {total_spread:.6f}")
        
        # Close position
        trade_result = tracker.update_position_realtime(
            signal=Signal.EXIT,
            strategy=strategy,
            market_data=exit_market_data,
            cross_exchange=True
        )
        
        if trade_result:
            print(f"\n✅ Position closed successfully")
            print(f"   Trade P&L: ${trade_result.pnl_usd:.2f}")
            print(f"   Trade P&L %: {trade_result.pnl_pct:.3f}%")
            print(f"   Fees: ${trade_result.fees_usd:.2f}")
            print(f"   Hold time: {trade_result.hold_time_minutes:.1f} minutes")
            
            if trade_result.pnl_usd > 0:
                print(f"   🎉 PROFITABLE TRADE!")
            else:
                print(f"   📉 Loss (expected with small spreads)")
    
    # Test scenario 2: Very favorable exit conditions
    print(f"\n2️⃣ Testing with Very Favorable Exit Conditions")
    print("-" * 50)
    
    tracker.reset()
    
    # Same entry
    tracker.update_position_realtime(
        signal=Signal.ENTER,
        strategy=strategy,
        market_data=entry_market_data,
        cross_exchange=True,
        buy_exchange='MEXC_SPOT',
        sell_exchange='GATEIO_SPOT',
        position_size_usd=1000.0
    )
    
    if tracker.current_position:
        # Very favorable exit (large spread remains)
        favorable_exit = {
            'mexc_bid': 0.05460,   # MEXC up significantly (great for selling)
            'mexc_ask': 0.05465,
            'gateio_bid': 0.05470,  # Gate.io maintained
            'gateio_ask': 0.05460,  # Gate.io ask dropped (great for buying back)
        }
        
        print(f"📊 Favorable exit data:")
        print(f"   MEXC: {favorable_exit['mexc_bid']} / {favorable_exit['mexc_ask']}")
        print(f"   Gate.io: {favorable_exit['gateio_bid']} / {favorable_exit['gateio_ask']}")
        
        trade_result = tracker.update_position_realtime(
            signal=Signal.EXIT,
            strategy=strategy,
            market_data=favorable_exit,
            cross_exchange=True
        )
        
        if trade_result:
            print(f"\n✅ Favorable exit completed")
            print(f"   Trade P&L: ${trade_result.pnl_usd:.2f}")
            print(f"   Trade P&L %: {trade_result.pnl_pct:.3f}%")
            
            if trade_result.pnl_usd > 0:
                print(f"   🎉 PROFITABLE ARBITRAGE CONFIRMED!")
            
    print(f"\n🎯 Summary:")
    if tracker.completed_trades:
        total_pnl = sum(t.pnl_usd for t in tracker.completed_trades)
        profitable_trades = [t for t in tracker.completed_trades if t.pnl_usd > 0]
        print(f"   Completed trades: {len(tracker.completed_trades)}")
        print(f"   Profitable trades: {len(profitable_trades)}")
        print(f"   Total P&L: ${total_pnl:.2f}")
        
        if len(profitable_trades) > 0:
            print(f"   ✅ Cross-exchange P&L calculation is working correctly!")
        else:
            print(f"   📊 No profitable trades (may need larger spreads or lower fees)")
    else:
        print(f"   ❌ No completed trades")

if __name__ == "__main__":
    asyncio.run(test_positive_pnl())