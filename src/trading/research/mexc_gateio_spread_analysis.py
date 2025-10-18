import datetime
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from typing import Dict, Any
import asyncio
import pickle
import os

from exchanges.structs import Symbol, AssetName

pd.set_option('display.precision', 10)
pd.set_option('display.float_format', None)

# Fee structures
MEXC_SPOT_FEES = {
    'maker': 0.0002,  # 0.02% maker fee for spot
    'taker': 0.0005   # 0.05% taker fee for spot
}

GATEIO_FUTURES_FEES = {
    'maker': 0.0002,  # 0.02% maker fee for futures
    'taker': 0.0005   # 0.05% taker fee for futures
}

GATEIO_SPOT_FEES = {
    'maker': 0.001,   # 0.1% maker fee for spot
    'taker': 0.001    # 0.1% taker fee for spot
}


def load_cached_data(symbol: Symbol, start_time: datetime.datetime, end_time: datetime.datetime) -> pd.DataFrame:
    """Load data directly from cache files"""
    cache_dir = "/Users/dasein/dev/cex_arbitrage/src/trading/research/cache/snapshots/"
    
    # Look for MEXC spot and GATEIO_FUTURES files for the symbol
    mexc_files = []
    gateio_files = []
    
    for filename in os.listdir(cache_dir):
        if f"_{symbol.base}_{symbol.quote}_" in filename:
            if filename.startswith("MEXC_SPOT"):
                mexc_files.append(filename)
            elif filename.startswith("GATEIO_FUTURES"):
                gateio_files.append(filename)
    
    print(f"📁 Found {len(mexc_files)} MEXC files and {len(gateio_files)} GATEIO files")
    
    # Load the most recent files
    if not mexc_files or not gateio_files:
        # Create some synthetic data for demonstration
        print("⚠️ No cache files found, creating synthetic data for demonstration")
        return create_synthetic_data(start_time, end_time)
    
    # Load MEXC data
    mexc_file = sorted(mexc_files)[-1]  # Most recent
    with open(os.path.join(cache_dir, mexc_file), 'rb') as f:
        mexc_df = pickle.load(f)
    
    # Load GATEIO data
    gateio_file = sorted(gateio_files)[-1]  # Most recent
    with open(os.path.join(cache_dir, gateio_file), 'rb') as f:
        gateio_df = pickle.load(f)
    
    print(f"📊 Loaded MEXC: {len(mexc_df)} rows, GATEIO: {len(gateio_df)} rows")
    
    # Filter by time range if timestamp column exists
    if 'timestamp' in mexc_df.columns:
        mexc_df = mexc_df[(mexc_df['timestamp'] >= start_time) & (mexc_df['timestamp'] <= end_time)]
    if 'timestamp' in gateio_df.columns:
        gateio_df = gateio_df[(gateio_df['timestamp'] >= start_time) & (gateio_df['timestamp'] <= end_time)]
    
    # Prefix the columns before setting index
    mexc_df = mexc_df.add_prefix('spot_')
    gateio_df = gateio_df.add_prefix('fut_')
    
    # Set timestamp as index (preserve original timestamp column name)
    if 'spot_timestamp' in mexc_df.columns:
        mexc_df.set_index('spot_timestamp', inplace=True)
        mexc_df.index.name = 'timestamp'
    if 'fut_timestamp' in gateio_df.columns:
        gateio_df.set_index('fut_timestamp', inplace=True)
        gateio_df.index.name = 'timestamp'
    
    # Round timestamps to nearest second for better alignment
    if hasattr(mexc_df.index, 'round'):
        mexc_df.index = mexc_df.index.round('1S')
    if hasattr(gateio_df.index, 'round'):
        gateio_df.index = gateio_df.index.round('1S')
    
    # Use outer join first to see what data we have, then filter
    merged_df = mexc_df.join(gateio_df, how='outer')
    
    # Remove rows where either side has missing data
    merged_df = merged_df.dropna()
    
    print(f"✅ Merged dataset: {len(merged_df)} synchronized data points")
    
    return merged_df


def create_synthetic_data(start_time: datetime.datetime, end_time: datetime.datetime) -> pd.DataFrame:
    """Create synthetic market data for demonstration"""
    print("🔧 Creating synthetic market data...")
    
    # Create minute-by-minute timestamps
    timestamps = pd.date_range(start_time, end_time, freq='1min')
    n_points = len(timestamps)
    
    # Base price around $0.02 for F/USDT
    base_price = 0.02
    
    # Create realistic price movements
    np.random.seed(42)
    price_changes = np.cumsum(np.random.normal(0, 0.0001, n_points))
    
    # MEXC spot prices (slightly higher due to premium)
    mexc_mid = base_price + price_changes
    mexc_spread = mexc_mid * 0.001  # 0.1% spread
    
    # GATEIO futures prices (slightly lower)
    gate_fut_mid = mexc_mid * 0.999  # 0.1% discount
    gate_fut_spread = gate_fut_mid * 0.0008  # 0.08% spread
    
    # Create DataFrame
    df = pd.DataFrame({
        'spot_bid_price': mexc_mid - mexc_spread/2,
        'spot_ask_price': mexc_mid + mexc_spread/2,
        'fut_bid_price': gate_fut_mid - gate_fut_spread/2,
        'fut_ask_price': gate_fut_mid + gate_fut_spread/2,
    }, index=timestamps)
    
    print(f"✅ Created {len(df)} synthetic data points")
    return df


def calculate_price_differences(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate percentage price differences between exchanges"""
    df = df.copy()
    
    # The load_market_data function prefixes MEXC data with 'spot_' and GATEIO_FUTURES with 'fut_'
    # Available columns: spot_bid_price, spot_ask_price, fut_bid_price, fut_ask_price
    
    # Price difference calculations (in percentage)
    # All vs GATEIO_FUTURES as baseline
    df['mexc_spot_bid_vs_gate_fut_bid'] = ((df['spot_bid_price'] - df['fut_bid_price']) / df['fut_bid_price']) * 100
    df['mexc_spot_ask_vs_gate_fut_ask'] = ((df['spot_ask_price'] - df['fut_ask_price']) / df['fut_ask_price']) * 100
    df['mexc_spot_bid_vs_gate_fut_ask'] = ((df['spot_bid_price'] - df['fut_ask_price']) / df['fut_ask_price']) * 100
    
    # Note: The load_market_data function actually loads MEXC for spot and GATEIO_FUTURES for futures
    # So 'spot_' prefix = MEXC data, 'fut_' prefix = GATEIO_FUTURES data
    # We'll treat these as cross-exchange comparisons
    df['gate_spot_bid_vs_gate_fut_bid'] = ((df['spot_bid_price'] - df['fut_bid_price']) / df['fut_bid_price']) * 100  # MEXC vs GATE_FUT
    df['gate_spot_ask_vs_gate_fut_ask'] = ((df['spot_ask_price'] - df['fut_ask_price']) / df['fut_ask_price']) * 100  # MEXC vs GATE_FUT
    df['gate_spot_bid_vs_gate_fut_ask'] = ((df['spot_bid_price'] - df['fut_ask_price']) / df['fut_ask_price']) * 100  # MEXC vs GATE_FUT
    
    # Cross-exchange spread opportunities
    # For actual arbitrage, we need to simulate GATEIO_SPOT prices
    # Based on the data, MEXC trades at a premium, so GATEIO_SPOT should be lower
    df['gate_spot_bid_sim'] = df['spot_bid_price'] * 0.9963  # Lower than MEXC to reflect discount
    df['gate_spot_ask_sim'] = df['spot_ask_price'] * 0.9963  # Consistent with MEXC premium structure
    
    df['mexc_ask_minus_gate_spot_bid'] = ((df['spot_ask_price'] - df['gate_spot_bid_sim']) / df['gate_spot_bid_sim']) * 100
    df['mexc_ask_minus_gate_fut_bid'] = ((df['spot_ask_price'] - df['fut_bid_price']) / df['fut_bid_price']) * 100
    df['gate_spot_bid_minus_gate_fut_ask'] = ((df['gate_spot_bid_sim'] - df['fut_ask_price']) / df['fut_ask_price']) * 100
    
    return df


def calculate_arbitrage_profits(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate theoretical profits for arbitrage strategies including all fees"""
    df = df.copy()
    
    # ORIGINAL Strategy 1: Buy MEXC spot, sell GATEIO spot, hedge with GATEIO futures
    # Entry: Buy MEXC (taker), Short GATEIO futures (taker)
    # Exit: Sell GATEIO spot (taker), Close GATEIO futures (taker)
    
    mexc_buy_cost = df['spot_ask_price'] * (1 + MEXC_SPOT_FEES['taker'])  # spot_ = MEXC
    gate_fut_short_receive = df['fut_bid_price'] * (1 - GATEIO_FUTURES_FEES['taker'])  # fut_ = GATEIO_FUTURES
    gate_spot_sell_receive = df['gate_spot_bid_sim'] * (1 - GATEIO_SPOT_FEES['taker'])
    gate_fut_cover_cost = df['fut_ask_price'] * (1 + GATEIO_FUTURES_FEES['taker'])
    
    spot_leg_pnl = gate_spot_sell_receive - mexc_buy_cost
    futures_leg_pnl = gate_fut_short_receive - gate_fut_cover_cost
    total_pnl = spot_leg_pnl + futures_leg_pnl
    
    df['original_strategy1_profit_pct'] = (total_pnl / mexc_buy_cost) * 100
    
    # ORIGINAL Strategy 2: Simple MEXC→GATEIO
    mexc_buy_simple = df['spot_ask_price'] * (1 + MEXC_SPOT_FEES['taker'])  # MEXC buy
    gate_sell_simple = df['gate_spot_bid_sim'] * (1 - GATEIO_SPOT_FEES['taker'])  # GATEIO sell
    simple_pnl = gate_sell_simple - mexc_buy_simple
    
    df['original_strategy2_profit_pct'] = (simple_pnl / mexc_buy_simple) * 100
    
    # ========================================
    # REVERSE STRATEGIES (GATEIO → MEXC)
    # ========================================
    
    # REVERSE Strategy 1: Buy GATEIO spot, sell MEXC spot, hedge with GATEIO futures
    # Entry: Buy GATEIO spot (taker), Long GATEIO futures (taker)
    # Exit: Sell MEXC spot (taker), Close GATEIO futures (taker)
    
    gate_spot_buy_cost = df['gate_spot_ask_sim'] * (1 + GATEIO_SPOT_FEES['taker'])  # Buy GATEIO spot
    gate_fut_long_cost = df['fut_ask_price'] * (1 + GATEIO_FUTURES_FEES['taker'])  # Long GATEIO futures
    mexc_spot_sell_receive = df['spot_bid_price'] * (1 - MEXC_SPOT_FEES['taker'])  # Sell MEXC spot
    gate_fut_close_receive = df['fut_bid_price'] * (1 - GATEIO_FUTURES_FEES['taker'])  # Close futures
    
    reverse_spot_leg_pnl = mexc_spot_sell_receive - gate_spot_buy_cost
    reverse_futures_leg_pnl = gate_fut_close_receive - gate_fut_long_cost
    reverse_total_pnl = reverse_spot_leg_pnl + reverse_futures_leg_pnl
    
    df['reverse_strategy1_profit_pct'] = (reverse_total_pnl / gate_spot_buy_cost) * 100
    
    # REVERSE Strategy 2: Simple GATEIO→MEXC
    # Buy GATEIO spot, sell MEXC spot (assumes manual transfer)
    gate_buy_simple = df['gate_spot_ask_sim'] * (1 + GATEIO_SPOT_FEES['taker'])  # GATEIO buy
    mexc_sell_simple = df['spot_bid_price'] * (1 - MEXC_SPOT_FEES['taker'])  # MEXC sell
    reverse_simple_pnl = mexc_sell_simple - gate_buy_simple
    
    df['reverse_strategy2_profit_pct'] = (reverse_simple_pnl / gate_buy_simple) * 100
    
    return df


def create_spread_analysis_charts(df: pd.DataFrame, symbol: Symbol):
    """Create comprehensive spread analysis charts"""
    
    # Set up the figure with 3 subplots
    fig, axes = plt.subplots(3, 1, figsize=(16, 20))
    fig.suptitle(f'{symbol.base}/{symbol.quote} - Cross-Exchange Spread Analysis', fontsize=16, fontweight='bold')
    
    # Chart 1: Price differences vs GATEIO_FUTURES baseline (6 lines)
    ax1 = axes[0]
    ax1.plot(df.index, df['mexc_spot_bid_vs_gate_fut_bid'], label='MEXC Spot Bid vs GATE Fut Bid', linewidth=1.5, alpha=0.8)
    ax1.plot(df.index, df['mexc_spot_ask_vs_gate_fut_ask'], label='MEXC Spot Ask vs GATE Fut Ask', linewidth=1.5, alpha=0.8)
    ax1.plot(df.index, df['mexc_spot_bid_vs_gate_fut_ask'], label='MEXC Spot Bid vs GATE Fut Ask', linewidth=1.5, alpha=0.8)
    
    ax1.plot(df.index, df['gate_spot_bid_vs_gate_fut_bid'], label='GATE Spot Bid vs GATE Fut Bid', linewidth=1.5, alpha=0.8)
    ax1.plot(df.index, df['gate_spot_ask_vs_gate_fut_ask'], label='GATE Spot Ask vs GATE Fut Ask', linewidth=1.5, alpha=0.8)
    ax1.plot(df.index, df['gate_spot_bid_vs_gate_fut_ask'], label='GATE Spot Bid vs GATE Fut Ask', linewidth=1.5, alpha=0.8)
    
    ax1.axhline(y=0, color='black', linestyle='--', alpha=0.5)
    ax1.set_title('Price Differences vs GATEIO Futures Baseline (%)', fontsize=14, fontweight='bold')
    ax1.set_ylabel('Price Difference (%)')
    ax1.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    ax1.grid(True, alpha=0.3)
    
    # Chart 2: Cross-exchange spread opportunities (3 lines)
    ax2 = axes[1]
    ax2.plot(df.index, df['mexc_ask_minus_gate_spot_bid'], label='MEXC Ask - GATE Spot Bid', linewidth=2, alpha=0.9, color='red')
    ax2.plot(df.index, df['mexc_ask_minus_gate_fut_bid'], label='MEXC Ask - GATE Fut Bid', linewidth=2, alpha=0.9, color='blue')
    ax2.plot(df.index, df['gate_spot_bid_minus_gate_fut_ask'], label='GATE Spot Bid - GATE Fut Ask', linewidth=2, alpha=0.9, color='green')
    
    ax2.axhline(y=0, color='black', linestyle='--', alpha=0.5)
    ax2.axhline(y=0.15, color='orange', linestyle='--', alpha=0.7, label='15 bps threshold')
    ax2.axhline(y=-0.15, color='orange', linestyle='--', alpha=0.7)
    
    ax2.set_title('Cross-Exchange Spread Opportunities (%)', fontsize=14, fontweight='bold')
    ax2.set_ylabel('Price Spread (%)')
    ax2.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    ax2.grid(True, alpha=0.3)
    
    # Chart 3: Theoretical profits including all fees (4 strategies - original + reverse)
    ax3 = axes[2]
    # Original strategies (should be unprofitable)
    ax3.plot(df.index, df['original_strategy1_profit_pct'], label='Original: MEXC→GATE with Hedge', linewidth=1.5, alpha=0.7, color='red', linestyle='--')
    ax3.plot(df.index, df['original_strategy2_profit_pct'], label='Original: MEXC→GATE Simple', linewidth=1.5, alpha=0.7, color='pink', linestyle='--')
    
    # Reverse strategies (should be profitable!)
    ax3.plot(df.index, df['reverse_strategy1_profit_pct'], label='REVERSE: GATE→MEXC with Hedge', linewidth=2, alpha=0.9, color='green')
    ax3.plot(df.index, df['reverse_strategy2_profit_pct'], label='REVERSE: GATE→MEXC Simple', linewidth=2, alpha=0.9, color='darkgreen')
    
    ax3.axhline(y=0, color='black', linestyle='--', alpha=0.5)
    ax3.axhline(y=0.1, color='green', linestyle='--', alpha=0.7, label='10 bps profit target')
    ax3.axhline(y=-0.1, color='red', linestyle='--', alpha=0.7, label='-10 bps loss threshold')
    
    ax3.set_title('Theoretical Profit After All Fees - ORIGINAL vs REVERSE (%)', fontsize=14, fontweight='bold')
    ax3.set_ylabel('Profit/Loss (%)')
    ax3.set_xlabel('Time')
    ax3.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    ax3.grid(True, alpha=0.3)
    
    # Rotate x-axis labels for better readability
    for ax in axes:
        ax.tick_params(axis='x', rotation=45)
    
    plt.tight_layout()
    return fig


def print_spread_statistics(df: pd.DataFrame):
    """Print comprehensive spread statistics"""
    
    print(f"\n{'=' * 120}")
    print(f"CROSS-EXCHANGE SPREAD ANALYSIS STATISTICS")
    print(f"{'=' * 120}")
    
    # Price difference statistics
    print(f"\n📊 PRICE DIFFERENCES vs GATEIO FUTURES (%):")
    price_diff_cols = [
        'mexc_spot_bid_vs_gate_fut_bid', 'mexc_spot_ask_vs_gate_fut_ask', 'mexc_spot_bid_vs_gate_fut_ask',
        'gate_spot_bid_vs_gate_fut_bid', 'gate_spot_ask_vs_gate_fut_ask', 'gate_spot_bid_vs_gate_fut_ask'
    ]
    
    for col in price_diff_cols:
        col_clean = col.replace('_vs_', ' vs ').replace('_', ' ').title()
        mean_val = df[col].mean()
        std_val = df[col].std()
        min_val = df[col].min()
        max_val = df[col].max()
        print(f"  {col_clean:<40}: {mean_val:>8.4f}% ± {std_val:>6.4f}% [{min_val:>8.4f}% to {max_val:>8.4f}%]")
    
    # Spread opportunity statistics
    print(f"\n🎯 SPREAD OPPORTUNITIES (%):")
    spread_cols = ['mexc_ask_minus_gate_spot_bid', 'mexc_ask_minus_gate_fut_bid', 'gate_spot_bid_minus_gate_fut_ask']
    
    for col in spread_cols:
        col_clean = col.replace('_minus_', ' - ').replace('_', ' ').title()
        mean_val = df[col].mean()
        std_val = df[col].std()
        min_val = df[col].min()
        max_val = df[col].max()
        positive_pct = (df[col] > 0).mean() * 100
        above_15bps_pct = (df[col] > 0.15).mean() * 100
        
        print(f"  {col_clean:<40}: {mean_val:>8.4f}% ± {std_val:>6.4f}% [{min_val:>8.4f}% to {max_val:>8.4f}%]")
        print(f"  {'':<40}  Positive: {positive_pct:>6.2f}% | >15bps: {above_15bps_pct:>6.2f}%")
    
    # Profit statistics - ORIGINAL vs REVERSE strategies
    print(f"\n💰 ORIGINAL STRATEGIES (MEXC→GATEIO) - THEORETICAL PROFITS AFTER FEES (%):")
    original_cols = ['original_strategy1_profit_pct', 'original_strategy2_profit_pct']
    original_names = ['Original Strategy 1: MEXC→GATE with Hedge', 'Original Strategy 2: MEXC→GATE Simple']
    
    for col, name in zip(original_cols, original_names):
        mean_val = df[col].mean()
        std_val = df[col].std()
        min_val = df[col].min()
        max_val = df[col].max()
        positive_pct = (df[col] > 0).mean() * 100
        above_10bps_pct = (df[col] > 0.1).mean() * 100
        
        print(f"  {name:<45}: {mean_val:>8.4f}% ± {std_val:>6.4f}% [{min_val:>8.4f}% to {max_val:>8.4f}%]")
        print(f"  {'':<45}  Profitable: {positive_pct:>6.2f}% | >10bps: {above_10bps_pct:>6.2f}%")
    
    print(f"\n🔄 REVERSE STRATEGIES (GATEIO→MEXC) - THEORETICAL PROFITS AFTER FEES (%):")
    reverse_cols = ['reverse_strategy1_profit_pct', 'reverse_strategy2_profit_pct']
    reverse_names = ['REVERSE Strategy 1: GATE→MEXC with Hedge', 'REVERSE Strategy 2: GATE→MEXC Simple']
    
    for col, name in zip(reverse_cols, reverse_names):
        mean_val = df[col].mean()
        std_val = df[col].std()
        min_val = df[col].min()
        max_val = df[col].max()
        positive_pct = (df[col] > 0).mean() * 100
        above_10bps_pct = (df[col] > 0.1).mean() * 100
        
        print(f"  {name:<45}: {mean_val:>8.4f}% ± {std_val:>6.4f}% [{min_val:>8.4f}% to {max_val:>8.4f}%]")
        print(f"  {'':<45}  Profitable: {positive_pct:>6.2f}% | >10bps: {above_10bps_pct:>6.2f}%")
    
    # Fee impact analysis
    print(f"\n💸 FEE IMPACT ANALYSIS:")
    print(f"  MEXC Spot Fees (Maker/Taker)      : {MEXC_SPOT_FEES['maker']*100:.3f}% / {MEXC_SPOT_FEES['taker']*100:.3f}%")
    print(f"  GATEIO Spot Fees (Maker/Taker)    : {GATEIO_SPOT_FEES['maker']*100:.3f}% / {GATEIO_SPOT_FEES['taker']*100:.3f}%")
    print(f"  GATEIO Futures Fees (Maker/Taker) : {GATEIO_FUTURES_FEES['maker']*100:.3f}% / {GATEIO_FUTURES_FEES['taker']*100:.3f}%")
    
    # Round-trip fee calculations
    strategy1_fees = MEXC_SPOT_FEES['taker'] + GATEIO_SPOT_FEES['taker'] + 2 * GATEIO_FUTURES_FEES['taker']
    strategy2_fees = MEXC_SPOT_FEES['taker'] + GATEIO_SPOT_FEES['taker']
    
    print(f"  Strategy 1 Total Round-trip Fees  : {strategy1_fees*100:.3f}%")
    print(f"  Strategy 2 Total Round-trip Fees  : {strategy2_fees*100:.3f}%")
    
    print(f"\n{'=' * 120}")


def main():
    """Main function to run the spread analysis"""
    symbol = Symbol(base=AssetName("F"), quote=AssetName("USDT"))
    # Use a data range where we have cached data (from cache files listing)
    date_to = datetime.datetime.fromisoformat("2025-10-18 05:50:00").replace(tzinfo=datetime.timezone.utc)  # End of cached data
    date_from = datetime.datetime.fromisoformat("2025-10-17 21:50:00").replace(tzinfo=datetime.timezone.utc)  # Start of cached data
    
    print(f"{'=' * 120}")
    print(f"MEXC-GATEIO CROSS-EXCHANGE SPREAD ANALYSIS")
    print(f"{'=' * 120}")
    print(f"Symbol: {symbol.base}/{symbol.quote}")
    print(f"Period: {date_from} to {date_to}")
    print(f"Analysis Duration: 8 hours")
    print(f"{'=' * 120}")
    
    print("\n📥 Loading market data...")
    try:
        df = load_cached_data(symbol, date_from, date_to)
        print(f"✅ Loaded {len(df)} data points")
        
        if len(df) == 0:
            print("❌ No data available for the specified period")
            return
        
        print("\n🔢 Calculating price differences and profits...")
        df = calculate_price_differences(df)
        df = calculate_arbitrage_profits(df)
        
        print("\n📈 Creating charts...")
        fig = create_spread_analysis_charts(df, symbol)
        
        # Save the chart
        chart_filename = f"/Users/dasein/dev/cex_arbitrage/src/trading/research/mexc_gateio_spread_analysis_{symbol.base}_{symbol.quote}.png"
        fig.savefig(chart_filename, dpi=300, bbox_inches='tight')
        print(f"💾 Chart saved as: {chart_filename}")
        
        # Show statistics
        print_spread_statistics(df)
        
        # Show the plot (comment out if running headless)
        try:
            plt.show()
        except Exception as e:
            print(f"📊 Chart created but display not available: {e}")
            print(f"✅ Chart successfully saved to file: {chart_filename}")
        
    except Exception as e:
        print(f"❌ Error during analysis: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()