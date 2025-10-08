#!/usr/bin/env python3
"""
Quick Arbitrage Analyzer - Fixed for your data format

This tool provides the quantitative analysis you need:
- Historical arbitrage opportunities (NOT real-time monitoring)
- Statistical metrics for trading decisions
- Spread analysis between Gate.io and MEXC
- Single-run analysis (not continuous scanning)
"""

import pandas as pd
import numpy as np
from pathlib import Path
import glob
from datetime import datetime
import argparse


def discover_symbol_pairs(data_dir: str):
    """Find symbols that exist on both exchanges."""
    gateio_files = glob.glob(f"{data_dir}/gateio_*_USDT_1m_*.csv")
    mexc_files = glob.glob(f"{data_dir}/mexc_*_USDT_1m_*.csv")
    
    # Extract symbols from filenames
    gateio_symbols = set()
    mexc_symbols = set()
    
    for file_path in gateio_files:
        filename = Path(file_path).stem
        # gateio_1INCH_USDT_1m_20250906_20250913 -> 1INCH
        parts = filename.split('_')
        if len(parts) >= 3:
            symbol = parts[1]  # 1INCH, BTC, etc.
            gateio_symbols.add(symbol)
    
    for file_path in mexc_files:
        filename = Path(file_path).stem
        # mexc_1INCH_USDT_1m_20250906_20250913 -> 1INCH
        parts = filename.split('_')
        if len(parts) >= 3:
            symbol = parts[1]  # 1INCH, BTC, etc.
            mexc_symbols.add(symbol)
    
    # Find common symbols
    common_symbols = gateio_symbols.intersection(mexc_symbols)
    return sorted(list(common_symbols))


def load_symbol_data(data_dir: str, symbol: str):
    """Load data for a symbol from both exchanges."""
    gateio_files = glob.glob(f"{data_dir}/gateio_{symbol}_USDT_1m_*.csv")
    mexc_files = glob.glob(f"{data_dir}/mexc_{symbol}_USDT_1m_*.csv")
    
    if not gateio_files or not mexc_files:
        return None, None
    
    # Load most recent files (in case of multiple)
    gateio_df = pd.read_csv(sorted(gateio_files)[-1])
    mexc_df = pd.read_csv(sorted(mexc_files)[-1])
    
    # Convert timestamps and sort
    for df in [gateio_df, mexc_df]:
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.sort_values('timestamp', inplace=True)
    
    return gateio_df, mexc_df


def calculate_arbitrage_metrics(symbol: str, gateio_df: pd.DataFrame, mexc_df: pd.DataFrame):
    """Calculate comprehensive arbitrage metrics."""
    
    # Merge data on timestamp (using closest timestamps)
    gateio_df = gateio_df.set_index('timestamp')
    mexc_df = mexc_df.set_index('timestamp')
    
    # Resample to align timestamps and forward fill
    merged = pd.merge_asof(
        gateio_df.sort_index()[['close']].rename(columns={'close': 'gateio_price'}),
        mexc_df.sort_index()[['close']].rename(columns={'close': 'mexc_price'}),
        left_index=True, right_index=True, direction='nearest'
    )
    
    # Remove any rows with missing data
    merged = merged.dropna()
    
    if len(merged) < 100:  # Need sufficient data
        return None
    
    # Calculate spreads (percentage)
    # Gate.io sell -> MEXC buy: (mexc_price - gateio_price) / gateio_price * 100
    merged['gateio_to_mexc_spread'] = (merged['mexc_price'] - merged['gateio_price']) / merged['gateio_price'] * 100
    
    # MEXC sell -> Gate.io buy: (gateio_price - mexc_price) / mexc_price * 100  
    merged['mexc_to_gateio_spread'] = (merged['gateio_price'] - merged['mexc_price']) / merged['mexc_price'] * 100
    
    # Take the best spread at each timestamp
    merged['best_spread'] = np.maximum(merged['gateio_to_mexc_spread'], merged['mexc_to_gateio_spread'])
    
    # Calculate metrics
    spreads = merged['best_spread']
    
    metrics = {
        'symbol': f"{symbol}/USDT",
        'total_observations': len(merged),
        'time_period_hours': (merged.index[-1] - merged.index[0]).total_seconds() / 3600,
        
        # Spread Statistics
        'max_spread_pct': spreads.max(),
        'avg_spread_pct': spreads.mean(),
        'median_spread_pct': spreads.median(),
        'std_spread_pct': spreads.std(),
        
        # Opportunity Analysis (0.3% threshold)
        'opportunities_03_count': (spreads > 0.3).sum(),
        'opportunities_03_pct': (spreads > 0.3).mean() * 100,
        'opportunities_03_minutes_per_day': (spreads > 0.3).mean() * 24 * 60,
        
        # Opportunity Analysis (0.5% threshold)  
        'opportunities_05_count': (spreads > 0.5).sum(),
        'opportunities_05_pct': (spreads > 0.5).mean() * 100,
        'opportunities_05_minutes_per_day': (spreads > 0.5).mean() * 24 * 60,
        
        # Volatility and Risk
        'spread_volatility': spreads.std(),
        'price_correlation': merged['gateio_price'].corr(merged['mexc_price']),
        
        # Trading Potential Score (0-100)
        'trading_score': min(100, max(0, 
            (spreads > 0.3).mean() * 50 +  # Frequency weight
            min(spreads.max(), 2.0) * 25 +  # Max spread weight (capped at 2%)
            (100 - spreads.std() * 10)      # Consistency weight
        ))
    }
    
    return metrics


def analyze_arbitrage_opportunities(data_dir: str = "data/arbitrage", max_symbols: int = None):
    """Analyze arbitrage opportunities from historical data."""
    
    print("=" * 80)
    print("🔍 HISTORICAL ARBITRAGE ANALYSIS")
    print("=" * 80)
    print(f"📂 Data directory: {data_dir}")
    print(f"📊 Analysis type: Historical (single-run, not monitoring)")
    print()
    
    # Discover available symbol pairs
    symbols = discover_symbol_pairs(data_dir)
    
    if not symbols:
        print("❌ No matching symbol pairs found between Gate.io and MEXC")
        print("💡 Ensure you have data files like: gateio_BTC_USDT_1m_*.csv and mexc_BTC_USDT_1m_*.csv")
        return []
    
    print(f"📈 Found {len(symbols)} symbols with data from both exchanges")
    
    if max_symbols:
        symbols = symbols[:max_symbols]
        print(f"🔢 Limiting analysis to first {max_symbols} symbols")
    
    print(f"🎯 Analyzing symbols: {', '.join(symbols)}")
    print()
    
    results = []
    
    for i, symbol in enumerate(symbols, 1):
        print(f"🔍 [{i}/{len(symbols)}] Analyzing {symbol}/USDT...")
        
        gateio_df, mexc_df = load_symbol_data(data_dir, symbol)
        
        if gateio_df is None or mexc_df is None:
            print(f"   ⚠️  Skipping {symbol} - insufficient data")
            continue
        
        metrics = calculate_arbitrage_metrics(symbol, gateio_df, mexc_df)
        
        if metrics is None:
            print(f"   ⚠️  Skipping {symbol} - insufficient aligned data")
            continue
        
        results.append(metrics)
        
        # Quick preview
        print(f"   ✅ Max spread: {metrics['max_spread_pct']:.3f}%")
        print(f"   ✅ Opportunities >0.3%: {metrics['opportunities_03_count']} ({metrics['opportunities_03_pct']:.1f}%)")
        print(f"   ✅ Trading score: {metrics['trading_score']:.1f}/100")
    
    return results


def generate_report(results, min_score: float = 0):
    """Generate analysis report with statistical insights."""
    
    if not results:
        print("\n❌ No results to report")
        return
    
    # Filter by minimum score
    if min_score > 0:
        results = [r for r in results if r['trading_score'] >= min_score]
        if not results:
            print(f"\n❌ No opportunities meet minimum trading score of {min_score}")
            return
    
    # Sort by trading score
    results.sort(key=lambda x: x['trading_score'], reverse=True)
    
    print("\n" + "=" * 80)
    print("📊 QUANTITATIVE ANALYSIS RESULTS")
    print("=" * 80)
    
    # Summary Statistics
    scores = [r['trading_score'] for r in results]
    max_spreads = [r['max_spread_pct'] for r in results]
    opportunities = [r['opportunities_03_minutes_per_day'] for r in results]
    
    print(f"📈 Total symbols analyzed: {len(results)}")
    print(f"💰 Average trading score: {np.mean(scores):.1f}/100")
    print(f"📏 Average max spread: {np.mean(max_spreads):.3f}%")
    print(f"⏰ Average opportunity time: {np.mean(opportunities):.1f} minutes/day")
    print()
    
    # Quality Tiers
    high_quality = [r for r in results if r['trading_score'] >= 70]
    medium_quality = [r for r in results if 40 <= r['trading_score'] < 70]
    low_quality = [r for r in results if r['trading_score'] < 40]
    
    print(f"🔥 High-quality opportunities (≥70): {len(high_quality)}")
    print(f"⚡ Medium-quality opportunities (40-69): {len(medium_quality)}")
    print(f"📉 Lower-quality opportunities (<40): {len(low_quality)}")
    print()
    
    # Top Opportunities
    print("🎯 TOP ARBITRAGE OPPORTUNITIES:")
    print("-" * 80)
    print(f"{'Rank':<4} {'Symbol':<12} {'Score':<6} {'Max':<8} {'Avg':<8} {'Opps>0.3%':<10} {'Minutes/Day':<12}")
    print("-" * 80)
    
    for i, metrics in enumerate(results[:15], 1):
        symbol = metrics['symbol'].replace('/USDT', '')
        print(f"{i:<4} {symbol:<12} {metrics['trading_score']:<6.1f} "
              f"{metrics['max_spread_pct']:<8.3f} {metrics['avg_spread_pct']:<8.3f} "
              f"{metrics['opportunities_03_pct']:<10.1f} {metrics['opportunities_03_minutes_per_day']:<12.1f}")
    
    # Detailed Analysis for Top 5
    if len(results) > 0:
        print("\n📋 DETAILED ANALYSIS (Top 5):")
        print("-" * 80)
        
        for metrics in results[:5]:
            print(f"\n🎯 {metrics['symbol']}")
            print(f"   Max Spread: {metrics['max_spread_pct']:.3f}%")
            print(f"   Average Spread: {metrics['avg_spread_pct']:.3f}%")
            print(f"   Spread Volatility: {metrics['std_spread_pct']:.3f}%")
            print(f"   Opportunities >0.3%: {metrics['opportunities_03_count']} times "
                  f"({metrics['opportunities_03_pct']:.1f}% of time)")
            print(f"   Opportunities >0.5%: {metrics['opportunities_05_count']} times "
                  f"({metrics['opportunities_05_pct']:.1f}% of time)")
            print(f"   Minutes per day >0.3%: {metrics['opportunities_03_minutes_per_day']:.1f}")
            print(f"   Price correlation: {metrics['price_correlation']:.3f}")
            print(f"   Trading score: {metrics['trading_score']:.1f}/100")
    
    # Save to CSV
    output_file = "arbitrage_analysis_report.csv"
    df = pd.DataFrame(results)
    df.to_csv(output_file, index=False)
    print(f"\n📄 Report saved to: {output_file}")
    
    # Strategic Insights
    print("\n💡 STRATEGIC INSIGHTS:")
    if len(high_quality) > 0:
        print(f"   🎯 {len(high_quality)} high-quality opportunities identified")
        print(f"   💰 Focus on symbols with trading score ≥70 for best returns")
    
    if np.mean(max_spreads) > 0.5:
        print(f"   📈 Strong spread patterns detected (avg {np.mean(max_spreads):.3f}%)")
        print(f"   💎 Market inefficiencies present - good arbitrage potential")
    
    best_symbol = results[0] if results else None
    if best_symbol and best_symbol['opportunities_03_minutes_per_day'] > 60:
        symbol_name = best_symbol['symbol'].replace('/USDT', '')
        print(f"   ⭐ Best opportunity: {symbol_name} with "
              f"{best_symbol['opportunities_03_minutes_per_day']:.0f} minutes/day of opportunities")
    
    print(f"\n✅ Historical analysis complete!")
    print(f"📊 This was a single-run analysis of historical data (not continuous monitoring)")


def main():
    parser = argparse.ArgumentParser(description="Quick Arbitrage Analysis - Historical Data")
    parser.add_argument('--data-dir', default='data/arbitrage', help='Data directory')
    parser.add_argument('--max-symbols', type=int, help='Limit number of symbols')
    parser.add_argument('--min-score', type=float, default=0, help='Minimum trading score')
    
    args = parser.parse_args()
    
    results = analyze_arbitrage_opportunities(args.data_dir, args.max_symbols)
    generate_report(results, args.min_score)


if __name__ == "__main__":
    main()