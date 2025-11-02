#!/usr/bin/env python3
"""
Simple All Strategies Runner

A simplified version that directly tests all strategies with real market data.
Supports both real market data and synthetic test data for development.
"""

import pandas as pd
import numpy as np
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import sys
import argparse

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.append(str(project_root))

from symbol_backtester import SymbolBacktester
from exchanges.structs.enums import KlineInterval

def create_test_data(periods: int = 1000, add_spikes: bool = True) -> pd.DataFrame:
    """
    Create realistic test data for strategy testing
    
    Args:
        periods: Number of time periods
        add_spikes: Whether to add directional spikes for testing
    """
    
    print(f"📊 Creating test data: {periods} periods, spikes: {add_spikes}")
    
    # Create timestamps
    timestamps = pd.date_range(start='2024-01-01', periods=periods, freq='1min')
    
    # Base prices with realistic movements
    mexc_base = 100.0
    gateio_base = 100.0
    
    mexc_prices = []
    gateio_prices = []
    
    for i in range(periods):
        # Add random walk with some correlation
        mexc_change = np.random.normal(0, 0.1)
        gateio_change = mexc_change * 0.8 + np.random.normal(0, 0.05)  # 80% correlation + noise
        
        # Add directional spikes periodically
        if add_spikes and i % 200 == 50:  # Every ~200 periods, add a spike
            spike_magnitude = np.random.uniform(0.5, 1.5)  # 0.5% to 1.5% spike
            if np.random.random() > 0.5:
                mexc_change += spike_magnitude  # MEXC spikes up more
                gateio_change += spike_magnitude * 0.6  # Gate.io follows less
            else:
                gateio_change += spike_magnitude  # Gate.io spikes up more
                mexc_change += spike_magnitude * 0.6  # MEXC follows less
        
        mexc_price = mexc_base + mexc_change
        gateio_price = gateio_base + gateio_change
        
        mexc_prices.append(mexc_price)
        gateio_prices.append(gateio_price)
        
        # Update base for next iteration
        mexc_base = mexc_price
        gateio_base = gateio_price
    
    # Create DataFrame
    df = pd.DataFrame({
        'timestamp': timestamps,
        'mexc_close': mexc_prices,
        'gateio_close': gateio_prices,
        'gateio_futures_close': [p * 0.999 for p in gateio_prices],  # Futures slightly lower
    })
    
    # Add derived columns
    df['mexc_vs_gateio_pct'] = ((df['mexc_close'] - df['gateio_close']) / df['gateio_close']) * 100
    df['gateio_vs_futures_pct'] = ((df['gateio_close'] - df['gateio_futures_close']) / df['gateio_futures_close']) * 100
    
    # Add technical indicators required by advanced strategies
    spread_window = 20
    df['spread_mean'] = df['mexc_vs_gateio_pct'].rolling(window=spread_window).mean()
    df['spread_std'] = df['mexc_vs_gateio_pct'].rolling(window=spread_window).std()
    df['spread_z_score'] = (df['mexc_vs_gateio_pct'] - df['spread_mean']) / df['spread_std']
    
    # Add spread velocity (rate of change)
    df['spread_velocity'] = df['mexc_vs_gateio_pct'].diff()
    
    # Add volume ratio (mock data since we don't have real volume)
    df['vol_ratio'] = np.random.uniform(0.8, 1.2, len(df))  # Mock volume ratio
    
    # Set column name attributes for compatibility
    df.attrs['mexc_c_col'] = 'mexc_close'
    df.attrs['gateio_c_col'] = 'gateio_close'
    df.attrs['gateio_futures_c_col'] = 'gateio_futures_close'
    
    print(f"✅ Test data created: {len(df)} rows")
    print(f"   Price range MEXC: ${df['mexc_close'].min():.2f} - ${df['mexc_close'].max():.2f}")
    print(f"   Price range Gate.io: ${df['gateio_close'].min():.2f} - ${df['gateio_close'].max():.2f}")
    print(f"   Max spread: {df['mexc_vs_gateio_pct'].abs().max():.3f}%")
    
    return df

async def run_optimized_spike_capture_tests(symbol: str = "BTC_USDT", 
                                           hours: int = 24, 
                                           timeframe: KlineInterval = KlineInterval.MINUTE_5,
                                           use_test_data: bool = False,
                                           periods: int = 1000, 
                                           quick_mode: bool = False):
    """Run both spike capture and mean reversion strategies with different parameter combinations"""
    
    print("=" * 80)
    print("🚀 SPIKE CAPTURE & MEAN REVERSION STRATEGY TESTING")
    print("=" * 80)
    print(f"Symbol: {symbol}")
    if use_test_data:
        print(f"Data: Synthetic test data ({periods} periods)")
    else:
        timeframe_str = "5m" if timeframe == KlineInterval.MINUTE_5 else "1m"
        print(f"Data: Real market data ({hours} hours, {timeframe_str} timeframe)")
    print(f"Mode: {'Quick' if quick_mode else 'Complete'}")
    print()
    
    # Initialize backtester
    backtester = SymbolBacktester()
    
    # Load data (real or test)
    if use_test_data:
        print("📊 Creating synthetic test data...")
        df = create_test_data(periods=periods, add_spikes=True)
    else:
        print(f"📊 Loading real market data ({hours} hours, {timeframe.value})...")
        df = await backtester.load_real_data(
            symbol_str=symbol,
            hours=hours,
            timeframe=timeframe
        )
        
        if df is None or len(df) == 0:
            print("❌ Failed to load real data, falling back to synthetic test data...")
            df = create_test_data(periods=periods, add_spikes=True)
        else:
            print(f"✅ Loaded {len(df)} data points from real market data")
    
    results = {}
    
    print("\n" + "=" * 80)
    print("📈 TESTING OPTIMIZED STRATEGIES")
    print("=" * 80)
    
    # Test both strategies with optimized parameters for the symbol
    configs = []
    
    # Add spike capture strategy (optimized parameters)
    spike_config = {
        'name': 'Optimized Spike Capture',
        'strategy': 'spike',
        'min_differential': 0.2 if quick_mode else 0.15,
        'min_single_move': 0.15 if quick_mode else 0.1,
        'max_hold_minutes': 8 if quick_mode else 10,
        'profit_target_multiplier': 0.4,
        'momentum_exit_threshold': 1.5
    }
    configs.append(spike_config)
    
    # Add mean reversion strategy (optimized parameters)
    mean_reversion_config = {
        'name': 'Optimized Mean Reversion',
        'strategy': 'mean_reversion',
        'entry_z_threshold': 1.5,
        'exit_z_threshold': 0.5,
        'stop_loss_pct': 0.5,
        'max_hold_minutes': 120
    }
    configs.append(mean_reversion_config)
    
    for i, config in enumerate(configs, 1):
        print(f"\n{i}️⃣ {config['name']} for {symbol}...")
        try:
            if config['strategy'] == 'spike':
                result = backtester.backtest_optimized_spike_capture(
                    df,
                    min_differential=config['min_differential'],
                    min_single_move=config['min_single_move'],
                    max_hold_minutes=config['max_hold_minutes'],
                    profit_target_multiplier=config['profit_target_multiplier'],
                    momentum_exit_threshold=config['momentum_exit_threshold'],
                    symbol=symbol
                )
            else:  # mean_reversion
                result = backtester.backtest_mean_reversion(
                    df,
                    entry_z_threshold=config['entry_z_threshold'],
                    exit_z_threshold=config['exit_z_threshold'],
                    stop_loss_pct=config['stop_loss_pct'],
                    max_hold_minutes=config['max_hold_minutes'],
                    symbol=symbol
                )
            
            results[config['name'].lower().replace(' ', '_')] = result
            print(f"   ✅ Trades: {result.get('total_trades', 0)}, "
                  f"P&L: {result.get('total_pnl_pct', 0):.3f}%, "
                  f"Win Rate: {result.get('win_rate', 0):.1f}%")
        except Exception as e:
            print(f"   ❌ Error: {e}")
            results[config['name'].lower().replace(' ', '_')] = {'total_trades': 0, 'error': str(e)}
    
    # Summary
    print("\n" + "=" * 80)
    print(f"📊 STRATEGY COMPARISON FOR {symbol}")
    print("=" * 80)
    print(f"{'Strategy':<25} {'Trades':<10} {'Win%':<10} {'Total P&L%':<15} {'Avg Hold(min)':<15}")
    print("-" * 80)
    
    for name, result in results.items():
        if 'error' in result:
            print(f"{name:<25} {'ERROR':<10} {'-':<10} {'-':<15} {'-':<15}")
        elif result.get('total_trades', 0) == 0:
            print(f"{name:<25} {'0':<10} {'-':<10} {'0.000':<15} {'-':<15}")
        else:
            trades = result.get('total_trades', 0)
            win_rate = result.get('win_rate', 0)
            total_pnl = result.get('total_pnl_pct', 0)
            avg_hold = result.get('avg_hold_time', 0)
            
            print(f"{name:<25} {trades:<10} {win_rate:<10.1f} {total_pnl:<15.3f} {avg_hold:<15.1f}")
    
    # Find best strategy
    print("\n" + "=" * 80)
    print(f"🏆 BEST STRATEGY FOR {symbol}")
    print("=" * 80)
    
    best_strategy = None
    best_pnl = -float('inf')
    
    for name, result in results.items():
        if 'error' not in result and result.get('total_trades', 0) > 0:
            pnl = result.get('total_pnl_pct', 0)
            if pnl > best_pnl:
                best_pnl = pnl
                best_strategy = name
    
    if best_strategy:
        print(f"🥇 Best Strategy: {best_strategy}")
        print(f"   Total P&L: {best_pnl:.3f}%")
        print(f"   Trades: {results[best_strategy].get('total_trades', 0)}")
        print(f"   Win Rate: {results[best_strategy].get('win_rate', 0):.1f}%")
        
        if best_pnl > 0:
            print(f"   ✅ PROFITABLE!")
            
            # Calculate potential returns
            avg_hold = results[best_strategy].get('avg_hold_time', 0)
            if avg_hold > 0:
                trades_per_hour = 60 / avg_hold
                hourly_return = results[best_strategy].get('avg_pnl_pct', 0) * trades_per_hour
                print(f"   💰 Estimated hourly return: {hourly_return:.3f}%")
        else:
            print(f"   ❌ Unprofitable - consider parameter optimization")
    else:
        print("❌ No strategies executed successfully")
    
    # Strategy insights
    print(f"\n💡 INSIGHTS FOR {symbol}:")
    
    profitable_strategies = [name for name, result in results.items() 
                           if 'error' not in result and result.get('total_pnl_pct', 0) > 0]
    
    if profitable_strategies:
        print(f"   🎯 Profitable strategies: {', '.join(profitable_strategies)}")
        if 'optimized_mean_reversion' in profitable_strategies:
            print(f"   📈 Mean reversion works well for {symbol}")
        if 'optimized_spike_capture' in profitable_strategies:
            print(f"   ⚡ Spike capture works well for {symbol}")
    else:
        print(f"   ⚠️ No profitable strategies found for {symbol}")
        print(f"   💡 Try different timeframes or parameter optimization")
    
    execution_count = len([r for r in results.values() if 'error' not in r and r.get('total_trades', 0) > 0])
    print(f"   📊 Strategies with trades: {execution_count}/{len(results)}")
    
    return results

async def main():
    """Main entry point"""
    
    parser = argparse.ArgumentParser(description='Cross-exchange arbitrage strategy parameter tester')
    parser.add_argument('--symbol', type=str, default='BTC_USDT',
                       help='Symbol to test (default: BTC_USDT)')
    parser.add_argument('--hours', type=int, default=24,
                       help='Hours of real data to load (default: 24)')
    parser.add_argument('--timeframe', type=str, default='5m', choices=['1m', '5m'],
                       help='Timeframe for real data (default: 5m)')
    parser.add_argument('--use-test-data', action='store_true',
                       help='Use synthetic test data instead of real data')
    parser.add_argument('--periods', type=int, default=1000,
                       help='Number of synthetic test periods (default: 1000)')
    parser.add_argument('--quick', action='store_true',
                       help='Quick test mode')
    
    args = parser.parse_args()
    
    print("🚀 Cross-Exchange Arbitrage Strategy Tester")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Convert timeframe string to KlineInterval
    timeframe = KlineInterval.MINUTE_1 if args.timeframe == '1m' else KlineInterval.MINUTE_5
    
    results = await run_optimized_spike_capture_tests(
        symbol=args.symbol,
        hours=args.hours,
        timeframe=timeframe,
        use_test_data=args.use_test_data,
        periods=args.periods,
        quick_mode=args.quick
    )
    
    print("\n" + "=" * 80)
    print("🎯 NEXT STEPS")
    print("=" * 80)
    print("1. Focus on configurations with positive P&L")
    print("2. The optimized spike capture strategy solves the 'MEXC +1%, Gate.io +0.5%' issue")
    if args.use_test_data:
        print("3. Test with real data (remove --use-test-data flag)")
        print("4. Use longer periods (--hours 48 or --hours 72) for more comprehensive testing")
    else:
        print("3. Test with longer time periods (--hours 48 or --hours 72)")
        print("4. Try different timeframes (--timeframe 1m for more granular data)")
    print("5. Use quick_test.py for individual symbol testing")
    
    return results

if __name__ == "__main__":
    asyncio.run(main())