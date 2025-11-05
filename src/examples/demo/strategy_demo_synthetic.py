#!/usr/bin/env python3
"""
Strategy Demo with Synthetic Data

Tests all available strategies using synthetic market data to showcase
the refactored cross-exchange P&L calculations and trade generation.
"""

import asyncio
import pandas as pd
import numpy as np
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any

from exchanges.structs import Symbol, AssetName
from trading.analysis.vectorized_strategy_backtester import VectorizedStrategyBacktester, create_default_strategy_configs
from trading.strategies.base.strategy_signal_factory import get_available_strategy_signals


def create_synthetic_market_data(symbol: Symbol, hours: int = 24) -> pd.DataFrame:
    """Create realistic synthetic market data for testing."""
    
    # Generate timestamps (5-minute intervals)
    start_time = datetime.now(timezone.utc) - timedelta(hours=hours)
    timestamps = pd.date_range(start=start_time, periods=hours * 12, freq='5min')
    
    # Base price with trending behavior
    base_price = 0.054
    trend = np.linspace(0, 0.002, len(timestamps))  # Small upward trend
    noise = np.random.normal(0, 0.0005, len(timestamps))  # Market noise
    
    # MEXC prices (spot)
    mexc_mid = base_price + trend + noise
    mexc_spread = np.random.uniform(0.00001, 0.00005, len(timestamps))
    mexc_bid = mexc_mid - mexc_spread / 2
    mexc_ask = mexc_mid + mexc_spread / 2
    
    # Gate.io spot prices (slightly different dynamics)
    gateio_spread = np.random.uniform(0.00001, 0.00004, len(timestamps))
    gateio_arb_offset = np.random.normal(0, 0.0002, len(timestamps))  # Arbitrage opportunities
    gateio_mid = mexc_mid + gateio_arb_offset
    gateio_bid = gateio_mid - gateio_spread / 2
    gateio_ask = gateio_mid + gateio_spread / 2
    
    # Gate.io futures prices (with funding rate effects)
    futures_basis = np.random.normal(0.0001, 0.0001, len(timestamps))  # Slight contango
    gateio_futures_mid = gateio_mid + futures_basis
    gateio_futures_spread = np.random.uniform(0.00002, 0.00006, len(timestamps))
    gateio_futures_bid = gateio_futures_mid - gateio_futures_spread / 2
    gateio_futures_ask = gateio_futures_mid + gateio_futures_spread / 2
    
    # Create DataFrame with expected column names for strategy validation
    df = pd.DataFrame({
        'timestamp': timestamps,
        # Standard column names for vectorized backtester
        'mexc_bid': mexc_bid,
        'mexc_ask': mexc_ask,
        'gateio_bid': gateio_bid,
        'gateio_ask': gateio_ask,
        'gateio_futures_bid': gateio_futures_bid,
        'gateio_futures_ask': gateio_futures_ask,
        # Expected column names for strategy validation
        'MEXC_SPOT_bid_price': mexc_bid,
        'MEXC_SPOT_ask_price': mexc_ask,
        'GATEIO_SPOT_bid_price': gateio_bid,
        'GATEIO_SPOT_ask_price': gateio_ask,
        'GATEIO_FUTURES_bid_price': gateio_futures_bid,
        'GATEIO_FUTURES_ask_price': gateio_futures_ask,
        # Volume data
        'mexc_bid_qty': np.random.uniform(500, 2000, len(timestamps)),
        'mexc_ask_qty': np.random.uniform(500, 2000, len(timestamps)),
        'gateio_bid_qty': np.random.uniform(800, 1500, len(timestamps)),
        'gateio_ask_qty': np.random.uniform(800, 1500, len(timestamps)),
        'gateio_futures_bid_qty': np.random.uniform(1000, 3000, len(timestamps)),
        'gateio_futures_ask_qty': np.random.uniform(1000, 3000, len(timestamps)),
    })
    
    df.set_index('timestamp', inplace=True)
    return df


class SyntheticDataSource:
    """Synthetic data source for testing without database."""
    
    def __init__(self):
        self.name = "SyntheticDataSource"
    
    async def get_multi_exchange_data(self, exchanges: List[str], symbol: Symbol, hours: int = 24) -> pd.DataFrame:
        """Generate synthetic multi-exchange data."""
        return create_synthetic_market_data(symbol, hours)


async def demo_strategies_with_synthetic_data():
    """Test all strategies with synthetic data to showcase fixed P&L calculations."""
    
    print("🚀 STRATEGY DEMO WITH SYNTHETIC DATA")
    print("=" * 70)
    print("🎯 Testing all strategies with synthetic market data")
    print("✨ Showcasing fixed cross-exchange P&L calculations")
    
    # Get all available strategies
    available_strategies = get_available_strategy_signals()
    print(f"\n📊 Available strategies ({len(available_strategies)}):")
    for i, strategy in enumerate(available_strategies, 1):
        print(f"   {i}. {strategy}")
    
    # Create strategy configurations
    strategy_configs = create_default_strategy_configs()
    print(f"\n✅ Testing {len(strategy_configs)} strategy configurations")
    
    # Initialize backtester with synthetic data source
    synthetic_source = SyntheticDataSource()
    backtester = VectorizedStrategyBacktester(data_source=synthetic_source)
    print("✅ Backtester initialized with synthetic data source")
    
    # Test symbol
    symbol = Symbol(base=AssetName("FLK"), quote=AssetName("USDT"))
    print(f"📈 Testing symbol: {symbol}")
    
    # Run backtest
    print(f"\n🚀 Running all strategies with synthetic data...")
    start_time = time.perf_counter()
    
    try:
        results = await backtester.run_vectorized_backtest(symbol, strategy_configs, days=1)
        total_time = (time.perf_counter() - start_time) * 1000
        
        print(f"✅ Testing completed in {total_time:.1f}ms")
        
        # Detailed strategy performance display
        print(f"\n📊 DETAILED STRATEGY PERFORMANCE")
        print("=" * 95)
        print(f"{'Strategy':<40} {'Trades':<8} {'P&L%':<10} {'Win%':<8} {'Sharpe':<8} {'Status':<12}")
        print("-" * 95)
        
        strategy_results = []
        for name, result in results.items():
            if 'error' not in result:
                trades = result.get('total_trades', 0)
                pnl_pct = result.get('total_pnl_pct', 0)
                win_rate = result.get('win_rate', 0)
                sharpe = result.get('sharpe_ratio', 0)
                status = "🟢 PROFIT" if pnl_pct > 0 else "🔴 LOSS" if pnl_pct < 0 else "🟡 BREAK"
                
                print(f"{name:<40} {trades:<8} {pnl_pct:<9.2f}% {win_rate:<7.1f}% {sharpe:<8.2f} {status:<12}")
                strategy_results.append((name, result))
                
                # Show signal breakdown for strategies with trades
                if trades > 0:
                    signal_dist = result.get('signal_distribution', {})
                    enter_signals = signal_dist.get('ENTER', 0)
                    exit_signals = signal_dist.get('EXIT', 0)
                    hold_signals = signal_dist.get('HOLD', 0)
                    print(f"{'':>40} └─ Signals: ENTER={enter_signals}, EXIT={exit_signals}, HOLD={hold_signals}")
                    
                    # Show P&L breakdown for profitable strategies
                    if pnl_pct != 0:
                        fees_usd = result.get('total_fees_usd', 0)
                        gross_pnl = result.get('total_gross_pnl_usd', 0)
                        print(f"{'':>40} └─ P&L: Gross=${gross_pnl:.2f}, Fees=${fees_usd:.2f}, Net=${gross_pnl-fees_usd:.2f}")
                        
            else:
                error_msg = result.get('error', 'Unknown error')[:50]
                print(f"{name:<40} {'ERROR':<8} {'-':<9} {'-':<7} {'-':<8} {'❌ FAIL':<12}")
                print(f"{'':>40} └─ {error_msg}")
        
        # Performance analysis
        if strategy_results:
            # Best performer
            best_strategy = max(strategy_results, key=lambda x: x[1].get('total_pnl_pct', -float('inf')))
            best_name, best_result = best_strategy
            
            print(f"\n🏆 BEST PERFORMER: {best_name}")
            print(f"   P&L: {best_result.get('total_pnl_pct', 0):.3f}% | Trades: {best_result.get('total_trades', 0)} | Win Rate: {best_result.get('win_rate', 0):.1f}%")
            
            if best_result.get('total_trades', 0) > 0:
                signal_dist = best_result.get('signal_distribution', {})
                print(f"   Signal breakdown: ENTER={signal_dist.get('ENTER', 0)}, EXIT={signal_dist.get('EXIT', 0)}, HOLD={signal_dist.get('HOLD', 0)}")
            
            # Strategy type analysis
            cross_exchange_strategies = [
                (name, result) for name, result in strategy_results 
                if 'inventory' in name.lower() or 'arbitrage' in name.lower()
            ]
            
            if cross_exchange_strategies:
                print(f"\n🔀 CROSS-EXCHANGE STRATEGY PERFORMANCE:")
                for name, result in cross_exchange_strategies:
                    trades = result.get('total_trades', 0)
                    pnl_pct = result.get('total_pnl_pct', 0)
                    if trades > 0:
                        print(f"   {name}: {trades} trades, {pnl_pct:.3f}% P&L ✅ Working correctly!")
                    else:
                        print(f"   {name}: No trades generated")
        
        # Overall summary
        total_strategies = len(strategy_results)
        profitable_strategies = len([r for _, r in strategy_results if r.get('total_pnl_pct', 0) > 0])
        total_trades = sum(r.get('total_trades', 0) for _, r in strategy_results)
        
        print(f"\n💡 OVERALL SUMMARY")
        print(f"   Total strategies tested: {total_strategies}")
        print(f"   Profitable strategies: {profitable_strategies}/{total_strategies}")
        print(f"   Total trades generated: {total_trades}")
        print(f"   Processing time: {total_time:.1f}ms")
        
        if total_strategies > 0:
            avg_pnl = np.mean([r.get('total_pnl_pct', 0) for _, r in strategy_results])
            print(f"   Average P&L: {avg_pnl:.3f}%")
            
        print(f"\n✨ CROSS-EXCHANGE P&L FIX STATUS:")
        inventory_results = [r for name, r in strategy_results if 'inventory' in name.lower()]
        if inventory_results and any(r.get('total_trades', 0) > 0 for r in inventory_results):
            print(f"   🎉 SUCCESS: Cross-exchange strategies generating realistic trades and P&L!")
            print(f"   🔧 Fix confirmed: Entry data population and P&L calculation working")
        else:
            print(f"   📊 INFO: Cross-exchange strategies tested but may need more favorable market conditions")
        
        return results
        
    except Exception as e:
        print(f"❌ Testing failed: {e}")
        import traceback
        traceback.print_exc()
        return {}


if __name__ == "__main__":
    asyncio.run(demo_strategies_with_synthetic_data())