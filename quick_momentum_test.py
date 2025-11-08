#!/usr/bin/env python3
"""
Quick test of hedged momentum strategy with FIXED LOGIC and improved parameters

CRITICAL FIX APPLIED:
- Removed illegal spot shorting logic
- Strategy now only trades LONG momentum signals
- Proper spot market mechanics: BUY assets only
- Hedge with SHORT futures position
"""
import asyncio
import sys
import os

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from trading.signals_v2.implementation.hedged_momentum_signal import HedgedMomentumSignal, HedgedMomentumParams
from exchanges.structs.common import Symbol, AssetName

async def test_improved_parameters():
    """Test hedged momentum with more conservative parameters."""
    
    print("🚀 Quick Test: FIXED Hedged Momentum Strategy (LONG-Only Spot)")
    print("=" * 60)
    
    # Conservative parameters for LONG-only spot strategy (FIXED LOGIC)
    improved_params = HedgedMomentumParams(
        momentum_threshold=3.5,           # Higher threshold for stronger signals (was 2.5)
        momentum_lookback=25,             # Longer lookback for stability (was 20)
        rsi_oversold=25,                  # More conservative RSI bounds
        rsi_overbought=75,
        hedge_ratio=0.75,                 # Less hedged for more profit potential (was 0.9)
        position_size_usd=1000.0,
        max_position_time_minutes=90,     # Longer hold time (was 60)
        stop_loss_pct=4.0,                # Wider stop loss (was 3.0)
        take_profit_pct=2.5,              # Higher take profit (was 1.5)
        max_daily_positions=8,            # Fewer positions for quality over quantity
        volatility_adjustment=True        # Keep dynamic hedging enabled
    )
    
    print("📊 Improved Strategy Parameters:")
    print(f"   Momentum Threshold: {improved_params.momentum_threshold}%")
    print(f"   Hedge Ratio: {improved_params.hedge_ratio*100}%")
    print(f"   Position Size: ${improved_params.position_size_usd}")
    print(f"   Max Hold Time: {improved_params.max_position_time_minutes} minutes")
    print(f"   Stop Loss: {improved_params.stop_loss_pct}%")
    print(f"   Take Profit: {improved_params.take_profit_pct}%")
    
    strategy = HedgedMomentumSignal(improved_params)
    
    # Test on multiple symbols
    test_symbols = [
        Symbol(base=AssetName("AIA"), quote=AssetName("USDT")),
        Symbol(base=AssetName("ETH"), quote=AssetName("USDT"))
    ]
    
    for symbol in test_symbols:
        print(f"\n🎯 Testing {symbol.base}_{symbol.quote}")
        print("-" * 40)
        print("📈 Running 48-hour backtest with improved parameters...")
        
        try:
            metrics, trades = await strategy.run_backtest(symbol, hours=48)
            
            print(f"📊 IMPROVED RESULTS FOR {symbol.base}_{symbol.quote}:")
            print(f"   Total Trades: {metrics.total_trades}")
            print(f"   Total P&L: ${metrics.total_pnl_usd:.2f} ({metrics.total_pnl_pct:.2f}%)")
            print(f"   Win Rate: {metrics.win_rate:.1f}%")
            print(f"   Avg Trade P&L: ${metrics.avg_trade_pnl:.2f}")
            print(f"   Max Drawdown: {metrics.max_drawdown:.2f}%")
            print(f"   Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
            print(f"   Trade Frequency: {metrics.trade_freq:.1f} avg delay (min)")
            
            if trades:
                print(f"\n🔍 Recent Trades:")
                for i, trade in enumerate(trades[-3:]):  # Show last 3 trades
                    print(f"   {i+1}. {trade['direction'].upper()} {trade['hold_time']:.1f}min "
                          f"P&L: ${trade['pnl_usd']:.2f} ({trade['exit_reason']})")
                          
        except Exception as e:
            print(f"❌ Error testing {symbol.base}_{symbol.quote}: {e}")
    
    print(f"\n💡 CRITICAL STRATEGY FIXES & IMPROVEMENTS:")
    print(f"   • FIXED: Removed illegal spot shorting logic")
    print(f"   • FIXED: Strategy now only trades LONG momentum signals")
    print(f"   • FIXED: Proper spot market mechanics (BUY only)")
    print(f"   • Higher momentum threshold reduces false signals")
    print(f"   • Wider stop loss prevents premature exits")
    print(f"   • Longer hold time allows trends to develop")
    print(f"   • Lower hedge ratio increases profit potential")

if __name__ == "__main__":
    asyncio.run(test_improved_parameters())