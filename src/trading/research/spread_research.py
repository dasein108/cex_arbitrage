
from db.database_manager import initialize_database_manager, close_database_manager
import signal
import asyncio
import numpy as np

from exchanges.structs import Symbol, AssetName, ExchangeEnum
from trading.analysis.data_loader import get_cached_book_ticker_data
from datetime import datetime, timezone, timedelta

def _signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    print(f"Received signal {signum}, initiating graceful shutdown...")
    asyncio.get_event_loop().run_until_complete(close_database_manager())


async def load_market_data():
    """Load market data with caching for both exchanges."""
    end_date = datetime(2025, 10, 11, 16, 15, 0, tzinfo=timezone.utc)
    start_date = end_date - timedelta(days=1)
    symbol = Symbol(base=AssetName("LUNC"), quote=AssetName("USDT"))
    LIMIT = 10000
    print(f"\n🎯 Symbol: {symbol}")
    print(f"📅 Period: {start_date.strftime('%Y-%m-%d %H:%M')} to {end_date.strftime('%Y-%m-%d %H:%M')}")
    exchange_spot = ExchangeEnum.MEXC.value
    exchange_futures = ExchangeEnum.GATEIO_FUTURES.value
    print(f"🏦 Exchanges: {exchange_spot} (spot) - {exchange_futures} (futures)")

    print("\n📊 Fetching market data from database...")

    # Load spot data
    spot_df = await get_cached_book_ticker_data(
        exchange=exchange_spot,
        symbol_base=symbol.base,
        symbol_quote=symbol.quote,
        start_time=start_date,
        end_time=end_date
    )

    futures_df = await get_cached_book_ticker_data(
        exchange=exchange_futures,
        symbol_base=symbol.base,
        symbol_quote=symbol.quote,
        start_time=start_date,
        end_time=end_date
    )

    def add_prefix_to_df_columns(df, prefix):
        # Remove specified columns from spot_df and futures_df
        columns_to_remove = ["exchange", "symbol_base", "symbol_quote"]

        df = df.copy()
        df = df.drop(columns=columns_to_remove, axis=1)
        df.columns = [f"{prefix}{col}" for col in df.columns]
        df.index = df.index.round("1s")

        return df

    spot_df = add_prefix_to_df_columns(spot_df, "spot_")
    futures_df = add_prefix_to_df_columns(futures_df, "fut_")


    # Load futures data
    # Validate data
    if spot_df.empty or futures_df.empty:
        raise ValueError(f"Insufficient data: spot={len(spot_df)}, futures={len(futures_df)} records")

    merged_df = spot_df.merge(
        futures_df,
        left_index=True,
        right_index=True,
        how="outer"
    )
    # merged_df.index = merged_df.index.round("1s")
    print(f"  ✅ Loaded spot: {len(spot_df)}, futures: {len(futures_df)} merged: {len(merged_df)} data points")


    return merged_df


def group_spread_bins(series, step=0.02, threshold=50):
    """
    Create histogram bins and group adjacent bins with low counts.

    Parameters:
    -----------
    series : pd.Series
        The spread percentage data
    step : float
        Bin width (default: 0.01)
    threshold : int
        Minimum count threshold for grouping (default: 10)

    Returns:
    --------
    grouped_values : np.array
        Bin values (mean for grouped, original for others)
    grouped_counts : np.array
        Counts (sum for grouped, original for others)
    """
    # Create bins and histogram
    bins = np.arange(series.min(), series.max() + step, step)
    counts, bin_edges = np.histogram(series, bins=bins)

    # Get non-empty bins (left edge of each bin)
    mask = counts > 0
    values = bin_edges[:-1][mask]
    counts = counts[mask]

    # Group adjacent low-count bins
    grouped_values = []
    grouped_counts = []

    i = 0
    while i < len(values):
        if counts[i] < threshold:
            # Group consecutive low-count bins
            group_vals = [values[i]]
            group_cnts = [counts[i]]

            j = i + 1
            while j < len(values) and counts[j] < threshold:
                group_vals.append(values[j])
                group_cnts.append(counts[j])
                j += 1

            grouped_values.append(np.mean(group_vals))
            grouped_counts.append(sum(group_cnts))
            i = j
        else:
            grouped_values.append(values[i])
            grouped_counts.append(counts[i])
            i += 1

    return np.array(grouped_values), np.array(grouped_counts)


async def main():
    """Main function to run the spread research analysis."""
    df = await load_market_data()
    print("Columns:", list(df.columns))
    # Columns: ['spot_bid_price', 'spot_bid_qty', 'spot_ask_price', 'spot_ask_qty', 'spot_mid_price', 'spot_spread_bps',
    # 'fut_bid_price', 'fut_bid_qty', 'fut_ask_price', 'fut_ask_qty', 'fut_mid_price', 'fut_spread_bps']
    # to buy spot and sell futures
    df['spot_fut_spread_prc'] = ((df['spot_bid_price'] - df['fut_ask_price']) / df['spot_bid_price']) * 100.0
    df['fut_spot_spread_prc'] = ((df['fut_bid_price'] - df['spot_ask_price']) / df['fut_bid_price']) * 100.0
    max_spot_fut = df['spot_fut_spread_prc'].max()
    min_spot_fut = df['spot_fut_spread_prc'].min()
    max_fut_spot = df['fut_spot_spread_prc'].max()
    min_fut_spot = df['fut_spot_spread_prc'].min()

    spot_fut_vals, spot_fut_cnts = group_spread_bins(df['spot_fut_spread_prc'])
    fut_spot_vals, fut_spot_cnts = group_spread_bins(df['fut_spot_spread_prc'])
    spot_fut_dict = dict(zip(spot_fut_vals, spot_fut_cnts))
    fut_spot_dict = dict(zip(fut_spot_vals, fut_spot_cnts))

    print("Spot-Futures Spread counts (step 0.01):", spot_fut_dict)
    print("Futures-Spot Spread counts (step 0.01):", fut_spot_dict)

    # Setup signal handlers for graceful shutdown




if __name__ == "__main__":
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    asyncio.run(main())