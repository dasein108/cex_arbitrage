"""
MEXC-Gate.io Futures Arbitrage Strategy Usage Examples

This module demonstrates how to use the MexcGateioFuturesArbitrageSignal strategy
for both backtesting and live trading scenarios.

Examples include:
1. Basic backtesting with default parameters
2. Advanced backtesting with custom configuration
3. Live signal generation for trading systems
4. Parameter optimization workflows
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Dict, List

from mexc_gateio_futures_arbitrage_signal import (
    MexcGateioFuturesArbitrageSignal,
    FeeStructure,
    create_mexc_gateio_futures_strategy
)


def create_sample_market_data(hours: int = 24) -> pd.DataFrame:
    """
    Create realistic sample market data for testing and examples.
    
    Args:
        hours: Number of hours of historical data to generate
        
    Returns:
        DataFrame with MEXC spot and Gate.io futures price data
    """
    # Generate timestamps (5-minute intervals)
    timestamps = pd.date_range(
        start=datetime.now(timezone.utc) - timedelta(hours=hours),
        end=datetime.now(timezone.utc),
        freq='5min'
    )
    
    # Simulate realistic price movements
    np.random.seed(42)  # For reproducible examples
    base_price = 0.05000  # 5 cents base price (typical for some altcoins)
    
    # Generate correlated price movements with slight spreads
    mexc_spot_mid = base_price + np.cumsum(np.random.normal(0, 0.000005, len(timestamps)))
    
    # Gate.io futures typically trade at slight premium/discount to spot
    futures_basis = np.random.normal(0.000002, 0.000008, len(timestamps))  # Small basis
    gateio_fut_mid = mexc_spot_mid + futures_basis
    
    # Add realistic bid-ask spreads
    mexc_spread = np.random.uniform(0.000008, 0.000015, len(timestamps))  # 8-15 bps
    gateio_spread = np.random.uniform(0.000005, 0.000012, len(timestamps))  # 5-12 bps
    
    df = pd.DataFrame({
        'mexc_spot_bid': mexc_spot_mid - mexc_spread / 2,
        'mexc_spot_ask': mexc_spot_mid + mexc_spread / 2,
        'gateio_futures_bid': gateio_fut_mid - gateio_spread / 2,
        'gateio_futures_ask': gateio_fut_mid + gateio_spread / 2,
    }, index=timestamps)
    
    # Ensure all prices are positive
    df = df.abs()
    
    # Add some additional market microstructure noise
    for col in df.columns:
        noise = np.random.normal(1.0, 0.00001, len(df))
        df[col] = df[col] * noise
    
    return df


def example_1_basic_backtesting():
    """Example 1: Basic backtesting with default parameters."""
    print("=== Example 1: Basic Backtesting ===")
    
    # Create sample data
    df = create_sample_market_data(hours=24)
    print(f"Created {len(df)} rows of sample market data (24 hours)")
    
    # Initialize strategy with default parameters
    strategy = MexcGateioFuturesArbitrageSignal()
    
    print(f"Strategy configuration:")
    print(f"  Entry quantile: {strategy.entry_quantile}")
    print(f"  Exit quantile: {strategy.exit_quantile}")
    print(f"  Position size: ${strategy.position_size_usd}")
    print(f"  Max daily trades: {strategy.max_daily_trades}")
    
    # Run backtest
    print("Running backtest...")
    performance = strategy.backtest(df)
    
    # Display results
    print("\n--- Backtest Results ---")
    print(f"Total trades executed: {performance.total_trades}")
    print(f"Total P&L: ${performance.total_pnl_usd:.2f} ({performance.total_pnl_pct:.2f}%)")
    print(f"Win rate: {performance.win_rate:.1f}%")
    print(f"Average trade P&L: ${performance.avg_trade_pnl:.2f}")
    print(f"Maximum drawdown: {performance.max_drawdown:.2f}%")
    print(f"Sharpe ratio: {performance.sharpe_ratio:.2f}")
    
    if hasattr(performance, 'strategy_metrics'):
        metrics = performance.strategy_metrics
        print(f"\n--- Strategy-Specific Metrics ---")
        print(f"Average MEXC to futures spread: {metrics['avg_mexc_to_fut_spread']*100:.3f}%")
        print(f"Average futures to MEXC spread: {metrics['avg_fut_to_mexc_spread']*100:.3f}%")
        print(f"Average spread volatility: {metrics['avg_volatility']*100:.3f}%")
        print(f"Opportunity rate: {metrics['opportunity_rate_pct']:.1f}%")
        print(f"Total opportunities: {metrics['total_opportunities']}")
    
    return performance


def example_2_advanced_backtesting():
    """Example 2: Advanced backtesting with custom configuration."""
    print("\n=== Example 2: Advanced Backtesting ===")
    
    # Create longer sample data
    df = create_sample_market_data(hours=72)  # 3 days
    print(f"Created {len(df)} rows of sample market data (72 hours)")
    
    # Define custom fee structure
    custom_fees = FeeStructure(
        mexc_spot_maker_fee=0.0008,      # 0.08% maker fee (VIP level)
        mexc_spot_taker_fee=0.001,       # 0.1% taker fee
        gateio_futures_maker_fee=0.0002, # 0.02% futures maker
        gateio_futures_taker_fee=0.0005, # 0.05% futures taker (better rates)
        funding_rate_daily=0.00008,      # Lower funding cost
        transfer_fee_usd=0.5             # Reduced transfer fee
    )
    
    # Initialize strategy with optimized parameters
    strategy = MexcGateioFuturesArbitrageSignal(
        entry_quantile=0.75,             # More aggressive entry (75th percentile)
        exit_quantile=0.25,              # More aggressive exit (25th percentile)
        historical_window_hours=48,      # Longer history for better quantiles
        position_size_usd=2000.0,        # Larger position size
        max_daily_trades=75,             # Allow more trades per day
        volatility_adjustment=True,      # Enable adaptive thresholds
        risk_limit_pct=0.03,            # Lower risk limit (3%)
        fee_structure=custom_fees
    )
    
    print(f"Advanced strategy configuration:")
    print(f"  Entry quantile: {strategy.entry_quantile} (more aggressive)")
    print(f"  Exit quantile: {strategy.exit_quantile} (more aggressive)")
    print(f"  Historical window: {strategy.historical_window_hours} hours")
    print(f"  Position size: ${strategy.position_size_usd}")
    print(f"  Volatility adjustment: {strategy.volatility_adjustment}")
    print(f"  Custom fees: MEXC {custom_fees.mexc_spot_taker_fee*100:.2f}%, Gate.io {custom_fees.gateio_futures_taker_fee*100:.2f}%")
    
    # Run advanced backtest
    print("Running advanced backtest...")
    performance = strategy.backtest(df)
    
    # Display detailed results
    print("\n--- Advanced Backtest Results ---")
    print(f"Total trades executed: {performance.total_trades}")
    print(f"Total P&L: ${performance.total_pnl_usd:.2f} ({performance.total_pnl_pct:.2f}%)")
    print(f"Win rate: {performance.win_rate:.1f}%")
    print(f"Average trade P&L: ${performance.avg_trade_pnl:.2f}")
    print(f"Maximum drawdown: {performance.max_drawdown:.2f}%")
    print(f"Sharpe ratio: {performance.sharpe_ratio:.2f}")
    print(f"Trade frequency: {performance.trade_freq:.1f} minutes between trades")
    
    # Analyze individual trades
    if performance.trades:
        profitable_trades = [t for t in performance.trades if t.pnl_usdt > 0]
        losing_trades = [t for t in performance.trades if t.pnl_usdt <= 0]
        
        print(f"\n--- Trade Analysis ---")
        print(f"Profitable trades: {len(profitable_trades)}")
        print(f"Losing trades: {len(losing_trades)}")
        
        if profitable_trades:
            avg_profit = np.mean([t.pnl_usdt for t in profitable_trades])
            max_profit = max([t.pnl_usdt for t in profitable_trades])
            print(f"Average profit per winning trade: ${avg_profit:.2f}")
            print(f"Maximum profit in single trade: ${max_profit:.2f}")
        
        if losing_trades:
            avg_loss = np.mean([t.pnl_usdt for t in losing_trades])
            max_loss = min([t.pnl_usdt for t in losing_trades])
            print(f"Average loss per losing trade: ${avg_loss:.2f}")
            print(f"Maximum loss in single trade: ${max_loss:.2f}")
    
    return performance


def example_3_live_signal_generation():
    """Example 3: Live signal generation for trading systems."""
    print("\n=== Example 3: Live Signal Generation ===")
    
    # Create recent market data (last 6 hours)
    df = create_sample_market_data(hours=6)
    print(f"Created {len(df)} rows of recent market data")
    
    # Initialize strategy for live trading
    strategy = create_mexc_gateio_futures_strategy(
        entry_quantile=0.80,
        exit_quantile=0.20,
        position_size_usd=1500.0
    )
    
    print("Initializing strategy for live trading...")
    
    # Simulate building up historical context
    print("Building historical spread context...")
    for timestamp in df.index[:50]:  # Process first 50 periods to build history
        strategy.calculate_spread_metrics(df, timestamp)
    
    # Generate live signals for recent periods
    print("\n--- Live Trading Signals ---")
    live_signals = []
    
    for timestamp in df.index[-10:]:  # Last 10 periods as "live" data
        signal = strategy.get_current_signal(df, timestamp)
        live_signals.append(signal)
        
        # Display signal information
        print(f"\nTimestamp: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Entry signal: {signal['entry_signal']}")
        print(f"  Exit signal: {signal['exit_signal']}")
        print(f"  Favorable direction: {signal['favorable_direction']}")
        print(f"  MEXC→Futures spread: {signal['mexc_to_fut_spread']*100:.3f}% (percentile: {signal['mexc_to_fut_percentile']:.1f})")
        print(f"  Futures→MEXC spread: {signal['fut_to_mexc_spread']*100:.3f}% (percentile: {signal['fut_to_mexc_percentile']:.1f})")
        print(f"  Spread volatility: {signal['spread_volatility']*100:.3f}%")
        print(f"  Daily trades remaining: {signal['daily_trades_remaining']}")
        
        if signal['entry_signal']:
            print(f"  🚨 ENTRY SIGNAL DETECTED - Direction: {signal['favorable_direction']}")
        elif signal['exit_signal']:
            print(f"  🚨 EXIT SIGNAL DETECTED")
    
    # Summary of signal activity
    entry_signals = sum(1 for s in live_signals if s['entry_signal'])
    exit_signals = sum(1 for s in live_signals if s['exit_signal'])
    
    print(f"\n--- Signal Summary ---")
    print(f"Entry signals in last 10 periods: {entry_signals}")
    print(f"Exit signals in last 10 periods: {exit_signals}")
    print(f"Signal rate: {(entry_signals + exit_signals) / len(live_signals) * 100:.1f}%")
    
    return live_signals


def example_4_parameter_optimization():
    """Example 4: Parameter optimization workflow."""
    print("\n=== Example 4: Parameter Optimization ===")
    
    # Create optimization dataset
    df = create_sample_market_data(hours=48)  # 2 days for optimization
    print(f"Created {len(df)} rows for parameter optimization")
    
    # Define parameter ranges to test
    entry_quantiles = [0.70, 0.75, 0.80, 0.85]
    exit_quantiles = [0.15, 0.20, 0.25, 0.30]
    position_sizes = [500, 1000, 1500, 2000]
    
    print("Testing parameter combinations...")
    
    optimization_results = []
    
    for entry_q in entry_quantiles:
        for exit_q in exit_quantiles:
            for pos_size in position_sizes:
                # Skip invalid combinations
                if entry_q <= exit_q:
                    continue
                
                try:
                    strategy = MexcGateioFuturesArbitrageSignal(
                        entry_quantile=entry_q,
                        exit_quantile=exit_q,
                        position_size_usd=pos_size,
                        max_daily_trades=100  # Allow many trades for optimization
                    )
                    
                    performance = strategy.backtest(df)
                    
                    # Calculate risk-adjusted return
                    risk_adjusted_return = (
                        performance.total_pnl_pct / max(performance.max_drawdown, 1.0)
                        if performance.max_drawdown > 0 else performance.total_pnl_pct
                    )
                    
                    optimization_results.append({
                        'entry_quantile': entry_q,
                        'exit_quantile': exit_q,
                        'position_size': pos_size,
                        'total_pnl_pct': performance.total_pnl_pct,
                        'total_trades': performance.total_trades,
                        'win_rate': performance.win_rate,
                        'max_drawdown': performance.max_drawdown,
                        'sharpe_ratio': performance.sharpe_ratio,
                        'risk_adjusted_return': risk_adjusted_return
                    })
                
                except Exception as e:
                    print(f"Error with params entry={entry_q}, exit={exit_q}, size={pos_size}: {e}")
                    continue
    
    # Sort by risk-adjusted return
    optimization_results.sort(key=lambda x: x['risk_adjusted_return'], reverse=True)
    
    print(f"\n--- Optimization Results (Top 5) ---")
    print("Rank | Entry Q | Exit Q | Position | Total Ret% | Trades | Win% | DrawDown% | Risk Adj Ret")
    print("-" * 90)
    
    for i, result in enumerate(optimization_results[:5], 1):
        print(f"{i:4d} | {result['entry_quantile']:7.2f} | "
              f"{result['exit_quantile']:6.2f} | ${result['position_size']:8.0f} | "
              f"{result['total_pnl_pct']:9.2f} | {result['total_trades']:6d} | "
              f"{result['win_rate']:4.1f} | {result['max_drawdown']:8.2f} | "
              f"{result['risk_adjusted_return']:11.2f}")
    
    # Recommend best configuration
    if optimization_results:
        best_config = optimization_results[0]
        print(f"\n--- Recommended Configuration ---")
        print(f"Entry quantile: {best_config['entry_quantile']}")
        print(f"Exit quantile: {best_config['exit_quantile']}")
        print(f"Position size: ${best_config['position_size']:.0f}")
        print(f"Expected performance: {best_config['total_pnl_pct']:.2f}% return")
        print(f"Expected trades: {best_config['total_trades']}")
        print(f"Expected win rate: {best_config['win_rate']:.1f}%")
    
    return optimization_results


def example_5_risk_analysis():
    """Example 5: Comprehensive risk analysis."""
    print("\n=== Example 5: Risk Analysis ===")
    
    # Create extended dataset for risk analysis
    df = create_sample_market_data(hours=96)  # 4 days
    print(f"Created {len(df)} rows for risk analysis")
    
    # Test strategy under different market conditions
    scenarios = [
        {
            'name': 'Conservative',
            'params': {
                'entry_quantile': 0.85,
                'exit_quantile': 0.15,
                'position_size_usd': 500.0,
                'max_daily_trades': 20
            }
        },
        {
            'name': 'Balanced',
            'params': {
                'entry_quantile': 0.80,
                'exit_quantile': 0.20,
                'position_size_usd': 1000.0,
                'max_daily_trades': 50
            }
        },
        {
            'name': 'Aggressive',
            'params': {
                'entry_quantile': 0.75,
                'exit_quantile': 0.25,
                'position_size_usd': 2000.0,
                'max_daily_trades': 100
            }
        }
    ]
    
    print("Testing different risk scenarios...")
    scenario_results = {}
    
    for scenario in scenarios:
        name = scenario['name']
        params = scenario['params']
        
        strategy = MexcGateioFuturesArbitrageSignal(**params)
        performance = strategy.backtest(df)
        
        scenario_results[name] = performance
        
        print(f"\n--- {name} Scenario ---")
        print(f"Total P&L: ${performance.total_pnl_usd:.2f} ({performance.total_pnl_pct:.2f}%)")
        print(f"Total trades: {performance.total_trades}")
        print(f"Win rate: {performance.win_rate:.1f}%")
        print(f"Max drawdown: {performance.max_drawdown:.2f}%")
        print(f"Sharpe ratio: {performance.sharpe_ratio:.2f}")
    
    # Risk comparison
    print(f"\n--- Risk Comparison ---")
    print("Scenario    | Return% | Trades | Win%  | Drawdown% | Sharpe | Risk Score")
    print("-" * 70)
    
    for name, perf in scenario_results.items():
        # Calculate simple risk score (lower is better)
        risk_score = (perf.max_drawdown * 0.5) - (perf.win_rate * 0.01) - (perf.sharpe_ratio * 10)
        
        print(f"{name:11} | {perf.total_pnl_pct:7.2f} | {perf.total_trades:6d} | "
              f"{perf.win_rate:5.1f} | {perf.max_drawdown:8.2f} | "
              f"{perf.sharpe_ratio:6.2f} | {risk_score:9.2f}")
    
    return scenario_results


if __name__ == '__main__':
    """Run all examples when script is executed directly."""
    print("MEXC-Gate.io Futures Arbitrage Strategy Examples")
    print("=" * 50)
    
    try:
        # Run all examples
        example_1_basic_backtesting()
        example_2_advanced_backtesting()
        example_3_live_signal_generation()
        example_4_parameter_optimization()
        example_5_risk_analysis()
        
        print("\n" + "=" * 50)
        print("All examples completed successfully!")
        print("Review the results above to understand the strategy's capabilities.")
        
    except Exception as e:
        print(f"\nError running examples: {e}")
        import traceback
        traceback.print_exc()