#!/usr/bin/env python3
"""
Test script for the enhanced spot/futures arbitrage bin analysis system.
Validates the get_best_spread_bins function with realistic market scenarios.
"""

import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timezone

from src.trading.research.my_vector_research import get_trading_signals
from trading.research.trading_utlis import get_best_spread_bins
from src.trading.research.trading_utlis import load_market_data, DEFAULT_FEES_PER_TRADE


async def test_arbitrage_analysis():
    """Test the arbitrage bin analysis with real market data."""
    
    print("="*80)
    print("SPOT/FUTURES ARBITRAGE BIN ANALYSIS TEST")
    print("="*80)
    print()
    
    # Load market data
    print("📊 Loading market data...")
    df = await load_market_data()
    
    # Add spread signals
    print("📈 Calculating spreads...")
    df_with_signals = get_trading_signals(df, entry_threshold=0.2, exit_threshold=0.1)
    
    print(f"\n📊 Data Summary:")
    print(f"  • Total data points: {len(df_with_signals)}")
    print(f"  • Date range: {df_with_signals.index[0]} to {df_with_signals.index[-1]}")
    print(f"  • Entry spread range: {df_with_signals['spot_fut_spread_prc'].min():.3f}% to {df_with_signals['spot_fut_spread_prc'].max():.3f}%")
    print(f"  • Exit spread range: {df_with_signals['fut_spot_spread_prc'].min():.3f}% to {df_with_signals['fut_spot_spread_prc'].max():.3f}%")
    print(f"  • Required fees: {DEFAULT_FEES_PER_TRADE:.3f}%")
    
    print("\n" + "="*80)
    print("TEST 1: Default Parameters (step=0.02%, threshold=50, min_profit=1bp)")
    print("="*80)
    
    # Test with default parameters
    opportunities = get_best_spread_bins(
        df_with_signals, 
        step=0.02, 
        threshold=50,
        min_profit_bps=1.0  # 1 basis point above fees
    )
    
    if len(opportunities) > 0:
        print(f"\n✅ Found {len(opportunities)} profitable opportunities")
        print("\nTop 5 Opportunities:")
        print("-"*60)
        print(f"{'Entry %':>10} {'Exit %':>10} {'Profit %':>10} {'Weight':>10}")
        print("-"*60)
        for i, opp in enumerate(opportunities[:5]):
            print(f"{opp[0]:10.3f} {opp[1]:10.3f} {opp[2]:10.3f} {opp[3]:10.0f}")
    
    print("\n" + "="*80)
    print("TEST 2: Aggressive Parameters (step=0.01%, threshold=25, min_profit=0.5bp)")
    print("="*80)
    
    # Test with more aggressive parameters
    opportunities_aggressive = get_best_spread_bins(
        df_with_signals, 
        step=0.01,  # Finer bins
        threshold=25,  # Lower grouping threshold
        min_profit_bps=0.5  # Only 0.5 basis points above fees
    )
    
    if len(opportunities_aggressive) > 0:
        print(f"\n✅ Found {len(opportunities_aggressive)} profitable opportunities")
        print("\nTop 5 Opportunities:")
        print("-"*60)
        print(f"{'Entry %':>10} {'Exit %':>10} {'Profit %':>10} {'Weight':>10}")
        print("-"*60)
        for i, opp in enumerate(opportunities_aggressive[:5]):
            print(f"{opp[0]:10.3f} {opp[1]:10.3f} {opp[2]:10.3f} {opp[3]:10.0f}")
    
    print("\n" + "="*80)
    print("TEST 3: Conservative Parameters (step=0.05%, threshold=100, min_profit=2bp)")
    print("="*80)
    
    # Test with conservative parameters
    opportunities_conservative = get_best_spread_bins(
        df_with_signals, 
        step=0.05,  # Wider bins
        threshold=100,  # Higher grouping threshold
        min_profit_bps=2.0  # 2 basis points above fees
    )
    
    if len(opportunities_conservative) > 0:
        print(f"\n✅ Found {len(opportunities_conservative)} profitable opportunities")
        print("\nTop 5 Opportunities:")
        print("-"*60)
        print(f"{'Entry %':>10} {'Exit %':>10} {'Profit %':>10} {'Weight':>10}")
        print("-"*60)
        for i, opp in enumerate(opportunities_conservative[:5]):
            print(f"{opp[0]:10.3f} {opp[1]:10.3f} {opp[2]:10.3f} {opp[3]:10.0f}")
    
    print("\n" + "="*80)
    print("ARBITRAGE STRATEGY RECOMMENDATIONS")
    print("="*80)
    
    if len(opportunities) > 0:
        # Calculate strategy metrics
        avg_profit = opportunities[:, 2].mean()
        max_profit = opportunities[:, 2].max()
        weighted_avg_profit = np.average(opportunities[:, 2], weights=opportunities[:, 3])
        
        print(f"\n📊 Strategy Metrics:")
        print(f"  • Average profit: {avg_profit:.3f}%")
        print(f"  • Weighted avg profit: {weighted_avg_profit:.3f}%")
        print(f"  • Maximum profit: {max_profit:.3f}%")
        print(f"  • Opportunity count: {len(opportunities)}")
        
        # Find the most frequent opportunity
        best_opportunity = opportunities[0]
        
        print(f"\n🎯 Recommended Entry/Exit Thresholds:")
        print(f"  • Entry when spot-futures spread > {best_opportunity[0]:.3f}%")
        print(f"  • Exit when futures-spot spread < {best_opportunity[1]:.3f}%")
        print(f"  • Expected profit: {best_opportunity[2]:.3f}% per cycle")
        
        # Calculate breakeven volume
        fixed_costs = 10  # Assume $10 fixed costs per trade
        avg_position_size = 10000  # Assume $10k position
        profit_per_trade = avg_position_size * (weighted_avg_profit / 100)
        breakeven_trades = fixed_costs / profit_per_trade if profit_per_trade > 0 else float('inf')
        
        print(f"\n💰 Economics (assuming $10k position):")
        print(f"  • Profit per trade: ${profit_per_trade:.2f}")
        print(f"  • Breakeven trades: {breakeven_trades:.1f}")
        print(f"  • Daily target: {max(1, int(breakeven_trades * 2))} trades for profitability")
    else:
        print("\n⚠️ No profitable opportunities found with current market conditions")
        print("Consider:")
        print("  • Reducing minimum profit threshold")
        print("  • Adjusting bin parameters")
        print("  • Waiting for higher volatility periods")
    
    print("\n" + "="*80)
    print("TEST COMPLETED")
    print("="*80)


def run_synthetic_test():
    """Test with synthetic data to validate the algorithm."""
    
    print("\n" + "="*80)
    print("SYNTHETIC DATA VALIDATION TEST")
    print("="*80)
    
    # Create synthetic data with known arbitrage opportunity
    np.random.seed(42)
    n_samples = 10000
    
    # Create base prices
    base_price = 100
    
    # Create spreads with known patterns
    # Entry spread: mostly around 0.2% with some at 0.5%
    entry_spreads = np.concatenate([
        np.random.normal(0.2, 0.05, int(n_samples * 0.7)),  # 70% around 0.2%
        np.random.normal(0.5, 0.02, int(n_samples * 0.3))   # 30% around 0.5%
    ])
    
    # Exit spread: mostly around -0.1% with some at -0.3%
    exit_spreads = np.concatenate([
        np.random.normal(-0.1, 0.05, int(n_samples * 0.7)),  # 70% around -0.1%
        np.random.normal(-0.3, 0.02, int(n_samples * 0.3))   # 30% around -0.3%
    ])
    
    # Create DataFrame
    df_synthetic = pd.DataFrame({
        'spot_fut_spread_prc': entry_spreads[:n_samples],
        'fut_spot_spread_prc': exit_spreads[:n_samples]
    })
    
    print(f"\n📊 Synthetic Data:")
    print(f"  • Samples: {n_samples}")
    print(f"  • Entry spread mean: {df_synthetic['spot_fut_spread_prc'].mean():.3f}%")
    print(f"  • Exit spread mean: {df_synthetic['fut_spot_spread_prc'].mean():.3f}%")
    print(f"  • Expected best profit: ~{0.5 - (-0.3) - DEFAULT_FEES_PER_TRADE:.3f}%")
    
    # Run analysis
    opportunities = get_best_spread_bins(
        df_synthetic, 
        step=0.02, 
        threshold=50,
        min_profit_bps=1.0
    )
    
    if len(opportunities) > 0:
        print(f"\n✅ Validation successful!")
        print(f"  • Found {len(opportunities)} opportunities")
        print(f"  • Best profit: {opportunities[0, 2]:.3f}%")
        print(f"  • Matches expected: {abs(opportunities[0, 2] - (0.5 - (-0.3) - DEFAULT_FEES_PER_TRADE)) < 0.05}")
    else:
        print("\n❌ Validation failed - no opportunities found")


if __name__ == "__main__":
    # Run synthetic test first
    run_synthetic_test()
    
    # Run real data test
    print("\n" + "="*80)
    print("RUNNING REAL MARKET DATA TEST")
    print("="*80)
    asyncio.run(test_arbitrage_analysis())