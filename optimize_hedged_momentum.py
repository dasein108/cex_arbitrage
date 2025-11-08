#!/usr/bin/env python3
"""
Hedged Momentum Strategy Parameter Optimization (FIXED VERSION)

This script runs systematic parameter optimization for the hedged momentum
strategy to find optimal settings for different market conditions.

STRATEGY UPDATE (CRITICAL FIX):
- Fixed critical spot shorting logic flaw
- Strategy now only trades LONG momentum signals in spot markets
- Cannot short spot assets without pre-existing inventory
- Hedge is always: BUY spot (LONG) + SHORT futures position
- This ensures proper market mechanics compliance
"""

import asyncio
import sys
import itertools
from datetime import datetime, timezone
import pandas as pd
import numpy as np

# Simple structs to avoid import issues
from simple_structs import Symbol, AssetName

sys.path.append('src')

# Update the hedged momentum signal to avoid import issues
import importlib.util
from trading.signals_v2.implementation.hedged_momentum_signal import HedgedMomentumSignal, HedgedMomentumParams




class HedgedMomentumOptimizer:
    """Parameter optimization for hedged momentum strategy."""
    
    def __init__(self):
        self.results = []
        
    async def optimize_parameters(self, symbol: Symbol, hours: int = 72) -> dict:
        """Run systematic parameter optimization."""
        
        print(f"🔬 Optimizing Hedged Momentum Parameters for {symbol}")
        print(f"📊 Testing period: {hours} hours")
        print("=" * 60)
        
        # Parameter grid for optimization (reduced grid for testing)
        param_grid = {
            'momentum_threshold': [2.0, 2.5, 3.0],
            'hedge_ratio': [0.8, 0.9],
            'max_position_time_minutes': [45, 60],
            'take_profit_pct': [1.0, 1.2],
            'stop_loss_pct': [2.5, 3.0]
        }
        
        # Generate all parameter combinations
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        combinations = list(itertools.product(*param_values))
        
        total_combinations = len(combinations)
        print(f"🧮 Testing {total_combinations} parameter combinations")
        print()
        
        best_score = -float('inf')
        best_params = None
        best_metrics = None
        
        for i, combo in enumerate(combinations, 1):
            # Create parameter set
            params = HedgedMomentumParams()
            for name, value in zip(param_names, combo):
                setattr(params, name, value)
                
            try:
                # Run backtest with these parameters
                strategy = HedgedMomentumSignal(params)
                metrics, trades = await strategy.run_backtest(symbol, hours)
                
                # Calculate composite score
                score = self._calculate_composite_score(metrics, trades)
                
                result = {
                    'combination': i,
                    'params': {name: value for name, value in zip(param_names, combo)},
                    'metrics': metrics,
                    'trades': len(trades),
                    'score': score
                }
                
                self.results.append(result)
                
                # Update best if this is better
                if score > best_score:
                    best_score = score
                    best_params = result['params'].copy()
                    best_metrics = metrics
                
                # Progress reporting
                if i % 10 == 0 or i == total_combinations:
                    progress = (i / total_combinations) * 100
                    print(f"Progress: {progress:.1f}% ({i}/{total_combinations}) - "
                          f"Current best score: {best_score:.2f}")
                    
            except Exception as e:
                print(f"❌ Error testing combination {i}: {e}")
                continue
                
        # Sort results by score
        self.results.sort(key=lambda x: x['score'], reverse=True)
        
        return {
            'best_params': best_params,
            'best_metrics': best_metrics,
            'best_score': best_score,
            'total_combinations': total_combinations,
            'top_results': self.results[:10]
        }
        
    def _calculate_composite_score(self, metrics, trades) -> float:
        """Calculate composite optimization score."""
        
        if not trades:
            return -100  # Heavily penalize no trades
            
        # Score components (normalized 0-100)
        profit_score = min(max(metrics.total_pnl_pct * 2, -50), 50) + 50  # -25% to +25% → 0-100
        
        win_rate_score = metrics.win_rate  # Already 0-100
        
        trade_frequency_score = min(len(trades) * 2, 50)  # Up to 25 trades → 0-50
        
        sharpe_score = min(max(metrics.sharpe_ratio * 25, -25), 25) + 25  # -1 to +1 → 0-50
        
        drawdown_penalty = max(0, 50 - metrics.max_drawdown)  # Penalize large drawdowns
        
        # Weighted composite score
        composite_score = (
            profit_score * 0.3 +          # 30% weight on profitability
            win_rate_score * 0.25 +       # 25% weight on win rate
            trade_frequency_score * 0.15 + # 15% weight on trade frequency
            sharpe_score * 0.20 +         # 20% weight on risk-adjusted returns
            drawdown_penalty * 0.10       # 10% weight on drawdown control
        )
        
        return composite_score
        
    def generate_report(self, optimization_results: dict, symbol: Symbol):
        """Generate comprehensive optimization report."""
        
        print("\n" + "=" * 80)
        print("📈 HEDGED MOMENTUM STRATEGY OPTIMIZATION RESULTS")
        print("=" * 80)
        
        best_params = optimization_results['best_params']
        best_metrics = optimization_results['best_metrics']
        
        print(f"\n🎯 OPTIMAL PARAMETERS for {symbol}:")
        print("-" * 50)
        print(f"   Momentum Threshold: {best_params['momentum_threshold']}%")
        print(f"   Hedge Ratio: {best_params['hedge_ratio']*100:.0f}%")
        print(f"   Max Position Time: {best_params['max_position_time_minutes']} minutes")
        print(f"   Take Profit: {best_params['take_profit_pct']}%")
        print(f"   Stop Loss: {best_params['stop_loss_pct']}%")
        
        print(f"\n📊 OPTIMAL PERFORMANCE:")
        print("-" * 30)
        print(f"   Total P&L: ${best_metrics.total_pnl_usd:.2f} ({best_metrics.total_pnl_pct:.2f}%)")
        print(f"   Win Rate: {best_metrics.win_rate:.1f}%")
        print(f"   Sharpe Ratio: {best_metrics.sharpe_ratio:.2f}")
        print(f"   Max Drawdown: {best_metrics.max_drawdown:.2f}%")
        print(f"   Trade Frequency: {best_metrics.trade_freq:.1f} trades/day")
        print(f"   Optimization Score: {optimization_results['best_score']:.2f}/100")
        
        print(f"\n🏆 TOP 10 PARAMETER COMBINATIONS:")
        print("-" * 80)
        headers = ["Rank", "Momentum", "Hedge%", "Time", "TakeProfit", "StopLoss", "P&L%", "WinRate%", "Score"]
        print(f"{headers[0]:<4} {headers[1]:<8} {headers[2]:<6} {headers[3]:<6} {headers[4]:<10} {headers[5]:<8} {headers[6]:<8} {headers[7]:<8} {headers[8]:<6}")
        print("-" * 80)
        
        for i, result in enumerate(optimization_results['top_results'], 1):
            params = result['params']
            metrics = result['metrics']
            
            print(f"{i:<4} {params['momentum_threshold']:<8.1f} "
                  f"{params['hedge_ratio']*100:<6.0f} "
                  f"{params['max_position_time_minutes']:<6} "
                  f"{params['take_profit_pct']:<10.1f} "
                  f"{params['stop_loss_pct']:<8.1f} "
                  f"{metrics.total_pnl_pct:<8.2f} "
                  f"{metrics.win_rate:<8.1f} "
                  f"{result['score']:<6.1f}")
        
        print(f"\n💡 STRATEGY INSIGHTS:")
        print("-" * 30)
        
        # Analyze optimal parameters
        if best_params['hedge_ratio'] >= 0.9:
            print(f"   🛡️ High hedge ratio ({best_params['hedge_ratio']*100:.0f}%) suggests risk-averse approach optimal")
        
        if best_params['momentum_threshold'] >= 2.5:
            print(f"   🎯 High momentum threshold ({best_params['momentum_threshold']}%) indicates selective entry strategy")
        
        if best_params['max_position_time_minutes'] <= 45:
            print(f"   ⚡ Short holding time ({best_params['max_position_time_minutes']}min) suggests fast momentum capture")
        
        if best_metrics.win_rate >= 60:
            print(f"   ✅ High win rate ({best_metrics.win_rate:.1f}%) indicates good signal quality")
        
        print(f"\n🛠️ IMPLEMENTATION RECOMMENDATIONS:")
        print("-" * 40)
        print(f"   1. Update HedgedMomentumParams with optimal settings:")
        for param, value in best_params.items():
            print(f"      {param}={value}")
        print(f"   2. Monitor performance in paper trading before live deployment")
        print(f"   3. Consider market regime detection for parameter adaptation")
        print(f"   4. Implement position sizing based on volatility")

async def main():
    """Run parameter optimization."""
    
    # Test symbols (just one for now)
    symbols = [
        Symbol(base=AssetName('AIA'), quote=AssetName('USDT')),
    ]
    
    optimizer = HedgedMomentumOptimizer()
    
    for symbol in symbols:
        try:
            print(f"\n🚀 Starting optimization for {symbol}")
            
            # Run optimization
            results = await optimizer.optimize_parameters(symbol, hours=72)
            
            # Generate report
            optimizer.generate_report(results, symbol)
            
        except Exception as e:
            print(f"❌ Optimization failed for {symbol}: {e}")
            import traceback
            traceback.print_exc()
        
        print("\n" + "="*80 + "\n")
    
    print("✅ Parameter optimization completed!")

if __name__ == "__main__":
    asyncio.run(main())