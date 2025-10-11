"""
Optimal Threshold Calculation Demo for MEXC Spot - Gate.io Futures Arbitrage

This demo fetches historical book ticker data from the database and calculates
optimal entry/exit thresholds for spot-futures arbitrage trading.
"""

import asyncio
from typing import Tuple
import pandas as pd

from db.database_manager import get_database_manager, initialize_database_manager
from config.config_manager import HftConfig
from db import initialize_database

from trading.analysis.threshold_optimizer import (
    calculate_optimal_thresholds,
    FeeConfiguration
)
from trading.analysis.data_loader import get_cached_book_ticker_data
from examples.demo.demo_config import DemoConfig
from examples.demo.result_formatters import (
    ThresholdFormatter,
    PerformanceFormatter, 
    StatisticsFormatter,
    RecommendationFormatter
)


async def initialize_components() -> Tuple[DemoConfig, FeeConfiguration]:
    """Initialize database connection and configuration."""
    print("\n📊 Initializing database connection...")
    config_manager = HftConfig()
    await initialize_database_manager()
    print("✅ Database connected successfully")
    
    # Load demo configuration
    demo_config = DemoConfig()
    
    # Configure trading fees
    print("\n💰 Configuring trading fees...")
    fees = FeeConfiguration.create_realistic()
    print(f"  Spot fees: {fees.spot_maker_fee}% maker, {fees.spot_taker_fee}% taker")
    print(f"  Futures fees: {fees.futures_maker_fee}% maker, {fees.futures_taker_fee}% taker")
    print(f"  Slippage: {fees.slippage_factor}%")
    print(f"  📝 Note: Arbitrage uses taker fees (market orders) for speed")
    
    return demo_config, fees


async def load_market_data(config: DemoConfig) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Load market data with caching for both exchanges."""
    print(f"\n🎯 Symbol: {config.symbol_pair_str}")
    print(f"📅 Period: {config.start_date.strftime('%Y-%m-%d %H:%M')} to {config.end_date.strftime('%Y-%m-%d %H:%M')}")
    print(f"🏦 Exchanges: {config.spot_exchange} (spot) - {config.futures_exchange} (futures)")
    
    print("\n📊 Fetching market data from database...")
    
    # Load spot data
    print(f"  Loading {config.spot_exchange} data...")
    spot_df = await get_cached_book_ticker_data(
        exchange=config.spot_exchange,
        symbol_base=config.symbol_base,
        symbol_quote=config.symbol_quote,
        start_time=config.start_date,
        end_time=config.end_date,
        limit=config.limit
    )
    print(f"  ✅ Loaded {len(spot_df)} spot data points")
    
    # Load futures data
    print(f"  Loading {config.futures_exchange} data...")
    futures_df = await get_cached_book_ticker_data(
        exchange=config.futures_exchange,
        symbol_base=config.symbol_base,
        symbol_quote=config.symbol_quote,
        start_time=config.start_date,
        end_time=config.end_date,
        limit=config.limit
    )
    print(f"  ✅ Loaded {len(futures_df)} futures data points")
    
    # Validate data
    if spot_df.empty or futures_df.empty:
        raise ValueError(f"Insufficient data: spot={len(spot_df)}, futures={len(futures_df)} records")
    
    return spot_df, futures_df


async def run_optimization(spot_df: pd.DataFrame, futures_df: pd.DataFrame, 
                          fees: FeeConfiguration, config: DemoConfig):
    """Run threshold optimization and return results."""
    print("\n🔍 Calculating optimal thresholds...")
    print("  This may take a minute as we test multiple threshold combinations...")
    
    return await calculate_optimal_thresholds(
        spot_df=spot_df,
        futures_df=futures_df,
        fees=fees,
        optimization_target=config.optimization_target,
        max_positions=config.max_positions,
        min_liquidity=config.min_liquidity,
        alignment_tolerance=config.alignment_tolerance
    )


def display_results(result, config: DemoConfig):
    """Display optimization results using formatters."""
    print("\n" + "=" * 70)
    print("OPTIMIZATION RESULTS")
    print("=" * 70)
    
    # Display formatted results
    print(ThresholdFormatter.format_thresholds(result))
    print(PerformanceFormatter.format_performance(result))
    print(StatisticsFormatter.format_market_statistics(result, config.spot_exchange, config.futures_exchange))
    print(RecommendationFormatter.format_recommendations(result))
    
    print("\n" + "=" * 70)
    print("Demo completed successfully!")


async def fetch_and_optimize_thresholds():
    """Main demo function - orchestrates the threshold optimization process."""
    print("=" * 70)
    print("OPTIMAL THRESHOLD CALCULATION DEMO")
    print("MEXC Spot - Gate.io Futures Arbitrage")
    print("=" * 70)
    
    try:
        # Initialize components
        config, fees = await initialize_components()
        
        # Load market data
        spot_df, futures_df = await load_market_data(config)
        
        # Run optimization
        result = await run_optimization(spot_df, futures_df, fees, config)
        
        # Display results
        display_results(result, config)
        
    except Exception as e:
        print(f"\n❌ Error during optimization: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up database connection
        try:
            db = get_database_manager()
            await db.close()
        except:
            pass


async def main():
    """Main entry point for the demo."""
    await fetch_and_optimize_thresholds()


if __name__ == "__main__":
    print("Starting Optimal Threshold Demo...")
    asyncio.run(main())