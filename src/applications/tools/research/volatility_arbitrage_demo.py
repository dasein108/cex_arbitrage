#!/usr/bin/env python3
"""
Volatility Arbitrage Demo Script

This script demonstrates the volatility arbitrage strategy implementation
with real market data analysis and backtesting capabilities.
"""

import asyncio
import sys
from datetime import datetime, UTC, timedelta
from pathlib import Path

# Add src to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from exchanges.structs.enums import ExchangeEnum
from applications.tools.research.spot_spot_candidate_analyzer import SpotSpotArbitrageCandidateAnalyzer
from applications.tools.research.volatility_arbitrage_backtest import VolatilityArbitrageBacktest, BacktestConfig
from applications.tools.research.volatility_indicators import VolatilityIndicators


async def demo_volatility_analysis():
    """Demo: Analyze current volatility opportunities"""
    print("=" * 80)
    print("🔍 VOLATILITY ARBITRAGE OPPORTUNITY ANALYSIS")
    print("=" * 80)
    
    # Initialize analyzer
    analyzer = SpotSpotArbitrageCandidateAnalyzer(
        exchanges=[ExchangeEnum.MEXC, ExchangeEnum.GATEIO],
        output_dir="volatility_results"
    )
    
    # Analysis parameters
    end_time = datetime.now(UTC)
    hours = 24  # Last 24 hours
    
    print(f"📅 Analysis Period: {end_time - timedelta(hours=hours)} to {end_time}")
    print(f"🏢 Exchanges: MEXC, Gate.io")
    print(f"⏰ Timeframe: 5-minute candles")
    print()
    
    try:
        # Run analysis
        results = await analyzer.analyze(end_time, hours, max_symbols=15)
        
        # Display results
        print(f"📊 ANALYSIS RESULTS:")
        print(f"   Opportunities Found: {results['opportunities_count']}")
        print(f"   Analysis Period: {results['analysis_period']}")
        
        if results['ranked_opportunities']:
            print(f"\n🎯 TOP VOLATILITY OPPORTUNITIES:")
            
            for i, (pair_tuple, signal) in enumerate(results['ranked_opportunities'][:5]):
                quality = signal.strength * signal.confidence
                print(f"\n   {i+1}. {signal.from_pair} → {signal.to_pair}")
                print(f"      Quality Score: {quality:.3f}")
                print(f"      Signal Strength: {signal.strength:.3f}")
                print(f"      Confidence: {signal.confidence:.3f}")
                print(f"      IRBI Score: {signal.irbi_score:.3f}")
                print(f"      VRD Score: {signal.vrd_score:.3f}")
                print(f"      SPS Score: {signal.sps_score:.3f}")
        
        if results['report_path']:
            print(f"\n💾 Detailed report saved to: {results['report_path']}")
        
        return results
        
    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        return None


async def demo_backtest():
    """Demo: Simple backtest with mock data"""
    print("\n" + "=" * 80)
    print("📈 VOLATILITY ARBITRAGE BACKTEST DEMO")
    print("=" * 80)
    
    # Create mock data for demonstration
    import pandas as pd
    import numpy as np
    
    # Generate mock price data for 3 symbols
    dates = pd.date_range(start='2024-01-01', end='2024-01-10', freq='5min')
    
    symbols = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT']
    mock_data = {}
    
    np.random.seed(42)  # For reproducible results
    
    for symbol in symbols:
        # Base price with different volatility characteristics
        base_price = {'BTC/USDT': 45000, 'ETH/USDT': 2500, 'BNB/USDT': 300}[symbol]
        volatility = {'BTC/USDT': 0.02, 'ETH/USDT': 0.03, 'BNB/USDT': 0.04}[symbol]
        
        # Generate random walk with varying volatility
        returns = np.random.normal(0, volatility, len(dates))
        
        # Add some volatility spikes for interesting signals
        spike_indices = np.random.choice(len(dates), size=20, replace=False)
        returns[spike_indices] *= 3  # Create volatility spikes
        
        prices = base_price * np.exp(np.cumsum(returns))
        
        # Create OHLCV data
        df = pd.DataFrame(index=dates)
        df['close'] = prices
        df['open'] = df['close'].shift(1).fillna(df['close'].iloc[0])
        df['high'] = df[['open', 'close']].max(axis=1) * (1 + np.random.uniform(0, 0.01, len(df)))
        df['low'] = df[['open', 'close']].min(axis=1) * (1 - np.random.uniform(0, 0.01, len(df)))
        df['volume'] = np.random.uniform(1000, 10000, len(df))
        
        mock_data[symbol] = df
    
    print(f"📊 Mock Data Generated:")
    for symbol, df in mock_data.items():
        print(f"   {symbol}: {len(df)} candles, Price range: ${df['close'].min():.0f} - ${df['close'].max():.0f}")
    
    # Configure backtest
    config = BacktestConfig(
        initial_capital=100000.0,
        max_position_size=0.15,  # 15% position size
        maker_fee=0.001,
        taker_fee=0.0015,
        default_execution='taker',
        stop_loss_pct=0.05,
        take_profit_pct=0.03
    )
    
    print(f"\n⚙️  Backtest Configuration:")
    print(f"   Initial Capital: ${config.initial_capital:,.0f}")
    print(f"   Max Position Size: {config.max_position_size:.1%}")
    print(f"   Maker Fee: {config.maker_fee:.3%}")
    print(f"   Taker Fee: {config.taker_fee:.3%}")
    print(f"   Stop Loss: {config.stop_loss_pct:.1%}")
    print(f"   Take Profit: {config.take_profit_pct:.1%}")
    
    # Run backtest
    backtest = VolatilityArbitrageBacktest(config)
    results = backtest.run_backtest(mock_data)
    
    # Display results
    print(f"\n📈 BACKTEST RESULTS:")
    print(f"   Total Trades: {results.total_trades}")
    print(f"   Winning Trades: {results.winning_trades}")
    print(f"   Losing Trades: {results.losing_trades}")
    print(f"   Win Rate: {results.win_rate:.1%}")
    print(f"   Total PnL: ${results.total_pnl:,.2f}")
    print(f"   Total Fees: ${results.total_fees:,.2f}")
    print(f"   Net PnL: ${results.total_pnl - results.total_fees:,.2f}")
    print(f"   Max Drawdown: {results.max_drawdown:.1%}")
    print(f"   Sharpe Ratio: {results.sharpe_ratio:.3f}")
    print(f"   Avg Trade PnL: ${results.avg_trade_pnl:,.2f}")
    
    if results.trades:
        print(f"\n🔄 RECENT TRADES:")
        for trade in results.trades[-5:]:  # Show last 5 trades
            action_emoji = {"open": "🟢", "close": "🔴", "hedge": "🔵"}.get(trade.action, "⚪")
            print(f"   {action_emoji} {trade.timestamp.strftime('%Y-%m-%d %H:%M')} | "
                  f"{trade.action.upper()} {trade.to_symbol or trade.from_symbol} | "
                  f"Size: {trade.size:.2f} | Price: ${trade.price:.2f} | "
                  f"PnL: ${trade.pnl:.2f} | Fees: ${trade.fees:.2f}")
    
    # Save results
    output_path = backtest.save_results(results, "demo_backtest_results.json")
    
    return results


def demo_indicators():
    """Demo: Test volatility indicators with sample data"""
    print("\n" + "=" * 80)
    print("📊 VOLATILITY INDICATORS DEMO")
    print("=" * 80)
    
    import pandas as pd
    import numpy as np
    
    # Create sample data with different volatility patterns
    dates = pd.date_range(start='2024-01-01', periods=100, freq='5min')
    
    # Stable pair (low volatility)
    stable_data = pd.DataFrame(index=dates)
    stable_returns = np.random.normal(0, 0.01, len(dates))  # 1% volatility
    stable_prices = 100 * np.exp(np.cumsum(stable_returns))
    stable_data['close'] = stable_prices
    stable_data['high'] = stable_prices * 1.005
    stable_data['low'] = stable_prices * 0.995
    
    # Volatile pair (high volatility with spikes)
    volatile_data = pd.DataFrame(index=dates)
    volatile_returns = np.random.normal(0, 0.03, len(dates))  # 3% volatility
    # Add some spikes
    spike_indices = [20, 45, 70]
    volatile_returns[spike_indices] = [0.08, -0.06, 0.07]  # Large moves
    volatile_prices = 100 * np.exp(np.cumsum(volatile_returns))
    volatile_data['close'] = volatile_prices
    volatile_data['high'] = volatile_prices * 1.02
    volatile_data['low'] = volatile_prices * 0.98
    
    print(f"📈 Sample Data Created:")
    print(f"   Stable Pair: σ = {stable_data['close'].pct_change().std():.4f}")
    print(f"   Volatile Pair: σ = {volatile_data['close'].pct_change().std():.4f}")
    
    # Test indicators
    indicators = VolatilityIndicators(
        irbi_threshold=0.15,
        vrd_threshold=1.3,
        sps_threshold=0.6
    )
    
    # Calculate individual indicators
    irbi_stable = indicators.calculate_irbi(stable_data)
    irbi_volatile = indicators.calculate_irbi(volatile_data)
    vrd = indicators.calculate_vrd(stable_data, volatile_data)
    sps_stable = indicators.calculate_sps(stable_data)
    sps_volatile = indicators.calculate_sps(volatile_data)
    
    print(f"\n📊 Indicator Results (Latest Values):")
    print(f"   IRBI - Stable: {irbi_stable.iloc[-1]:.3f}")
    print(f"   IRBI - Volatile: {irbi_volatile.iloc[-1]:.3f}")
    print(f"   VRD (Volatile/Stable): {vrd.iloc[-1]:.3f}")
    print(f"   SPS - Stable: {sps_stable.iloc[-1]:.3f}")
    print(f"   SPS - Volatile: {sps_volatile.iloc[-1]:.3f}")
    
    # Generate signal
    signal = indicators.generate_signal(
        stable_data, volatile_data, 
        "STABLE/USDT", "VOLATILE/USDT"
    )
    
    print(f"\n🎯 Generated Signal:")
    print(f"   Action: {signal.action}")
    print(f"   From Pair: {signal.from_pair}")
    print(f"   To Pair: {signal.to_pair}")
    print(f"   Strength: {signal.strength:.3f}")
    print(f"   Confidence: {signal.confidence:.3f}")
    print(f"   Quality Score: {signal.strength * signal.confidence:.3f}")
    
    return signal


async def main():
    """Main demo runner"""
    print("🚀 VOLATILITY ARBITRAGE STRATEGY DEMO")
    print("🎯 Testing volatility-based cross-pair arbitrage with delta neutrality")
    print()
    
    # Demo 1: Volatility Indicators
    demo_indicators()
    
    # Demo 2: Backtest with mock data
    await demo_backtest()
    
    # Demo 3: Real market analysis (commented out to avoid API calls in demo)
    print("\n" + "=" * 80)
    print("🔍 REAL MARKET ANALYSIS")
    print("=" * 80)
    print("ℹ️  Real market analysis requires exchange API access.")
    print("   Uncomment the line below to run with real data:")
    print("   # await demo_volatility_analysis()")
    
    # Uncomment to run real analysis:
    # await demo_volatility_analysis()
    
    print("\n✅ Demo completed successfully!")
    print("\n📋 Next Steps:")
    print("   1. Run real market analysis with exchange connections")
    print("   2. Adjust indicator thresholds based on market conditions")
    print("   3. Implement live trading with proper risk management")
    print("   4. Monitor performance and adjust strategy parameters")


if __name__ == "__main__":
    asyncio.run(main())