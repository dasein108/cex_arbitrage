import datetime
from typing import Tuple

from exchanges.structs import Symbol, AssetName
from trading.research.trading_utlis import load_market_data, add_spread_delta_calculations, \
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
                'spot_buy_price': row['spot_ask_price'],  # FIXED: We PAY spot_ask when buying spot
                'fut_sell_price': row['fut_bid_price'],    # FIXED: We RECEIVE fut_bid when selling futures
                'spread': position
            }
        elif position is not None and (bool(exit_signal.loc[row.name]) or time_diff >= 6):
            exit_spread = row['fut_spot_spread_prc']
            pnl_spot_pts = row['spot_bid_price'] - entry_data['spot_buy_price']  # Profit from selling spot
            pnl_fut_pts = entry_data['fut_sell_price'] - row['fut_ask_price']     # Profit from buying futures
            pnl_fut_pct = (pnl_fut_pts / entry_data['fut_sell_price'])
            pnl_spot_pct = (pnl_spot_pts / entry_data['spot_buy_price'])

            pnl = pnl_fut_pct - pnl_spot_pct
            # Calculate bid-ask spreads and actual PnL

            # Calculate percentage spreads

            trades.append({
                'entry_spot_ask': entry_data['spot_buy_price'],  # FIXED: Price we PAY for spot
                'entry_fut_bid': entry_data['fut_sell_price'],    # FIXED: Price we RECEIVE for futures
                'exit_spot_bid': row['spot_bid_price'],    # FIXED: Price we RECEIVE when selling spot
                'exit_fut_ask': row['fut_ask_price'],      # FIXED: Price we PAY when buying futures
                'entry_spread': position,
                'exit_spread': exit_spread,
                'pnl': pnl,
                'pnl_spot_pts': pnl_spot_pts,
                'pnl_fut_pts': pnl_fut_pts,
                'pnl_fut_pct': pnl_fut_pct,
                'pnl_spot_pct': pnl_spot_pct,
                'hours': time_diff
            })
            position, entry_data = None, None
    
    return trades


async def main():
    # 📅 Symbol: BICO/USDT - Fetching market data from database - from 2025-10-11 16:09 to 2025-10-11 18:09
    # 📅 Symbol: BICO/USDT - Fetching market data from database - from 2025-10-11 16:16 to 2025-10-11 18:16 - not so good
    symbol = Symbol(base=AssetName("XPIN"), quote=AssetName("USDT"))  # Using MYX as it has most data
    date_to = datetime.datetime.utcnow()
    date_from = date_to - datetime.timedelta(hours=2)
    df = await load_market_data(symbol, date_from, date_to)
    df = add_spread_delta_calculations(df)
    opportunities = get_best_spread_bins(df)

    # Step 2: Filter outliers for reliable data
    filtered_ops = filter_outliers(opportunities, method='iqr', multiplier=1.5)

    # Step 3: Calculate mean spreads as floats
    mean_entry, mean_exit = calculate_mean_spreads(filtered_ops)

    entry_signal, exit_signal = get_trading_signals(df, entry_threshold=mean_entry, exit_threshold=mean_exit)

    # Simple arbitrage backtester
    trades = simple_arbitrage_backtest(df, entry_signal, exit_signal)
    
    # Print detailed trades table
    if trades:
        print(f"\n{'='*180}")
        print(f"EXECUTION PRICES:")
        print(f"{'Trade':<5} "
              f"{'Entry Spot Ask':<14} {'Exit Spot Bid':<14} {'spot diff ':<14} {'spot pct ':<14} "
              f"{'Entry Fut Bid':<14} {'Exit Fur Ask':<14} {'fut diff ':<14} {'fut pct ':<14} "
              f"{'entry s. %':<10} {'exit s %':<10} {'PnL %':<8} {'Hours':<6}")
        print(f"{'='*180}")
        for i, t in enumerate(trades, 1):
            print(f"{i:<5} "
                  f"{t['entry_spot_ask']:<14.10f} {t['exit_spot_bid']:<14.10f} {t['pnl_spot_pts']:<14.10f} {t['pnl_spot_pct']:<14.4f} "
                  f"{t['entry_fut_bid']:<14.10f} {t['exit_fut_ask']:<14.10f} {t['pnl_fut_pts']:<14.10f} {t['pnl_fut_pct']:<14.4f} "
                  f"{t['entry_spread']:<10.4f} {t['exit_spread']:<10.4f} {t['pnl']:<8.4f} {t['hours']:<6.2f}")

    else:
        print("No trades executed")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())