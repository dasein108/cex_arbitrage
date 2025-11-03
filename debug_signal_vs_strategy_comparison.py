#!/usr/bin/env python3
"""
Debug Script: Signal Generation vs Strategy Execution Comparison

This script demonstrates the fundamental difference between:
1. ArbitrageAnalyzer - Complete strategy execution with trades and P&L
2. ArbitrageSignalStrategy - Signal generation only (no trade execution)

The key finding: ArbitrageSignalStrategy is a SIGNAL GENERATION framework,
while ArbitrageAnalyzer is a COMPLETE STRATEGY EXECUTION framework.
"""

import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, UTC
import time
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / 'src'
sys.path.insert(0, str(src_path))

from exchanges.structs import Symbol, AssetName, BookTicker
from trading.research.cross_arbitrage.arbitrage_analyzer import ArbitrageAnalyzer
from trading.analysis.arbitrage_signal_strategy import ArbitrageSignalStrategy
from trading.analysis.signal_types import Signal


def print_section_header(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 80)
    print(f"🔍 {title}")
    print("=" * 80)


def print_subsection(title: str):
    """Print a formatted subsection header."""
    print(f"\n📋 {title}")
    print("-" * 60)


async def debug_arbitrage_analyzer_approach():
    """Debug the working ArbitrageAnalyzer approach."""
    print_section_header("WORKING APPROACH: ArbitrageAnalyzer (Complete Strategy Execution)")
    
    try:
        # Initialize the analyzer
        analyzer = ArbitrageAnalyzer(use_db_book_tickers=True)
        symbol = Symbol(base='FLK', quote='USDT')
        
        print_subsection("1. Data Loading and Analysis")
        df, results = await analyzer.run_analysis(symbol, days=1)
        
        if df is None or len(df) == 0:
            print("❌ No data available for analysis")
            return None, None
        
        print(f"✅ Loaded {len(df)} data points")
        print(f"📊 Columns available: {list(df.columns)[:10]}...")  # First 10 columns
        
        # Check for key indicator columns
        indicator_columns = [col for col in df.columns if any(indicator in col.lower() 
                           for indicator in ['spread', 'regime', 'volatility', 'momentum'])]
        print(f"🎯 Indicator columns found: {len(indicator_columns)}")
        for col in indicator_columns[:5]:  # Show first 5
            print(f"   • {col}")
        
        print_subsection("2. Strategy Execution - Reverse Delta Neutral")
        
        # Execute the strategy (this is where trades are generated)
        df_rdn = analyzer.add_reverse_delta_neutral_backtest(
            df.copy(),
            entry_spread_threshold=-2.5,
            exit_spread_threshold=-0.3,
            stop_loss_threshold=-6.0,
            max_holding_hours=24,
            total_fees=0.0067
        )
        
        # Analyze strategy results
        rdn_columns = [col for col in df_rdn.columns if 'rdn_' in col]
        print(f"📈 RDN strategy columns created: {len(rdn_columns)}")
        for col in rdn_columns:
            print(f"   • {col}")
        
        # Check for actual trades
        trades = (df_rdn['rdn_trade_pnl'] != 0).sum()
        signals = df_rdn['rdn_signal'].value_counts()
        final_pnl = df_rdn['rdn_cumulative_pnl'].iloc[-1]
        
        print(f"\n🎯 RDN Strategy Results:")
        print(f"   • Total trades executed: {trades}")
        print(f"   • Signal distribution: {dict(signals)}")
        print(f"   • Final cumulative P&L: {final_pnl:.3f}%")
        
        if trades > 0:
            # Show sample trade data
            trade_indices = df_rdn[df_rdn['rdn_trade_pnl'] != 0].index[:3]
            print(f"\n📝 Sample trade details:")
            for idx in trade_indices:
                trade_pnl = df_rdn.loc[idx, 'rdn_trade_pnl']
                signal = df_rdn.loc[idx, 'rdn_signal']
                entry_spread = df_rdn.loc[idx, 'rdn_entry_spread']
                print(f"   • {idx}: Signal={signal}, P&L={trade_pnl:.3f}%, Entry Spread={entry_spread:.3f}%")
        
        return df, df_rdn
        
    except Exception as e:
        print(f"❌ ArbitrageAnalyzer debug failed: {e}")
        import traceback
        traceback.print_exc()
        return None, None


async def debug_arbitrage_signal_strategy_approach():
    """Debug the non-working ArbitrageSignalStrategy approach."""
    print_section_header("NON-WORKING APPROACH: ArbitrageSignalStrategy (Signal Generation Only)")
    
    try:
        # Initialize the signal strategy
        symbol = Symbol(base=AssetName('FLK'), quote=AssetName('USDT'))
        strategy = ArbitrageSignalStrategy(
            symbol=symbol,
            strategy_type='reverse_delta_neutral',
            is_live_mode=False
        )
        
        print_subsection("1. Strategy Initialization")
        await strategy.initialize(days=1)
        
        # Get historical data
        historical_df = strategy.get_historical_data()
        print(f"✅ Loaded {len(historical_df)} historical data points")
        print(f"📊 Columns available: {list(historical_df.columns)[:10]}...")
        
        # Get strategy metrics
        metrics = strategy.get_strategy_metrics()
        print(f"🎯 Strategy metrics: {metrics}")
        
        print_subsection("2. Signal Generation (Row-by-Row Processing)")
        
        signals_generated = []
        signal_details = []
        
        # Process first 10 rows to debug signal generation
        sample_rows = historical_df.head(10)
        
        for i, (_, row) in enumerate(sample_rows.iterrows()):
            # Create BookTicker objects from row data
            spot_book_tickers = {}
            
            # MEXC spot
            if 'MEXC_bid_price' in row.index and pd.notna(row['MEXC_bid_price']):
                spot_book_tickers['MEXC'] = BookTicker(
                    symbol=Symbol(base=symbol.base, quote=symbol.quote),
                    bid_price=float(row['MEXC_bid_price']),
                    ask_price=float(row['MEXC_ask_price']),
                    bid_quantity=float(row.get('MEXC_bid_qty', 1000)),
                    ask_quantity=float(row.get('MEXC_ask_qty', 1000)),
                    timestamp=int(pd.Timestamp.now().timestamp() * 1000)
                )
            
            # Gate.io spot
            if 'GATEIO_bid_price' in row.index and pd.notna(row['GATEIO_bid_price']):
                spot_book_tickers['GATEIO'] = BookTicker(
                    symbol=Symbol(base=symbol.base, quote=symbol.quote),
                    bid_price=float(row['GATEIO_bid_price']),
                    ask_price=float(row['GATEIO_ask_price']),
                    bid_quantity=float(row.get('GATEIO_bid_qty', 1000)),
                    ask_quantity=float(row.get('GATEIO_ask_qty', 1000)),
                    timestamp=int(pd.Timestamp.now().timestamp() * 1000)
                )
            
            # Gate.io futures
            futures_book_ticker = None
            if 'GATEIO_FUTURES_bid_price' in row.index and pd.notna(row['GATEIO_FUTURES_bid_price']):
                futures_book_ticker = BookTicker(
                    symbol=Symbol(base=symbol.base, quote=symbol.quote),
                    bid_price=float(row['GATEIO_FUTURES_bid_price']),
                    ask_price=float(row['GATEIO_FUTURES_ask_price']),
                    bid_quantity=float(row.get('GATEIO_FUTURES_bid_qty', 1000)),
                    ask_quantity=float(row.get('GATEIO_FUTURES_ask_qty', 1000)),
                    timestamp=int(pd.Timestamp.now().timestamp() * 1000)
                )
            
            # Generate signal if we have sufficient data
            if spot_book_tickers and futures_book_ticker:
                signal = strategy.update_with_live_data(
                    spot_book_tickers=spot_book_tickers,
                    futures_book_ticker=futures_book_ticker
                )
                signals_generated.append(signal.value)
                
                # Calculate spreads for debugging
                mexc_price = (spot_book_tickers['MEXC'].bid_price + spot_book_tickers['MEXC'].ask_price) / 2
                gateio_spot_price = (spot_book_tickers['GATEIO'].bid_price + spot_book_tickers['GATEIO'].ask_price) / 2
                futures_price = (futures_book_ticker.bid_price + futures_book_ticker.ask_price) / 2
                
                mexc_vs_futures_spread = ((mexc_price - futures_price) / mexc_price) * 100
                gateio_vs_futures_spread = ((gateio_spot_price - futures_price) / gateio_spot_price) * 100
                
                signal_details.append({
                    'row': i,
                    'signal': signal.value,
                    'mexc_price': mexc_price,
                    'gateio_spot_price': gateio_spot_price,
                    'futures_price': futures_price,
                    'mexc_vs_futures_spread': mexc_vs_futures_spread,
                    'gateio_vs_futures_spread': gateio_vs_futures_spread
                })
                
                print(f"   Row {i:2d}: Signal={signal.value:>5} | "
                      f"MEXC vs Futures: {mexc_vs_futures_spread:>6.2f}% | "
                      f"Gate.io vs Futures: {gateio_vs_futures_spread:>6.2f}%")
            else:
                signals_generated.append(Signal.HOLD.value)
                print(f"   Row {i:2d}: Signal={'HOLD':>5} | Insufficient data")
        
        # Analyze signal generation results
        signal_counts = pd.Series(signals_generated).value_counts()
        print(f"\n🎯 Signal Generation Results (first 10 rows):")
        print(f"   • Signals generated: {dict(signal_counts)}")
        print(f"   • ENTER signals: {signal_counts.get('ENTER', 0)}")
        print(f"   • EXIT signals: {signal_counts.get('EXIT', 0)}")
        print(f"   • HOLD signals: {signal_counts.get('HOLD', 0)}")
        
        return historical_df, signal_details
        
    except Exception as e:
        print(f"❌ ArbitrageSignalStrategy debug failed: {e}")
        import traceback
        traceback.print_exc()
        return None, None


def analyze_fundamental_differences():
    """Analyze the fundamental architectural differences."""
    print_section_header("FUNDAMENTAL ARCHITECTURAL DIFFERENCES")
    
    print_subsection("ArbitrageAnalyzer (Working - Complete Strategy)")
    print("🎯 Purpose: Complete strategy execution with trade simulation")
    print("📋 Key Features:")
    print("   • Full strategy implementation in dedicated methods")
    print("   • Position tracking and management")
    print("   • P&L calculation and accumulation")
    print("   • Trade execution simulation")
    print("   • Risk management (stop loss, position limits)")
    print("   • Entry/exit logic with state management")
    print("   • Comprehensive performance metrics")
    
    print("📈 Methods for strategy execution:")
    print("   • add_reverse_delta_neutral_backtest()")
    print("   • add_inventory_spot_arbitrage_backtest()")
    print("   • add_spread_volatility_harvesting_backtest()")
    
    print("💰 Trade Generation:")
    print("   • Executes actual trade logic")
    print("   • Tracks positions from entry to exit")
    print("   • Calculates real P&L from spread capture")
    print("   • Manages multiple concurrent positions")
    
    print_subsection("ArbitrageSignalStrategy (Non-working - Signal Only)")
    print("🎯 Purpose: Signal generation for external strategy execution")
    print("📋 Key Features:")
    print("   • Signal generation only (ENTER/EXIT/HOLD)")
    print("   • No position tracking")
    print("   • No P&L calculation")
    print("   • No trade execution")
    print("   • No state management between signals")
    print("   • Designed for integration with external trading systems")
    
    print("📊 Methods for signal generation:")
    print("   • update_with_live_data() - returns Signal enum")
    print("   • initialize() - loads historical context")
    print("   • get_strategy_metrics() - returns signal stats")
    
    print("⚠️  Signal Generation Only:")
    print("   • Returns ENTER/EXIT/HOLD signals")
    print("   • No trade execution or position management")
    print("   • Requires external system to act on signals")
    print("   • No P&L tracking or performance calculation")


def print_key_findings_and_solution():
    """Print the key findings and recommended solution."""
    print_section_header("KEY FINDINGS AND SOLUTION")
    
    print_subsection("🔍 Root Cause Analysis")
    print("❌ ISSUE: Comparing apples to oranges")
    print("   • ArbitrageAnalyzer = Complete trading strategy with execution")
    print("   • ArbitrageSignalStrategy = Signal generation framework only")
    print()
    print("🎯 WHY TRADES ARE DIFFERENT:")
    print("   • Working demo: Actually executes trades with P&L tracking")
    print("   • New framework: Only generates signals (no trade execution)")
    print()
    print("📊 ARCHITECTURE MISMATCH:")
    print("   • Working demo expects complete strategy implementations")
    print("   • New framework is designed as a signal provider for external systems")
    
    print_subsection("✅ SOLUTION OPTIONS")
    print("1️⃣ OPTION 1: Extend ArbitrageSignalStrategy (Recommended)")
    print("   • Add trade execution layer on top of signal generation")
    print("   • Implement position tracking and P&L calculation")
    print("   • Create strategy execution wrapper around signal generation")
    print()
    print("2️⃣ OPTION 2: Use ArbitrageAnalyzer for backtesting")
    print("   • Keep ArbitrageAnalyzer for complete strategy backtesting")
    print("   • Use ArbitrageSignalStrategy for live signal generation")
    print("   • Implement bridge between the two systems")
    print()
    print("3️⃣ OPTION 3: Create hybrid system")
    print("   • Extract strategy logic from ArbitrageAnalyzer")
    print("   • Integrate with ArbitrageSignalStrategy signal generation")
    print("   • Unified framework for both backtesting and live trading")
    
    print_subsection("🚀 RECOMMENDED IMPLEMENTATION")
    print("Create StrategyExecutor class that:")
    print("   • Uses ArbitrageSignalStrategy for signal generation")
    print("   • Adds position tracking and trade execution logic")
    print("   • Calculates P&L and performance metrics")
    print("   • Maintains compatibility with existing ArbitrageAnalyzer results")
    print()
    print("Benefits:")
    print("   ✅ Unified signal generation across backtesting and live trading")
    print("   ✅ Clear separation of signal generation vs strategy execution")
    print("   ✅ Backward compatibility with existing analysis")
    print("   ✅ Foundation for more sophisticated strategy frameworks")


async def main():
    """Main debug analysis."""
    print("🔬 DEBUG ANALYSIS: Signal Generation vs Strategy Execution")
    print("=" * 80)
    print("Investigating why ArbitrageAnalyzer generates trades while")
    print("ArbitrageSignalStrategy generates zero trades...")
    
    # Debug both approaches
    analyzer_df, analyzer_strategy_df = await debug_arbitrage_analyzer_approach()
    signal_df, signal_details = await debug_arbitrage_signal_strategy_approach()
    
    # Compare results
    if analyzer_strategy_df is not None and signal_details is not None:
        print_section_header("DIRECT COMPARISON")
        
        print_subsection("Trade Generation Comparison")
        
        # ArbitrageAnalyzer results
        analyzer_trades = (analyzer_strategy_df['rdn_trade_pnl'] != 0).sum()
        analyzer_final_pnl = analyzer_strategy_df['rdn_cumulative_pnl'].iloc[-1]
        analyzer_signals = analyzer_strategy_df['rdn_signal'].value_counts()
        
        print(f"🏆 ArbitrageAnalyzer (Working):")
        print(f"   • Total trades executed: {analyzer_trades}")
        print(f"   • Final P&L: {analyzer_final_pnl:.3f}%")
        print(f"   • Signal distribution: {dict(analyzer_signals)}")
        
        # ArbitrageSignalStrategy results
        signal_counts = pd.Series([detail['signal'] for detail in signal_details]).value_counts()
        
        print(f"\n📊 ArbitrageSignalStrategy (Non-working):")
        print(f"   • Total signals generated: {len(signal_details)}")
        print(f"   • Signal distribution: {dict(signal_counts)}")
        print(f"   • Trades executed: 0 (signals only, no execution logic)")
        print(f"   • P&L calculated: None (no trade execution)")
        
        print(f"\n❗ CRITICAL DIFFERENCE:")
        print(f"   • ArbitrageAnalyzer: {analyzer_trades} completed trades with P&L tracking")
        print(f"   • ArbitrageSignalStrategy: {len(signal_details)} signals but NO trade execution")
    
    # Analyze fundamental differences
    analyze_fundamental_differences()
    
    # Print solution
    print_key_findings_and_solution()
    
    print_section_header("CONCLUSION")
    print("🎯 The 'bug' is actually an architectural difference:")
    print("   • ArbitrageAnalyzer = Complete trading system")
    print("   • ArbitrageSignalStrategy = Signal generation component")
    print()
    print("✅ To make ArbitrageSignalStrategy work like ArbitrageAnalyzer:")
    print("   1. Add StrategyExecutor wrapper class")
    print("   2. Implement position tracking on top of signals")
    print("   3. Add P&L calculation and trade execution logic")
    print("   4. Create unified backtesting interface")
    print()
    print("🚀 This will provide the best of both worlds:")
    print("   • Reusable signal generation for live trading")
    print("   • Complete strategy execution for backtesting")
    print("   • Unified architecture across the system")


if __name__ == "__main__":
    asyncio.run(main())