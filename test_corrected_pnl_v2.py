#!/usr/bin/env python3
"""
Test Script V2 - Correct Understanding of Arbitrage P&L
=======================================================

The issue is that I was misunderstanding the arbitrage mechanics. Let me clarify:

The profit should simply be the spread convergence applied to the position size.
We don't actually "lose" the $1000 - that's just the position size being traded.
"""

import pandas as pd
import numpy as np
from pathlib import Path


def test_corrected_pnl_v2():
    """Test the ACTUALLY corrected P&L calculation."""
    
    print("🧪 TESTING CORRECTED P&L CALCULATION V2")
    print("=" * 60)
    
    # Load data
    cache_dir = Path("/Users/dasein/dev/cex_arbitrage/src/trading/research/cache")
    backtest_file = cache_dir / "hedged_arbitrage_backtest_F_USDT_3d_20251019_143231.csv"
    positions_file = cache_dir / "hedged_arbitrage_positions_F_USDT_3d_20251019_143231.csv"
    
    df = pd.read_csv(backtest_file)
    positions = pd.read_csv(positions_file)
    
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    positions['entry_time'] = pd.to_datetime(positions['entry_time'])
    positions['exit_time'] = pd.to_datetime(positions['exit_time'])
    
    # Configuration
    position_size_usd = 1000.0
    fees_bps = 20.0
    
    print("🎯 CORRECT ARBITRAGE UNDERSTANDING:")
    print("1. We're capturing the spread between entry and exit")
    print("2. The position size stays constant - we're not 'losing' the $1000")
    print("3. Profit = (exit_spread - entry_spread) * position_size - fees")
    print()
    
    total_old_pnl = 0
    total_new_pnl = 0
    
    for i, pos in positions.head(5).iterrows():
        print(f"\n🔍 TRADE {i+1}:")
        
        entry_spread = pos['entry_spread'] / 100  # Convert to decimal
        exit_spread = pos['exit_spread'] / 100    # Convert to decimal
        spread_improvement = exit_spread - entry_spread
        
        # OLD calculation (reported)
        old_pnl = pos['pnl_usd']
        
        # NEW CORRECTED calculation: Spread improvement on position size
        gross_profit = spread_improvement * position_size_usd
        fee_cost = (fees_bps / 10000) * position_size_usd
        new_pnl = gross_profit - fee_cost
        
        print(f"Entry spread: {entry_spread*100:.4f}%")
        print(f"Exit spread: {exit_spread*100:.4f}%")
        print(f"Spread improvement: {spread_improvement*100:.4f}%")
        print(f"Gross profit: ${gross_profit:.2f}")
        print(f"Fee cost: ${fee_cost:.2f}")
        print(f"Net profit (corrected): ${new_pnl:.2f}")
        print(f"Old profit (reported): ${old_pnl:.2f}")
        print(f"Improvement: ${new_pnl - old_pnl:.2f}")
        
        total_old_pnl += old_pnl
        total_new_pnl += new_pnl
    
    print(f"\n🎯 SUMMARY (First 5 Trades):")
    print(f"Old total P&L: ${total_old_pnl:.2f}")
    print(f"New total P&L: ${total_new_pnl:.2f}")
    print(f"Total improvement: ${total_new_pnl - total_old_pnl:.2f}")
    
    # Calculate for all trades
    all_trades_old = positions['pnl_usd'].sum()
    all_trades_new = 0
    
    for _, pos in positions.iterrows():
        entry_spread = pos['entry_spread'] / 100
        exit_spread = pos['exit_spread'] / 100
        spread_improvement = exit_spread - entry_spread
        gross_profit = spread_improvement * position_size_usd
        fee_cost = (fees_bps / 10000) * position_size_usd
        new_pnl = gross_profit - fee_cost
        all_trades_new += new_pnl
    
    print(f"\n🎯 ALL TRADES SUMMARY:")
    print(f"Old total P&L (reported): ${all_trades_old:.2f}")
    print(f"New total P&L (corrected): ${all_trades_new:.2f}")
    print(f"Total improvement: ${all_trades_new - all_trades_old:.2f}")
    print(f"New ROI: {all_trades_new / position_size_usd * 100:.2f}%")
    
    # Calculate win rate
    winning_trades = 0
    for _, pos in positions.iterrows():
        entry_spread = pos['entry_spread'] / 100
        exit_spread = pos['exit_spread'] / 100
        spread_improvement = exit_spread - entry_spread
        gross_profit = spread_improvement * position_size_usd
        fee_cost = (fees_bps / 10000) * position_size_usd
        new_pnl = gross_profit - fee_cost
        if new_pnl > 0:
            winning_trades += 1
    
    win_rate = winning_trades / len(positions) * 100
    print(f"New win rate: {win_rate:.1f}% ({winning_trades}/{len(positions)})")
    
    print(f"\n✅ CONCLUSION:")
    if all_trades_new > 0:
        print("✅ Strategy is profitable with corrected calculation!")
        print("✅ The issue was in P&L calculation methodology, not strategy logic")
    else:
        print("❌ Strategy still shows losses even with corrected calculation")
        print("❌ May need to investigate other issues (fees, spread modeling, etc.)")


if __name__ == "__main__":
    test_corrected_pnl_v2()