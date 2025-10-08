#!/usr/bin/env python3
"""
Example Usage of Multi-Symbol Analytics

Demonstrates how to use the flexible analytics tools with different symbols
and exchange combinations. Perfect for agents to understand the capabilities.
"""

import asyncio
import sys
from pathlib import Path

# Add paths for imports from project root
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent
src_path = project_root / "src"
analytics_path = project_root / "hedged_arbitrage" / "analytics"

sys.path.insert(0, str(src_path))
sys.path.insert(0, str(analytics_path))

from exchanges.structs.common import Symbol
from exchanges.structs.types import AssetName

try:
    from .data_fetcher import MultiSymbolDataFetcher, UnifiedSnapshot
    from .spread_analyzer import SpreadAnalyzer
    from .pnl_calculator import PnLCalculator
    from .performance_tracker import PerformanceTracker
except ImportError:
    from data_fetcher import MultiSymbolDataFetcher, UnifiedSnapshot
    from spread_analyzer import SpreadAnalyzer
    from pnl_calculator import PnLCalculator
    from performance_tracker import PerformanceTracker


async def example_neiroeth_analysis():
    """Example: Analyze NEIROETH with default exchanges."""
    print("🔍 Example 1: NEIROETH Analysis")
    print("=" * 50)
    
    # Create symbol
    symbol = Symbol(base=AssetName("NEIROETH"), quote=AssetName("USDT"))
    
    # Initialize components
    fetcher = MultiSymbolDataFetcher(symbol)
    analyzer = SpreadAnalyzer(fetcher)
    calculator = PnLCalculator()
    
    # Initialize data fetcher
    if await fetcher.initialize():
        print(f"✅ Initialized for {symbol.base}/{symbol.quote}")
        
        # Get latest data
        snapshot = await fetcher.get_latest_snapshots()
        if snapshot:
            print(f"📊 Latest data timestamp: {snapshot.timestamp}")
            spreads = snapshot.get_spreads()
            cross_spreads = snapshot.get_cross_exchange_spreads()
            print(f"   Internal spreads: {len(spreads)} exchanges")
            print(f"   Cross-exchange spreads: {len(cross_spreads)} pairs")
        
        # Analyze opportunities
        opportunities = await analyzer.identify_opportunities()
        print(f"🎯 Found {len(opportunities)} arbitrage opportunities")
        
        if opportunities:
            best = opportunities[0]
            print(f"   Best: {best.spread_pct:.3f}% spread ({best.opportunity_type})")
            
            # Calculate P&L
            pnl = await calculator.calculate_arbitrage_pnl(best, 50.0)
            if pnl:
                print(f"   Estimated profit: ${pnl.net_profit:.4f}")
                print(f"   Capital required: ${pnl.capital_required:.2f}")
    else:
        print("❌ Failed to initialize")
    
    print()


async def example_btc_custom_exchanges():
    """Example: Analyze BTC with custom exchange configuration."""
    print("🔍 Example 2: BTC with Custom Exchanges")
    print("=" * 50)
    
    # Create symbol
    symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
    
    # Custom exchanges (Note: These would need to be configured in the system)
    custom_exchanges = {
        'GATEIO_SPOT': 'GATEIO_SPOT',
        'MEXC_SPOT': 'MEXC_SPOT'
        # Could add: 'BINANCE_SPOT': 'BINANCE_SPOT' if configured
    }
    
    # Initialize with custom exchanges
    fetcher = MultiSymbolDataFetcher(symbol, custom_exchanges)
    analyzer = SpreadAnalyzer(fetcher, entry_threshold_pct=0.05)  # Lower threshold for BTC
    
    if await fetcher.initialize():
        print(f"✅ Initialized for {symbol.base}/{symbol.quote}")
        print(f"📊 Using exchanges: {list(custom_exchanges.keys())}")
        
        # Historical analysis
        stats = await analyzer.get_historical_statistics(hours_back=12)
        if stats:
            print(f"📈 Historical analysis (12h):")
            print(f"   Mean spread: {stats.mean_spread:.4f}%")
            print(f"   Opportunities/hour: {stats.opportunity_rate:.2f}")
            print(f"   Volatility regime: {stats.volatility_regime}")
            print(f"   Trend: {stats.trend_direction}")
        else:
            print("📈 No historical data available")
    else:
        print("❌ Failed to initialize")
    
    print()


async def example_multi_symbol_comparison():
    """Example: Compare multiple symbols for portfolio optimization."""
    print("🔍 Example 3: Multi-Symbol Comparison")
    print("=" * 50)
    
    symbols = [
        Symbol(base=AssetName("NEIROETH"), quote=AssetName("USDT")),
        Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
        Symbol(base=AssetName("ETH"), quote=AssetName("USDT"))
    ]
    
    results = []
    
    for symbol in symbols:
        print(f"📊 Analyzing {symbol.base}/{symbol.quote}...")
        
        try:
            fetcher = MultiSymbolDataFetcher(symbol)
            analyzer = SpreadAnalyzer(fetcher)
            calculator = PnLCalculator()
            
            if await fetcher.initialize():
                # Quick analysis
                opportunities = await analyzer.identify_opportunities()
                
                if opportunities:
                    # Estimate portfolio impact
                    portfolio_impact = await calculator.estimate_portfolio_impact(
                        opportunities, portfolio_size=10000.0, max_position_pct=3.0
                    )
                    
                    results.append({
                        'symbol': f"{symbol.base}/{symbol.quote}",
                        'opportunities': len(opportunities),
                        'estimated_profit': portfolio_impact['total_estimated_profit'],
                        'risk_adjusted_return': portfolio_impact['risk_adjusted_return'],
                        'capital_utilization': portfolio_impact['capital_utilization_pct']
                    })
                else:
                    results.append({
                        'symbol': f"{symbol.base}/{symbol.quote}",
                        'opportunities': 0,
                        'estimated_profit': 0,
                        'risk_adjusted_return': 0
                    })
            else:
                print(f"   ❌ Failed to initialize {symbol.base}/{symbol.quote}")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    # Sort by risk-adjusted return
    results.sort(key=lambda x: x['risk_adjusted_return'], reverse=True)
    
    print("\n🏆 RANKING:")
    for i, result in enumerate(results, 1):
        print(f"{i}. {result['symbol']}")
        print(f"   Opportunities: {result['opportunities']}")
        print(f"   Estimated Profit: ${result['estimated_profit']:.2f}")
        print(f"   Risk-Adjusted Return: {result['risk_adjusted_return']:.4f}")
        if 'capital_utilization' in result:
            print(f"   Capital Utilization: {result['capital_utilization']:.1f}%")
        print()


async def example_performance_tracking():
    """Example: Performance tracking capabilities."""
    print("🔍 Example 4: Performance Tracking")
    print("=" * 50)
    
    tracker = PerformanceTracker()
    
    # Simulate some trading activity
    from datetime import datetime, timedelta
    from performance_tracker import ExecutionMetrics
    from pnl_calculator import TradeExecution, ArbitragePnL
    
    # Mock execution
    execution = ExecutionMetrics(
        trade_id="example_001",
        execution_start=datetime.utcnow() - timedelta(milliseconds=45),
        execution_end=datetime.utcnow(),
        execution_duration_ms=45.0,
        planned_price=1.5000,
        executed_price=1.5001,
        price_slippage_pct=0.007,
        execution_success=True
    )
    tracker.record_execution(execution)
    
    # Mock P&L
    buy_exec = TradeExecution(
        exchange='MEXC_SPOT', side='buy', symbol='EXAMPLE/USDT',
        quantity=100.0, price=1.5001, fee_rate=0.002,
        fee_amount=0.30, slippage=0.01, timestamp=datetime.utcnow()
    )
    
    sell_exec = TradeExecution(
        exchange='GATEIO_SPOT', side='sell', symbol='EXAMPLE/USDT',
        quantity=100.0, price=1.5051, fee_rate=0.002,
        fee_amount=0.30, slippage=0.01, timestamp=datetime.utcnow()
    )
    
    pnl = ArbitragePnL(
        opportunity_id="example_001",
        calculation_time=datetime.utcnow(),
        buy_execution=buy_exec,
        sell_execution=sell_exec,
        total_quantity=100.0,
        gross_revenue=150.51,
        gross_cost=150.01,
        gross_profit=0.50,
        total_fees=0.60,
        estimated_slippage=0.02,
        funding_cost=0.0,
        execution_cost=1.0,
        net_profit=-1.12,
        net_profit_pct=-0.075,
        max_drawdown_risk=15.0,
        execution_risk_score=0.15,
        capital_required=150.51
    )
    tracker.record_trade_pnl(pnl)
    
    # Get performance metrics
    performance = tracker.get_current_performance()
    print("📊 Current Performance:")
    print(f"   Execution time: {performance.get('avg_execution_time_ms', 0):.1f}ms")
    print(f"   Success rate: {performance.get('execution_success_rate_pct', 0):.1f}%")
    print(f"   Total trades: {performance.get('total_trades', 0)}")
    print(f"   Cumulative P&L: ${performance.get('cumulative_pnl', 0):.4f}")
    
    # Risk metrics
    risk = tracker.get_risk_metrics()
    if not risk.get('insufficient_data'):
        print("\n🛡️  Risk Metrics:")
        print(f"   Max drawdown: {risk.get('max_drawdown_pct', 0):.2f}%")
        print(f"   Volatility: {risk.get('volatility', 0):.4f}")
    
    print()


async def main():
    """Run all examples."""
    print("🚀 Multi-Symbol Analytics Examples")
    print("=" * 60)
    print()
    
    try:
        await example_neiroeth_analysis()
        await example_btc_custom_exchanges()
        await example_multi_symbol_comparison()
        await example_performance_tracking()
        
        print("✅ All examples completed successfully!")
        print()
        print("💡 Key Takeaways:")
        print("• Analytics work with any symbol (not just NEIROETH)")
        print("• Exchanges are configurable for each symbol")
        print("• Comprehensive P&L and risk analysis available")
        print("• Performance tracking for strategy optimization")
        print("• Agent-friendly structured data returns")
        print()
        print("🔧 Command Line Usage:")
        print("python analyze_symbol.py --symbol BTC --quote USDT")
        print("python analyze_symbol.py --symbol ETH --quote USDT --mode historical")
        print("python analyze_symbol.py --mode portfolio --symbols BTC,ETH,NEIROETH --quote USDT")
        
    except Exception as e:
        print(f"❌ Example failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())