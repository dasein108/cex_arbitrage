#!/usr/bin/env python3
"""
Comprehensive Debug Analysis for Hedged Cross-Arbitrage Strategy
================================================================

This script provides detailed analysis to identify why the hedged arbitrage backtest
is showing negative returns when it should theoretically be profitable.

Key areas investigated:
1. Signal generation logic verification
2. Position entry/exit execution analysis  
3. P&L calculation methodology debugging
4. Fee and spread modeling validation
5. Data quality assessment
"""

import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
import matplotlib.pyplot as plt
import seaborn as sns


class HedgedArbitrageDebugger:
    """Comprehensive debugging suite for hedged arbitrage strategy."""
    
    def __init__(self):
        self.cache_dir = Path("/Users/dasein/dev/cex_arbitrage/src/trading/research/cache")
        self.backtest_file = self.cache_dir / "hedged_arbitrage_backtest_F_USDT_3d_20251019_143231.csv"
        self.positions_file = self.cache_dir / "hedged_arbitrage_positions_F_USDT_3d_20251019_143231.csv"
        
    def load_data(self):
        """Load backtest and position data."""
        print("📥 Loading data files...")
        
        self.df = pd.read_csv(self.backtest_file)
        self.positions = pd.read_csv(self.positions_file)
        
        self.df['timestamp'] = pd.to_datetime(self.df['timestamp'])
        self.positions['entry_time'] = pd.to_datetime(self.positions['entry_time'])
        self.positions['exit_time'] = pd.to_datetime(self.positions['exit_time'])
        
        print(f"✅ Loaded {len(self.df)} data points and {len(self.positions)} positions")
        
    def analyze_signal_logic(self):
        """Debug the signal generation logic."""
        print("\n🔍 SIGNAL LOGIC ANALYSIS")
        print("=" * 50)
        
        # Check where signals are generated
        enter_signals = self.df[self.df['signal'] == 'ENTER']
        exit_signals = self.df[self.df['signal'] == 'EXIT']
        
        print(f"Entry signals: {len(enter_signals)}")
        print(f"Exit signals: {len(exit_signals)}")
        print(f"Hold signals: {len(self.df) - len(enter_signals) - len(exit_signals)}")
        
        # Analyze first few entry signals
        print("\n📊 First 3 Entry Signals:")
        for idx, (i, row) in enumerate(enter_signals.head(3).iterrows()):
            print(f"\nEntry Signal {idx + 1}:")
            print(f"  Time: {row['timestamp']}")
            print(f"  MEXC vs Gate.io futures spread: {row['mexc_vs_gateio_futures_arb']:.4f}%")
            print(f"  Gate.io spot vs futures spread: {row['gateio_spot_vs_futures_arb']:.4f}%")
            print(f"  Action: {row['position_action']}")
            
        # Analyze exit signals
        print("\n📊 First 3 Exit Signals:")
        for idx, (i, row) in enumerate(exit_signals.head(3).iterrows()):
            print(f"\nExit Signal {idx + 1}:")
            print(f"  Time: {row['timestamp']}")
            print(f"  MEXC vs Gate.io futures spread: {row['mexc_vs_gateio_futures_arb']:.4f}%")
            print(f"  Gate.io spot vs futures spread: {row['gateio_spot_vs_futures_arb']:.4f}%")
            print(f"  Action: {row['position_action']}")
            
    def analyze_position_execution(self):
        """Debug position entry and exit execution."""
        print("\n🔍 POSITION EXECUTION ANALYSIS")
        print("=" * 50)
        
        print("📊 Position Summary:")
        print(f"Total positions: {len(self.positions)}")
        print(f"Closed positions: {len(self.positions[self.positions['status'] == 'CLOSED'])}")
        print(f"Average holding period: {self.positions['holding_period_minutes'].mean():.1f} minutes")
        
        # Analyze P&L distribution
        pnls = self.positions['pnl_usd'].values
        winning_trades = len(pnls[pnls > 0])
        losing_trades = len(pnls[pnls <= 0])
        
        print(f"\n💰 P&L Analysis:")
        print(f"Winning trades: {winning_trades} ({winning_trades/len(pnls)*100:.1f}%)")
        print(f"Losing trades: {losing_trades} ({losing_trades/len(pnls)*100:.1f}%)")
        print(f"Average P&L: ${pnls.mean():.2f}")
        print(f"Total P&L: ${pnls.sum():.2f}")
        print(f"Best trade: ${pnls.max():.2f}")
        print(f"Worst trade: ${pnls.min():.2f}")
        
    def debug_specific_trades(self):
        """Debug specific trades to understand P&L calculation."""
        print("\n🔍 DETAILED TRADE ANALYSIS")
        print("=" * 50)
        
        # Get trades with detailed market data
        trades_with_data = []
        
        for _, pos in self.positions.head(3).iterrows():
            entry_time = pos['entry_time']
            exit_time = pos['exit_time']
            
            # Find corresponding market data
            entry_data = self.df[self.df['timestamp'] == entry_time].iloc[0]
            exit_data = self.df[self.df['timestamp'] == exit_time].iloc[0]
            
            trade_analysis = self._analyze_single_trade(pos, entry_data, exit_data)
            trades_with_data.append(trade_analysis)
            
        # Print detailed analysis
        for i, trade in enumerate(trades_with_data):
            print(f"\n📊 TRADE {i + 1} DETAILED ANALYSIS:")
            print(f"Entry Time: {trade['entry_time']}")
            print(f"Exit Time: {trade['exit_time']}")
            print(f"Holding Period: {trade['holding_period']} minutes")
            
            print(f"\n📈 Entry Execution:")
            print(f"  MEXC spot ask (buy): ${trade['entry_mexc_ask']:.6f}")
            print(f"  Gate.io futures bid (sell): ${trade['entry_gateio_futures_bid']:.6f}")
            print(f"  Entry spread: {trade['entry_spread']:.4f}%")
            
            print(f"\n📉 Exit Execution:")
            print(f"  Gate.io spot bid (sell): ${trade['exit_gateio_spot_bid']:.6f}")
            print(f"  Gate.io futures ask (buy): ${trade['exit_gateio_futures_ask']:.6f}")
            print(f"  Exit spread: {trade['exit_spread']:.4f}%")
            
            print(f"\n💰 P&L Breakdown:")
            print(f"  Spot leg P&L: {trade['spot_pnl_pct']:.4f}%")
            print(f"  Futures leg P&L: {trade['futures_pnl_pct']:.4f}%")
            print(f"  Gross P&L: {trade['gross_pnl_pct']:.4f}%")
            print(f"  Fees (20 bps): -0.2000%")
            print(f"  Net P&L: {trade['net_pnl_pct']:.4f}%")
            print(f"  Dollar P&L: ${trade['pnl_usd']:.2f}")
            
            print(f"\n🔍 Issue Analysis:")
            self._diagnose_trade_issues(trade)
    
    def _analyze_single_trade(self, pos, entry_data, exit_data):
        """Analyze a single trade in detail."""
        # Extract prices (replicating the backtest logic)
        entry_mexc_ask = entry_data['mexc_spot_ask_price']
        entry_gateio_futures_bid = entry_data['gateio_futures_bid_price']
        exit_gateio_spot_bid = exit_data['gateio_spot_bid_price']
        exit_gateio_futures_ask = exit_data['gateio_futures_ask_price']
        
        # Calculate P&L components (replicating backtest calculation)
        spot_pnl_pct = (exit_gateio_spot_bid - entry_mexc_ask) / entry_mexc_ask * 100
        futures_pnl_pct = (entry_gateio_futures_bid - exit_gateio_futures_ask) / entry_gateio_futures_bid * 100
        
        gross_pnl_pct = spot_pnl_pct + futures_pnl_pct
        net_pnl_pct = gross_pnl_pct - 0.20  # 20 bps fees
        pnl_usd = (net_pnl_pct / 100) * 1000  # $1000 position size
        
        return {
            'entry_time': pos['entry_time'],
            'exit_time': pos['exit_time'],
            'holding_period': pos['holding_period_minutes'],
            'entry_mexc_ask': entry_mexc_ask,
            'entry_gateio_futures_bid': entry_gateio_futures_bid,
            'exit_gateio_spot_bid': exit_gateio_spot_bid,
            'exit_gateio_futures_ask': exit_gateio_futures_ask,
            'entry_spread': pos['entry_spread'],
            'exit_spread': pos['exit_spread'],
            'spot_pnl_pct': spot_pnl_pct,
            'futures_pnl_pct': futures_pnl_pct,
            'gross_pnl_pct': gross_pnl_pct,
            'net_pnl_pct': net_pnl_pct,
            'pnl_usd': pnl_usd,
            'reported_pnl': pos['pnl_usd']
        }
    
    def _diagnose_trade_issues(self, trade):
        """Diagnose potential issues with a trade."""
        issues = []
        
        # Check if P&L calculation matches
        if abs(trade['pnl_usd'] - trade['reported_pnl']) > 0.01:
            issues.append(f"P&L calculation mismatch: calculated ${trade['pnl_usd']:.2f} vs reported ${trade['reported_pnl']:.2f}")
        
        # Check if spreads moved in expected direction
        entry_spread = trade['entry_spread']
        exit_spread = trade['exit_spread']
        
        if entry_spread > 0:
            issues.append(f"Entry spread is positive ({entry_spread:.4f}%), should be negative for entry signal")
        
        if exit_spread < 0:
            issues.append(f"Exit spread is negative ({exit_spread:.4f}%), should be positive for exit signal")
        
        # Check for reasonable spread convergence
        spread_improvement = exit_spread - entry_spread
        if spread_improvement < 0:
            issues.append(f"Spread moved against position: {spread_improvement:.4f}% deterioration")
        
        # Check price movements
        spot_move = (trade['exit_gateio_spot_bid'] / trade['entry_mexc_ask'] - 1) * 100
        futures_move = (trade['exit_gateio_futures_ask'] / trade['entry_gateio_futures_bid'] - 1) * 100
        
        if abs(spot_move) > 5:
            issues.append(f"Large spot price move: {spot_move:.2f}%")
        
        if abs(futures_move) > 5:
            issues.append(f"Large futures price move: {futures_move:.2f}%")
        
        if issues:
            for issue in issues:
                print(f"  ⚠️  {issue}")
        else:
            print(f"  ✅ No obvious issues detected")
    
    def analyze_strategy_assumptions(self):
        """Analyze the core strategy assumptions."""
        print("\n🔍 STRATEGY ASSUMPTIONS ANALYSIS")
        print("=" * 50)
        
        print("📊 Strategy Logic Verification:")
        print("Expected Entry: MEXC vs Gate.io futures spread < 25th percentile (negative spread)")
        print("Expected Exit: Gate.io spot vs futures spread > 25th percentile (positive spread)")
        print()
        
        # Check actual entry/exit spread patterns
        entry_trades = self.positions.copy()
        
        print("📈 Entry Spread Analysis:")
        entry_spreads = entry_trades['entry_spread'].values
        print(f"  Mean entry spread: {entry_spreads.mean():.4f}%")
        print(f"  Median entry spread: {np.median(entry_spreads):.4f}%")
        print(f"  Entry spreads < 0: {len(entry_spreads[entry_spreads < 0])} / {len(entry_spreads)}")
        
        print("\n📉 Exit Spread Analysis:")
        exit_spreads = entry_trades['exit_spread'].values
        print(f"  Mean exit spread: {exit_spreads.mean():.4f}%")
        print(f"  Median exit spread: {np.median(exit_spreads):.4f}%")
        print(f"  Exit spreads > 0: {len(exit_spreads[exit_spreads > 0])} / {len(exit_spreads)}")
        
        print("\n📊 Spread Improvement Analysis:")
        spread_improvements = exit_spreads - entry_spreads
        print(f"  Mean spread improvement: {spread_improvements.mean():.4f}%")
        print(f"  Trades with positive improvement: {len(spread_improvements[spread_improvements > 0])} / {len(spread_improvements)}")
        
        # Check theoretical vs actual profitability
        print("\n💰 Theoretical vs Actual Profitability:")
        print("Theoretical expectation: Entry on negative spread, exit on positive spread should be profitable")
        
        for i, (_, pos) in enumerate(entry_trades.head(3).iterrows()):
            theoretical_profit = pos['exit_spread'] - pos['entry_spread']
            actual_profit = pos['pnl_usd'] / 1000 * 100  # Convert to percentage
            
            print(f"\nTrade {i+1}:")
            print(f"  Entry spread: {pos['entry_spread']:.4f}%")
            print(f"  Exit spread: {pos['exit_spread']:.4f}%") 
            print(f"  Theoretical profit: {theoretical_profit:.4f}%")
            print(f"  Actual profit: {actual_profit:.4f}%")
            print(f"  Difference: {actual_profit - theoretical_profit:.4f}%")
    
    def identify_root_causes(self):
        """Identify the most likely root causes of poor performance."""
        print("\n🎯 ROOT CAUSE ANALYSIS")
        print("=" * 50)
        
        issues = []
        
        # 1. Check win rate
        pnls = self.positions['pnl_usd'].values
        win_rate = len(pnls[pnls > 0]) / len(pnls) * 100
        
        if win_rate < 30:
            issues.append(f"CRITICAL: Very low win rate ({win_rate:.1f}%) suggests fundamental strategy flaw")
        
        # 2. Check average P&L vs fees
        avg_pnl_pct = pnls.mean() / 1000 * 100
        if avg_pnl_pct < -0.15:  # Worse than just fees
            issues.append(f"CRITICAL: Average P&L ({avg_pnl_pct:.3f}%) is worse than fees (-0.20%), indicating systematic losses")
        
        # 3. Check spread behavior
        entry_spreads = self.positions['entry_spread'].values
        exit_spreads = self.positions['exit_spread'].values
        
        if np.mean(entry_spreads) > -0.2:
            issues.append(f"WARNING: Entry spreads averaging {np.mean(entry_spreads):.3f}% may not be attractive enough")
        
        if np.mean(exit_spreads) < 0.2:
            issues.append(f"WARNING: Exit spreads averaging {np.mean(exit_spreads):.3f}% may not be favorable enough")
        
        # 4. Check for execution issues
        spread_improvements = exit_spreads - entry_spreads
        negative_improvements = len(spread_improvements[spread_improvements < 0])
        
        if negative_improvements > len(spread_improvements) * 0.3:
            issues.append(f"WARNING: {negative_improvements}/{len(spread_improvements)} trades had negative spread movement")
        
        # 5. Check signal timing
        avg_holding = self.positions['holding_period_minutes'].mean()
        if avg_holding < 15:
            issues.append(f"WARNING: Very short holding periods ({avg_holding:.1f} min) may indicate premature exits")
        
        print("🚨 IDENTIFIED ISSUES:")
        for i, issue in enumerate(issues, 1):
            print(f"{i}. {issue}")
        
        if not issues:
            print("✅ No major issues identified in strategy mechanics")
        
        # Provide recommendations
        print(f"\n💡 RECOMMENDATIONS:")
        
        if win_rate < 30:
            print("1. URGENT: Review signal generation logic - current thresholds may be incorrect")
            print("2. Consider reversing entry/exit conditions or adjusting percentile thresholds")
        
        if avg_pnl_pct < -0.15:
            print("3. Check P&L calculation logic for systematic errors")
            print("4. Verify bid/ask price usage in entry/exit execution")
        
        if negative_improvements > len(spread_improvements) * 0.3:
            print("5. Analyze market microstructure - spreads may not be mean-reverting as expected")
            print("6. Consider adding minimum holding periods or different exit criteria")
    
    def run_full_analysis(self):
        """Run complete debugging analysis."""
        print("🔍 HEDGED CROSS-ARBITRAGE STRATEGY DEBUGGING")
        print("=" * 80)
        
        self.load_data()
        self.analyze_signal_logic()
        self.analyze_position_execution()
        self.debug_specific_trades()
        self.analyze_strategy_assumptions()
        self.identify_root_causes()
        
        print(f"\n✅ DEBUGGING ANALYSIS COMPLETE")
        print("=" * 80)


if __name__ == "__main__":
    debugger = HedgedArbitrageDebugger()
    debugger.run_full_analysis()