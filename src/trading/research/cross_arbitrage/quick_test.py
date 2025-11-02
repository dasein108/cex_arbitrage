#!/usr/bin/env python3
"""
Quick Symbol Testing Script

Ultra-simple entry point for testing arbitrage strategies on any symbol.
Just provide symbol name and data source, get instant backtest results.

Usage:
    python quick_test.py --symbol BTC_USDT
    python quick_test.py --symbol ETH_USDT --periods 2000
    python quick_test.py --help
"""

import argparse
import asyncio
import sys
from pathlib import Path
from symbol_backtester import SymbolBacktester
from exchanges.structs.enums import KlineInterval

async def main():
    """Main entry point for quick symbol testing"""
    
    parser = argparse.ArgumentParser(
        description='Quick symbol backtesting for cross-exchange arbitrage',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python quick_test.py --symbol BTC_USDT
  python quick_test.py --symbol ETH_USDT --hours 48 --timeframe 1m
  python quick_test.py --symbol QUBIC_USDT --strategy mean_reversion
  python quick_test.py --symbol DOGE_USDT --use-test-data --periods 2000
  
The script will:
1. Load real market data from exchanges (or create test data with --use-test-data)
2. Run the optimized spike capture or mean reversion strategy  
3. Show profitability analysis
4. Suggest next steps for live trading
        """
    )
    
    parser.add_argument('--symbol', type=str, default='BTC_USDT',
                       help='Symbol to test (default: BTC_USDT)')
    parser.add_argument('--hours', type=int, default=24,
                       help='Hours of real data to load (default: 24)')
    parser.add_argument('--timeframe', type=str, default='5m', choices=['1m', '5m'],
                       help='Timeframe for real data (default: 5m)')
    parser.add_argument('--use-test-data', action='store_true',
                       help='Use synthetic test data instead of real data')
    parser.add_argument('--periods', type=int, default=1000,
                       help='Number of periods for synthetic test data (default: 1000)')
    parser.add_argument('--quick', action='store_true',
                       help='Quick test mode with relaxed parameters')
    parser.add_argument('--min-diff', type=float, default=0.15,
                       help='Minimum differential threshold %% (default: 0.15)')
    parser.add_argument('--min-move', type=float, default=0.1,
                       help='Minimum single move threshold %% (default: 0.1)')
    parser.add_argument('--max-hold', type=int, default=10,
                       help='Maximum hold time in minutes (default: 10)')
    parser.add_argument('--strategy', type=str, default='spike', choices=['spike', 'mean_reversion'],
                       help='Strategy type: spike or mean_reversion (default: spike)')
    
    args = parser.parse_args()
    
    print("🚀 QUICK SYMBOL BACKTESTER")
    print("=" * 80)
    print(f"Symbol: {args.symbol}")
    if args.use_test_data:
        print(f"Data: Synthetic test data ({args.periods} periods)")
    else:
        print(f"Data: Real market data ({args.hours} hours, {args.timeframe} timeframe)")
    print(f"Strategy: {args.strategy}")
    print(f"Mode: {'Quick' if args.quick else 'Standard'}")
    print()
    
    # Adjust parameters for quick mode
    if args.quick:
        min_differential = max(args.min_diff, 0.2)  # More relaxed
        min_single_move = max(args.min_move, 0.15)  # More relaxed
        max_hold_minutes = min(args.max_hold, 8)    # Shorter
        profit_target_multiplier = 0.5              # Higher target
    else:
        min_differential = args.min_diff
        min_single_move = args.min_move 
        max_hold_minutes = args.max_hold
        profit_target_multiplier = 0.4
    
    try:
        # Initialize backtester
        backtester = SymbolBacktester()
        
        # Load data (real or test)
        if args.use_test_data:
            print("📊 Creating synthetic test data...")
            df = backtester.create_test_data(
                symbol=args.symbol, 
                periods=args.periods,
                spike_frequency=100  # Spike every 100 periods
            )
        else:
            # Convert timeframe string to KlineInterval
            timeframe = KlineInterval.MINUTE_1 if args.timeframe == '1m' else KlineInterval.MINUTE_5
            
            print(f"📊 Loading real market data ({args.hours} hours, {args.timeframe})...")
            df = await backtester.load_real_data(
                symbol_str=args.symbol,
                hours=args.hours,
                timeframe=timeframe
            )
            
        # Prepare data information for report
        data_info = {
            'symbol': args.symbol,
            'data_source': 'Real market data' if not args.use_test_data else 'Synthetic test data',
            'timeframe': args.timeframe if not args.use_test_data else 'N/A',
            'data_period_hours': args.hours if not args.use_test_data else 'N/A',
            'data_points': len(df),
            'test_mode': 'Quick' if args.quick else 'Standard'
        }
        
        # Run backtest
        print("\n🔄 Running backtest...")
        if args.strategy == 'spike':
            results = backtester.backtest_optimized_spike_capture(
                df,
                min_differential=min_differential,
                min_single_move=min_single_move,
                max_hold_minutes=max_hold_minutes,
                profit_target_multiplier=profit_target_multiplier,
                symbol=args.symbol,
                save_report=True,
                data_info=data_info
            )
        else:  # mean_reversion
            # Use mean reversion specific parameters
            entry_z_threshold = 1.5 if not args.quick else 1.0
            exit_z_threshold = 0.5 if not args.quick else 0.7
            stop_loss_pct = 0.5 if not args.quick else 0.7
            results = backtester.backtest_mean_reversion(
                df,
                entry_z_threshold=entry_z_threshold,
                exit_z_threshold=exit_z_threshold,
                stop_loss_pct=stop_loss_pct,
                max_hold_minutes=max_hold_minutes * 6,  # Mean reversion needs longer
                symbol=args.symbol,
                save_report=True,
                data_info=data_info
            )
        
        # Display comprehensive results
        print("\n" + "=" * 80)
        print("📊 BACKTEST RESULTS")
        print("=" * 80)
        
        print(f"Symbol: {results['symbol']}")
        print(f"Total Trades: {results['total_trades']}")
        
        if results['total_trades'] > 0:
            print(f"Win Rate: {results['win_rate']:.1f}%")
            print(f"Total P&L: {results['total_pnl_pct']:.3f}%")
            print(f"Average P&L per Trade: {results['avg_pnl_pct']:.3f}%")
            print(f"Best Trade: {results['max_pnl_pct']:.3f}%")
            print(f"Worst Trade: {results['min_pnl_pct']:.3f}%")
            print(f"Average Hold Time: {results['avg_hold_time']:.1f} minutes")
            print(f"Sharpe Ratio: {results['sharpe_ratio']:.2f}")
            
            # Profitability analysis
            print("\n" + "=" * 80)
            print("💰 PROFITABILITY ANALYSIS")
            print("=" * 80)
            
            if results['total_pnl_pct'] > 0:
                print("✅ STRATEGY IS PROFITABLE!")
                print(f"   Net profit after all costs: {results['total_pnl_pct']:.3f}%")
                
                # Calculate hourly return estimate
                avg_hold_time = results['avg_hold_time']
                if avg_hold_time > 0:
                    trades_per_hour = 60 / avg_hold_time
                    hourly_return = results['avg_pnl_pct'] * trades_per_hour
                    print(f"   Estimated hourly return: {hourly_return:.3f}%")
                
                # Performance rating
                if results['win_rate'] > 60 and results['sharpe_ratio'] > 1.5:
                    print("   🎉 EXCELLENT performance!")
                elif results['win_rate'] > 50 and results['sharpe_ratio'] > 1.0:
                    print("   ✅ GOOD performance")
                else:
                    print("   ⚠️ Marginal performance - consider parameter tuning")
                    
            else:
                print("❌ Strategy shows losses")
                print(f"   Net loss: {results['total_pnl_pct']:.3f}%")
                print("   🔧 Suggestions:")
                print("      - Lower the differential threshold (--min-diff)")
                print("      - Increase profit target multiplier")
                print("      - Try different symbol with more volatility")
            
            # Trade distribution analysis
            trades_df = results['trades_df']
            if len(trades_df) > 0:
                print(f"\n📈 TRADE DISTRIBUTION:")
                winning_trades = len(trades_df[trades_df['net_pnl_pct'] > 0])
                losing_trades = len(trades_df[trades_df['net_pnl_pct'] <= 0])
                
                print(f"   Winning trades: {winning_trades}")
                print(f"   Losing trades: {losing_trades}")
                
                if winning_trades > 0:
                    avg_win = trades_df[trades_df['net_pnl_pct'] > 0]['net_pnl_pct'].mean()
                    print(f"   Average win: {avg_win:.3f}%")
                
                if losing_trades > 0:
                    avg_loss = trades_df[trades_df['net_pnl_pct'] <= 0]['net_pnl_pct'].mean()
                    print(f"   Average loss: {avg_loss:.3f}%")
                
                # Exit reason analysis
                print(f"\n🚪 EXIT REASONS:")
                exit_counts = trades_df['exit_reason'].value_counts()
                for reason, count in exit_counts.items():
                    pct = (count / len(trades_df)) * 100
                    print(f"   {reason}: {count} ({pct:.1f}%)")
        else:
            print("❌ No trades generated")
            print("\n🔧 TROUBLESHOOTING:")
            print("   - Try lowering --min-diff threshold")
            print("   - Try lowering --min-move threshold") 
            if args.use_test_data:
                print("   - Increase --periods for more opportunities")
            else:
                print("   - Increase --hours for more historical data")
                print("   - Try different --timeframe (1m for more granular data)")
            print("   - Use --quick mode for relaxed parameters")
        
        # Next steps recommendations
        print("\n" + "=" * 80)
        print("🎯 NEXT STEPS")
        print("=" * 80)
        
        if results['total_trades'] > 0 and results['total_pnl_pct'] > 0:
            if args.use_test_data:
                print("1. ✅ Strategy shows promise - proceed to real data testing")
                print("2. 📊 Run with real data (remove --use-test-data flag)")
                print("3. 🔄 Test with longer periods (--hours 48 or --hours 72)")
                print("4. ⚖️ Parameter optimization with real data")
                print("5. 📝 Paper trading for validation")
                print("6. 🚀 Live trading with small position sizes")
            else:
                print("1. ✅ Strategy shows promise with real data!")
                print("2. 🔄 Test with longer periods (--hours 48 or --hours 72)")
                print("3. ⚖️ Parameter optimization with different timeframes")
                print("4. 📝 Paper trading for validation")
                print("5. 🚀 Live trading with small position sizes")
        else:
            print("1. 🔧 Parameter optimization needed")
            print("2. 🎯 Try different symbols")
            print("3. 📊 Analyze market conditions")
            print("4. 📈 Consider strategy modifications")
        
        print(f"\n💡 Parameter suggestions for {args.symbol}:")
        print(f"   Tested: min_diff={min_differential:.2f}%, min_move={min_single_move:.2f}%")
        
        if results['total_trades'] == 0:
            print(f"   Try: min_diff={min_differential*0.7:.2f}%, min_move={min_single_move*0.7:.2f}%")
        elif results['total_pnl_pct'] < 0:
            print(f"   Try: min_diff={min_differential*0.8:.2f}%, profit_target={profit_target_multiplier*1.2:.1f}x")
        
        # Data source recommendations
        if not args.use_test_data:
            print(f"\n📊 Data loading suggestions:")
            print(f"   • Try different timeframes: --timeframe 1m (more granular) or 5m (less noise)")
            print(f"   • Increase data range: --hours 48 or --hours 72 for more opportunities")
            print(f"   • For development: --use-test-data for faster testing")
        
        return results
        
    except Exception as e:
        print(f"\n❌ Error during backtesting: {e}")
        print("Please check your parameters and try again.")
        return None

if __name__ == "__main__":
    asyncio.run(main())