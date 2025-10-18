"""
Analyze bid-ask spreads to understand execution costs
"""

import datetime
from exchanges.structs import Symbol, AssetName
from trading.research.trading_utlis import load_market_data
import pandas as pd
from trading.research.cost_utils import (calculate_spread_statistics, optimize_parameters_statistical,
                                         optimize_parameters_risk_adjusted, compare_parameter_approaches,
                                         print_optimization_summary, optimize_parameters_random_sampling,
                                         optimize_parameters_statistical_fast)

async def analyze_spreads():
    symbol = Symbol(base=AssetName("F"), quote=AssetName("USDT"))
    date_to = datetime.datetime.utcnow()
    date_from = date_to - datetime.timedelta(hours=1)
    
    print(f"Loading data for {symbol.base}/{symbol.quote}...")
    df = await load_market_data(symbol, date_from, date_to)
    
    # # Calculate bid-ask spreads
    # df['spot_ba_spread'] = df['spot_ask_price'] - df['spot_bid_price']
    # df['spot_ba_spread_pct'] = (df['spot_ba_spread'] / df['spot_bid_price']) * 100
    #
    # df['fut_ba_spread'] = df['fut_ask_price'] - df['fut_bid_price']
    # df['fut_ba_spread_pct'] = (df['fut_ba_spread'] / df['fut_bid_price']) * 100
    #
    # # Calculate theoretical entry spreads for BOTH strategies
    # # Original: Buy spot (ask), Sell futures (bid)
    # df['original_entry_spread'] = df['spot_ask_price'] - df['fut_bid_price']
    # df['original_entry_spread_pct'] = (df['original_entry_spread'] / df['spot_ask_price']) * 100
    #
    # # Reverse: Sell spot (bid), Buy futures (ask)
    # df['reverse_entry_spread'] = df['fut_ask_price'] - df['spot_bid_price']
    # df['reverse_entry_spread_pct'] = (df['reverse_entry_spread'] / df['fut_ask_price']) * 100
    #
    # print(f"\n{'='*80}")
    # print(f"BID-ASK SPREAD ANALYSIS")
    # print(f"{'='*80}")
    #
    # print(f"\n📊 SPOT BID-ASK SPREAD:")
    # print(f"  Mean:    {df['spot_ba_spread_pct'].mean():.4f}%")
    # print(f"  Median:  {df['spot_ba_spread_pct'].median():.4f}%")
    # print(f"  Min:     {df['spot_ba_spread_pct'].min():.4f}%")
    # print(f"  Max:     {df['spot_ba_spread_pct'].max():.4f}%")
    #
    # print(f"\n📊 FUTURES BID-ASK SPREAD:")
    # print(f"  Mean:    {df['fut_ba_spread_pct'].mean():.4f}%")
    # print(f"  Median:  {df['fut_ba_spread_pct'].median():.4f}%")
    # print(f"  Min:     {df['fut_ba_spread_pct'].min():.4f}%")
    # print(f"  Max:     {df['fut_ba_spread_pct'].max():.4f}%")
    #
    # print(f"\n📊 COMBINED EXECUTION COST:")
    # combined_cost = df['spot_ba_spread_pct'].mean() + df['fut_ba_spread_pct'].mean()
    # print(f"  Total bid-ask cost per round-trip: {combined_cost:.4f}%")
    # fees = 0.05 * 4  # 0.05% per side × 4 sides
    # print(f"  Total fees per round-trip:         {fees:.4f}%")
    # print(f"  TOTAL EXECUTION COST:              {combined_cost + fees:.4f}%")
    #
    # print(f"\n📊 ORIGINAL STRATEGY (Buy Spot, Sell Futures):")
    # print(f"  Entry spread mean:   {df['original_entry_spread_pct'].mean():.4f}%")
    # print(f"  Entry spread median: {df['original_entry_spread_pct'].median():.4f}%")
    # print(f"  Negative entries:    {(df['original_entry_spread_pct'] < 0).sum()} / {len(df)} ({(df['original_entry_spread_pct'] < 0).mean()*100:.1f}%)")
    #
    # print(f"\n📊 REVERSE STRATEGY (Sell Spot, Buy Futures):")
    # print(f"  Entry spread mean:   {df['reverse_entry_spread_pct'].mean():.4f}%")
    # print(f"  Entry spread median: {df['reverse_entry_spread_pct'].median():.4f}%")
    # print(f"  Negative entries:    {(df['reverse_entry_spread_pct'] < 0).sum()} / {len(df)} ({(df['reverse_entry_spread_pct'] < 0).mean()*100:.1f}%)")
    #
    # print(f"\n💡 PROFITABILITY ANALYSIS:")
    # min_profit_needed = combined_cost + fees
    # print(f"  Minimum entry advantage needed: {min_profit_needed:.4f}%")
    #
    # # Original strategy
    # profitable_original = df['original_entry_spread_pct'] < -min_profit_needed
    # print(f"\n  Original strategy profitable entries:")
    # print(f"    Count: {profitable_original.sum()} / {len(df)} ({profitable_original.mean()*100:.1f}%)")
    # if profitable_original.sum() > 0:
    #     print(f"    Avg advantage: {df[profitable_original]['original_entry_spread_pct'].mean():.4f}%")
    #
    # # Reverse strategy
    # profitable_reverse = df['reverse_entry_spread_pct'] < -min_profit_needed
    # print(f"\n  Reverse strategy profitable entries:")
    # print(f"    Count: {profitable_reverse.sum()} / {len(df)} ({profitable_reverse.mean()*100:.1f}%)")
    # if profitable_reverse.sum() > 0:
    #     print(f"    Avg advantage: {df[profitable_reverse]['reverse_entry_spread_pct'].mean():.4f}%")
    #
    # print(f"\n{'='*80}")
    # print(f"CONCLUSION")
    # print(f"{'='*80}")
    #
    # if profitable_original.sum() == 0 and profitable_reverse.sum() == 0:
    #     print("❌ NEITHER STRATEGY CAN BE PROFITABLE!")
    #     print(f"\nReason: Bid-ask spreads ({combined_cost:.4f}%) + fees ({fees:.4f}%)")
    #     print(f"        = {combined_cost + fees:.4f}% total cost")
    #     print(f"\nBut entry advantages are never large enough to overcome this cost.")
    #     print(f"\nSolutions:")
    #     print(f"  1. Use exchanges with tighter spreads (< 0.1% per instrument)")
    #     print(f"  2. Use limit orders instead of market orders")
    #     print(f"  3. Trade more liquid pairs")
    #     print(f"  4. Wait for larger spread dislocations (> 1.5%)")
    # elif profitable_original.sum() > profitable_reverse.sum():
    #     print(f"✅ ORIGINAL STRATEGY is better!")
    #     print(f"   Profitable entries: {profitable_original.mean()*100:.1f}%")
    # else:
    #     print(f"✅ REVERSE STRATEGY is better!")
    #     print(f"   Profitable entries: {profitable_reverse.mean()*100:.1f}%")

    print(calculate_spread_statistics(df))
    stat_result = optimize_parameters_statistical(df)
    print(stat_result)
    stat_result_fase  = optimize_parameters_statistical_fast(df)
    print(stat_result_fase)
    random_result = optimize_parameters_random_sampling(df, n_samples=5000)
    print(random_result)
    # risk_adjusted = optimize_parameters_risk_adjusted(df)
    # compare_approaches = compare_parameter_approaches(df)
    # print_optimization_summary(compare_approaches)
# calculate_spread_statistics, optimize_parameters_statistical,
#                                          optimize_parameters_risk_adjusted, compare_parameter_approaches,
#                                          print_optimization_summary

if __name__ == "__main__":
    import asyncio
    asyncio.run(analyze_spreads())
