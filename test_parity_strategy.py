#!/usr/bin/env python3
"""
Quick Test: Cross-Exchange Price Parity Arbitrage Strategy

This script tests the new parity arbitrage strategy which:
1. Buys when MEXC and Gate.io futures prices are near equal (parity)
2. Waits for price divergence between exchanges
3. Exits when spread reaches target (mean reversion profit)

Key Innovation: Buy at fair value, profit from temporary divergences.
"""

import asyncio
import sys
import os

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from trading.signals_v2.implementation.cross_exchange_parity_signal import CrossExchangeParitySignal, CrossExchangeParityParams
from exchanges.structs.common import Symbol, AssetName

async def test_parity_strategy():
    """Test the cross-exchange parity arbitrage strategy."""
    
    print("🎯 TESTING: Cross-Exchange Price Parity Arbitrage Strategy")
    print("=" * 65)
    print()
    print("💡 STRATEGY CONCEPT:")
    print("   • Enter when MEXC spot ≈ Gate.io futures price (low risk)")
    print("   • Wait for temporary price divergence between exchanges")
    print("   • Exit when spread widens enough (mean reversion profit)")
    print("   • Natural risk management via price parity entry")
    print()
    
    # Conservative parameters for new strategy
    params = CrossExchangeParityParams(
        parity_threshold_bps=8.0,         # Enter when spread <= 8 basis points (tighter than 5)
        lookback_periods=60,              # 1 hour lookback for median spread
        divergence_multiplier=2.0,        # Exit when spread > median * 2.0 
        position_size_usd=1000.0,
        max_position_time_minutes=180,    # 3 hours max (allow time for reversion)
        min_hold_time_minutes=10,         # Hold at least 10 minutes
        max_spread_bps=40.0,              # Emergency exit if spread > 40bps
        take_profit_bps=12.0,             # Take profit at 12 basis points
        max_daily_positions=3,            # Very conservative (quality over quantity)
        min_volume_ratio=0.05,            # Require some volume balance
        volatility_filter=True
    )
    
    print("📊 STRATEGY PARAMETERS:")
    print(f"   Entry Condition: Price spread ≤ {params.parity_threshold_bps} basis points")
    print(f"   Exit Condition: Spread ≥ median × {params.divergence_multiplier} or {params.take_profit_bps}bps")
    print(f"   Position Size: ${params.position_size_usd}")
    print(f"   Max Hold Time: {params.max_position_time_minutes} minutes")
    print(f"   Emergency Exit: {params.max_spread_bps} basis points")
    print(f"   Daily Position Limit: {params.max_daily_positions} trades")
    print()
    
    strategy = CrossExchangeParitySignal(params)
    
    # Test on multiple symbols to validate approach
    test_symbols = [
        Symbol(base=AssetName("AIA"), quote=AssetName("USDT")),
        Symbol(base=AssetName("ETH"), quote=AssetName("USDT")),
    ]
    
    for symbol in test_symbols:
        print(f"🎯 Testing {symbol.base}_{symbol.quote}")
        print("-" * 40)
        
        try:
            print("📥 Loading market data and calculating spread analytics...")
            
            # Test with 3 days of data for better statistics
            metrics, trades = await strategy.run_backtest(symbol, hours=72)
            
            print(f"\\n📊 RESULTS FOR {symbol.base}_{symbol.quote}:")
            print(f"   Total Trades: {metrics.total_trades}")
            print(f"   Total P&L: ${metrics.total_pnl_usd:.2f} ({metrics.total_pnl_pct:.2f}%)")
            print(f"   Win Rate: {metrics.win_rate:.1f}%")
            print(f"   Avg Trade P&L: ${metrics.avg_trade_pnl:.2f}")
            print(f"   Trade Frequency: {metrics.trade_freq:.1f} trades/day")
            
            if trades:
                # Calculate additional metrics
                winning_trades = [t for t in trades if t["pnl_usd"] > 0]
                losing_trades = [t for t in trades if t["pnl_usd"] < 0]
                avg_hold_time = sum(t["hold_time_minutes"] for t in trades) / len(trades)
                
                print(f"   Avg Hold Time: {avg_hold_time:.1f} minutes")
                print(f"   Winning Trades: {len(winning_trades)}")
                print(f"   Losing Trades: {len(losing_trades)}")
                
                if winning_trades:
                    avg_win = sum(t["pnl_usd"] for t in winning_trades) / len(winning_trades)
                    print(f"   Avg Win: ${avg_win:.2f}")
                
                if losing_trades:
                    avg_loss = sum(t["pnl_usd"] for t in losing_trades) / len(losing_trades)
                    print(f"   Avg Loss: ${avg_loss:.2f}")
                
                # Show trade details
                print(f"\\n🔍 Trade Details:")
                for i, trade in enumerate(trades):
                    entry_time = trade["entry_time"].strftime("%m-%d %H:%M")
                    exit_time = trade["exit_time"].strftime("%m-%d %H:%M")
                    pnl_sign = "+" if trade["pnl_usd"] >= 0 else ""
                    print(f"   {i+1}. {entry_time} -> {exit_time}: "
                          f"{pnl_sign}${trade['pnl_usd']:.2f} ({trade['hold_time_minutes']:.0f}min)")
                    print(f"      Exit: {trade['exit_reason']}")
                    
                # Show spread analytics
                if hasattr(strategy, 'median_spread_bps') and strategy.median_spread_bps > 0:
                    print(f"\\n📈 Spread Analytics:")
                    print(f"   Median Spread: {strategy.median_spread_bps:.2f} basis points")
                    print(f"   Entry Threshold: {params.parity_threshold_bps} basis points")
                    exit_target = max(strategy.median_spread_bps * params.divergence_multiplier, params.take_profit_bps)
                    print(f"   Exit Target: {exit_target:.2f} basis points")
                    
        except Exception as e:
            print(f"❌ Error testing {symbol.base}_{symbol.quote}: {e}")
            import traceback
            traceback.print_exc()
        
        print()
    
    print("💡 STRATEGY ANALYSIS:")
    print("-" * 30)
    print("✅ ADVANTAGES OF PARITY ARBITRAGE:")
    print("   • Low-risk entry: Buy when prices are fair/equal")
    print("   • Predictable profits: Mean reversion is more reliable than momentum")
    print("   • Natural stop-loss: Emergency exit when spreads become extreme")
    print("   • Lower transaction costs: Fewer false signals vs momentum chasing")
    print("   • Market-neutral: Benefits from exchange inefficiencies")
    print()
    print("🎯 WHY THIS BEATS MOMENTUM STRATEGIES:")
    print("   • Momentum strategies buy at peaks (high risk)")
    print("   • Parity strategies buy at equilibrium (low risk)")
    print("   • Mean reversion is more predictable than trend continuation")
    print("   • Price parity provides natural entry discipline")
    print()
    print("🛠️ OPTIMIZATION OPPORTUNITIES:")
    print("   • Adjust parity threshold based on symbol volatility")
    print("   • Dynamic exit targets based on market conditions")
    print("   • Volume-weighted entry timing")
    print("   • Multi-timeframe spread analysis")

if __name__ == "__main__":
    asyncio.run(test_parity_strategy())