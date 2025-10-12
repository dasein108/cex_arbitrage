import datetime
from typing import Tuple

from exchanges.structs import Symbol, AssetName
from trading.research.trading_utlis import load_market_data, DEFAULT_FEES_PER_TRADE
import pandas as pd


def add_delta_neutral_calculations(df: pd.DataFrame) -> pd.DataFrame:
    """Add delta-neutral specific calculations to the dataframe."""
    df = df.copy()
    
    # Core calculations for delta-neutral strategy
    df['spot_fut_spread'] = df['spot_ask_price'] - df['fut_bid_price']  # What we pay to enter
    df['fut_spot_spread'] = df['fut_ask_price'] - df['spot_bid_price']  # What we pay to exit
    df = df.dropna(subset=['spot_fut_spread', 'fut_spot_spread'])

    # Historical mean spread (24h @ 10min intervals = 144 periods)
    df['historical_spread'] = df['spot_fut_spread'].rolling(window=144).mean()
    
    # Normalized spread for signal generation
    df['normalized_spread'] = (df['spot_fut_spread'] - df['historical_spread']) / df['historical_spread'].abs()
    
    return df


def get_trading_signals(df: pd.DataFrame, entry_threshold: float = 0.02, exit_threshold: float = 0.01) -> Tuple[pd.Series, pd.Series]:
    """Generate delta-neutral trading signals based on normalized spread deviation."""
    
    # Entry when futures underperform (negative normalized spread)
    entry_signal = df['normalized_spread'] < -entry_threshold
    
    # Exit when spreads normalize
    exit_signal = df['normalized_spread'] > -exit_threshold
    
    return entry_signal, exit_signal


def simple_delta_neutral_backtest(df: pd.DataFrame, entry_signal: pd.Series, exit_signal: pd.Series) -> list:
    """
    Backtest delta-neutral strategy.
    Entry: Long futures, Short spot (delta-neutral position)
    Exit: Close both legs when spreads normalize
    """
    signals = df[entry_signal | exit_signal].copy()
    
    trades, position, entry_data = [], None, None
    
    for _, row in signals.iterrows():
        time_diff = (row.name - entry_data['timestamp']).total_seconds() / 3600 if entry_data else 0
        
        if position is None and bool(entry_signal.loc[row.name]):
            position = row['normalized_spread']
            entry_data = {
                'timestamp': row.name,
                'spot_ask_price': row['spot_ask_price'],    # Price we PAY when buying spot (short position)
                'fut_bid_price': row['fut_bid_price'],      # Price we RECEIVE when selling futures (long position)
                'entry_spread': row['spot_fut_spread'],
                'normalized_spread': position
            }
        elif position is not None and (bool(exit_signal.loc[row.name]) or time_diff >= 6):
            # Calculate PnL for each leg separately
            # Spot leg: We bought at spot_ask, sell at spot_bid
            pnl_spot_pts = row['spot_bid_price'] - entry_data['spot_ask_price']  # Profit from spot position
            pnl_spot_pct = (pnl_spot_pts / entry_data['spot_ask_price'])
            
            # Futures leg: We sold at fut_bid, buy back at fut_ask  
            pnl_fut_pts = entry_data['fut_bid_price'] - row['fut_ask_price']     # Profit from futures position
            pnl_fut_pct = (pnl_fut_pts / entry_data['fut_bid_price'])
            
            # Total PnL (delta-neutral: futures leg offsets spot leg)
            total_pnl_pct = pnl_spot_pct + pnl_fut_pct
            
            trades.append({
                'entry_spot_ask': entry_data['spot_ask_price'],      # Price paid for spot
                'entry_fut_bid': entry_data['fut_bid_price'],        # Price received for futures
                'exit_spot_bid': row['spot_bid_price'],              # Price received selling spot  
                'exit_fut_ask': row['fut_ask_price'],                # Price paid buying futures
                'entry_spread': entry_data['normalized_spread'],
                'exit_spread': row['normalized_spread'],
                'pnl': total_pnl_pct,
                'pnl_spot_pts': pnl_spot_pts,
                'pnl_fut_pts': pnl_fut_pts,
                'pnl_spot_pct': pnl_spot_pct,
                'pnl_fut_pct': pnl_fut_pct,
                'hours': time_diff
            })
            position, entry_data = None, None
    
    return trades


async def main():
    symbol = Symbol(base=AssetName("XPIN"), quote=AssetName("USDT"))
    # date_to = datetime.datetime.utcnow()
    date_to = datetime.datetime.fromisoformat("2025-10-12 03:45").replace(tzinfo=datetime.timezone.utc)  # For consistent testing
    date_from = date_to - datetime.timedelta(hours=2)
    df = await load_market_data(symbol, date_from, date_to)
    df = add_delta_neutral_calculations(df)
    
    # Debug: Print spread statistics
    print(f"\n📊 SPREAD ANALYSIS:")
    print(f"Data points: {len(df)}")
    print(f"Normalized spread range: {df['normalized_spread'].min():.4f} to {df['normalized_spread'].max():.4f}")
    print(f"Normalized spread mean: {df['normalized_spread'].mean():.4f}")
    print(f"Negative spreads (entry opportunities): {(df['normalized_spread'] < 0).sum()}")
    
    # OPTION 1: Use manual thresholds for debugging
    entry_threshold = 0.02  # Enter when normalized spread < -2%
    exit_threshold = 0.005  # Exit when normalized spread > -0.5% (closer to zero)
    
    print(f"\n🎯 USING MANUAL THRESHOLDS FOR DEBUGGING:")
    print(f"Entry threshold: {entry_threshold:.3f} ({entry_threshold*100:.1f}%)")
    print(f"Exit threshold: {exit_threshold:.3f} ({exit_threshold*100:.1f}%)")
    print(f"Entry condition: normalized_spread < -{entry_threshold:.3f}")
    print(f"Exit condition: normalized_spread > -{exit_threshold:.3f}")
    
    # OPTION 2: Use optimized thresholds (commented out for debugging)
    # print("🔧 THRESHOLD OPTIMIZATION ENABLED")
    # from trading.research.threshold_optimizer import compare_optimization_methods, print_optimization_results
    # optimization_results = compare_optimization_methods(df)
    # print_optimization_results(optimization_results)
    # entry_threshold = optimization_results['recommendation']['entry_threshold']
    # exit_threshold = optimization_results['recommendation']['exit_threshold']
    
    entry_signal, exit_signal = get_trading_signals(df, entry_threshold=entry_threshold, exit_threshold=exit_threshold)
    
    # Debug: Analyze signals
    print(f"\n🔍 SIGNAL ANALYSIS:")
    print(f"Entry signals: {entry_signal.sum()}")
    print(f"Exit signals: {exit_signal.sum()}")
    print(f"Total signals: {(entry_signal | exit_signal).sum()}")
    
    if entry_signal.sum() > 0:
        entry_spreads = df.loc[entry_signal, 'normalized_spread']
        print(f"Entry spread range: {entry_spreads.min():.4f} to {entry_spreads.max():.4f}")
    
    if exit_signal.sum() > 0:
        exit_spreads = df.loc[exit_signal, 'normalized_spread']
        print(f"Exit spread range: {exit_spreads.min():.4f} to {exit_spreads.max():.4f}")
    
    # Delta-neutral arbitrage backtester
    trades = simple_delta_neutral_backtest(df, entry_signal, exit_signal)
    
    print(f"\n💼 TRADE GENERATION:")
    print(f"Trades executed: {len(trades)}")
    
    # Fees analysis
    round_trip_fees = DEFAULT_FEES_PER_TRADE * 2  # Round trip on both legs
    total_fees_per_trade = round_trip_fees * 2  # Both spot and futures legs
    print(f"\n💰 FEES ANALYSIS:")
    print(f"Single trade fee: {DEFAULT_FEES_PER_TRADE:.4f} ({DEFAULT_FEES_PER_TRADE*100:.2f}%)")
    print(f"Round-trip fees per leg: {round_trip_fees:.4f} ({round_trip_fees*100:.2f}%)")
    print(f"Total fees per delta-neutral trade: {total_fees_per_trade:.4f} ({total_fees_per_trade*100:.2f}%)")
    print(f"Minimum profitable spread: {total_fees_per_trade:.4f} ({total_fees_per_trade*100:.2f}%)")
    
    if len(trades) > 0:
        sample_trade = trades[0]
        print(f"\n🔬 FIRST TRADE ANALYSIS:")
        print(f"Entry spread: {sample_trade['entry_spread']:.4f}")
        print(f"Exit spread: {sample_trade['exit_spread']:.4f}")
        print(f"Spread capture: {sample_trade['entry_spread'] - sample_trade['exit_spread']:.4f}")
        print(f"Spot entry price: {sample_trade['entry_spot_ask']:.6f}")
        print(f"Spot exit price: {sample_trade['exit_spot_bid']:.6f}")
        print(f"Futures entry price: {sample_trade['entry_fut_bid']:.6f}")
        print(f"Futures exit price: {sample_trade['exit_fut_ask']:.6f}")
        print(f"Spot PnL: {sample_trade['pnl_spot_pct']:.4f}%")
        print(f"Futures PnL: {sample_trade['pnl_fut_pct']:.4f}%")
        print(f"Total PnL (before fees): {sample_trade['pnl']:.4f}%")
        print(f"Total PnL (after fees): {sample_trade['pnl'] - total_fees_per_trade:.4f}%")
        print(f"Profitable after fees: {'✅ YES' if sample_trade['pnl'] > total_fees_per_trade else '❌ NO'}")
    
    # Print detailed trades table
    if trades:
        print(f"\n{'='*180}")
        print(f"DELTA-NEUTRAL EXECUTION PRICES:")
        print(f"{'Trade':<5} "
              f"{'Entry Spot Ask':<14} {'Exit Spot Bid':<14} {'spot diff ':<14} {'spot pct ':<14} "
              f"{'Entry Fut Bid':<14} {'Exit Fut Ask':<14} {'fut diff ':<14} {'fut pct ':<14} "
              f"{'entry norm%':<10} {'exit norm%':<10} {'PnL %':<8} {'Hours':<6}")
        print(f"{'='*180}")
        for i, t in enumerate(trades, 1):
            print(f"{i:<5} "
                  f"{t['entry_spot_ask']:<14.10f} {t['exit_spot_bid']:<14.10f} {t['pnl_spot_pts']:<14.10f} {t['pnl_spot_pct']:<14.4f} "
                  f"{t['entry_fut_bid']:<14.10f} {t['exit_fut_ask']:<14.10f} {t['pnl_fut_pts']:<14.10f} {t['pnl_fut_pct']:<14.4f} "
                  f"{t['entry_spread']:<10.4f} {t['exit_spread']:<10.4f} {t['pnl']:<8.4f} {t['hours']:<6.2f}")
        
        # Print summary statistics
        total_trades = len(trades)
        profitable_trades = sum(1 for t in trades if t['pnl'] > 0)
        total_pnl = sum(t['pnl'] for t in trades)
        avg_pnl = total_pnl / total_trades if total_trades > 0 else 0
        avg_hours = sum(t['hours'] for t in trades) / total_trades if total_trades > 0 else 0
        
        print(f"\n{'='*80}")
        print(f"DELTA-NEUTRAL STRATEGY SUMMARY:")
        print(f"Total Trades: {total_trades}")
        print(f"Profitable Trades: {profitable_trades} ({profitable_trades/total_trades*100:.1f}%)")
        print(f"Total PnL: {total_pnl:.4f}%")
        print(f"Average PnL per Trade: {avg_pnl:.4f}%")
        print(f"Average Holding Time: {avg_hours:.2f} hours")
        print(f"Entry Threshold: -{entry_threshold*100:.1f}% normalized spread")
        print(f"Exit Threshold: -{exit_threshold*100:.1f}% normalized spread")
        print(f"{'='*80}")
        
    else:
        print("No delta-neutral trades executed")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())