import datetime
from typing import Tuple

from exchanges.structs import Symbol, AssetName
from trading.research.data_utlis import load_market_data, add_calculations, \
    get_best_spread_bins, filter_outliers, calculate_mean_spreads
import pandas as pd


def get_trading_signals(df: pd.DataFrame, entry_threshold: float = 0.2, exit_threshold: float = 0.1) -> Tuple[pd.Series, pd.Series]:

    entry_signal = df['spot_fut_spread_prc'] > entry_threshold

    exit_signal = df['fut_spot_spread_prc'] < exit_threshold

    return entry_signal, exit_signal


async def main():
    symbol = Symbol(base=AssetName("LUNC"), quote=AssetName("USDT"))  # Using MYX as it has most data
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

    # TODO: add vectorbt backtesting here

    print(f"entry: {mean_entry}, exit: {mean_exit}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())