#!/usr/bin/env python3
"""
Debug Vectorized Backtesting P&L Issues

Investigates why vectorized backtesting shows 0% P&L for strategies.
"""

import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from trading.signals.backtesting.position_tracker import PositionTracker
from trading.signals.implementations.inventory_spot_strategy_signal_v2 import InventorySpotStrategySignalV2
from trading.signals.types.signal_types import Signal
from exchanges.structs import Symbol, AssetName

async def debug_vectorized_pnl():
    """Debug vectorized backtesting P&L calculation."""
    
    print("🔍 Debugging Vectorized Backtesting P&L Issues")
    print("=" * 60)
    
    # Create strategy
    strategy = InventorySpotStrategySignalV2(
        symbol=Symbol(base=AssetName('FLK'), quote=AssetName('USDT')),
        position_size_usd=1000.0,
        min_execution_confidence=0.7,
        safe_offset_percentile=25.0
    )
    
    print(f"✅ Strategy created: {strategy.strategy_type}")
    
    # Create realistic historical data with opportunities
    print(f"\n1️⃣ Creating Test Historical Data")
    print("-" * 40)
    
    dates = pd.date_range(start='2024-01-01 10:00:00', periods=20, freq='5min')
    
    # Create data with clear arbitrage opportunities
    base_price = 0.0545
    
    historical_data = pd.DataFrame({
        'timestamp': dates,
        # Create scenarios with clear spreads
        'mexc_bid': [base_price - 0.0001 + i * 0.00001 for i in range(20)],
        'mexc_ask': [base_price + 0.0001 + i * 0.00001 for i in range(20)],
        'gateio_bid': [base_price - 0.00005 + i * 0.00001 for i in range(20)],
        'gateio_ask': [base_price + 0.00005 + i * 0.00001 for i in range(20)],
        'gateio_futures_bid': [base_price - 0.00015 + i * 0.00001 for i in range(20)],
        'gateio_futures_ask': [base_price + 0.00015 + i * 0.00001 for i in range(20)],
    })
    
    # Add signals manually - create entry/exit pairs
    historical_data['signal'] = Signal.HOLD.value
    historical_data.loc[2, 'signal'] = Signal.ENTER.value  # First entry
    historical_data.loc[5, 'signal'] = Signal.EXIT.value   # First exit
    historical_data.loc[8, 'signal'] = Signal.ENTER.value  # Second entry
    historical_data.loc[12, 'signal'] = Signal.EXIT.value  # Second exit
    historical_data.loc[15, 'signal'] = Signal.ENTER.value # Third entry
    historical_data.loc[18, 'signal'] = Signal.EXIT.value  # Third exit
    
    historical_data.set_index('timestamp', inplace=True)
    
    print(f"✅ Historical data created: {len(historical_data)} rows")
    print(f"   Price range: {historical_data['gateio_bid'].min():.6f} - {historical_data['gateio_ask'].max():.6f}")
    print(f"   Signals: ENTER={sum(historical_data['signal'] == Signal.ENTER.value)}, EXIT={sum(historical_data['signal'] == Signal.EXIT.value)}")
    
    # Test vectorized position tracking
    print(f"\n2️⃣ Testing Vectorized Position Tracking")
    print("-" * 40)
    
    tracker = PositionTracker(initial_capital=10000.0)
    
    positions, trades = tracker.track_positions_vectorized(
        df=historical_data,
        strategy=strategy,
        same_exchange=True,
        exchange='GATEIO_SPOT',
        rotating_amount=1.5,
        position_size_usd=1000.0
    )
    
    print(f"✅ Vectorized tracking completed")
    print(f"   Positions created: {len(positions)}")
    print(f"   Trades completed: {len(trades)}")
    
    if positions:
        print(f"   First position strategy: {positions[0].strategy_type}")
        print(f"   First position entry data keys: {len(positions[0].entry_data)}")
    
    if trades:
        print(f"\n📊 Trade Analysis:")
        total_pnl = sum(t.pnl_usd for t in trades)
        avg_pnl = total_pnl / len(trades)
        winning_trades = [t for t in trades if t.pnl_usd > 0]
        losing_trades = [t for t in trades if t.pnl_usd < 0]
        zero_trades = [t for t in trades if t.pnl_usd == 0]
        
        print(f"   Total P&L: ${total_pnl:.4f}")
        print(f"   Average P&L: ${avg_pnl:.4f}")
        print(f"   Winning trades: {len(winning_trades)}")
        print(f"   Losing trades: {len(losing_trades)}")
        print(f"   Zero P&L trades: {len(zero_trades)} ⚠️")
        
        print(f"\n🔍 Individual Trade Details:")
        for i, trade in enumerate(trades):
            print(f"   Trade {i+1}: ${trade.pnl_usd:.4f} ({trade.pnl_pct:.3f}%) - "
                  f"Hold: {trade.hold_time_minutes:.1f}min - Fees: ${trade.fees_usd:.2f}")
            
            # Check entry/exit data
            if hasattr(trade, 'entry_data') and hasattr(trade, 'exit_data'):
                entry_buy = trade.entry_data.get('buy_price', 0)
                entry_sell = trade.entry_data.get('sell_price', 0)
                exit_buy = trade.exit_data.get('exit_buy_price', 0)
                exit_sell = trade.exit_data.get('exit_sell_price', 0)
                print(f"     Entry: buy={entry_buy:.6f}, sell={entry_sell:.6f}")
                print(f"     Exit:  buy={exit_buy:.6f}, sell={exit_sell:.6f}")
        
        # Check for systematic issues
        if len(zero_trades) == len(trades):
            print(f"\n❌ CRITICAL ISSUE: All trades have 0 P&L!")
            print(f"   This suggests a systematic calculation problem")
            
            # Debug first trade in detail
            if trades:
                first_trade = trades[0]
                print(f"\n🔬 Detailed Analysis of First Trade:")
                print(f"   Strategy type: {first_trade.strategy_type}")
                print(f"   Entry time: {first_trade.entry_time}")
                print(f"   Exit time: {first_trade.exit_time}")
                print(f"   Quantity: {first_trade.quantity}")
                print(f"   Entry data keys: {list(first_trade.entry_data.keys()) if first_trade.entry_data else 'None'}")
                print(f"   Exit data keys: {list(first_trade.exit_data.keys()) if first_trade.exit_data else 'None'}")
    else:
        print(f"\n❌ No trades generated!")
        print(f"   This suggests signal detection or position tracking issues")
        
        # Check signal detection
        signal_changes = historical_data['signal'].ne(historical_data['signal'].shift())
        signal_points = historical_data[signal_changes]
        print(f"   Signal changes detected: {len(signal_points)}")
        print(f"   Signal change points:")
        for idx, row in signal_points.iterrows():
            signal_name = {Signal.ENTER.value: 'ENTER', Signal.EXIT.value: 'EXIT', Signal.HOLD.value: 'HOLD'}.get(row['signal'], 'UNKNOWN')
            print(f"     {idx}: {signal_name}")
    
    # Test with different parameters
    print(f"\n3️⃣ Testing with Different Parameters")
    print("-" * 40)
    
    tracker2 = PositionTracker(initial_capital=10000.0)
    
    positions2, trades2 = tracker2.track_positions_vectorized(
        df=historical_data,
        strategy=strategy,
        cross_exchange=True,  # Try cross-exchange instead
        buy_exchange='GATEIO_SPOT',
        sell_exchange='MEXC_SPOT',
        position_size_usd=1000.0
    )
    
    print(f"✅ Cross-exchange test completed")
    print(f"   Positions: {len(positions2)}")
    print(f"   Trades: {len(trades2)}")
    
    if trades2:
        total_pnl2 = sum(t.pnl_usd for t in trades2)
        print(f"   Total P&L: ${total_pnl2:.4f}")
        zero_trades2 = [t for t in trades2 if t.pnl_usd == 0]
        print(f"   Zero P&L trades: {len(zero_trades2)}")

if __name__ == "__main__":
    asyncio.run(debug_vectorized_pnl())