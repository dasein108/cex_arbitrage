
from db.database_manager import initialize_database_manager, close_database_manager
import signal
import asyncio
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd

from exchanges.structs import Symbol, AssetName, ExchangeEnum
from trading.analysis.data_loader import get_cached_book_ticker_data
from datetime import datetime, timezone, timedelta

def _signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    print(f"Received signal {signum}, initiating graceful shutdown...")
    asyncio.get_event_loop().run_until_complete(close_database_manager())


async def load_market_data():
    """Load market data with caching for both exchanges."""
    # Use the actual data we have in database
    end_date = datetime(2025, 10, 5, 12, 30, 0, tzinfo=timezone.utc)
    start_date = datetime(2025, 10, 5, 12, 9, 0, tzinfo=timezone.utc)
    symbol = Symbol(base=AssetName("MYX"), quote=AssetName("USDT"))  # Using MYX as it has most data
    print(f"\n🎯 Symbol: {symbol}")
    print(f"📅 Period: {start_date.strftime('%Y-%m-%d %H:%M')} to {end_date.strftime('%Y-%m-%d %H:%M')}")
    exchange_spot = ExchangeEnum.GATEIO_FUTURES.value  # Using same exchange data for demo
    exchange_futures = ExchangeEnum.GATEIO_FUTURES.value
    print(f"🏦 Simulating arbitrage with: {exchange_spot} data at different times")

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
        
        # Set timestamp as index first
        if 'timestamp' in df.columns:
            df = df.set_index('timestamp')
        
        # Remove specified columns 
        df = df.drop(columns=[col for col in columns_to_remove if col in df.columns], axis=1)
        df.columns = [f"{prefix}{col}" for col in df.columns]
        
        if isinstance(df.index, pd.DatetimeIndex):
            df.index = df.index.round("1s")

        return df

    # Add small artificial spread to simulate different exchanges (for demo purposes)
    spot_df['bid_price'] = spot_df['bid_price'] * 1.0002  # Simulate slightly higher spot prices
    spot_df['ask_price'] = spot_df['ask_price'] * 1.0002
    futures_df['bid_price'] = futures_df['bid_price'] * 0.9998  # Simulate slightly lower futures prices
    futures_df['ask_price'] = futures_df['ask_price'] * 0.9998
    
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


def calculate_and_plot_profitable_entry_points(df, fees, ax):
    """
    Plot bid/ask values for each exchange and mark optimal, profitable entry points.
    Formula: profitable = entry_point - fee < mean_exit_point - fee
    """
    total_fees = fees['spot_taker_fee'] + fees['futures_taker_fee']
    
    # Calculate mean exit points (where we close positions)
    # For Spot→Futures strategy: entry = spot_bid - fut_ask, exit = fut_bid - spot_ask
    # For Futures→Spot strategy: entry = fut_bid - spot_ask, exit = spot_bid - fut_ask
    
    mean_stf_exit = df['fut_spot_spread_prc'].mean()  # Mean exit for Spot→Futures
    mean_fts_exit = df['spot_fut_spread_prc'].mean()  # Mean exit for Futures→Spot
    
    # Intelligent sampling for large datasets - max 500 points for visualization
    data_len = len(df)
    if data_len > 500:
        sample_step = max(1, data_len // 500)
        sample_df = df.iloc[::sample_step].copy()
        print(f"  📊 Sampling every {sample_step}th point: {len(sample_df)} points for visualization")
    else:
        sample_df = df.copy()
    
    sample_indices = range(len(sample_df))
    
    # Plot bid/ask prices
    ax.plot(sample_indices, sample_df['spot_bid_price'], 'b-', alpha=0.7, label='Spot Bid', linewidth=1)
    ax.plot(sample_indices, sample_df['spot_ask_price'], 'b--', alpha=0.7, label='Spot Ask', linewidth=1)
    ax.plot(sample_indices, sample_df['fut_bid_price'], 'r-', alpha=0.7, label='Futures Bid', linewidth=1)
    ax.plot(sample_indices, sample_df['fut_ask_price'], 'r--', alpha=0.7, label='Futures Ask', linewidth=1)
    
    # Calculate profitability for each point
    # Spot→Futures entry profitability: (spot_bid - fut_ask - fees) vs (mean_exit - fees)
    stf_entry_net = sample_df['spot_fut_spread_prc'] - total_fees
    stf_exit_net = mean_stf_exit - total_fees
    stf_profitable = stf_entry_net > stf_exit_net
    
    # Futures→Spot entry profitability: (fut_bid - spot_ask - fees) vs (mean_exit - fees)  
    fts_entry_net = sample_df['fut_spot_spread_prc'] - total_fees
    fts_exit_net = mean_fts_exit - total_fees
    fts_profitable = fts_entry_net > fts_exit_net
    
    # Mark profitable entry points
    profitable_stf_indices = [i for i, profitable in enumerate(stf_profitable) if profitable]
    profitable_fts_indices = [i for i, profitable in enumerate(fts_profitable) if profitable]
    
    # Limit scatter points for performance (max 100 points each)
    max_scatter_points = 100
    
    # Mark optimal Spot→Futures entries (green circles)
    if profitable_stf_indices:
        # Sample if too many points
        if len(profitable_stf_indices) > max_scatter_points:
            step = len(profitable_stf_indices) // max_scatter_points
            profitable_stf_indices = profitable_stf_indices[::step]
        
        stf_idx_array = np.array(profitable_stf_indices)
        ax.scatter(stf_idx_array, sample_df.iloc[stf_idx_array]['spot_bid_price'].values, 
                  color='green', s=30, marker='o', alpha=0.8, zorder=5)
        ax.scatter(stf_idx_array, sample_df.iloc[stf_idx_array]['fut_ask_price'].values, 
                  color='green', s=30, marker='o', alpha=0.8, zorder=5)
    
    # Mark optimal Futures→Spot entries (orange triangles)
    if profitable_fts_indices:
        # Sample if too many points
        if len(profitable_fts_indices) > max_scatter_points:
            step = len(profitable_fts_indices) // max_scatter_points
            profitable_fts_indices = profitable_fts_indices[::step]
        
        fts_idx_array = np.array(profitable_fts_indices)
        ax.scatter(fts_idx_array, sample_df.iloc[fts_idx_array]['fut_bid_price'].values, 
                  color='orange', s=30, marker='^', alpha=0.8, zorder=5)
        ax.scatter(fts_idx_array, sample_df.iloc[fts_idx_array]['spot_ask_price'].values, 
                  color='orange', s=30, marker='^', alpha=0.8, zorder=5)
    
    # Create custom legend for entry points
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], color='blue', linestyle='-', label='Spot Bid'),
        Line2D([0], [0], color='blue', linestyle='--', label='Spot Ask'),
        Line2D([0], [0], color='red', linestyle='-', label='Futures Bid'),
        Line2D([0], [0], color='red', linestyle='--', label='Futures Ask'),
        Line2D([0], [0], marker='o', color='green', linestyle='None', 
               markersize=8, label=f'Profitable STF Entry ({len(profitable_stf_indices)})'),
        Line2D([0], [0], marker='^', color='orange', linestyle='None', 
               markersize=8, label=f'Profitable FTS Entry ({len(profitable_fts_indices)})')
    ]
    
    ax.legend(handles=legend_elements, loc='upper left', fontsize=9)
    ax.set_xlabel('Time Sample (every 10th point)')
    ax.set_ylabel('Price (USDT)')
    ax.set_title('Bid/Ask Prices with Profitable Entry Points\n(Entry-Fee < Mean_Exit-Fee)')
    ax.grid(True, alpha=0.3)
    
    # Add statistics text box
    stats_text = f'''Entry Point Analysis:
• STF Mean Exit: {mean_stf_exit:.3f}%
• FTS Mean Exit: {mean_fts_exit:.3f}%
• Total Fees: {total_fees:.2f}%
• STF Profitable: {len(profitable_stf_indices)}/{len(sample_df)}
• FTS Profitable: {len(profitable_fts_indices)}/{len(sample_df)}'''
    
    ax.text(0.02, 0.98, stats_text, transform=ax.transAxes, fontsize=9,
           verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))


def create_spread_visualizations(df, fees):
    """Create comprehensive spread analysis visualizations."""
    print(f"\n📈 Creating comprehensive visualization for {len(df):,} data points...")
    print("    This may take a moment for large datasets...")
    
    plt.style.use('seaborn-v0_8')
    fig = plt.figure(figsize=(20, 16))
    fig.suptitle(f'Arbitrage Spread Analysis - MYX/USDT ({len(df):,} data points)', fontsize=16)
    
    # Create custom grid layout
    gs = fig.add_gridspec(3, 4, height_ratios=[1, 1, 1], width_ratios=[1, 1, 1, 1])
    
    # Create axes with custom layout
    ax_spread_dist = fig.add_subplot(gs[0, 0])           # Spread Distribution
    ax_bid_ask = fig.add_subplot(gs[0, 1:])              # Bid/Ask full width (3 columns)
    ax_time_series = fig.add_subplot(gs[1, 0])           # Time Series
    ax_optimal_thresh = fig.add_subplot(gs[1, 1])        # Optimal Thresholds
    ax_heatmap = fig.add_subplot(gs[1, 2])               # Frequency Heatmap
    ax_summary = fig.add_subplot(gs[2, :])               # Summary Statistics full width
    
    # Calculate total fees for round-trip
    total_fees = fees['spot_taker_fee'] + fees['futures_taker_fee']  # 0.1% total
    
    # 1. Spread Distribution Histogram (Optimized for large datasets)
    print("  📊 Creating spread distribution...")
    
    # Adaptive bin count for large datasets
    bin_count = min(100, max(30, len(df) // 2000))  # Scale bins with data size
    
    ax_spread_dist.hist(df['spot_fut_spread_prc'], bins=bin_count, alpha=0.7, label='Spot→Futures', color='blue')
    ax_spread_dist.hist(df['fut_spot_spread_prc'], bins=bin_count, alpha=0.7, label='Futures→Spot', color='red')
    ax_spread_dist.axvline(total_fees, color='black', linestyle='--', label=f'Min Profitable: {total_fees:.2f}%')
    ax_spread_dist.set_xlabel('Spread %')
    ax_spread_dist.set_ylabel('Frequency')
    ax_spread_dist.set_title(f'Spread Distribution ({len(df):,} points)')
    ax_spread_dist.legend()
    ax_spread_dist.grid(True, alpha=0.3)
    
    # 2. Bid/Ask Values with Profitable Entry Points (Full Width)
    calculate_and_plot_profitable_entry_points(df, fees, ax_bid_ask)
    
    # 3. Time Series of Spreads (Optimized resampling for large datasets)
    print("  📈 Creating time series analysis...")
    
    # Intelligent resampling based on data size
    data_hours = (df.index[-1] - df.index[0]).total_seconds() / 3600
    if len(df) > 10000:
        resample_freq = '30min'  # Larger intervals for big datasets
    elif data_hours > 24:
        resample_freq = '15min'  # Medium intervals for day+ data
    else:
        resample_freq = '5min'   # Fine intervals for small data
    
    time_sample = df.resample(resample_freq).mean()
    ax_time_series.plot(time_sample.index, time_sample['spot_fut_spread_prc'], label='Spot→Futures', alpha=0.8)
    ax_time_series.plot(time_sample.index, time_sample['fut_spot_spread_prc'], label='Futures→Spot', alpha=0.8)
    ax_time_series.axhline(total_fees, color='black', linestyle='--', alpha=0.7, label='Min Profitable')
    ax_time_series.set_xlabel('Time')
    ax_time_series.set_ylabel('Spread %')
    ax_time_series.set_title(f'Spread Evolution Over Time ({resample_freq} intervals)')
    ax_time_series.legend()
    ax_time_series.grid(True, alpha=0.3)
    plt.setp(ax_time_series.xaxis.get_majorticklabels(), rotation=45)
    
    # 4. Optimal Entry Thresholds Analysis (Optimized for large datasets)
    print("  📈 Calculating optimal thresholds...")
    
    # Use pre-computed arrays for faster vectorized operations
    stf_spreads = df['spot_fut_spread_prc'].values
    fts_spreads = df['fut_spot_spread_prc'].values
    
    # Optimized threshold range - fewer points for faster computation
    thresholds = np.arange(0.05, 0.5, 0.05)  # Wider steps for speed
    
    stf_profits = []
    fts_profits = []
    
    for t in thresholds:
        # Vectorized operations for speed
        stf_mask = stf_spreads > t
        fts_mask = fts_spreads > t
        
        stf_count = stf_mask.sum()
        fts_count = fts_mask.sum()
        
        if stf_count > 0:
            stf_mean = stf_spreads[stf_mask].mean()
            stf_profits.append(stf_count * (stf_mean - total_fees))
        else:
            stf_profits.append(0)
            
        if fts_count > 0:
            fts_mean = fts_spreads[fts_mask].mean()
            fts_profits.append(fts_count * (fts_mean - total_fees))
        else:
            fts_profits.append(0)
    
    ax_optimal_thresh.plot(thresholds, stf_profits, 'o-', label='Spot→Futures', color='blue')
    ax_optimal_thresh.plot(thresholds, fts_profits, 'o-', label='Futures→Spot', color='red')
    
    # Mark optimal points
    if stf_profits: 
        optimal_stf_idx = np.argmax(stf_profits)
        ax_optimal_thresh.axvline(thresholds[optimal_stf_idx], color='blue', linestyle=':', alpha=0.7)
        ax_optimal_thresh.text(thresholds[optimal_stf_idx], max(stf_profits)*0.8, f'Opt: {thresholds[optimal_stf_idx]:.2f}%', 
                      rotation=90, color='blue', ha='right')
    
    if fts_profits:
        optimal_fts_idx = np.argmax(fts_profits)
        ax_optimal_thresh.axvline(thresholds[optimal_fts_idx], color='red', linestyle=':', alpha=0.7)
        ax_optimal_thresh.text(thresholds[optimal_fts_idx], max(fts_profits)*0.8, f'Opt: {thresholds[optimal_fts_idx]:.2f}%', 
                      rotation=90, color='red', ha='left')
    
    ax_optimal_thresh.set_xlabel('Entry Threshold %')
    ax_optimal_thresh.set_ylabel('Expected Profit')
    ax_optimal_thresh.set_title('Optimal Entry Thresholds')
    ax_optimal_thresh.legend()
    ax_optimal_thresh.grid(True, alpha=0.3)
    
    # 5. Spread vs Frequency Heatmap (Optimized for large datasets)
    print("  📈 Creating frequency heatmap...")
    
    # Adaptive bin size for large datasets
    bin_step = 0.02 if len(df) > 50000 else 0.01
    spot_fut_vals, spot_fut_cnts = group_spread_bins(df['spot_fut_spread_prc'], step=bin_step, threshold=20)
    fut_spot_vals, fut_spot_cnts = group_spread_bins(df['fut_spot_spread_prc'], step=bin_step, threshold=20)
    
    # Create frequency data
    spread_data = []
    for val, cnt in zip(spot_fut_vals, spot_fut_cnts):
        spread_data.append({'Spread': val, 'Count': cnt, 'Direction': 'Spot→Futures'})
    for val, cnt in zip(fut_spot_vals, fut_spot_cnts):
        spread_data.append({'Spread': val, 'Count': cnt, 'Direction': 'Futures→Spot'})
    
    spread_df = pd.DataFrame(spread_data)
    pivot_data = spread_df.pivot(index='Spread', columns='Direction', values='Count').fillna(0)
    
    sns.heatmap(pivot_data.T, ax=ax_heatmap, cmap='YlOrRd', annot=False, cbar_kws={'label': 'Frequency'})
    ax_heatmap.axvline(total_fees, color='blue', linewidth=2, label='Min Profitable')
    ax_heatmap.set_title(f'Spread Frequency Heatmap (bins: {bin_step:.2f}%)')
    ax_heatmap.set_xlabel('Spread %')
    
    # 6. Summary Statistics Table (Full Width)
    ax_summary.axis('off')
    
    # Calculate key metrics
    stf_mean = df['spot_fut_spread_prc'].mean()
    fts_mean = df['fut_spot_spread_prc'].mean()
    stf_profitable_pct = (df['spot_fut_spread_prc'] > total_fees).mean() * 100
    fts_profitable_pct = (df['fut_spot_spread_prc'] > total_fees).mean() * 100
    
    if stf_profits:
        optimal_stf_threshold = thresholds[np.argmax(stf_profits)]
    else:
        optimal_stf_threshold = 0
        
    if fts_profits:
        optimal_fts_threshold = thresholds[np.argmax(fts_profits)]
    else:
        optimal_fts_threshold = 0
    
    summary_text = f'''
ARBITRAGE ANALYSIS SUMMARY

💰 Fee Structure:
  • Total Round-trip: {total_fees:.2f}%
  • MEXC Spot Taker: {fees['spot_taker_fee']:.2f}%
  • Gate.io Futures Taker: {fees['futures_taker_fee']:.2f}%

📊 Spread Statistics:
  • Spot→Futures Avg: {stf_mean:.3f}%
  • Futures→Spot Avg: {fts_mean:.3f}%

🎯 Profitable Opportunities:
  • Spot→Futures: {stf_profitable_pct:.1f}%
  • Futures→Spot: {fts_profitable_pct:.1f}%

⚡ Optimal Entry Thresholds:
  • Spot→Futures: {optimal_stf_threshold:.2f}%
  • Futures→Spot: {optimal_fts_threshold:.2f}%

📈 Data Points: {len(df):,} samples
    '''
    
    ax_summary.text(0.1, 0.9, summary_text, transform=ax_summary.transAxes, 
                  fontsize=11, verticalalignment='top', fontfamily='monospace',
                  bbox=dict(boxstyle='round', facecolor='lightgray', alpha=0.8))
    
    plt.tight_layout()
    plt.savefig('arbitrage_spread_analysis.png', dpi=300, bbox_inches='tight')
    plt.show()
    
    return optimal_stf_threshold, optimal_fts_threshold


def quick_spread_analysis(df, fees):
    """Quick 5-line analysis for immediate insights."""
    total_fees = fees['spot_taker_fee'] + fees['futures_taker_fee']
    stf_opportunities = (df['spot_fut_spread_prc'] > total_fees).mean() * 100
    fts_opportunities = (df['fut_spot_spread_prc'] > total_fees).mean() * 100
    best_stf_spread = df['spot_fut_spread_prc'].quantile(0.9)  # Top 10% spreads
    best_fts_spread = df['fut_spot_spread_prc'].quantile(0.9)  # Top 10% spreads
    
    print(f"💰 QUICK ANALYSIS: {stf_opportunities:.1f}% STF opportunities, {fts_opportunities:.1f}% FTS opportunities")
    print(f"🎯 TOP 10% SPREADS: STF={best_stf_spread:.3f}%, FTS={best_fts_spread:.3f}% (vs {total_fees:.2f}% fees)")
    return best_stf_spread, best_fts_spread


async def main():
    """Main function to run the spread research analysis."""
    df = await load_market_data()
    print("Columns:", list(df.columns))
    # Columns: ['spot_bid_price', 'spot_bid_qty', 'spot_ask_price', 'spot_ask_qty', 'spot_mid_price', 'spot_spread_bps',
    # 'fut_bid_price', 'fut_bid_qty', 'fut_ask_price', 'fut_ask_qty', 'fut_mid_price', 'fut_spread_bps']
    # to buy spot and sell futures

    fees = {
        "spot_maker_fee": 0.0,  # MEXC spot maker
        "spot_taker_fee": 0.05,  # MEXC spot taker
        "futures_maker_fee": 0.02,  # Gate.io futures maker
        "futures_taker_fee": 0.05,  # Gate.io futures taker
    }

    # entry spread
    df['spot_fut_spread_prc'] = ((df['spot_bid_price'] - df['fut_ask_price']) / df['spot_bid_price']) * 100.0
    # exit spread
    df['fut_spot_spread_prc'] = ((df['fut_bid_price'] - df['spot_ask_price']) / df['fut_bid_price']) * 100.0

    max_spot_fut = df['spot_fut_spread_prc'].max()
    min_spot_fut = df['spot_fut_spread_prc'].min()
    mean_spot_fut = df['spot_fut_spread_prc'].mean()
    max_fut_spot = df['fut_spot_spread_prc'].max()
    min_fut_spot = df['fut_spot_spread_prc'].min()
    mean_fut_spot = df['fut_spot_spread_prc'].mean()

    spot_fut_vals, spot_fut_cnts = group_spread_bins(df['spot_fut_spread_prc'])
    fut_spot_vals, fut_spot_cnts = group_spread_bins(df['fut_spot_spread_prc'])
    spot_fut_dict = dict(zip(spot_fut_vals, spot_fut_cnts))
    fut_spot_dict = dict(zip(fut_spot_vals, fut_spot_cnts))

    print("Spot-Futures Spread counts (step 0.01):", spot_fut_dict)
    print("Futures-Spot Spread counts (step 0.01):", fut_spot_dict)
    
    # Quick analysis (5 lines of insight)
    quick_spread_analysis(df, fees)
    
    # Create comprehensive visualizations
    print("\n📈 Creating spread analysis visualizations...")
    optimal_stf, optimal_fts = create_spread_visualizations(df, fees)
    
    print(f"\n🎯 OPTIMAL TRADING THRESHOLDS:")
    print(f"   • Spot→Futures Entry: {optimal_stf:.2f}% (Buy spot, sell futures)")
    print(f"   • Futures→Spot Entry: {optimal_fts:.2f}% (Buy futures, sell spot)")
    print(f"   • Total Fees: {fees['spot_taker_fee'] + fees['futures_taker_fee']:.2f}%")
    print(f"\n💡 Recommendation: Set entry thresholds above optimal values for safety margin")
    print(f"   • Conservative STF: {optimal_stf + 0.02:.2f}%")
    print(f"   • Conservative FTS: {optimal_fts + 0.02:.2f}%")
    print(f"\n📊 Chart saved as: arbitrage_spread_analysis.png")




if __name__ == "__main__":
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    asyncio.run(main())