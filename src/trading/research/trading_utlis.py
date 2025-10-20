from datetime import datetime, timezone

import numpy as np
import pandas as pd
from typing import List, Dict
from exchanges.structs import Symbol, AssetName, ExchangeEnum
from trading.analysis.data_loader import get_cached_book_ticker_data

fees = {
    "spot_maker_fee": 0.0,  # MEXC spot maker
    "spot_taker_fee": 0.05,  # MEXC spot taker
    "futures_maker_fee": 0.02,  # Gate.io futures maker
    "futures_taker_fee": 0.05,  # Gate.io futures taker
}

DEFAULT_FEES_PER_TRADE = fees["spot_taker_fee"] + fees["futures_taker_fee"]


def _add_prefix_to_df_columns(df, prefix: str, columns_to_remove: List[str]= None) -> pd.DataFrame:
    # Remove specified columns from spot_df and futures_df
    if not columns_to_remove:
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

async def load_market_data(symbol: Symbol = None, start_date=None, end_date=None, exchanges: List[ExchangeEnum] = None) -> pd.DataFrame:
    """Load market data with caching for both exchanges."""
    # Use the actual data we have in database
    if end_date is None:
        end_date = datetime.utcnow()
    if start_date is None:
        start_date = end_date - pd.Timedelta(hours=8)
    if symbol is None:
        symbol = Symbol(base=AssetName("LUNC"), quote=AssetName("USDT"))  # Using MYX as it has most data
    print(f"📅 Symbol: {symbol} - Fetching market data from database - from {start_date.strftime('%Y-%m-%d %H:%M')} to {end_date.strftime('%Y-%m-%d %H:%M')}")

    if exchanges is None:
        exchanges = [ExchangeEnum.MEXC, ExchangeEnum.GATEIO_FUTURES, ExchangeEnum.GATEIO]

    exchange_df: Dict[ExchangeEnum, pd.DataFrame] = {}
    for exchange in exchanges:
        df = await get_cached_book_ticker_data(
            exchange=exchange.value,
            symbol_base=symbol.base,
            symbol_quote=symbol.quote,
            start_time=start_date,
            end_time=end_date
        )
        df = df.drop(columns=["exchange", "symbol_base", "symbol_quote"], axis=1)
        df = _add_prefix_to_df_columns(df, exchange.value.lower() + "_")
        # Remove duplicate rounding - already done in _add_prefix_to_df_columns
        df.index = df.index.round("1s")
        
        # Remove any duplicate timestamps within individual exchange data
        df = df[~df.index.duplicated(keep='first')]

        exchange_df[exchange] = df

    merged_df = pd.concat(list(exchange_df.values()), axis=1, join="outer")
    merged_df = merged_df.sort_index()
    
    # Remove duplicate timestamps to avoid double-counting
    merged_df = merged_df[~merged_df.index.duplicated(keep='first')]

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


def add_spread_delta_calculations(df: pd.DataFrame) -> pd.DataFrame:
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


def calculate_total_arbitrage_spread(df: pd.DataFrame, fees_pct: float = 0.2) -> pd.DataFrame:
    """
    Calculate total arbitrage spread with fees from book ticker data.
    
    This calculates the combined arbitrage opportunity between:
    1. MEXC spot vs Gate.io futures
    2. Gate.io spot vs Gate.io futures
    
    Args:
        df: DataFrame with columns:
            - mexc_bid_price, mexc_ask_price (MEXC spot)
            - gateio_bid_price, gateio_ask_price (Gate.io spot)
            - gateio_futures_bid_price, gateio_futures_ask_price (Gate.io futures)
        fees_pct: Total fees percentage (default 0.2% = 0.1% + 0.05% + 0.05%)
    
    Returns:
        DataFrame with additional columns:
        - mexc_vs_gateio_futures_arb: MEXC spot → Gate.io futures arbitrage
        - gateio_spot_vs_futures_arb: Gate.io spot vs futures arbitrage
        - total_arbitrage_sum: Sum of both opportunities
        - total_arbitrage_sum_fees: After fees (the key signal value)
    """
    df = df.copy()
    
    # 1. MEXC spot vs Gate.io futures (buy MEXC, sell Gate.io futures)
    df['mexc_vs_gateio_futures_arb'] = (
        (df['gateio_futures_bid_price'] - df['mexc_spot_ask_price']) /
        df['gateio_futures_bid_price'] * 100
    )
    
    # 2. Gate.io spot vs futures (buy Gate.io spot, sell Gate.io futures)
    df['gateio_spot_vs_futures_arb'] = (
        (df['gateio_spot_bid_price'] - df['gateio_futures_ask_price']) /
        df['gateio_spot_bid_price'] * 100
    )
    
    # 3. Total arbitrage sum
    df['total_arbitrage_sum'] = (
        df['mexc_vs_gateio_futures_arb'] + df['gateio_spot_vs_futures_arb']
    )
    
    # 4. Apply fees
    df['total_arbitrage_sum_fees'] = df['total_arbitrage_sum'] - fees_pct
    
    return df


def get_current_arbitrage_spread(
    latest_book_tickers: pd.DataFrame,
    fees_pct: float = 0.2
) -> Dict[str, float]:
    """
    Calculate current arbitrage spread from latest book ticker data.
    
    Args:
        latest_book_tickers: DataFrame with latest book ticker data
            Should contain bid/ask prices for MEXC, Gate.io spot and futures
        fees_pct: Total fees percentage (default 0.2%)
    
    Returns:
        Dict with:
        - current_spread: Current total_arbitrage_sum_fees value
        - mexc_futures_arb: MEXC vs Gate.io futures component
        - spot_futures_arb: Gate.io spot vs futures component
        - timestamp: When this was calculated
    """
    if latest_book_tickers.empty:
        return {
            'current_spread': 0.0,
            'mexc_futures_arb': 0.0,
            'spot_futures_arb': 0.0,
            'timestamp': datetime.now(timezone.utc)
        }
    
    # Get the most recent row
    latest = latest_book_tickers.iloc[-1]
    
    # Calculate arbitrage components
    mexc_futures_arb = (
        (latest['gateio_futures_bid_price'] - latest['mexc_spot_ask_price']) /
        latest['gateio_futures_bid_price'] * 100
    )
    
    spot_futures_arb = (
        (latest['gateio_spot_bid_price'] - latest['gateio_futures_ask_price']) /
        latest['gateio_spot_bid_price'] * 100
    )
    
    # Total spread after fees
    total_sum = mexc_futures_arb + spot_futures_arb
    current_spread = total_sum - fees_pct
    
    return {
        'current_spread': float(current_spread),
        'mexc_futures_arb': float(mexc_futures_arb),
        'spot_futures_arb': float(spot_futures_arb),
        'total_sum': float(total_sum),
        'timestamp': latest.name if isinstance(latest.name, datetime) else datetime.now(timezone.utc)
    }


async def generate_arbitrage_signal_from_db(
    symbol: Symbol,
    lookback_hours: int = 24,
    entry_percentile: int = 10,
    exit_threshold: float = 0.05,
    position_open: bool = False,
    position_duration: int = 0,
    position_pnl: float = 0.0
) -> Dict[str, any]:
    """
    Generate arbitrage signal using database book ticker data.
    
    This combines:
    1. Load historical book ticker data from DB
    2. Calculate arbitrage spreads
    3. Get current spread
    4. Generate trading signal
    
    Args:
        symbol: Trading symbol
        lookback_hours: Hours of historical data for percentile calc (default 24)
        entry_percentile: Percentile threshold for entry (default 10)
        exit_threshold: Exit when spread below this (default 0.05%)
        position_open: Whether position currently open
        position_duration: How long position open (periods)
        position_pnl: Current P&L if position open
    
    Returns:
        Dict with:
        - signal: 'enter', 'exit', or 'none'
        - current_spread: Current arbitrage spread after fees
        - entry_threshold: Calculated percentile threshold
        - spread_percentile: Where current sits in distribution
        - historical_stats: Mean, std, min, max of historical spreads
    """
    from arbitrage_signals import generate_arbitrage_signal, SignalConfig
    
    # Load historical data
    end_date = datetime.now(timezone.utc)
    start_date = end_date - pd.Timedelta(hours=lookback_hours)
    
    print(f"📊 Loading {lookback_hours}h of data for {symbol.base}/{symbol.quote}")
    
    # Load market data from all 3 exchanges
    df = await load_market_data(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        exchanges=[ExchangeEnum.MEXC, ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES]
    )
    
    if df.empty:
        print("❌ No data available")
        return {
            'signal': 'none',
            'current_spread': 0.0,
            'error': 'No data available'
        }
    
    # Calculate arbitrage spreads
    df = calculate_total_arbitrage_spread(df)
    
    # Get historical spread array for percentile calculation
    historical_spreads = df['total_arbitrage_sum_fees'].dropna().values
    
    if len(historical_spreads) < 100:
        print(f"⚠️  Only {len(historical_spreads)} data points, need at least 100")
        return {
            'signal': 'none',
            'current_spread': 0.0,
            'error': f'Insufficient data: {len(historical_spreads)} points'
        }
    
    # Get current spread from latest data
    current_data = get_current_arbitrage_spread(df.tail(1))
    current_spread = current_data['current_spread']
    
    # Configure signal generation
    config = SignalConfig(
        entry_min_spread=0.1,
        entry_percentile=entry_percentile,
        exit_spread=exit_threshold,
        exit_max_duration=120,
        exit_stop_loss=-0.3
    )
    
    # Generate signal
    signal = generate_arbitrage_signal(
        current_spread=current_spread,
        spread_history=historical_spreads,
        position_open=position_open,
        position_duration=position_duration,
        position_pnl=position_pnl,
        config=config
    )
    
    # Calculate statistics
    entry_threshold = np.percentile(historical_spreads, 100 - entry_percentile)
    spread_percentile = (historical_spreads < current_spread).sum() / len(historical_spreads) * 100
    
    return {
        'signal': signal,
        'current_spread': current_spread,
        'mexc_futures_arb': current_data['mexc_futures_arb'],
        'spot_futures_arb': current_data['spot_futures_arb'],
        'entry_threshold': float(entry_threshold),
        'spread_percentile': float(spread_percentile),
        'timestamp': current_data['timestamp'],
        'historical_stats': {
            'mean': float(np.mean(historical_spreads)),
            'std': float(np.std(historical_spreads)),
            'min': float(np.min(historical_spreads)),
            'max': float(np.max(historical_spreads)),
            'count': len(historical_spreads)
        }
    }


if __name__ == "__main__":
    import asyncio

    async def main():
        # Example usage
        symbol = Symbol(base=AssetName("F"), quote=AssetName("USDT"))
        
        # Test 1: Load recent data and calculate spreads
        print("="*60)
        print("TEST 1: Calculate arbitrage spreads")
        end_date = datetime.now(timezone.utc)
        start_date = end_date - pd.Timedelta(hours=1)
        
        df = await load_market_data(symbol=symbol, start_date=start_date, end_date=end_date)
        df = calculate_total_arbitrage_spread(df)
        
        print(f"Data shape: {df.shape}")
        print("\nLast 5 arbitrage calculations:")
        print(df[['mexc_vs_gateio_futures_arb', 'gateio_spot_vs_futures_arb', 
                 'total_arbitrage_sum_fees']].tail())
        
        # Test 2: Get current spread
        print("\n" + "="*60)
        print("TEST 2: Current spread calculation")
        current = get_current_arbitrage_spread(df.tail(1))
        print(f"Current spread: {current['current_spread']:.3f}%")
        print(f"  MEXC→Futures: {current['mexc_futures_arb']:.3f}%")
        print(f"  Spot→Futures: {current['spot_futures_arb']:.3f}%")
        
        # Test 3: Generate signal
        print("\n" + "="*60)
        print("TEST 3: Signal generation")
        signal_data = await generate_arbitrage_signal_from_db(
            symbol=symbol,
            lookback_hours=24,
            position_open=False
        )
        
        print(f"Signal: {signal_data['signal'].upper()}")
        print(f"Current spread: {signal_data['current_spread']:.3f}%")
        print(f"Entry threshold: {signal_data['entry_threshold']:.3f}%")
        print(f"Percentile: {signal_data['spread_percentile']:.1f}%")
        print(f"Historical mean: {signal_data['historical_stats']['mean']:.3f}%")

    asyncio.run(main())