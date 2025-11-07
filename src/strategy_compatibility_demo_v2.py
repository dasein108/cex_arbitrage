#!/usr/bin/env python3
"""
Strategy Compatibility Demo v2.0 - All-Strategy Testing with Trade Details

Tests all available strategies with detailed trade information:
- All registered strategies tested automatically
- Detailed trade count and performance metrics for each strategy
- No artificial v1/v2 separation - all strategies treated equally
- Comprehensive output showing individual strategy performance

Usage:
    python strategy_compatibility_demo_v2.py
"""

import asyncio
import pandas as pd
import numpy as np
import time
from typing import Dict, List, Any

from exchanges.structs import Symbol, AssetName
from trading.signals.backtesting.vectorized_strategy_backtester import VectorizedStrategyBacktester, \
    create_default_strategy_configs
from trading.strategies.base.strategy_signal_factory import get_available_strategy_signals
from trading.research.cross_arbitrage.arbitrage_analyzer import ArbitrageAnalyzer


async def demo_strategy_compatibility_v2():
    """
    Test all available strategies with detailed trade information.
    """
    print("🚀 STRATEGY COMPATIBILITY DEMO v2.0 - ALL-STRATEGY TESTING")
    print("=" * 80)
    print("🎯 Testing all registered strategies with detailed trade analysis")

    # Get all available strategies
    available_strategies = get_available_strategy_signals()
    print(f"📊 Discovered {len(available_strategies)} registered strategies:")
    for i, strategy in enumerate(available_strategies, 1):
        print(f"   {i}. {strategy}")

    # Create configurations for all strategies
    # strategy_configs = create_default_strategy_configs()
    strategy_configs = [        {
            'name': 'Inventory Spot V2 (Arbitrage Logic)',
            'type': 'inventory_spot_v2',
            'params': {
                'min_profit_bps': 27.0,
                'min_execution_confidence': 0.6,
                'safe_offset_percentile': 75.0,
                'position_size_usd': 1000.0,
                'lookback_periods': 200
            }
        }]
    print(f"✅ Created configurations for {len(strategy_configs)} strategies")

    # Initialize backtester (prefer without database for demo)
    try:
        print("⚠️ Using backtester without database for demo purposes")
        backtester = VectorizedStrategyBacktester()
        print("✅ Backtester initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize backtester: {e}")
        return {}

    # Test symbol
    symbol = Symbol(base=AssetName("FLK"), quote=AssetName("USDT"))
    print(f"📈 Testing symbol: {symbol}")

    # Run compact backtest
    print(f"\n🚀 Running all strategies...")
    start_time = time.perf_counter()

    try:
        results = await backtester.run_vectorized_backtest(symbol, strategy_configs, days=1)
        total_time = (time.perf_counter() - start_time) * 1000

        print(f"✅ Testing completed in {total_time:.1f}ms")

        # Detailed strategy comparison with trade information
        print(f"\n📊 DETAILED STRATEGY PERFORMANCE")
        print("=" * 90)
        print(f"{'Strategy':<35} {'Trades':<8} {'P&L%':<10} {'Win%':<8} {'Sharpe':<8} {'Status':<12}")
        print("-" * 90)

        strategy_results = []
        for name, result in results.items():
            if 'error' not in result:
                trades = result.get('total_trades', 0)
                pnl_pct = result.get('total_pnl_pct', 0)
                win_rate = result.get('win_rate', 0)
                sharpe = result.get('sharpe_ratio', 0)
                status = "🟢 PROFIT" if pnl_pct > 0 else "🔴 LOSS" if pnl_pct < 0 else "🟡 BREAK"

                print(f"{name:<35} {trades:<8} {pnl_pct:<9.2f}% {win_rate:<7.1f}% {sharpe:<8.2f} {status:<12}")
                strategy_results.append((name, result))
                
                # Show individual trade details if trades > 0
                if trades > 0:
                    signal_dist = result.get('signal_distribution', {})
                    enter_signals = signal_dist.get('ENTER', 0)
                    exit_signals = signal_dist.get('EXIT', 0)
                    hold_signals = signal_dist.get('HOLD', 0)
                    print(f"{'':>35} └─ Signals: ENTER={enter_signals}, EXIT={exit_signals}, HOLD={hold_signals}")
            else:
                error_msg = result.get('error', 'Unknown error')
                print(f"{name:<35} {'ERROR':<8} {'-':<9} {'-':<7} {'-':<8} {'❌ FAIL':<12}")
                print(f"{'':>35} └─ Error: {error_msg}")

        # Best performer analysis
        successful_results = [(name, result) for name, result in strategy_results]
        if successful_results:
            best_strategy = max(successful_results, key=lambda x: x[1].get('total_pnl_pct', -float('inf')))
            best_name, best_result = best_strategy
            
            print(f"\n🏆 BEST PERFORMER: {best_name}")
            print(f"   P&L: {best_result.get('total_pnl_pct', 0):.3f}% | Trades: {best_result.get('total_trades', 0)} | Win Rate: {best_result.get('win_rate', 0):.1f}%")
            
            # Show best strategy's trade breakdown
            if best_result.get('total_trades', 0) > 0:
                signal_dist = best_result.get('signal_distribution', {})
                print(f"   Signal breakdown: ENTER={signal_dist.get('ENTER', 0)}, EXIT={signal_dist.get('EXIT', 0)}, HOLD={signal_dist.get('HOLD', 0)}")

        # Overall performance summary
        total_strategies = len(strategy_results)
        profitable_strategies = len([r for _, r in strategy_results if r.get('total_pnl_pct', 0) > 0])
        total_trades = sum(r.get('total_trades', 0) for _, r in strategy_results)

        print(f"\n💡 OVERALL SUMMARY")
        print(f"   Total strategies tested: {total_strategies}")
        print(f"   Profitable strategies: {profitable_strategies}/{total_strategies}")
        print(f"   Total trades generated: {total_trades}")
        print(f"   Processing time: {total_time:.1f}ms for {total_strategies} strategies")
        
        if total_strategies > 0:
            avg_pnl = np.mean([r.get('total_pnl_pct', 0) for _, r in strategy_results])
            print(f"   Average P&L: {avg_pnl:.3f}%")

        return results

    except Exception as e:
        print(f"❌ Testing failed: {e}")
        import traceback
        traceback.print_exc()
        return {}


if __name__ == "__main__":
    async def main():
        # Run compact all-strategy testing
        await demo_strategy_compatibility_v2()


    asyncio.run(main())
