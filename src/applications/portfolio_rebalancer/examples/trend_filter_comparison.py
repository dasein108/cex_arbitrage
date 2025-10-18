"""
Comparison example between standard and trend-filtered rebalancing strategies.
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


async def run_strategy_comparison():
    """Compare standard vs trend-filtered rebalancing strategies."""
    
    print("=== Portfolio Rebalancing Strategy Comparison ===\n")
    
    # Configure assets - using your volatile assets
    assets = ['VFY', 'XAN', 'AIA', 'TRUTH']  # More stable for testing
    
    # Create configuration
    config = RebalanceConfig(
        upside_threshold=0.40,      # 40% above mean triggers sell
        downside_threshold=0.35,    # 35% below mean triggers buy  
        sell_percentage=0.20,       # Sell only 20% to avoid missing rallies
        usdt_reserve=0.30,         # Keep 30% reserve for volatility
        min_order_value=15.0,      # $15 minimum order
        cooldown_minutes=30,       # 30 minute cooldown
        initial_capital=10000.0,   # $10,000 starting capital
        trading_fee=0.001          # 0.1% MEXC fee
    )
    
    # Define backtest period
    end_date = datetime.now()
    start_date = end_date - timedelta(days=19)  # Last 19 days (same as your previous test)
    
    print(f"Testing Period: {start_date.date()} to {end_date.date()}")
    print(f"Assets: {', '.join(assets)}")
    print(f"Initial Capital: ${config.initial_capital:,.2f}\n")
    
    # Strategy 1: Standard Threshold Rebalancer
    print("🔄 Running Standard Threshold Strategy...")
    
    standard_engine = BacktestEngine(
        assets=assets,
        initial_capital=config.initial_capital,
        config=config,
        use_trend_filter=False  # Standard strategy
    )
    
    try:
        standard_results = await standard_engine.run_backtest(
            start_date=start_date,
            end_date=end_date
        )
        print("✅ Standard strategy completed\n")
    except Exception as e:
        print(f"❌ Standard strategy failed: {e}\n")
        standard_results = None
    
    # Strategy 2: Trend-Filtered Rebalancer
    print("📈 Running Trend-Filtered Strategy...")
    
    trend_engine = BacktestEngine(
        assets=assets,
        initial_capital=config.initial_capital,
        config=config,
        use_trend_filter=True  # Trend-filtered strategy
    )
    
    try:
        trend_results = await trend_engine.run_backtest(
            start_date=start_date,
            end_date=end_date
        )
        print("✅ Trend-filtered strategy completed\n")
    except Exception as e:
        print(f"❌ Trend-filtered strategy failed: {e}\n")
        trend_results = None
    
    # Compare Results
    if standard_results and trend_results:
        print("="*80)
        print("STRATEGY COMPARISON RESULTS")
        print("="*80)
        
        # Print both summaries
        print(standard_results.summary())
        print(trend_results.summary())
        
        # Calculate improvements
        print("="*50)
        print("IMPROVEMENT ANALYSIS")
        print("="*50)
        
        improvements = calculate_improvements(standard_results, trend_results)
        
        for metric, improvement in improvements.items():
            if improvement > 0:
                print(f"✅ {metric}: +{improvement:.2f} (Better)")
            elif improvement < 0:
                print(f"❌ {metric}: {improvement:.2f} (Worse)")
            else:
                print(f"⚪ {metric}: No change")
        
        # Key insights
        print("\n" + "="*50)
        print("KEY INSIGHTS")
        print("="*50)
        
        if improvements['Sharpe Ratio'] > 0.1:
            print("🎯 SIGNIFICANT improvement in risk-adjusted returns!")
        
        if improvements['Max Drawdown'] > 5:  # 5% improvement in drawdown
            print("🛡️  NOTABLE reduction in maximum drawdown!")
        
        if improvements['Win Rate'] > 10:  # 10% improvement in win rate
            print("🎯 SUBSTANTIAL improvement in trade success rate!")
        
        if trend_results.trend_filter_stats:
            filter_rate = trend_results.trend_filter_stats.get('filter_rate', 0)
            if filter_rate > 0.2:  # More than 20% filtered
                print(f"🚫 Trend filter blocked {filter_rate:.1%} of potential trades")
            
            mean_rev_rate = trend_results.trend_filter_stats.get('mean_reversion_rate', 0)
            if mean_rev_rate > 0.3:  # More than 30% mean reversion
                print(f"📊 {mean_rev_rate:.1%} of trades were during mean-reversion periods")
        
        # Recommendation
        print("\n🔍 RECOMMENDATION:")
        
        score = 0
        if improvements['Sharpe Ratio'] > 0:
            score += 2
        if improvements['Max Drawdown'] > 0:
            score += 2
        if improvements['Win Rate'] > 0:
            score += 1
        if improvements['Total Return'] > 0:
            score += 1
        
        if score >= 4:
            print("🟢 STRONGLY RECOMMEND Trend-Filtered Strategy")
        elif score >= 2:
            print("🟡 CONSIDER Trend-Filtered Strategy")
        else:
            print("🔴 STICK with Standard Strategy")
    
    else:
        print("❌ Could not complete comparison due to strategy failures")


def calculate_improvements(standard: 'BacktestResults', trend: 'BacktestResults') -> dict:
    """Calculate improvements from standard to trend-filtered strategy."""
    
    improvements = {}
    
    # Performance metrics (percentage points for ratios)
    improvements['Total Return'] = (trend.total_return - standard.total_return) * 100
    improvements['Sharpe Ratio'] = trend.sharpe_ratio - standard.sharpe_ratio
    improvements['Max Drawdown'] = (standard.max_drawdown - trend.max_drawdown) * 100  # Improvement = reduction
    improvements['Win Rate'] = (trend.win_rate - standard.win_rate) * 100
    
    # Trading metrics
    improvements['Total Trades'] = trend.total_trades - standard.total_trades
    improvements['Total Fees'] = standard.total_fees - trend.total_fees  # Improvement = reduction
    
    return improvements


async def run_parameter_sensitivity():
    """Test trend filter with different threshold parameters."""
    
    print("\n" + "="*60)
    print("TREND FILTER PARAMETER SENSITIVITY ANALYSIS")
    print("="*60)
    
    assets = ['HANA', 'XAN', 'AIA']  # Smaller set for faster testing
    
    # Base configuration
    base_config = RebalanceConfig(
        upside_threshold=0.30,      # Lower for more sensitivity
        downside_threshold=0.25,
        sell_percentage=0.20,
        usdt_reserve=0.30,
        min_order_value=15.0,
        cooldown_minutes=30,
        initial_capital=10000.0,
        trading_fee=0.001
    )
    
    # Test different threshold combinations
    test_configs = [
        ('Conservative', 0.50, 0.40),  # High thresholds
        ('Moderate', 0.35, 0.30),     # Medium thresholds  
        ('Aggressive', 0.25, 0.20),   # Low thresholds
    ]
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=14)  # Shorter period for parameter testing
    
    results = []
    
    for name, upside, downside in test_configs:
        print(f"\n📊 Testing {name} thresholds (↑{upside:.0%}, ↓{downside:.0%})...")
        
        config = RebalanceConfig(
            upside_threshold=upside,
            downside_threshold=downside,
            sell_percentage=base_config.sell_percentage,
            usdt_reserve=base_config.usdt_reserve,
            min_order_value=base_config.min_order_value,
            cooldown_minutes=base_config.cooldown_minutes,
            initial_capital=base_config.initial_capital,
            trading_fee=base_config.trading_fee
        )
        
        engine = BacktestEngine(
            assets=assets,
            initial_capital=config.initial_capital,
            config=config,
            use_trend_filter=True
        )
        
        try:
            result = await engine.run_backtest(start_date, end_date)
            results.append((name, result))
            
            print(f"   Return: {result.total_return:.1%}, "
                  f"Sharpe: {result.sharpe_ratio:.2f}, "
                  f"Drawdown: {result.max_drawdown:.1%}, "
                  f"Trades: {result.total_trades}")
            
        except Exception as e:
            print(f"   Failed: {e}")
    
    # Find best configuration
    if results:
        print(f"\n🏆 PARAMETER ANALYSIS RESULTS:")
        
        best_sharpe = max(results, key=lambda x: x[1].sharpe_ratio)
        best_return = max(results, key=lambda x: x[1].total_return)
        best_drawdown = min(results, key=lambda x: x[1].max_drawdown)
        
        print(f"   Best Sharpe Ratio: {best_sharpe[0]} ({best_sharpe[1].sharpe_ratio:.2f})")
        print(f"   Best Total Return: {best_return[0]} ({best_return[1].total_return:.1%})")
        print(f"   Best Max Drawdown: {best_drawdown[0]} ({best_drawdown[1].max_drawdown:.1%})")


if __name__ == "__main__":
    print("Portfolio Rebalancer - Trend Filter Strategy Comparison\n")
    
    try:
        # Run main comparison
        asyncio.run(run_strategy_comparison())
        
        # Optionally run parameter sensitivity analysis
        run_param_test = input("\nRun parameter sensitivity analysis? (y/n): ")
        if run_param_test.lower() == 'y':
            asyncio.run(run_parameter_sensitivity())
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()