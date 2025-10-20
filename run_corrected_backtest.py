#!/usr/bin/env python3
"""
Run Corrected Hedged Cross-Arbitrage Backtest
=============================================

This script runs the corrected backtest to verify that the P&L calculation fix
resolves the negative returns issue.
"""

import asyncio
import sys
import os
from datetime import datetime

# Add src to path
sys.path.insert(0, '/Users/dasein/dev/cex_arbitrage/src')

from trading.research.hedged_cross_arbitrage_backtest import HedgedCrossArbitrageBacktest, BacktestConfig


async def run_corrected_backtest():
    """Run the backtest with corrected P&L calculation."""
    
    print("🚀 RUNNING CORRECTED HEDGED CROSS-ARBITRAGE BACKTEST")
    print("=" * 80)
    
    # Create config (same as original test)
    config = BacktestConfig(
        symbol="F_USDT",
        days=3,
        min_transfer_time_minutes=10,
        position_size_usd=1000,
        max_concurrent_positions=2,
        fees_bps=20.0,
        spread_bps=5.0
    )
    
    print(f"📊 Configuration:")
    print(f"  Symbol: {config.symbol}")
    print(f"  Period: {config.days} days")
    print(f"  Position Size: ${config.position_size_usd:,.0f}")
    print(f"  Transfer Delay: {config.min_transfer_time_minutes} minutes")
    print(f"  Fees: {config.fees_bps} bps")
    print(f"  Max Concurrent Positions: {config.max_concurrent_positions}")
    
    # Create and run backtest
    backtest = HedgedCrossArbitrageBacktest(config, cache_dir="cache_corrected")
    
    try:
        print(f"\n🔄 Running backtest...")
        results = await backtest.run_backtest()
        
        print(f"\n📊 CORRECTED BACKTEST RESULTS:")
        print("=" * 80)
        print(backtest.format_report(results))
        
        # Compare with expected results
        performance = results['performance']
        
        print(f"\n🎯 VALIDATION CHECKS:")
        print("=" * 40)
        
        # Check win rate
        if performance.win_rate > 80:
            print(f"✅ Win Rate: {performance.win_rate:.1f}% (GOOD - above 80%)")
        else:
            print(f"⚠️  Win Rate: {performance.win_rate:.1f}% (concerning - below 80%)")
        
        # Check total P&L
        if performance.total_pnl > 100:
            print(f"✅ Total P&L: ${performance.total_pnl:.2f} (GOOD - positive and substantial)")
        elif performance.total_pnl > 0:
            print(f"✅ Total P&L: ${performance.total_pnl:.2f} (GOOD - positive)")
        else:
            print(f"❌ Total P&L: ${performance.total_pnl:.2f} (BAD - still negative)")
        
        # Check ROI
        roi = (performance.total_pnl / config.position_size_usd) * 100
        if roi > 10:
            print(f"✅ ROI: {roi:.2f}% (EXCELLENT - above 10%)")
        elif roi > 5:
            print(f"✅ ROI: {roi:.2f}% (GOOD - above 5%)")
        elif roi > 0:
            print(f"✅ ROI: {roi:.2f}% (ACCEPTABLE - positive)")
        else:
            print(f"❌ ROI: {roi:.2f}% (BAD - negative)")
        
        # Check average P&L per trade
        if performance.avg_pnl_per_trade > 5:
            print(f"✅ Avg P&L per Trade: ${performance.avg_pnl_per_trade:.2f} (GOOD - above $5)")
        elif performance.avg_pnl_per_trade > 2:
            print(f"✅ Avg P&L per Trade: ${performance.avg_pnl_per_trade:.2f} (ACCEPTABLE - above fees)")
        else:
            print(f"⚠️  Avg P&L per Trade: ${performance.avg_pnl_per_trade:.2f} (concerning)")
        
        # Check Sharpe ratio
        if performance.sharpe_ratio > 1:
            print(f"✅ Sharpe Ratio: {performance.sharpe_ratio:.2f} (GOOD - above 1.0)")
        elif performance.sharpe_ratio > 0:
            print(f"✅ Sharpe Ratio: {performance.sharpe_ratio:.2f} (ACCEPTABLE - positive)")
        else:
            print(f"❌ Sharpe Ratio: {performance.sharpe_ratio:.2f} (BAD - negative)")
        
        print(f"\n🔍 COMPARISON WITH ORIGINAL RESULTS:")
        print("=" * 40)
        print(f"Original Total P&L: $-66.61")
        print(f"Corrected Total P&L: ${performance.total_pnl:.2f}")
        print(f"Improvement: ${performance.total_pnl + 66.61:.2f}")
        print(f"Original ROI: -6.66%")
        print(f"Corrected ROI: {roi:.2f}%")
        print(f"Original Win Rate: 0.0%")
        print(f"Corrected Win Rate: {performance.win_rate:.1f}%")
        
        # Overall assessment
        print(f"\n🎯 OVERALL ASSESSMENT:")
        print("=" * 40)
        if performance.total_pnl > 100 and performance.win_rate > 80:
            print("🎉 EXCELLENT: Strategy is highly profitable with corrected calculation!")
            print("🎉 The fix completely resolved the negative returns issue.")
        elif performance.total_pnl > 50 and performance.win_rate > 70:
            print("✅ GOOD: Strategy is profitable with reasonable performance.")
            print("✅ The fix successfully resolved the main issues.")
        elif performance.total_pnl > 0:
            print("✅ ACCEPTABLE: Strategy is profitable but may need optimization.")
            print("✅ The fix resolved the negative returns.")
        else:
            print("❌ ISSUE: Strategy still shows poor performance even after fix.")
            print("❌ Additional investigation may be needed.")
        
        # Create visualizations
        print(f"\n📊 Creating performance visualizations...")
        plots = backtest.create_visualizations(results, save_plots=True)
        print(f"✅ Visualizations saved to cache_corrected/ directory")
        
        return results
        
    except Exception as e:
        print(f"❌ Backtest failed: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    results = asyncio.run(run_corrected_backtest())