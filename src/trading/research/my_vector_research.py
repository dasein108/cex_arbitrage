import datetime
from typing import Tuple

from exchanges.structs import Symbol, AssetName
from trading.research.trading_utlis import load_market_data, add_calculations, \
    get_best_spread_bins, filter_outliers, calculate_mean_spreads
import pandas as pd


def get_trading_signals(df: pd.DataFrame, entry_threshold: float = 0.2, exit_threshold: float = 0.1) -> Tuple[pd.Series, pd.Series]:

    entry_signal = df['spot_fut_spread_prc'] > entry_threshold

    exit_signal = df['fut_spot_spread_prc'] < exit_threshold

    return entry_signal, exit_signal


def simple_arbitrage_backtest(df: pd.DataFrame, entry_signal: pd.Series, exit_signal: pd.Series) -> list:
    signals = df[entry_signal | exit_signal].copy()
    # signals = signals[~signals.index.duplicated(keep='first')].copy()  # Remove duplicate indicesRetry

    trades, position, entry_data = [], None, None
    
    for _, row in signals.iterrows():
        time_diff = (row.name - entry_data['timestamp']).total_seconds() / 3600 if entry_data else 0
        
        if position is None and bool(entry_signal.loc[row.name]):
            position = row['spot_fut_spread_prc']
            entry_data = {
                'timestamp': row.name,
                'spot_ask': row['spot_ask_price'],  # FIXED: We PAY spot_ask when buying spot
                'fut_bid': row['fut_bid_price'],    # FIXED: We RECEIVE fut_bid when selling futures
                'spread': position
            }
        elif position is not None and (bool(exit_signal.loc[row.name]) or time_diff >= 6):
            exit_spread = row['fut_spot_spread_prc']
            pnl = position - exit_spread
            trades.append({
                'entry_spot_ask': entry_data['spot_ask'],  # FIXED: Price we PAY for spot
                'entry_fut_bid': entry_data['fut_bid'],    # FIXED: Price we RECEIVE for futures
                'exit_spot_bid': row['spot_bid_price'],    # FIXED: Price we RECEIVE when selling spot
                'exit_fut_ask': row['fut_ask_price'],      # FIXED: Price we PAY when buying futures
                'entry_spread': position,
                'exit_spread': exit_spread,
                'pnl': pnl,
                'hours': time_diff
            })
            position, entry_data = None, None
    
    return trades


async def main():
    symbol = Symbol(base=AssetName("F"), quote=AssetName("USDT"))  # Using MYX as it has most data
    date_to = datetime.datetime.utcnow()
    date_from = date_to - datetime.timedelta(hours=2)
    df = await load_market_data(symbol, date_from, date_to)
    df = add_calculations(df)
    opportunities = get_best_spread_bins(df)

    # Step 2: Filter outliers for reliable data
    filtered_ops = filter_outliers(opportunities, method='iqr', multiplier=1.5)

    # Step 3: Calculate mean spreads as floats
    mean_entry, mean_exit = calculate_mean_spreads(filtered_ops)

    entry_signal, exit_signal = get_trading_signals(df, entry_threshold=mean_entry, exit_threshold=mean_exit)

    # Simple arbitrage backtester
    trades = simple_arbitrage_backtest(df, entry_signal, exit_signal)
    
    # Print trades table
    if trades:
        print(f"\n{'='*120}")
        print(f"{'Trade':<5} {'Entry Spot Ask':<12} {'Entry Fut Bid':<12} {'Exit Spot Bid':<12} {'Exit Fut Ask':<12} {'Entry %':<8} {'Exit %':<8} {'PnL %':<8} {'Hours':<6}")
        print(f"{'='*120}")
        for i, t in enumerate(trades, 1):
            print(f"{i:<5} {t['entry_spot_ask']:<12.10f} {t['entry_fut_bid']:<12.10f} {t['exit_spot_bid']:<12.10f} {t['exit_fut_ask']:<12.10f} {t['entry_spread']:<8.4f} {t['exit_spread']:<8.4f} {t['pnl']:<8.4f} {t['hours']:<6.2f}")
        print(f"{'='*120}")
        print(f"Total Trades: {len(trades)}, Total PnL: {sum(t['pnl'] for t in trades):.4f}%")
    else:
        print("No trades executed")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())