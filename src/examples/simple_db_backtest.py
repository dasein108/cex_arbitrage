#!/usr/bin/env python3
"""
Simple Database Backtest Runner

Quick way to run backtest using database snapshots with existing infrastructure.
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from trading.research.cross_arbitrage.hedged_cross_arbitrage_backtest import BacktestConfig


async def run_simple_db_backtest():
    """Run backtest using database snapshots"""
    
    print("🚀 Simple Database Snapshot Backtest")
    print("=" * 50)
    
    # Import the enhanced backtest class
    from examples.backtest_with_db_snapshots import DatabaseSnapshotBacktest
    
    # Configuration
    config = BacktestConfig(
        symbol="F_USDT",
        days=2,                    # Start with 2 days
        min_transfer_time_minutes=10,
        position_size_usd=1000,
        max_concurrent_positions=1,
        fees_bps=20.0              # 0.2% total fees
    )
    
    print(f"📊 Configuration:")
    print(f"  Symbol: {config.symbol}")
    print(f"  Period: {config.days} days")
    print(f"  Position Size: ${config.position_size_usd}")
    print(f"  Fees: {config.fees_bps} bps")
    
    # Create and run backtest
    backtest = DatabaseSnapshotBacktest(config)
    
    try:
        results = await backtest.run_backtest()
        
        # Print results
        print("\n" + "="*60)
        print("📊 BACKTEST RESULTS")
        print("="*60)
        
        perf = results['performance']
        print(f"💰 Total P&L: ${perf.total_pnl:.2f}")
        print(f"📈 Total Trades: {perf.total_trades}")
        print(f"🎯 Win Rate: {perf.win_rate:.1f}% ({perf.winning_trades}W / {perf.losing_trades}L)")
        print(f"📊 Avg P&L per Trade: ${perf.avg_pnl_per_trade:.2f}")
        print(f"⚠️  Max Drawdown: ${perf.max_drawdown:.2f}")
        print(f"📈 Sharpe Ratio: {perf.sharpe_ratio:.2f}")
        
        # Analysis
        if perf.total_pnl > 0:
            roi_pct = (perf.total_pnl / config.position_size_usd) * 100
            print(f"\n🎉 PROFITABLE STRATEGY!")
            print(f"📈 Total ROI: {roi_pct:.2f}%")
            print(f"📅 Daily Average: ${perf.total_pnl / config.days:.2f}")
        else:
            print(f"\n⚠️  STRATEGY SHOWS LOSSES")
            print(f"🔍 This indicates either:")
            print(f"   • Spread thresholds need adjustment")
            print(f"   • Market conditions changed")
            print(f"   • Fee assumptions are wrong")
        
        print(f"\n📁 Detailed results saved in: {backtest.cache_dir}")
        
        return results
        
    except Exception as e:
        print(f"❌ Backtest failed: {e}")
        import traceback
        traceback.print_exc()
        return None


async def quick_data_check():
    """Quick check to see what data is available"""
    
    print("🔍 Checking Available Database Data")
    print("=" * 40)
    
    from trading.analysis.data_loader import get_cached_book_ticker_data
    
    # Check last 24 hours
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=24)
    
    exchanges = ['MEXC', 'GATEIO', 'GATEIO_FUTURES']
    symbol_base = 'F'
    symbol_quote = 'USDT'
    
    print(f"📊 Checking data for {symbol_base}/{symbol_quote} in last 24 hours...")
    
    for exchange in exchanges:
        try:
            df = await get_cached_book_ticker_data(
                exchange=exchange,
                symbol_base=symbol_base,
                symbol_quote=symbol_quote,
                start_time=start_time,
                end_time=end_time
            )
            
            if df.empty:
                print(f"❌ {exchange}: No data available")
            else:
                print(f"✅ {exchange}: {len(df)} snapshots available")
                print(f"   Time range: {df['timestamp'].min()} to {df['timestamp'].max()}")
                
                # Show sample prices
                latest = df.iloc[-1]
                print(f"   Latest: bid={latest['bid_price']:.6f}, ask={latest['ask_price']:.6f}")
                
        except Exception as e:
            print(f"❌ {exchange}: Error loading data - {e}")
        
        print()


if __name__ == "__main__":
    
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        # Just check data availability
        asyncio.run(quick_data_check())
    else:
        # Run backtest
        asyncio.run(run_simple_db_backtest())
        
        print("\n💡 Commands:")
        print("  python src/examples/simple_db_backtest.py        # Run backtest")
        print("  python src/examples/simple_db_backtest.py check  # Check data availability")