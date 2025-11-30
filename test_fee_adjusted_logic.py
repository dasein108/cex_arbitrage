#!/usr/bin/env python3
"""
Test fee-adjusted entry logic for MEXC-Gate.io futures arbitrage strategy.

This script verifies that the updated strategy only enters trades when spreads
are sufficient to cover trading fees and generate profit.
"""

import sys
sys.path.append('src')

import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

from trading.signals_v2.implementation.mexc_gateio_futures_arbitrage_signal import (
    MexcGateioFuturesArbitrageSignal, FeeStructure
)
from trading.signals_v2.entities import ExchangeEnum
from trading.data_sources.column_utils import get_column_key

def test_fee_adjusted_logic():
    """Test that the strategy only enters profitable trades after fees."""
    print("🧪 Testing Fee-Adjusted Entry Logic")
    print("=" * 60)
    
    # Create strategy with fee-adjusted thresholds
    strategy = MexcGateioFuturesArbitrageSignal(
        min_spread_threshold=0.0015,  # 0.15% margin above fees
        entry_quantile=0.70
    )
    
    print(f"Strategy Configuration:")
    print(f"  min_spread_threshold: {strategy.min_spread_threshold:.4f} ({strategy.min_spread_threshold*100:.2f}%)")
    print(f"  entry_quantile: {strategy.entry_quantile}")
    print(f"  Combined trading fees: {strategy.fee_structure.mexc_spot_taker_fee + strategy.fee_structure.gateio_futures_taker_fee:.4f} ({(strategy.fee_structure.mexc_spot_taker_fee + strategy.fee_structure.gateio_futures_taker_fee)*100:.2f}%)")
    print()
    
    # Create test data with various spread scenarios
    timestamps = pd.date_range(
        start=datetime.now(timezone.utc) - timedelta(hours=2),
        end=datetime.now(timezone.utc),
        freq='5min'
    )
    
    # Test scenarios:
    # 1. Insufficient spread (loss) - spread < fees
    # 2. Marginal spread (small profit) - spread = fees + small margin  
    # 3. Good spread (profitable) - spread > fees + threshold
    
    test_spreads = [
        ("Insufficient (Loss)", 0.0005),      # 0.05% < 0.11% fees = guaranteed loss
        ("Marginal (Break-even)", 0.0011),    # 0.11% = exactly fees = break-even
        ("Marginal (Small profit)", 0.0013),  # 0.13% = fees + 0.02% = small profit
        ("Good (Profitable)", 0.0020),        # 0.20% = fees + 0.09% = good profit
        ("Excellent (Very profitable)", 0.0035), # 0.35% = fees + 0.24% = excellent profit
    ]
    
    for scenario_name, spread_value in test_spreads:
        print(f"📊 Testing: {scenario_name} (spread: {spread_value*100:.2f}%)")
        
        # Create realistic test data
        base_mexc_bid = 0.05000
        base_mexc_ask = base_mexc_bid + 0.00001  # 1 bps spread
        
        # Create Gate.io futures prices with the specified spread
        gateio_fut_bid = base_mexc_ask + spread_value  # This creates the arbitrage spread
        gateio_fut_ask = gateio_fut_bid + 0.00001
        
        # Verify the spread calculation
        mexc_to_fut_spread = gateio_fut_bid - base_mexc_ask
        fut_to_mexc_spread = base_mexc_bid - gateio_fut_ask
        
        print(f"  MEXC bid: {base_mexc_bid:.6f}, ask: {base_mexc_ask:.6f}")
        print(f"  Gate.io futures bid: {gateio_fut_bid:.6f}, ask: {gateio_fut_ask:.6f}")
        print(f"  MEXC to Futures spread: {mexc_to_fut_spread:.6f} ({mexc_to_fut_spread*100:.3f}%)")
        print(f"  Futures to MEXC spread: {fut_to_mexc_spread:.6f} ({fut_to_mexc_spread*100:.3f}%)")
        
        # Create DataFrame with this scenario
        test_df = pd.DataFrame({
            strategy.col_mexc_bid: [base_mexc_bid] * len(timestamps),
            strategy.col_mexc_ask: [base_mexc_ask] * len(timestamps), 
            strategy.col_gateio_fut_bid: [gateio_fut_bid] * len(timestamps),
            strategy.col_gateio_fut_ask: [gateio_fut_ask] * len(timestamps),
        }, index=timestamps)
        
        # Apply strategy signals
        df_with_signals = strategy.apply_signals(test_df)
        
        # Check results
        entry_signals = df_with_signals['entry_signal'].sum()
        total_fees = strategy.fee_structure.mexc_spot_taker_fee + strategy.fee_structure.gateio_futures_taker_fee
        net_profit = mexc_to_fut_spread - total_fees
        
        print(f"  Entry signals generated: {entry_signals}")
        print(f"  Net profit after fees: {net_profit:.6f} ({net_profit*100:.3f}%)")
        
        # Validate logic
        should_enter = net_profit > strategy.min_spread_threshold
        print(f"  Should enter trade: {should_enter}")
        print(f"  Strategy decision: {'ENTER' if entry_signals > 0 else 'NO ENTRY'}")
        
        if should_enter and entry_signals == 0:
            print(f"  ❌ ERROR: Should enter but no signals generated!")
        elif not should_enter and entry_signals > 0:
            print(f"  ❌ ERROR: Should not enter but signals generated!")
        else:
            print(f"  ✅ Correct decision")
        
        print()
    
    print("🎯 Fee-Adjusted Logic Test Summary:")
    print("  • Strategy now requires spreads > 0.26% (0.11% fees + 0.15% margin)")
    print("  • This should eliminate unprofitable trades")
    print("  • Only high-quality arbitrage opportunities will generate signals")
    print()

if __name__ == "__main__":
    test_fee_adjusted_logic()