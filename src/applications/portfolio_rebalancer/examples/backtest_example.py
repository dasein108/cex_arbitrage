"""
Example backtest for portfolio rebalancing strategy.
"""

import asyncio
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add parent directories to path
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from exchanges.structs.enums import KlineInterval
from src.applications.portfolio_rebalancer import (
    BacktestEngine, RebalanceConfig
)


async def run_backtest():
    """Run a sample backtest with volatile crypto assets."""
    
    # Configure assets - use actual MEXC trading pairs
    # These are examples - replace with your chosen volatile assets
    assets = ['VFY', 'XAN', 'AIA', 'TRUTH']  # More stable for testing
    # assets = ['BTC', 'ETH', 'SOL']  # More volatile options
    
    # Create configuration optimized for volatile assets
    config = RebalanceConfig(
        upside_threshold=0.10,      # 40% above mean triggers sell
        downside_threshold=0.15,    # 35% below mean triggers buy
        sell_percentage=0.20,       # Sell only 20% to avoid missing rallies
        usdt_reserve=0.30,         # Keep 30% reserve for volatility
        min_order_value=15.0,      # $15 minimum order
        cooldown_minutes=30,       # 30 minute cooldown
        initial_capital=10000.0,   # $10,000 starting capital
        trading_fee=0.001          # 0.1% MEXC fee
    )
    
    # Create backtest engine (it will initialize MEXC config internally)
    engine = BacktestEngine(
        assets=assets,
        initial_capital=config.initial_capital,
        config=config,
        use_trend_filter=True
    )
    
    # Define backtest period
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)  # Last 30 days
    
    print(f"""
=== Portfolio Rebalancing Backtest ===
Assets: {', '.join(assets)}
Period: {start_date.date()} to {end_date.date()}
Initial Capital: ${config.initial_capital:,.2f}

Configuration:
- Upside Threshold: {config.upside_threshold:.0%}
- Downside Threshold: {config.downside_threshold:.0%}
- Sell Percentage: {config.sell_percentage:.0%}
- USDT Reserve: {config.usdt_reserve:.0%}
- Cooldown: {config.cooldown_minutes} minutes
""")
    
    # Run backtest
    try:
        results = await engine.run_backtest(
            start_date=start_date,
            end_date=end_date
        )
        
        # Print results
        print(results.summary())
        
        # Optional: Plot results if matplotlib is available
        try:
            engine.plot_results()
        except Exception as e:
            print(f"Could not plot results: {e}")
        
        # Print some additional insights
        print("\n=== Additional Insights ===")
        
        if results.total_rebalances > 0:
            rebalance_frequency = results.days_tested / results.total_rebalances
            print(f"Rebalancing Frequency: Every {rebalance_frequency:.1f} days")
        
        if results.total_return > 0:
            print(f"Outperformed Buy & Hold: Analysis needed")
        else:
            print(f"Underperformed Buy & Hold: Consider adjusting thresholds")
        
        if results.max_drawdown < -0.20:
            print(f"High Drawdown Warning: Consider tighter risk management")
        
    except Exception as e:
        print(f"Backtest failed: {e}")
        import traceback
        traceback.print_exc()


async def parameter_sweep():
    """Test different parameter combinations."""
    
    assets = ['BTC', 'ETH', 'BNB']
    
    # Parameter combinations to test
    test_configs = [
        # Conservative
        RebalanceConfig(
            upside_threshold=0.50,
            downside_threshold=0.40,
            sell_percentage=0.15,
            usdt_reserve=0.40
        ),
        # Balanced (default)
        RebalanceConfig(
            upside_threshold=0.40,
            downside_threshold=0.35,
            sell_percentage=0.20,
            usdt_reserve=0.30
        ),
        # Aggressive
        RebalanceConfig(
            upside_threshold=0.30,
            downside_threshold=0.25,
            sell_percentage=0.25,
            usdt_reserve=0.20
        ),
    ]
    
    # No need to setup MEXC client manually - BacktestEngine handles it internally
    
    # Test period
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    print("=== Parameter Sweep Results ===\n")
    
    results_summary = []
    
    for i, config in enumerate(test_configs, 1):
        print(f"Testing Configuration {i}...")
        
        engine = BacktestEngine(
            assets=assets,
            initial_capital=10000,
            config=config
        )
        
        try:
            results = await engine.run_backtest(
                start_date=start_date,
                end_date=end_date
            )
            
            results_summary.append({
                'config': f"Config {i}",
                'upside': config.upside_threshold,
                'downside': config.downside_threshold,
                'return': results.total_return,
                'sharpe': results.sharpe_ratio,
                'drawdown': results.max_drawdown,
                'trades': results.total_trades
            })
            
        except Exception as e:
            print(f"  Failed: {e}")
    
    # Print comparison
    print("\n=== Configuration Comparison ===")
    print("Config | Upside | Downside | Return | Sharpe | Drawdown | Trades")
    print("-------|--------|----------|--------|--------|----------|--------")
    
    for r in results_summary:
        print(f"{r['config']:6} | {r['upside']:.0%:6} | {r['downside']:.0%:8} | "
              f"{r['return']:+.2%:6} | {r['sharpe']:.2f:6} | {r['drawdown']:.2%:8} | "
              f"{r['trades']:6}")


if __name__ == "__main__":
    print("Starting Portfolio Rebalancing Backtest...")
    
    # Run single backtest
    asyncio.run(run_backtest())
    
    # Optionally run parameter sweep
    # asyncio.run(parameter_sweep())