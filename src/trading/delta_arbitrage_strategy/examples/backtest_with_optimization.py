"""
Backtesting with Dynamic Parameter Optimization

This example demonstrates how to integrate the delta arbitrage optimizer
with the existing backtesting system to use dynamic parameters instead
of static ones.
"""

import asyncio
import datetime
import sys
import os

import pandas as pd
from typing import List, Tuple
from exchanges.structs import Symbol, AssetName

# Import existing backtesting functions
from trading.research.trading_utlis import load_market_data
from trading.research.backtesting_direct_arbitrage import (
    delta_neutral_backtest, 
    print_trade_summary,
    add_execution_calculations
)

# Import optimization components
from ..optimization.parameter_optimizer import DeltaArbitrageOptimizer, OptimizationResult
from ..optimization.optimization_config import OptimizationConfig, DEFAULT_OPTIMIZATION_CONFIG


async def optimized_delta_neutral_backtest(
    df: pd.DataFrame,
    optimizer: DeltaArbitrageOptimizer,
    optimization_window_hours: int = 24,
    reoptimize_every_hours: int = 6,
    static_params: dict = None
) -> Tuple[List, List[OptimizationResult]]:
    """
    Run backtest with dynamic parameter optimization.
    
    This function splits the data into windows and reoptimizes parameters
    periodically, simulating how the system would work in live trading.
    
    Args:
        df: Historical market data
        optimizer: Parameter optimizer instance
        optimization_window_hours: Hours of data to use for optimization
        reoptimize_every_hours: How often to reoptimize parameters
        static_params: Optional static parameters to override optimization
        
    Returns:
        Tuple of (trades, optimization_history)
    """
    print(f"🚀 Starting optimized backtesting")
    print(f"   • Total data points: {len(df)}")
    print(f"   • Optimization window: {optimization_window_hours} hours")
    print(f"   • Reoptimization frequency: {reoptimize_every_hours} hours")
    print("=" * 80)
    
    # Prepare data with execution calculations
    df_with_calcs = add_execution_calculations(df)
    
    # Initialize tracking variables
    all_trades = []
    optimization_history = []
    current_params = None
    
    # Split data into chunks for periodic reoptimization
    if 'timestamp' in df.index.names:
        df_indexed = df_with_calcs.copy()
    else:
        df_indexed = df_with_calcs.set_index('timestamp') if 'timestamp' in df_with_calcs.columns else df_with_calcs
    
    # Calculate chunk size based on reoptimization frequency
    # Assume data is roughly hourly for simplicity
    chunk_size = max(reoptimize_every_hours, len(df_indexed) // 10)  # At least 10 chunks
    
    total_chunks = len(df_indexed) // chunk_size + (1 if len(df_indexed) % chunk_size > 0 else 0)
    print(f"📊 Processing {total_chunks} chunks of ~{chunk_size} data points each\n")
    
    for chunk_idx in range(total_chunks):
        start_idx = chunk_idx * chunk_size
        end_idx = min(start_idx + chunk_size, len(df_indexed))
        
        # Get current chunk for trading
        current_chunk = df_indexed.iloc[start_idx:end_idx].copy()
        
        print(f"🔄 Processing chunk {chunk_idx + 1}/{total_chunks}")
        print(f"   • Chunk data points: {len(current_chunk)}")
        
        # Get optimization data (look back from current chunk start)
        opt_start_idx = max(0, start_idx - optimization_window_hours)
        opt_end_idx = start_idx + min(optimization_window_hours, len(current_chunk))
        optimization_data = df_indexed.iloc[opt_start_idx:opt_end_idx].copy()
        
        print(f"   • Optimization data points: {len(optimization_data)}")
        
        # Optimize parameters if we have sufficient data
        if len(optimization_data) >= 50:
            try:
                optimization_result = await optimizer.optimize_parameters(
                    optimization_data.reset_index(),
                    lookback_hours=optimization_window_hours
                )
                
                optimization_history.append(optimization_result)
                current_params = optimization_result
                
                print(f"   ✅ Parameters optimized:")
                print(f"      • Entry threshold: {optimization_result.entry_threshold_pct:.4f}%")
                print(f"      • Exit threshold: {optimization_result.exit_threshold_pct:.4f}%")
                print(f"      • Confidence: {optimization_result.confidence_score:.3f}")
                
            except Exception as e:
                print(f"   ⚠️ Optimization failed: {e}")
                if current_params is None:
                    # Use default parameters for first chunk if optimization fails
                    current_params = OptimizationResult(
                        entry_threshold_pct=0.5,
                        exit_threshold_pct=0.1,
                        confidence_score=0.3,
                        analysis_period_hours=0,
                        mean_reversion_speed=0.1,
                        spread_volatility=0.2,
                        optimization_timestamp=datetime.datetime.now().timestamp()
                    )
        else:
            print(f"   ⚠️ Insufficient data for optimization, using previous parameters")
            if current_params is None:
                # Use default parameters
                current_params = OptimizationResult(
                    entry_threshold_pct=0.5,
                    exit_threshold_pct=0.1,
                    confidence_score=0.3,
                    analysis_period_hours=0,
                    mean_reversion_speed=0.1,
                    spread_volatility=0.2,
                    optimization_timestamp=datetime.datetime.now().timestamp()
                )
        
        # Override with static parameters if provided
        if static_params:
            entry_threshold = static_params.get('max_entry_cost_pct', current_params.entry_threshold_pct)
            exit_threshold = static_params.get('min_profit_pct', current_params.exit_threshold_pct)
            max_hours = static_params.get('max_hours', 6)
            print(f"   🔧 Using static parameters: entry={entry_threshold:.4f}%, exit={exit_threshold:.4f}%")
        else:
            entry_threshold = current_params.entry_threshold_pct
            exit_threshold = current_params.exit_threshold_pct
            max_hours = 6  # Default from original backtest
        
        # Run backtest on current chunk with optimized parameters
        chunk_trades = delta_neutral_backtest(
            current_chunk.reset_index(),
            max_entry_cost_pct=entry_threshold,
            min_profit_pct=exit_threshold,
            max_hours=max_hours,
            spot_fee=0.0005,
            fut_fee=0.0005
        )
        
        print(f"   📈 Chunk results: {len(chunk_trades)} trades")
        
        # Add trades to overall results
        all_trades.extend(chunk_trades)
        print()  # Empty line for readability
    
    print("=" * 80)
    print(f"🎉 Optimized backtesting completed!")
    print(f"   • Total trades: {len(all_trades)}")
    print(f"   • Optimization runs: {len(optimization_history)}")
    
    return all_trades, optimization_history


def analyze_optimization_performance(optimization_history: List[OptimizationResult]):
    """Analyze how optimization parameters evolved over time."""
    if not optimization_history:
        print("No optimization history to analyze")
        return
    
    print("\n📊 OPTIMIZATION PERFORMANCE ANALYSIS")
    print("=" * 80)
    
    # Convert to DataFrame for analysis
    opt_data = []
    for i, opt in enumerate(optimization_history):
        opt_data.append({
            'run': i + 1,
            'entry_threshold': opt.entry_threshold_pct,
            'exit_threshold': opt.exit_threshold_pct,
            'confidence': opt.confidence_score,
            'mean_reversion_speed': opt.mean_reversion_speed,
            'spread_volatility': opt.spread_volatility
        })
    
    opt_df = pd.DataFrame(opt_data)
    
    print(f"Optimization Statistics:")
    print(f"{'Parameter':<20} {'Mean':<10} {'Std':<10} {'Min':<10} {'Max':<10}")
    print("-" * 70)
    
    for col in ['entry_threshold', 'exit_threshold', 'confidence', 'mean_reversion_speed', 'spread_volatility']:
        mean_val = opt_df[col].mean()
        std_val = opt_df[col].std()
        min_val = opt_df[col].min()
        max_val = opt_df[col].max()
        print(f"{col:<20} {mean_val:<10.4f} {std_val:<10.4f} {min_val:<10.4f} {max_val:<10.4f}")
    
    # Parameter stability analysis
    entry_cv = opt_df['entry_threshold'].std() / opt_df['entry_threshold'].mean() if opt_df['entry_threshold'].mean() > 0 else 0
    exit_cv = opt_df['exit_threshold'].std() / opt_df['exit_threshold'].mean() if opt_df['exit_threshold'].mean() > 0 else 0
    
    print(f"\nParameter Stability (Coefficient of Variation):")
    print(f"• Entry threshold CV: {entry_cv:.3f} ({'Stable' if entry_cv < 0.2 else 'Variable' if entry_cv < 0.5 else 'Unstable'})")
    print(f"• Exit threshold CV: {exit_cv:.3f} ({'Stable' if exit_cv < 0.2 else 'Variable' if exit_cv < 0.5 else 'Unstable'})")
    
    # Confidence trend
    avg_confidence = opt_df['confidence'].mean()
    confidence_trend = "Improving" if opt_df['confidence'].iloc[-1] > opt_df['confidence'].iloc[0] else "Declining"
    print(f"• Average confidence: {avg_confidence:.3f}")
    print(f"• Confidence trend: {confidence_trend}")


async def main():
    """Main example function demonstrating optimized backtesting."""
    # Configuration
    symbol = Symbol(base=AssetName("LUNC"), quote=AssetName("USDT"))
    
    # Use recent data period
    date_to = datetime.datetime.fromisoformat("2025-10-12 06:17").replace(tzinfo=datetime.timezone.utc)
    date_from = date_to - datetime.timedelta(hours=24)
    
    print(f"🚀 DELTA-NEUTRAL ARBITRAGE WITH DYNAMIC OPTIMIZATION")
    print(f"=" * 80)
    print(f"Symbol: {symbol.base}/{symbol.quote}")
    print(f"Period: {date_from} to {date_to}")
    print(f"=" * 80)
    
    # Load market data
    print("📥 Loading market data...")
    try:
        df = await load_market_data(symbol, date_from, date_to)
        print(f"✅ Loaded {len(df)} data points\n")
    except Exception as e:
        print(f"❌ Failed to load market data: {e}")
        return
    
    # Initialize optimizer with configuration
    config = OptimizationConfig(
        target_hit_rate=0.7,           # Target 70% success rate
        min_trades_per_day=5,          # At least 5 trades per day
        entry_percentile_range=(75, 85), # Conservative entry thresholds
        exit_percentile_range=(25, 35),  # Conservative exit thresholds
    )
    
    optimizer = DeltaArbitrageOptimizer(config)
    
    # Run comparison: static vs optimized
    print("🔄 Running comparison: Static vs Optimized parameters\n")
    
    # 1. Run with static parameters (original approach)
    print("📊 STATIC PARAMETERS BACKTEST")
    print("-" * 50)
    static_trades = delta_neutral_backtest(
        df,
        max_entry_cost_pct=0.5,  # Static 0.5%
        min_profit_pct=0.1,      # Static 0.1%
        max_hours=6,
        spot_fee=0.0005,
        fut_fee=0.0005
    )
    
    print(f"Static backtest results:")
    print_trade_summary(static_trades)
    
    # 2. Run with optimized parameters
    print("\n📈 OPTIMIZED PARAMETERS BACKTEST")
    print("-" * 50)
    optimized_trades, optimization_history = await optimized_delta_neutral_backtest(
        df,
        optimizer,
        optimization_window_hours=12,  # Use 12 hours for optimization
        reoptimize_every_hours=6,      # Reoptimize every 6 hours
    )
    
    print(f"Optimized backtest results:")
    print_trade_summary(optimized_trades)
    
    # 3. Analyze optimization performance
    analyze_optimization_performance(optimization_history)
    
    # 4. Performance comparison
    print(f"\n📊 PERFORMANCE COMPARISON")
    print("=" * 80)
    
    if static_trades and optimized_trades:
        static_df = pd.DataFrame(static_trades)
        optimized_df = pd.DataFrame(optimized_trades)
        
        static_total_pnl = static_df['net_pnl_pct'].sum()
        optimized_total_pnl = optimized_df['net_pnl_pct'].sum()
        
        static_win_rate = (static_df['net_pnl_pct'] > 0).mean()
        optimized_win_rate = (optimized_df['net_pnl_pct'] > 0).mean()
        
        static_avg_pnl = static_df['net_pnl_pct'].mean()
        optimized_avg_pnl = optimized_df['net_pnl_pct'].mean()
        
        print(f"{'Metric':<25} {'Static':<15} {'Optimized':<15} {'Improvement':<15}")
        print("-" * 75)
        print(f"{'Total P&L %':<25} {static_total_pnl:<15.4f} {optimized_total_pnl:<15.4f} {((optimized_total_pnl/static_total_pnl - 1) * 100 if static_total_pnl != 0 else 0):<15.1f}%")
        print(f"{'Average P&L %':<25} {static_avg_pnl:<15.4f} {optimized_avg_pnl:<15.4f} {((optimized_avg_pnl/static_avg_pnl - 1) * 100 if static_avg_pnl != 0 else 0):<15.1f}%")
        print(f"{'Win Rate':<25} {static_win_rate:<15.1%} {optimized_win_rate:<15.1%} {((optimized_win_rate/static_win_rate - 1) * 100 if static_win_rate != 0 else 0):<15.1f}%")
        print(f"{'Trade Count':<25} {len(static_trades):<15} {len(optimized_trades):<15} {((len(optimized_trades)/len(static_trades) - 1) * 100 if len(static_trades) != 0 else 0):<15.1f}%")
    
    # 5. Show optimizer statistics
    print(f"\n⚡ OPTIMIZER PERFORMANCE STATISTICS")
    print("-" * 50)
    stats = optimizer.get_optimization_stats()
    print(f"• Optimization runs: {stats['optimization_count']}")
    print(f"• Total optimization time: {stats['total_optimization_time_seconds']:.2f}s")
    print(f"• Average optimization time: {stats['average_optimization_time_seconds']*1000:.1f}ms")
    print(f"• Cache hit ratio: {stats['cache_stats']['cache_size']}/{stats['cache_stats']['max_cache_size']}")
    
    print(f"\n✅ Example completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())