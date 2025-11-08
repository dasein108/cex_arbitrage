#!/usr/bin/env python3
"""
Hedged Momentum Strategy Backtesting Script

This script tests the hedged momentum strategy that combines spot momentum
trading with futures hedging for risk management.
"""

import asyncio
import sys

# Add src to path
sys.path.append('src')

from trading.signals_v2.implementation.hedged_momentum_signal import HedgedMomentumSignal, HedgedMomentumParams
from exchanges.structs import Symbol, AssetName
from infrastructure.logging import get_logger

logger = get_logger("hedged_momentum_test")

async def run_hedged_momentum_backtest():
    """Run comprehensive backtest of hedged momentum strategy."""
    
    print("🚀 Hedged Momentum Strategy Backtest")
    print("=" * 60)
    
    # Strategy parameters
    params = HedgedMomentumParams(
        # Momentum detection
        momentum_lookback=20,
        momentum_threshold=2.5,      # Require 2.5% momentum for entry
        rsi_oversold=25,
        rsi_overbought=75,
        
        # Position management
        position_size_usd=1000.0,
        hedge_ratio=0.85,            # 85% hedged (15% net exposure)
        max_position_time_minutes=45, # Max 45 minute holds
        
        # Risk management
        stop_loss_pct=2.5,           # 2.5% stop loss
        take_profit_pct=1.2,         # 1.2% take profit
        max_daily_positions=8,       # Max 8 positions per day
        
        # Dynamic hedging
        volatility_adjustment=True,
        rehedge_threshold=0.2
    )
    
    print(f"📊 Strategy Parameters:")
    print(f"   Momentum Threshold: {params.momentum_threshold}%")
    print(f"   Hedge Ratio: {params.hedge_ratio*100}%")
    print(f"   Position Size: ${params.position_size_usd}")
    print(f"   Max Hold Time: {params.max_position_time_minutes} minutes")
    print(f"   Stop Loss: {params.stop_loss_pct}%")
    print(f"   Take Profit: {params.take_profit_pct}%")
    print()
    
    # Test symbols
    test_symbols = [
        Symbol(base=AssetName('AIA'), quote=AssetName('USDT')),
        Symbol(base=AssetName('ETH'), quote=AssetName('USDT')),
    ]
    
    for symbol in test_symbols:
        print(f"🎯 Testing {symbol}")
        print("-" * 40)
        
        try:
            # Create strategy instance
            strategy = HedgedMomentumSignal(params)
            
            # Run 48-hour backtest
            print(f"📈 Running 48-hour backtest...")
            metrics, trades = await strategy.run_backtest(symbol, hours=48)
            
            # Display results
            print(f"📊 RESULTS FOR {symbol}:")
            print(f"   Total Trades: {len(trades)}")
            print(f"   Total P&L: ${metrics.total_pnl_usd:.2f} ({metrics.total_pnl_pct:.2f}%)")
            print(f"   Win Rate: {metrics.win_rate:.1f}%")
            print(f"   Avg Trade P&L: ${metrics.avg_trade_pnl:.2f}")
            print(f"   Max Drawdown: {metrics.max_drawdown:.2f}%")
            print(f"   Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
            print(f"   Trade Frequency: {metrics.trade_freq:.1f} trades/day")
            print()
            
            # Show individual trades
            if trades:
                print(f"🔍 TRADE DETAILS:")
                print(f"{'#':<3} {'Entry':<16} {'Dir':<5} {'Hold':<6} {'P&L$':<8} {'P&L%':<7} {'Exit Reason':<20}")
                print("-" * 75)
                
                for i, trade in enumerate(trades[:10], 1):  # Show first 10 trades
                    entry_time = trade["entry_time"].strftime("%m-%d %H:%M")
                    pnl_color = "+" if trade["pnl_usd"] > 0 else ""
                    
                    print(f"{i:<3} {entry_time:<16} {trade['direction']:<5} "
                          f"{trade['hold_time']:<6.1f} {pnl_color}{trade['pnl_usd']:<8.2f} "
                          f"{pnl_color}{trade['pnl_pct']:<7.2f} {trade['exit_reason'][:20]:<20}")
                
                if len(trades) > 10:
                    print(f"... and {len(trades) - 10} more trades")
                print()
                
        except Exception as e:
            print(f"❌ Error testing {symbol}: {e}")
            import traceback
            traceback.print_exc()
            print()
            
    print("✅ Hedged momentum backtesting completed!")
    
    # Strategy analysis
    print(f"\n💡 STRATEGY ANALYSIS:")
    print(f"This hedged momentum strategy aims to:")
    print(f"   1. Capture momentum moves with technical indicators")
    print(f"   2. Hedge {params.hedge_ratio*100}% of exposure via futures")
    print(f"   3. Limit risk with stops and time-based exits")
    print(f"   4. Adapt hedge ratios based on volatility")
    print()
    
    print(f"Expected characteristics:")
    print(f"   • Lower volatility than pure momentum (due to hedging)")
    print(f"   • Consistent smaller profits rather than large swings")
    print(f"   • Protection against major adverse moves")
    print(f"   • Profit from basis spread changes + momentum timing")

async def test_signal_generation():
    """Test signal generation in isolation."""
    
    print("\n🧪 SIGNAL GENERATION TEST")
    print("=" * 40)
    
    params = HedgedMomentumParams()
    strategy = HedgedMomentumSignal(params)
    symbol = Symbol(base=AssetName('AIA'), quote=AssetName('USDT'))
    
    # Update market data
    await strategy.update_market_data(symbol, hours=6)
    
    # Check momentum signals
    print("📊 Current momentum signals:")
    for exchange, signal in strategy.momentum_signals.items():
        print(f"   {exchange.value}: {signal['signal']} "
              f"(strength: {signal['strength']:.2f}, "
              f"momentum: {signal.get('momentum', 0):.2f}%)")
    
    # Test entry signal generation
    entry_signal = strategy.generate_entry_signal(symbol)
    
    if entry_signal:
        print(f"\n🎯 ENTRY SIGNAL GENERATED:")
        print(f"   Direction: {entry_signal['direction']}")
        print(f"   Spot Exchange: {entry_signal['spot_exchange'].value}")
        print(f"   Futures Exchange: {entry_signal['futures_exchange'].value}")
        print(f"   Spot Price: ${entry_signal['spot_price']:.4f}")
        print(f"   Futures Price: ${entry_signal['futures_price']:.4f}")
        print(f"   Hedge Ratio: {entry_signal['hedge_ratio']:.1%}")
        print(f"   Reason: {entry_signal['reason']}")
    else:
        print("\n⏸️  No entry signal generated at current time")
        
    print("\n✅ Signal generation test completed!")

if __name__ == "__main__":
    async def main():
        await test_signal_generation()
        await run_hedged_momentum_backtest()
    
    asyncio.run(main())