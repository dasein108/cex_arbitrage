#!/usr/bin/env python3
"""
Reverse Arbitrage Strategies Demo

Demonstrates the three new reverse arbitrage strategies:
1. Reverse Delta-Neutral (profit from spread compression)
2. Inventory-Based Spot Arbitrage (no transfer fees)
3. Spread Volatility Harvesting (multi-tier approach)

Usage:
    python reverse_arbitrage_demo.py
"""

import sys
import asyncio
from pathlib import Path
import pandas as pd
from datetime import datetime

from exchanges.structs import Symbol

# Add src to path
src_path = Path(__file__).parent / 'src'
sys.path.insert(0, str(src_path))

from trading.research.cross_arbitrage.arbitrage_analyzer import ArbitrageAnalyzer


def extract_reverse_delta_neutral_trades(df: pd.DataFrame) -> pd.DataFrame:
    """Extract all RDN trades with entry/exit details."""
    trades = []
    
    for idx in df.index:
        if df.loc[idx, 'rdn_signal'].startswith('EXIT_'):
            # Found an exit, extract the trade details
            exit_reason = df.loc[idx, 'rdn_signal'].replace('EXIT_', '')
            
            trade = {
                'strategy': 'Reverse Delta-Neutral',
                'entry_time': df.loc[idx, 'rdn_entry_time'],
                'exit_time': idx,
                'entry_spread': df.loc[idx, 'rdn_entry_spread'],
                'exit_spread': df.loc[idx, 'rdn_combined_spread'],
                'spot_entry_price': df.loc[idx, 'rdn_spot_entry'],
                'futures_entry_price': df.loc[idx, 'rdn_futures_entry'],
                'spot_exit_price': df.loc[idx, 'rdn_spot_exit'],
                'futures_exit_price': df.loc[idx, 'rdn_futures_exit'],
                'holding_hours': df.loc[idx, 'rdn_holding_hours'],
                'trade_pnl_pct': df.loc[idx, 'rdn_trade_pnl'],
                'exit_reason': exit_reason,
                'spread_compression': df.loc[idx, 'rdn_entry_spread'] - df.loc[idx, 'rdn_combined_spread']
            }
            trades.append(trade)
    
    return pd.DataFrame(trades)


def extract_inventory_arbitrage_trades(df: pd.DataFrame) -> pd.DataFrame:
    """Extract all inventory arbitrage trades with details."""
    trades = []
    
    for idx in df.index:
        if df.loc[idx, 'inv_signal'] == 'TRADE':
            trade = {
                'strategy': 'Inventory Spot Arbitrage',
                'trade_time': idx,
                'direction': df.loc[idx, 'inv_trade_direction'],
                'trade_size_usd': df.loc[idx, 'inv_trade_size_usd'],
                'spread_captured_pct': df.loc[idx, 'inv_spread_captured'],
                'trade_pnl_pct': df.loc[idx, 'inv_trade_pnl'],
                'mexc_balance_before': df.shift(1).loc[idx, 'inv_mexc_balance'] if idx in df.shift(1).index else df.loc[idx, 'inv_mexc_balance'],
                'gateio_balance_before': df.shift(1).loc[idx, 'inv_gateio_balance'] if idx in df.shift(1).index else df.loc[idx, 'inv_gateio_balance'],
                'mexc_balance_after': df.loc[idx, 'inv_mexc_balance'],
                'gateio_balance_after': df.loc[idx, 'inv_gateio_balance'],
                'total_balance_after': df.loc[idx, 'inv_total_balance'],
                'balance_ratio_after': df.loc[idx, 'inv_balance_ratio'],
                'imbalance_penalty': df.loc[idx, 'inv_imbalance_penalty']
            }
            trades.append(trade)
    
    return pd.DataFrame(trades)


def extract_volatility_harvesting_trades(df: pd.DataFrame) -> pd.DataFrame:
    """Extract all volatility harvesting position entries and exits."""
    trades = []
    
    # Track entries
    for idx in df.index:
        if df.loc[idx, 'svh_signal'] == 'ENTER':
            trade = {
                'strategy': 'Spread Volatility Harvesting',
                'action': 'ENTRY',
                'time': idx,
                'position_id': df.loc[idx, 'svh_position_id'],
                'position_tier': df.loc[idx, 'svh_position_tier'],
                'position_size': df.loc[idx, 'svh_position_size'],
                'entry_spread': df.loc[idx, 'svh_entry_spread'],
                'exit_spread': None,
                'spread_volatility': df.loc[idx, 'svh_spread_volatility'],
                'active_positions': df.loc[idx, 'svh_active_positions'],
                'trade_pnl_pct': 0.0,
                'exit_reason': None
            }
            trades.append(trade)
        
        elif df.loc[idx, 'svh_signal'].startswith('EXIT_'):
            exit_reason = df.loc[idx, 'svh_signal'].replace('EXIT_', '')
            trade = {
                'strategy': 'Spread Volatility Harvesting',
                'action': 'EXIT',
                'time': idx,
                'position_id': None,  # Not tracked in current implementation
                'position_tier': None,
                'position_size': None,
                'entry_spread': None,
                'exit_spread': df.loc[idx, 'svh_combined_spread'],
                'spread_volatility': df.loc[idx, 'svh_spread_volatility'],
                'active_positions': df.loc[idx, 'svh_active_positions'],
                'trade_pnl_pct': df.loc[idx, 'svh_trade_pnl'],
                'exit_reason': exit_reason
            }
            trades.append(trade)
    
    return pd.DataFrame(trades)


def save_trades_to_csv(df_strategies: dict, symbol: str, output_dir: str = "reverse_arbitrage_results"):
    """Save all trades from each strategy to separate CSV files."""
    
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved_files = []
    
    # Extract and save trades for each strategy
    for strategy_name, df in df_strategies.items():
        if strategy_name == 'reverse_delta_neutral':
            trades_df = extract_reverse_delta_neutral_trades(df)
            filename = f"rdn_trades_{symbol}_{timestamp}.csv"
        elif strategy_name == 'inventory_arbitrage':
            trades_df = extract_inventory_arbitrage_trades(df)
            filename = f"inv_trades_{symbol}_{timestamp}.csv"
        elif strategy_name == 'volatility_harvesting':
            trades_df = extract_volatility_harvesting_trades(df)
            filename = f"svh_trades_{symbol}_{timestamp}.csv"
        else:
            continue
        
        if not trades_df.empty:
            filepath = output_path / filename
            trades_df.to_csv(filepath, index=False)
            saved_files.append(filepath)
            print(f"   💾 Saved {len(trades_df)} {strategy_name} trades to: {filepath}")
        else:
            print(f"   ⚠️  No trades found for {strategy_name}")
    
    return saved_files


async def demonstrate_reverse_strategies():
    """Demonstrate all three reverse arbitrage strategies."""
    print("🚀 Reverse Arbitrage Strategies Demonstration")
    print("=" * 60)
    
    try:
        # Initialize the analyzer
        analyzer = ArbitrageAnalyzer() #tf=1
        
        # Load some sample data (you can replace this with your actual data loading)
        print("📊 Loading market data...")
        symbol = Symbol(base='PIGGY', quote='USDT')
        df, results = await analyzer.run_analysis(symbol, days=3)

        if df is None or len(df) == 0:
            print("❌ No data available for analysis")
            return
        
        print(f"✅ Loaded {len(df)} data points")
        
        # Store strategy DataFrames for CSV export
        strategy_dataframes = {}
        
        # Strategy 1: Reverse Delta-Neutral
        print("\n🔄 Testing Reverse Delta-Neutral Strategy...")
        df_rdn = analyzer.add_reverse_delta_neutral_backtest(
            df.copy(),
            entry_spread_threshold=-2.5,  # Enter when spread < -2.5%
            exit_spread_threshold=-0.3,   # Exit when spread > -0.3%
            stop_loss_threshold=-6.0,     # Emergency exit at -6%
            max_holding_hours=24,          # Max 24 hours per position
            total_fees=0.0067             # 0.67% total fees
        )
        strategy_dataframes['reverse_delta_neutral'] = df_rdn
        
        # Display RDN results
        rdn_trades = (df_rdn['rdn_trade_pnl'] != 0).sum()
        rdn_final_pnl = df_rdn['rdn_cumulative_pnl'].iloc[-1]
        rdn_winning_trades = (df_rdn['rdn_trade_pnl'] > 0).sum()
        rdn_win_rate = (rdn_winning_trades / rdn_trades * 100) if rdn_trades > 0 else 0
        
        print(f"   📈 Reverse Delta-Neutral Results:")
        print(f"   • Total trades: {rdn_trades}")
        print(f"   • Winning trades: {rdn_winning_trades}")
        print(f"   • Win rate: {rdn_win_rate:.1f}%")
        print(f"   • Final P&L: {rdn_final_pnl:.3f}%")
        
        # Strategy 2: Inventory Spot Arbitrage
        print("\n📦 Testing Inventory Spot Arbitrage Strategy...")
        df_inv = analyzer.add_inventory_spot_arbitrage_backtest(
            df.copy(),
            min_spread_threshold=0.30,         # Minimum 0.30% spread
            initial_mexc_balance_usd=5000.0,   # Starting balances
            initial_gateio_balance_usd=5000.0,
            min_trade_size_usd=500.0,          # Trade size limits
            max_trade_size_usd=2000.0,
            total_fees=0.0025                  # 0.25% fees
        )
        strategy_dataframes['inventory_arbitrage'] = df_inv
        
        # Display Inventory results
        inv_trades = (df_inv['inv_trade_pnl'] != 0).sum()
        inv_final_pnl = df_inv['inv_cumulative_pnl'].iloc[-1]
        inv_final_balance = df_inv['inv_total_balance'].iloc[-1]
        
        print(f"   📈 Inventory Arbitrage Results:")
        print(f"   • Total trades: {inv_trades}")
        print(f"   • Final P&L: {inv_final_pnl:.3f}%")
        print(f"   • Final total balance: ${inv_final_balance:.2f}")
        
        # Strategy 3: Spread Volatility Harvesting
        print("\n⚡ Testing Spread Volatility Harvesting Strategy...")
        df_svh = analyzer.add_spread_volatility_harvesting_backtest(
            df.copy(),
            volatility_threshold=1.0,              # Minimum volatility
            extreme_negative_threshold=-5.0,       # Extreme threshold
            moderate_negative_threshold=-2.0,      # Moderate threshold
            max_positions=3,                       # Max concurrent positions
            tail_hedge_cost=0.01                   # 1% monthly hedge cost
        )
        strategy_dataframes['volatility_harvesting'] = df_svh
        
        # Display SVH results
        svh_final_pnl = df_svh['svh_cumulative_pnl'].iloc[-1]
        svh_total_positions = df_svh['svh_active_positions'].max()
        
        print(f"   📈 Volatility Harvesting Results:")
        print(f"   • Final P&L: {svh_final_pnl:.3f}%")
        print(f"   • Max concurrent positions: {svh_total_positions}")
        
        # Comprehensive Analysis
        print("\n🔍 Running Comprehensive Analysis...")
        df_comprehensive = analyzer.add_comprehensive_reverse_arbitrage_analysis(
            df.copy(),
            include_all_strategies=True,
            rdn_params={'entry_spread_threshold': -2.5},
            inv_params={'min_spread_threshold': 0.30},
            svh_params={'volatility_threshold': 1.0}
        )
        
        # Generate report
        report = analyzer.generate_reverse_arbitrage_report(df_comprehensive)
        
        # Display comprehensive results
        print("\n📋 COMPREHENSIVE STRATEGY REPORT")
        print("=" * 50)
        
        # Period summary
        print(f"📅 Analysis Period: {report['period_summary']['date_range']}")
        print(f"📊 Total Periods: {report['period_summary']['total_periods']}")
        
        # Market regimes
        if report['period_summary']['market_regimes']:
            print("\n🏛️ Market Regimes:")
            for regime, count in report['period_summary']['market_regimes'].items():
                percentage = (count / report['period_summary']['total_periods']) * 100
                print(f"   • {regime}: {count} periods ({percentage:.1f}%)")
        
        # Individual strategy results
        print("\n📈 Individual Strategy Performance:")
        for strategy_name, strategy_data in report['strategies'].items():
            if 'status' in strategy_data:
                print(f"   • {strategy_data['display_name']}: {strategy_data['status']}")
            else:
                print(f"   • {strategy_data['display_name']}:")
                print(f"     - Final P&L: {strategy_data['final_pnl_pct']:.3f}%")
                print(f"     - Total Trades: {strategy_data['total_trades']}")
                print(f"     - Win Rate: {strategy_data['win_rate_pct']:.1f}%")
                print(f"     - Sharpe Ratio: {strategy_data['sharpe_ratio']:.2f}")
                print(f"     - Max Drawdown: {strategy_data['max_drawdown_pct']:.3f}%")
        
        # Combined portfolio
        if 'combined_portfolio' in report:
            print(f"\n🎯 Combined Portfolio Performance:")
            print(f"   • Total P&L: {report['combined_portfolio']['final_pnl_pct']:.3f}%")
            print(f"   • Sharpe Ratio: {report['combined_portfolio']['sharpe_ratio']:.2f}")
            print(f"   • Max Drawdown: {report['combined_portfolio']['max_drawdown_pct']:.3f}%")
        
        # Key insights
        print("\n💡 KEY INSIGHTS:")
        
        total_strategies_profitable = sum(1 for s in report['strategies'].values() 
                                        if 'final_pnl_pct' in s and s['final_pnl_pct'] > 0)
        
        print(f"   • {total_strategies_profitable}/3 strategies were profitable")
        
        if report['period_summary']['market_regimes']:
            negative_regimes = sum(count for regime, count in report['period_summary']['market_regimes'].items() 
                                 if 'NEGATIVE' in regime)
            total_periods = report['period_summary']['total_periods']
            negative_percentage = (negative_regimes / total_periods) * 100
            print(f"   • {negative_percentage:.1f}% of time in negative spread regimes (good for reverse strategies)")
        
        # Recommendations
        print("\n🎯 RECOMMENDATIONS:")
        
        best_strategy = None
        best_pnl = -float('inf')
        
        for strategy_name, strategy_data in report['strategies'].items():
            if 'final_pnl_pct' in strategy_data and strategy_data['final_pnl_pct'] > best_pnl:
                best_pnl = strategy_data['final_pnl_pct']
                best_strategy = strategy_data['display_name']
        
        if best_strategy and best_pnl > 0:
            print(f"   • Best performing strategy: {best_strategy} ({best_pnl:.3f}%)")
            print(f"   • Consider focusing on this strategy for live trading")
        elif best_pnl <= 0:
            print(f"   • No strategies were profitable in this period")
            print(f"   • Wait for different market conditions or adjust parameters")
        
        # Export all trades to CSV files
        print(f"\n💾 Exporting trades to CSV files...")
        try:
            saved_files = save_trades_to_csv(strategy_dataframes, symbol.base, "reverse_arbitrage_results")
            if saved_files:
                print(f"✅ Successfully exported trades to {len(saved_files)} CSV files")
                for file_path in saved_files:
                    print(f"   📄 {file_path}")
            else:
                print(f"⚠️  No trade files were created (no trades found in strategies)")
        except Exception as csv_error:
            print(f"❌ Error exporting trades to CSV: {csv_error}")
        
        print(f"\n✅ Demo completed successfully!")
        
    except Exception as e:
        print(f"❌ Error during demonstration: {e}")
        import traceback
        traceback.print_exc()


def print_strategy_overview():
    """Print overview of the three reverse arbitrage strategies."""
    print("📚 REVERSE ARBITRAGE STRATEGIES OVERVIEW")
    print("=" * 60)
    
    print("\n1️⃣ REVERSE DELTA-NEUTRAL ARBITRAGE")
    print("   🎯 Strategy: Enter LONG spot + SHORT futures when spread is deeply negative")
    print("   💰 Profit: From spread compression (negative → less negative)")
    print("   📊 Best for: High volatility periods with extreme negative spreads")
    print("   ⚡ Entry: Spread < -2.5% (configurable)")
    print("   🚪 Exit: Spread > -0.3% (compression)")
    print("   🛡️ Risk: Stop loss at -6% spread")
    
    print("\n2️⃣ INVENTORY-BASED SPOT ARBITRAGE")
    print("   🎯 Strategy: Use existing balances for spot-to-spot arbitrage")
    print("   💰 Profit: From price differences without transfer fees")
    print("   📊 Best for: High frequency trading with existing balances")
    print("   ⚡ Entry: Spot spread > 0.30% (after fees)")
    print("   🔄 Feature: Automatic inventory rebalancing")
    print("   🛡️ Risk: Imbalance penalties and position limits")
    
    print("\n3️⃣ SPREAD VOLATILITY HARVESTING")
    print("   🎯 Strategy: Multi-tier approach across different spread regimes")
    print("   💰 Profit: From volatility in negative spread environment")
    print("   📊 Best for: Diversified approach with multiple concurrent positions")
    print("   ⚡ Entry: Based on volatility + regime classification")
    print("   🏛️ Regimes: EXTREME (-5%+), MODERATE (-2%+), NORMAL")
    print("   🛡️ Risk: Tail hedging + position size scaling")
    
    print("\n🔧 KEY TECHNICAL FEATURES:")
    print("   • Market regime classification (EXTREME, DEEP, MODERATE, NORMAL, POSITIVE)")
    print("   • Volatility-based position sizing")
    print("   • Momentum and correlation indicators")
    print("   • Comprehensive risk management")
    print("   • Multi-strategy portfolio optimization")
    print("   • Performance tracking and reporting")


async def main():
    """Main entry point."""
    print_strategy_overview()
    print("\n" + "=" * 60)
    await demonstrate_reverse_strategies()


if __name__ == "__main__":
    asyncio.run(main())