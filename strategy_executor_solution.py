#!/usr/bin/env python3
"""
Strategy Executor Solution

This demonstrates how to create a trade execution layer on top of 
ArbitrageSignalStrategy to generate actual trades like ArbitrageAnalyzer.

The ArbitrageSignalStrategy is a signal generation component, not a complete 
trading system. To get trades, we need to add execution logic.
"""

import asyncio
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

# Mock imports for demonstration
class Signal(Enum):
    ENTER = "ENTER"
    EXIT = "EXIT" 
    HOLD = "HOLD"

@dataclass
class Trade:
    """Represents a completed trade."""
    entry_time: datetime
    exit_time: Optional[datetime]
    entry_price: float
    exit_price: Optional[float]
    position_size: float
    pnl_pct: float
    strategy_type: str
    exit_reason: str = ""

@dataclass
class Position:
    """Represents an active trading position."""
    entry_time: datetime
    entry_price: float
    position_size: float
    strategy_type: str
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

class StrategyExecutor:
    """
    Execution layer that wraps ArbitrageSignalStrategy to generate actual trades.
    
    This class:
    1. Uses ArbitrageSignalStrategy for signal generation
    2. Adds position tracking and trade execution logic
    3. Calculates P&L and performance metrics
    4. Maintains compatibility with ArbitrageAnalyzer results
    """
    
    def __init__(self, strategy_name: str):
        self.strategy_name = strategy_name
        self.active_positions: List[Position] = []
        self.completed_trades: List[Trade] = []
        self.cumulative_pnl = 0.0
        
        # Strategy-specific parameters
        self.max_positions = 3
        self.position_size_usd = 1000.0
        self.total_fees_pct = 0.0025  # 0.25% total fees
        
    def generate_signal(self, market_data: Dict) -> Signal:
        """
        Mock signal generation - replace with actual ArbitrageSignalStrategy call.
        """
        # This would be replaced with:
        # signal = self.arbitrage_signal_strategy.update_with_live_data(...)
        
        # Mock logic for demonstration
        spread = market_data.get('mexc_vs_futures_spread', 0)
        
        if spread < -2.5 and len(self.active_positions) < self.max_positions:
            return Signal.ENTER
        elif spread > -0.3 and len(self.active_positions) > 0:
            return Signal.EXIT
        else:
            return Signal.HOLD
    
    def execute_signal(self, signal: Signal, market_data: Dict, timestamp: datetime) -> bool:
        """
        Execute trading logic based on signal.
        
        This is the KEY MISSING PIECE that ArbitrageSignalStrategy doesn't have.
        """
        if signal == Signal.ENTER:
            return self._enter_position(market_data, timestamp)
        elif signal == Signal.EXIT:
            return self._exit_positions(market_data, timestamp)
        
        return False
    
    def _enter_position(self, market_data: Dict, timestamp: datetime) -> bool:
        """Enter a new position."""
        if len(self.active_positions) >= self.max_positions:
            return False
        
        entry_price = market_data.get('mexc_price', 0)
        if entry_price <= 0:
            return False
        
        position = Position(
            entry_time=timestamp,
            entry_price=entry_price,
            position_size=self.position_size_usd,
            strategy_type=self.strategy_name,
            stop_loss=entry_price * 0.94,  # 6% stop loss
            take_profit=entry_price * 1.02  # 2% take profit
        )
        
        self.active_positions.append(position)
        print(f"🔵 ENTER: {self.strategy_name} position at ${entry_price:.4f} ({timestamp})")
        return True
    
    def _exit_positions(self, market_data: Dict, timestamp: datetime, exit_reason: str = "SIGNAL") -> bool:
        """Exit all active positions."""
        if not self.active_positions:
            return False
        
        exit_price = market_data.get('mexc_price', 0)
        if exit_price <= 0:
            return False
        
        trades_created = 0
        
        for position in self.active_positions[:]:  # Copy list to modify during iteration
            # Calculate P&L
            price_change_pct = ((exit_price - position.entry_price) / position.entry_price) * 100
            pnl_pct = price_change_pct - self.total_fees_pct * 100  # Subtract fees
            
            # Create completed trade
            trade = Trade(
                entry_time=position.entry_time,
                exit_time=timestamp,
                entry_price=position.entry_price,
                exit_price=exit_price,
                position_size=position.position_size,
                pnl_pct=pnl_pct,
                strategy_type=self.strategy_name,
                exit_reason=exit_reason
            )
            
            self.completed_trades.append(trade)
            self.cumulative_pnl += pnl_pct
            
            print(f"🔴 EXIT: {self.strategy_name} position ${position.entry_price:.4f} → ${exit_price:.4f} "
                  f"P&L: {pnl_pct:.3f}% ({exit_reason})")
            
            trades_created += 1
        
        # Clear all positions
        self.active_positions.clear()
        return trades_created > 0
    
    def get_performance_summary(self) -> Dict:
        """Get performance metrics similar to ArbitrageAnalyzer output."""
        if not self.completed_trades:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'win_rate_pct': 0.0,
                'total_pnl_pct': 0.0,
                'avg_pnl_pct': 0.0,
                'cumulative_pnl': 0.0
            }
        
        winning_trades = sum(1 for trade in self.completed_trades if trade.pnl_pct > 0)
        total_trades = len(self.completed_trades)
        win_rate = (winning_trades / total_trades) * 100
        avg_pnl = sum(trade.pnl_pct for trade in self.completed_trades) / total_trades
        
        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'win_rate_pct': win_rate,
            'total_pnl_pct': sum(trade.pnl_pct for trade in self.completed_trades),
            'avg_pnl_pct': avg_pnl,
            'cumulative_pnl': self.cumulative_pnl
        }


def simulate_backtest_with_execution():
    """
    Demonstrate how StrategyExecutor generates trades like ArbitrageAnalyzer.
    """
    print("🚀 Strategy Executor Demonstration")
    print("=" * 60)
    print("This shows how to add trade execution to ArbitrageSignalStrategy")
    print()
    
    # Create strategy executor
    executor = StrategyExecutor("Reverse Delta Neutral")
    
    # Simulate market data over time
    print("📊 Simulating market data and signals...")
    
    base_price = 0.1500
    timestamps = [datetime.now() + timedelta(minutes=i*5) for i in range(20)]
    
    for i, timestamp in enumerate(timestamps):
        # Simulate price movements and spreads
        price_noise = (i % 4 - 2) * 0.001  # Small price variations
        mexc_price = base_price + price_noise
        futures_price = mexc_price * 1.025  # 2.5% premium = -2.5% spread
        
        # Create spread that triggers entry then exit
        if i < 8:
            # Entry phase: negative spread
            spread = -3.0 + (i * 0.2)  # -3.0% to -1.4%
        else:
            # Exit phase: spread compression
            spread = -1.4 + ((i - 8) * 0.15)  # -1.4% to +0.4%
        
        market_data = {
            'mexc_price': mexc_price,
            'futures_price': futures_price,
            'mexc_vs_futures_spread': spread
        }
        
        # Generate signal
        signal = executor.generate_signal(market_data)
        
        # Execute based on signal
        trade_executed = executor.execute_signal(signal, market_data, timestamp)
        
        if not trade_executed and signal != Signal.HOLD:
            print(f"⚪ {signal.value}: No action (conditions not met)")
    
    # Show results
    print(f"\n📈 Strategy Execution Results:")
    print("=" * 40)
    
    performance = executor.get_performance_summary()
    
    print(f"• Strategy: {executor.strategy_name}")
    print(f"• Total trades: {performance['total_trades']}")
    print(f"• Winning trades: {performance['winning_trades']}")
    print(f"• Win rate: {performance['win_rate_pct']:.1f}%")
    print(f"• Total P&L: {performance['total_pnl_pct']:.3f}%")
    print(f"• Average P&L per trade: {performance['avg_pnl_pct']:.3f}%")
    print(f"• Cumulative P&L: {performance['cumulative_pnl']:.3f}%")
    
    print(f"\n📋 Trade Details:")
    for i, trade in enumerate(executor.completed_trades, 1):
        holding_time = (trade.exit_time - trade.entry_time).total_seconds() / 60
        print(f"  Trade {i}: Entry=${trade.entry_price:.4f} → Exit=${trade.exit_price:.4f} "
              f"P&L={trade.pnl_pct:.3f}% ({holding_time:.0f}min)")
    
    print(f"\n✅ SUCCESS: StrategyExecutor generated {performance['total_trades']} trades!")
    print(f"Compare this to ArbitrageSignalStrategy which generates 0 trades (signals only)")


def print_implementation_guide():
    """Print guide for implementing this solution."""
    print("\n" + "=" * 80)
    print("🛠️  IMPLEMENTATION GUIDE")
    print("=" * 80)
    
    print("\n1️⃣ CREATE STRATEGY EXECUTOR WRAPPER")
    print("   • Wrap ArbitrageSignalStrategy with StrategyExecutor")
    print("   • Add position tracking and trade execution logic")
    print("   • Implement P&L calculation and performance metrics")
    
    print("\n2️⃣ INTEGRATE WITH EXISTING SIGNAL GENERATION")
    print("   ```python")
    print("   class StrategyExecutor:")
    print("       def __init__(self, signal_strategy):")
    print("           self.signal_strategy = signal_strategy")
    print("           self.positions = []")
    print("           self.trades = []")
    print("   ")
    print("       def update_with_market_data(self, market_data):")
    print("           # Get signal from ArbitrageSignalStrategy")
    print("           signal = self.signal_strategy.update_with_live_data(...)")
    print("           ")
    print("           # Execute trades based on signal")
    print("           if signal == Signal.ENTER:")
    print("               self.enter_position(market_data)")
    print("           elif signal == Signal.EXIT:")
    print("               self.exit_positions(market_data)")
    print("   ```")
    
    print("\n3️⃣ MAINTAIN COMPATIBILITY")
    print("   • Keep same interface as ArbitrageAnalyzer for backtesting")
    print("   • Return DataFrames with trade columns (rdn_trade_pnl, etc.)")
    print("   • Provide same performance metrics and reporting")
    
    print("\n4️⃣ UNIFIED ARCHITECTURE")
    print("   • ArbitrageSignalStrategy: Signal generation")
    print("   • StrategyExecutor: Trade execution and P&L tracking")
    print("   • Unified interface for both backtesting and live trading")
    
    print("\n🎯 RESULT: Best of both worlds!")
    print("   ✅ Reusable signals for live trading")
    print("   ✅ Complete trade execution for backtesting")
    print("   ✅ Unified architecture across the system")


if __name__ == "__main__":
    simulate_backtest_with_execution()
    print_implementation_guide()