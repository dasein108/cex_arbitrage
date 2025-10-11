from datetime import datetime, timezone

import numpy as np
import pandas as pd

from exchanges.structs import Symbol, AssetName, ExchangeEnum
from trading.analysis.data_loader import get_cached_book_ticker_data

fees = {
    "spot_maker_fee": 0.0,  # MEXC spot maker
    "spot_taker_fee": 0.05,  # MEXC spot taker
    "futures_maker_fee": 0.02,  # Gate.io futures maker
    "futures_taker_fee": 0.05,  # Gate.io futures taker
}

DEFAULT_FEES_PER_TRADE = fees["spot_taker_fee"] + fees["futures_taker_fee"]


def _add_prefix_to_df_columns(df, prefix):
    # Remove specified columns from spot_df and futures_df
    columns_to_remove = ["exchange", "symbol_base", "symbol_quote"]

    df = df.copy()

    # Set timestamp as index first
    if 'timestamp' in df.columns:
        df = df.set_index('timestamp')

    # Remove specified columns
    df = df.drop(columns=[col for col in columns_to_remove if col in df.columns], axis=1)
    df.columns = [f"{prefix}{col}" for col in df.columns]

    if isinstance(df.index, pd.DatetimeIndex):
        df.index = df.index.round("1s")

    return df

async def load_market_data(symbol: Symbol = None, start_date=None, end_date=None) -> pd.DataFrame:
    """Load market data with caching for both exchanges."""
    # Use the actual data we have in database
    if end_date is None:
        end_date = datetime(2025, 10, 11, 11, 30, 0, tzinfo=timezone.utc)
    if start_date is None:
        start_date = end_date - pd.Timedelta(days=1)
    if symbol is None:
        symbol = Symbol(base=AssetName("LUNC"), quote=AssetName("USDT"))  # Using MYX as it has most data
    print(f"📅 Symbol: {symbol} - Fetching market data from database - from {start_date.strftime('%Y-%m-%d %H:%M')} to {end_date.strftime('%Y-%m-%d %H:%M')}")

    exchange_spot = ExchangeEnum.GATEIO_FUTURES.value  # Using same exchange data for demo
    exchange_futures = ExchangeEnum.GATEIO_FUTURES.value


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

    # Add small artificial spread to simulate different exchanges (for demo purposes)
    spot_df['bid_price'] = spot_df['bid_price'] * 1.0002  # Simulate slightly higher spot prices
    spot_df['ask_price'] = spot_df['ask_price'] * 1.0002
    futures_df['bid_price'] = futures_df['bid_price'] * 0.9998  # Simulate slightly lower futures prices
    futures_df['ask_price'] = futures_df['ask_price'] * 0.9998

    spot_df = _add_prefix_to_df_columns(spot_df, "spot_")
    futures_df = _add_prefix_to_df_columns(futures_df, "fut_")


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
    
    # Remove duplicate timestamps to avoid double-counting
    merged_df = merged_df[~merged_df.index.duplicated(keep='first')]
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


def add_calculations(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # entry spread
    df['spot_fut_spread_prc'] = ((df['spot_bid_price'] - df['fut_ask_price']) / df['spot_bid_price']) * 100.0
    # exit spread
    df['fut_spot_spread_prc'] = ((df['fut_bid_price'] - df['spot_ask_price']) / df['fut_bid_price']) * 100.0

    return df


def get_best_spread_bins(df: pd.DataFrame, step=0.02, threshold=50, min_profit_pct=0.01):
    """
    Analyze spread bins to identify profitable arbitrage opportunities.

    This function implements a bin-based arbitrage opportunity detection system that:
    1. Groups entry and exit spreads into histogram bins for statistical analysis
    2. Matches entry bins with exit bins to form complete arbitrage cycles
    3. Calculates maximum profit potential for each bin pair
    4. Filters opportunities by profitability threshold (fees + minimum profit)

    Parameters:
    -----------
    df : pd.DataFrame
        Market data with spot_fut_spread_prc and fut_spot_spread_prc columns
    step : float
        Bin width for histogram grouping (default: 0.02%)
    threshold : int
        Minimum count threshold for bin grouping (default: 50)
    min_profit_bps : float
        Minimum profit in basis points above fees (default: 1.0 bps = 0.01%)

    Returns:
    --------
    np.array : Array of profitable opportunities with columns:
        - spot_fut_val: Entry spread bin value (spot bid - futures ask)
        - fut_spot_val: Exit spread bin value (futures bid - spot ask)
        - max_profit: Maximum profit potential (entry - exit - fees)
        - count_weight: Combined frequency weight for statistical confidence
    """
    # Get binned spread distributions for entry and exit
    spot_fut_vals, spot_fut_cnts = group_spread_bins(df['spot_fut_spread_prc'], step=step, threshold=threshold)
    fut_spot_vals, fut_spot_cnts = group_spread_bins(df['fut_spot_spread_prc'], step=step, threshold=threshold)

    # Calculate total fee threshold (round-trip fees + minimum profit)
    profit_threshold = DEFAULT_FEES_PER_TRADE + min_profit_pct

    # Initialize results list for profitable bin combinations
    profitable_opportunities = []

    # Analyze all possible entry-exit bin combinations
    for i, entry_spread in enumerate(spot_fut_vals):
        for j, exit_spread in enumerate(fut_spot_vals):
            # Calculate theoretical profit for this bin pair
            # Profit = Entry Spread - Exit Spread - Total Fees
            # Entry: We receive entry_spread when selling spot and buying futures
            # Exit: We pay exit_spread when buying spot and selling futures
            max_profit = entry_spread - exit_spread - DEFAULT_FEES_PER_TRADE * 2

            # Filter by profitability threshold
            if max_profit >= min_profit_pct:
                # Calculate combined frequency weight for statistical confidence
                # Higher counts indicate more frequent occurrence of this opportunity
                count_weight = np.sqrt(spot_fut_cnts[i] * fut_spot_cnts[j])

                profitable_opportunities.append([
                    entry_spread,      # Entry spread value (spot_fut_val)
                    exit_spread,       # Exit spread value (fut_spot_val)
                    max_profit,        # Maximum profit potential
                    count_weight       # Statistical confidence weight
                ])

    # Convert to numpy array and sort by profit potential
    if profitable_opportunities:
        result = np.array(profitable_opportunities)
        # Sort by maximum profit (descending) for best opportunities first
        result = result[result[:, 2].argsort()[::-1]]

        # Add informative logging
        print(f"📊 Arbitrage Analysis Results:")
        print(f"  • Entry bins analyzed: {len(spot_fut_vals)}")
        print(f"  • Exit bins analyzed: {len(fut_spot_vals)}")
        print(f"  • Profitable opportunities: {len(result)}")
        if len(result) > 0:
            print(f"  • Best opportunity: Entry={result[0,0]:.3f}%, Exit={result[0,1]:.3f}%, Profit={result[0,2]:.3f}%")
            print(f"  • Profit range: {result[-1,2]:.3f}% to {result[0,2]:.3f}%")
            print(f"  • Required fees threshold: {DEFAULT_FEES_PER_TRADE:.3f}%")

        return result
    else:
        print(f"⚠️ No profitable opportunities found with threshold {profit_threshold:.3f}%")
        return np.array([])  # Return empty array if no opportunities found


def filter_outliers(opportunities: np.array, method='iqr', multiplier=1.5):
    """
    Filter outliers from arbitrage opportunities to remove extreme values.

    Parameters:
    -----------
    opportunities : np.array
        Array from get_best_spread_bins with [entry_spread, exit_spread, max_profit, count_weight]
    method : str
        Outlier detection method ('iqr', 'std', 'percentile')
    multiplier : float
        Multiplier for outlier threshold (default: 1.5 for IQR method)

    Returns:
    --------
    np.array : Filtered opportunities without outliers
    """
    if len(opportunities) == 0:
        return opportunities

    # Extract profit column for outlier detection
    profits = opportunities[:, 2]

    if method == 'iqr':
        # Interquartile Range method
        q1 = np.percentile(profits, 25)
        q3 = np.percentile(profits, 75)
        iqr = q3 - q1
        lower_bound = q1 - multiplier * iqr
        upper_bound = q3 + multiplier * iqr
        mask = (profits >= lower_bound) & (profits <= upper_bound)

    elif method == 'std':
        # Standard deviation method
        mean_profit = np.mean(profits)
        std_profit = np.std(profits)
        lower_bound = mean_profit - multiplier * std_profit
        upper_bound = mean_profit + multiplier * std_profit
        mask = (profits >= lower_bound) & (profits <= upper_bound)

    elif method == 'percentile':
        # Percentile method (remove top/bottom X%)
        pct = multiplier  # Use multiplier as percentile (e.g., 5 for 5%)
        lower_bound = np.percentile(profits, pct)
        upper_bound = np.percentile(profits, 100 - pct)
        mask = (profits >= lower_bound) & (profits <= upper_bound)

    filtered_opportunities = opportunities[mask]

    print(f"🔍 Outlier Filtering Results:")
    print(f"  • Original opportunities: {len(opportunities)}")
    print(f"  • Filtered opportunities: {len(filtered_opportunities)}")
    print(f"  • Removed outliers: {len(opportunities) - len(filtered_opportunities)}")
    print(f"  • Method: {method} with multiplier {multiplier}")
    if len(filtered_opportunities) > 0:
        print(f"  • Profit range after filtering: {filtered_opportunities[:, 2].min():.3f}% to {filtered_opportunities[:, 2].max():.3f}%")

    return filtered_opportunities


def calculate_mean_spreads(opportunities: np.array):
    """
    Calculate mean entry and exit spreads from filtered arbitrage opportunities.

    Parameters:
    -----------
    opportunities : np.array
        Array from get_best_spread_bins or filter_outliers with
        [entry_spread, exit_spread, max_profit, count_weight]

    Returns:
    --------
    tuple : (mean_entry_spread, mean_exit_spread) as floats
    """
    if len(opportunities) == 0:
        print("⚠️ No opportunities provided for mean calculation")
        return 0.0, 0.0

    # Calculate weighted means using count_weight for statistical accuracy
    weights = opportunities[:, 3]  # count_weight column

    # Weighted mean entry spread
    mean_entry_spread = np.average(opportunities[:, 0], weights=weights)

    # Weighted mean exit spread
    mean_exit_spread = np.average(opportunities[:, 1], weights=weights)

    print(f"📈 Mean Spread Analysis:")
    print(f"  • Weighted mean entry spread: {mean_entry_spread:.4f}%")
    print(f"  • Weighted mean exit spread: {mean_exit_spread:.4f}%")
    print(f"  • Expected profit margin: {mean_entry_spread - mean_exit_spread - DEFAULT_FEES_PER_TRADE * 2:.4f}%")
    print(f"  • Based on {len(opportunities)} opportunities")

    return float(mean_entry_spread), float(mean_exit_spread)
