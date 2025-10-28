#!/usr/bin/env python3
"""
Run Hedged Cross-Arbitrage Backtest Using Database Book Ticker Snapshots

Uses real book ticker data from database instead of candle approximations.
"""

import asyncio
import pandas as pd
from datetime import datetime, timedelta, timezone

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from trading.research.cross_arbitrage.hedged_cross_arbitrage_backtest import (
    HedgedCrossArbitrageBacktest, BacktestConfig
)
from examples.simple_db_loader import get_cached_book_ticker_data


class DatabaseSnapshotBacktest(HedgedCrossArbitrageBacktest):
    """
    Enhanced backtest that uses real database book ticker snapshots
    """
    
    async def _load_and_prepare_data(self) -> pd.DataFrame:
        """Load real book ticker data from database and calculate spreads."""
        print(f"📥 Loading {self.config.symbol} DB snapshots for {self.config.days} days...")
        # Calculate time range (use hours for testing with limited data)
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=3)  # Use 3 hours to match our test data
        
        # Extract symbol components
        symbol_parts = self.config.symbol.split('_')
        symbol_base = symbol_parts[0]
        symbol_quote = symbol_parts[1] if len(symbol_parts) > 1 else 'USDT'
        
        print(f"📊 Loading data for {symbol_base}/{symbol_quote}...")
        
        # Load data from all 3 exchanges in parallel
        tasks = [
            get_cached_book_ticker_data(
                exchange='MEXC',  # Use string directly
                symbol_base=symbol_base,
                symbol_quote=symbol_quote,
                start_time=start_time,
                end_time=end_time
            ),
            get_cached_book_ticker_data(
                exchange='GATEIO',  # Use string directly
                symbol_base=symbol_base,
                symbol_quote=symbol_quote,
                start_time=start_time,
                end_time=end_time
            ),
            get_cached_book_ticker_data(
                exchange='GATEIO_FUTURES',  # Use string directly
                symbol_base=symbol_base,
                symbol_quote=symbol_quote,
                start_time=start_time,
                end_time=end_time
            )
        ]
        
        dfs = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Check results
        mexc_df, gateio_df, gateio_futures_df = dfs
        
        for i, (name, df) in enumerate([('MEXC', mexc_df), ('GATEIO', gateio_df), ('GATEIO_FUTURES', gateio_futures_df)]):
            if isinstance(df, Exception):
                print(f"❌ {name} error: {df}")
                raise RuntimeError(f"Failed to load {name} data: {df}")
            print(f"📊 {name}: {len(df)} rows found")
            if df.empty:
                print(f"❌ No {name} data for period {start_time} to {end_time}")
                raise RuntimeError(f"No {name} data available for the specified period")
            print(f"✅ {name}: {len(df)} snapshots loaded")
        
        # Merge dataframes on timestamp with forward fill for alignment
        print("🔄 Merging and aligning data...")
        
        # Ensure timestamp columns are datetime
        for df in [mexc_df, gateio_df, gateio_futures_df]:
            if 'timestamp' not in df.columns:
                df['timestamp'] = pd.to_datetime(df.index)
            else:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Set timestamp as index for merging
        mexc_df = mexc_df.set_index('timestamp')
        gateio_df = gateio_df.set_index('timestamp')
        gateio_futures_df = gateio_futures_df.set_index('timestamp')
        
        # Add exchange prefixes to columns
        mexc_df = mexc_df.add_prefix('mexc_spot_')
        gateio_df = gateio_df.add_prefix('gateio_spot_')
        gateio_futures_df = gateio_futures_df.add_prefix('gateio_futures_')
        
        # Merge on timestamp with outer join to keep all data
        merged_df = mexc_df.join(gateio_df, how='outer', sort=True)
        merged_df = merged_df.join(gateio_futures_df, how='outer', sort=True)
        
        # Forward fill missing values and drop rows with any NaN
        merged_df = merged_df.fillna(method='ffill').dropna()
        
        if merged_df.empty:
            raise RuntimeError("No overlapping data found across all exchanges")
        
        # Reset index to get timestamp as column
        merged_df = merged_df.reset_index()
        
        # Calculate arbitrage spreads using EXACT backtest formula
        print("📈 Calculating arbitrage spreads...")
        
        # MEXC vs Gate.io Futures arbitrage (using backtest formula)
        merged_df['mexc_vs_gateio_futures_arb'] = (
            (merged_df['gateio_futures_bid_price'] - merged_df['mexc_spot_ask_price']) / 
            merged_df['gateio_futures_bid_price'] * 100
        )
        
        # Gate.io Spot vs Futures arbitrage (using backtest formula)  
        merged_df['gateio_spot_vs_futures_arb'] = (
            (merged_df['gateio_spot_bid_price'] - merged_df['gateio_futures_ask_price']) /
            merged_df['gateio_spot_bid_price'] * 100
        )
        
        # Sort by timestamp
        merged_df = merged_df.sort_values('timestamp').reset_index(drop=True)
        
        print(f"✅ Loaded {len(merged_df)} synchronized snapshots from "
              f"{merged_df['timestamp'].min()} to {merged_df['timestamp'].max()}")
        
        # Show spread statistics
        mexc_spread_stats = merged_df['mexc_vs_gateio_futures_arb'].describe()
        gateio_spread_stats = merged_df['gateio_spot_vs_futures_arb'].describe()
        
        print("\n📊 Spread Statistics:")
        print(f"MEXC vs Gate.io Futures: mean={mexc_spread_stats['mean']:.4f}%, "
              f"std={mexc_spread_stats['std']:.4f}%, "
              f"min={mexc_spread_stats['min']:.4f}%, "
              f"max={mexc_spread_stats['max']:.4f}%")
        print(f"Gate.io Spot vs Futures: mean={gateio_spread_stats['mean']:.4f}%, "
              f"std={gateio_spread_stats['std']:.4f}%, "
              f"min={gateio_spread_stats['min']:.4f}%, "
              f"max={gateio_spread_stats['max']:.4f}%")
        
        return merged_df


async def run_database_backtest():
    """Run backtest using database snapshots"""
    
    print("🚀 Hedged Cross-Arbitrage Backtest with Database Snapshots")
    print("=" * 70)
    
    # Configuration for database backtest
    config = BacktestConfig(
        symbol="F_USDT",  # Adjust as needed
        days=1,           # Use 1 day to match our sample data
        min_transfer_time_minutes=10,
        position_size_usd=1000,
        max_concurrent_positions=2,
        fees_bps=20.0     # 0.2% total fees
    )
    
    # Create enhanced backtest
    backtest = DatabaseSnapshotBacktest(config)
    
    try:
        # Run backtest with real data
        print("⏳ Running backtest with database snapshots...")
        results = await backtest.run_backtest()
        
        # Print comprehensive report
        print("\n" + "="*80)
        print(backtest.format_report(results))
        
        # Create visualizations
        print("\n📊 Creating visualizations...")
        plots = backtest.create_visualizations(results)
        
        print(f"\n✅ Database snapshot backtest completed successfully!")
        print(f"📁 Results saved in: {backtest.cache_dir}")
        
        # Compare with previous results
        perf = results['performance']
        print(f"\n🎯 Key Results:")
        print(f"  💰 Total P&L: ${perf.total_pnl:.2f}")
        print(f"  📈 Total Trades: {perf.total_trades}")
        print(f"  🎲 Win Rate: {perf.win_rate:.1f}%")
        print(f"  📊 Avg P&L per Trade: ${perf.avg_pnl_per_trade:.2f}")
        print(f"  ⚠️  Max Drawdown: ${perf.max_drawdown:.2f}")
        
        if perf.total_pnl > 0:
            print(f"  🎉 Strategy is PROFITABLE with real data!")
        else:
            print(f"  ⚠️  Strategy shows losses with real data")
            
        return results
        
    except Exception as e:
        print(f"❌ Database backtest failed: {e}")
        import traceback
        traceback.print_exc()
        return None


async def compare_candle_vs_database():
    """Compare results between candle-based and database-based backtests"""
    
    print("\n🔄 Comparing Candle vs Database Backtest Results")
    print("=" * 60)
    
    config = BacktestConfig(
        symbol="F_USDT",
        days=1,  # Short period for comparison
        position_size_usd=1000
    )
    
    try:
        # Run database backtest
        print("1️⃣ Running database snapshot backtest...")
        db_backtest = DatabaseSnapshotBacktest(config)
        db_results = await db_backtest.run_backtest()
        
        # Run original candle backtest
        print("\n2️⃣ Running original candle backtest...")
        candle_backtest = HedgedCrossArbitrageBacktest(config)
        candle_results = await candle_backtest.run_backtest()
        
        # Compare results
        print(f"\n📊 COMPARISON RESULTS:")
        print(f"{'Metric':<25} {'Database':<15} {'Candles':<15} {'Difference':<15}")
        print("-" * 70)
        
        db_perf = db_results['performance']
        candle_perf = candle_results['performance']
        
        metrics = [
            ('Total P&L', 'total_pnl', '${:.2f}'),
            ('Total Trades', 'total_trades', '{:.0f}'),
            ('Win Rate %', 'win_rate', '{:.1f}%'),
            ('Avg P&L per Trade', 'avg_pnl_per_trade', '${:.2f}'),
            ('Max Drawdown', 'max_drawdown', '${:.2f}')
        ]
        
        for name, attr, fmt in metrics:
            db_val = getattr(db_perf, attr)
            candle_val = getattr(candle_perf, attr)
            diff = db_val - candle_val
            
            print(f"{name:<25} {fmt.format(db_val):<15} {fmt.format(candle_val):<15} {fmt.format(diff):<15}")
        
        # Analysis
        print(f"\n🔍 ANALYSIS:")
        if abs(db_perf.total_pnl - candle_perf.total_pnl) < 0.01:
            print("✅ Results are very similar - strategy logic is consistent")
        elif db_perf.total_pnl > candle_perf.total_pnl:
            print("📈 Database data shows better performance - real data has more opportunities")
        else:
            print("📉 Candle data shows better performance - real data may be noisier")
            
        print(f"💡 Trade count difference: {db_perf.total_trades - candle_perf.total_trades} trades")
        
    except Exception as e:
        print(f"❌ Comparison failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("🧪 Database Snapshot Backtesting")
    print()
    
    # Choose what to run
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "compare":
        # Run comparison
        asyncio.run(compare_candle_vs_database())
    else:
        # Run database backtest
        asyncio.run(run_database_backtest())
        
        print("\n💡 To compare with candle backtest, run:")
        print("python src/examples/backtest_with_db_snapshots.py compare")