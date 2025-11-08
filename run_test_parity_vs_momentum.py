#!/usr/bin/env python3
"""
Strategy Comparison: Price Parity Arbitrage vs Hedged Momentum

This script compares the new cross-exchange price parity strategy with 
the existing hedged momentum strategy to validate the superior approach.

Key Hypothesis:
- Buying at price parity (low risk) should outperform momentum chasing
- Mean reversion profits should be more consistent than momentum profits
- Lower transaction costs due to fewer false signals
"""

import asyncio
import sys
import os

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from trading.signals_v2.implementation.hedged_momentum_signal import HedgedMomentumSignal, HedgedMomentumParams
from trading.signals_v2.implementation.cross_exchange_parity_signal import CrossExchangeParitySignal, CrossExchangeParityParams
from exchanges.structs.common import Symbol, AssetName

async def compare_strategies():
    """Compare parity arbitrage vs momentum strategies."""
    
    print("🏁 STRATEGY COMPARISON: Parity Arbitrage vs Hedged Momentum")
    print("=" * 70)
    
    # Test symbol
    symbol = Symbol(base=AssetName("AIA"), quote=AssetName("USDT"))
    test_hours = 48  # 2 days of data
    
    # Strategy 1: Current Hedged Momentum (with improved parameters)
    momentum_params = HedgedMomentumParams(
        momentum_threshold=3.5,           # Higher threshold as suggested
        momentum_lookback=25,
        rsi_oversold=25,
        rsi_overbought=75,
        hedge_ratio=0.75,
        position_size_usd=1000.0,
        max_position_time_minutes=90,     # Longer hold time
        stop_loss_pct=4.0,
        take_profit_pct=2.5,
        max_daily_positions=8,
        volatility_adjustment=True
    )
    
    # Strategy 2: New Cross-Exchange Parity Arbitrage
    parity_params = CrossExchangeParityParams(
        parity_threshold_bps=5.0,         # Enter when spread <= 5 basis points
        lookback_periods=50,
        divergence_multiplier=2.5,        # Exit when spread > median * 2.5
        position_size_usd=1000.0,
        max_position_time_minutes=120,    # Allow more time for mean reversion
        min_hold_time_minutes=5,
        max_spread_bps=50.0,              # Emergency exit
        take_profit_bps=15.0,             # 15 basis points profit target
        max_daily_positions=5,            # Conservative
        min_volume_ratio=0.1,
        volatility_filter=True
    )
    
    print(f"🎯 Testing Symbol: {symbol.base}_{symbol.quote}")
    print(f"📅 Test Period: {test_hours} hours")
    print()
    
    # Test Strategy 1: Hedged Momentum
    print("📈 STRATEGY 1: HEDGED MOMENTUM (Improved Parameters)")
    print("-" * 50)
    print(f"   Momentum Threshold: {momentum_params.momentum_threshold}%")
    print(f"   Hedge Ratio: {momentum_params.hedge_ratio*100}%")
    print(f"   Max Hold Time: {momentum_params.max_position_time_minutes} minutes")
    print(f"   Stop Loss: {momentum_params.stop_loss_pct}%")
    print(f"   Take Profit: {momentum_params.take_profit_pct}%")
    
    try:
        momentum_strategy = HedgedMomentumSignal(momentum_params)
        momentum_metrics, momentum_trades = await momentum_strategy.run_backtest(symbol, hours=test_hours)
        
        print(f"\\n📊 MOMENTUM RESULTS:")
        print(f"   Total Trades: {momentum_metrics.total_trades}")
        print(f"   Total P&L: ${momentum_metrics.total_pnl_usd:.2f} ({momentum_metrics.total_pnl_pct:.2f}%)")
        print(f"   Win Rate: {momentum_metrics.win_rate:.1f}%")
        print(f"   Avg Trade P&L: ${momentum_metrics.avg_trade_pnl:.2f}")
        print(f"   Trade Frequency: {momentum_metrics.trade_freq:.1f} trades/day")
        
        if momentum_trades:
            avg_hold_time = sum(t["hold_time"] for t in momentum_trades) / len(momentum_trades)
            winning_trades = [t for t in momentum_trades if t["pnl_usd"] > 0]
            print(f"   Avg Hold Time: {avg_hold_time:.1f} minutes")
            print(f"   Winning Trades: {len(winning_trades)}/{len(momentum_trades)}")
            
    except Exception as e:
        print(f"❌ Momentum strategy failed: {e}")
        momentum_metrics = None
    
    # Test Strategy 2: Cross-Exchange Parity
    print(f"\\n📊 STRATEGY 2: CROSS-EXCHANGE PARITY ARBITRAGE (NEW)")
    print("-" * 50)
    print(f"   Parity Threshold: {parity_params.parity_threshold_bps} basis points")
    print(f"   Divergence Multiplier: {parity_params.divergence_multiplier}x median")
    print(f"   Take Profit: {parity_params.take_profit_bps} basis points")
    print(f"   Max Hold Time: {parity_params.max_position_time_minutes} minutes")
    print(f"   Emergency Exit: {parity_params.max_spread_bps} basis points")
    
    try:
        parity_strategy = CrossExchangeParitySignal(parity_params)
        parity_metrics, parity_trades = await parity_strategy.run_backtest(symbol, hours=test_hours)
        
        print(f"\\n📊 PARITY ARBITRAGE RESULTS:")
        print(f"   Total Trades: {parity_metrics.total_trades}")
        print(f"   Total P&L: ${parity_metrics.total_pnl_usd:.2f} ({parity_metrics.total_pnl_pct:.2f}%)")
        print(f"   Win Rate: {parity_metrics.win_rate:.1f}%")
        print(f"   Avg Trade P&L: ${parity_metrics.avg_trade_pnl:.2f}")
        print(f"   Trade Frequency: {parity_metrics.trade_freq:.1f} trades/day")
        
        if parity_trades:
            avg_hold_time = sum(t["hold_time_minutes"] for t in parity_trades) / len(parity_trades)
            winning_trades = [t for t in parity_trades if t["pnl_usd"] > 0]
            print(f"   Avg Hold Time: {avg_hold_time:.1f} minutes")
            print(f"   Winning Trades: {len(winning_trades)}/{len(parity_trades)}")
            
            # Show sample trades
            print(f"\\n🔍 Sample Parity Trades:")
            for i, trade in enumerate(parity_trades[:5]):
                print(f"   {i+1}. {trade['entry_time'].strftime('%H:%M')} -> {trade['exit_time'].strftime('%H:%M')} "
                      f"P&L: ${trade['pnl_usd']:.2f} ({trade['hold_time_minutes']:.1f}min) - {trade['exit_reason']}")
            
    except Exception as e:
        print(f"❌ Parity strategy failed: {e}")
        import traceback
        traceback.print_exc()
        parity_metrics = None
    
    # Strategy Comparison
    print(f"\\n🏆 STRATEGY COMPARISON SUMMARY")
    print("=" * 50)
    
    if momentum_metrics and parity_metrics:
        
        print(f"{'Metric':<25} {'Momentum':<15} {'Parity':<15} {'Winner'}")
        print("-" * 65)
        
        # Total P&L
        momentum_pnl = momentum_metrics.total_pnl_usd
        parity_pnl = parity_metrics.total_pnl_usd
        pnl_winner = "Parity" if parity_pnl > momentum_pnl else "Momentum"
        print(f"{'Total P&L ($)':<25} {momentum_pnl:<15.2f} {parity_pnl:<15.2f} {pnl_winner}")
        
        # Win Rate
        momentum_wr = momentum_metrics.win_rate
        parity_wr = parity_metrics.win_rate
        wr_winner = "Parity" if parity_wr > momentum_wr else "Momentum"
        print(f"{'Win Rate (%)':<25} {momentum_wr:<15.1f} {parity_wr:<15.1f} {wr_winner}")
        
        # Avg Trade P&L
        momentum_avg = momentum_metrics.avg_trade_pnl
        parity_avg = parity_metrics.avg_trade_pnl
        avg_winner = "Parity" if parity_avg > momentum_avg else "Momentum"
        print(f"{'Avg Trade P&L ($)':<25} {momentum_avg:<15.2f} {parity_avg:<15.2f} {avg_winner}")
        
        # Trade Frequency
        momentum_freq = momentum_metrics.trade_freq
        parity_freq = parity_metrics.trade_freq
        freq_winner = "Parity" if parity_freq > momentum_freq else "Momentum"
        print(f"{'Trades per Day':<25} {momentum_freq:<15.1f} {parity_freq:<15.1f} {freq_winner}")
        
        # Total Trades
        momentum_count = momentum_metrics.total_trades
        parity_count = parity_metrics.total_trades
        count_winner = "Parity" if parity_count > momentum_count else "Momentum"
        print(f"{'Total Trades':<25} {momentum_count:<15} {parity_count:<15} {count_winner}")
        
    print(f"\\n💡 STRATEGY ANALYSIS:")
    print("-" * 30)
    
    if parity_metrics:
        print(f"✅ PARITY ARBITRAGE ADVANTAGES:")
        print(f"   • Enters at fair value (low risk entry)")
        print(f"   • Profits from predictable mean reversion")
        print(f"   • Natural stop-loss when spreads widen excessively")
        print(f"   • Lower false signal rate vs momentum chasing")
        
    if momentum_metrics and momentum_metrics.total_pnl_usd < 0:
        print(f"\\n⚠️ MOMENTUM STRATEGY ISSUES:")
        print(f"   • Buying momentum often means buying at peaks")
        print(f"   • Very short hold times suggest poor signal quality")
        print(f"   • Hedging costs eat into small profits")
        print(f"   • High frequency leads to more transaction costs")
    
    print(f"\\n🎯 RECOMMENDATION:")
    if parity_metrics and momentum_metrics:
        if parity_metrics.total_pnl_usd > momentum_metrics.total_pnl_usd:
            print(f"   🏆 IMPLEMENT PARITY ARBITRAGE STRATEGY")
            print(f"   📈 Superior P&L: ${parity_metrics.total_pnl_usd:.2f} vs ${momentum_metrics.total_pnl_usd:.2f}")
            print(f"   💡 Focus on price parity entries and mean reversion exits")
        else:
            print(f"   🔄 CONTINUE OPTIMIZING MOMENTUM STRATEGY")
            print(f"   📊 Consider higher thresholds and longer hold times")
    
    print(f"\\n🛠️ NEXT STEPS:")
    print(f"   1. Test parity strategy on more symbols")
    print(f"   2. Optimize parity parameters for different market conditions")
    print(f"   3. Implement risk management and position sizing")
    print(f"   4. Deploy in paper trading environment")

async def main():
    """Run strategy comparison."""
    await compare_strategies()

if __name__ == "__main__":
    asyncio.run(main())