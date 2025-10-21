#!/usr/bin/env python3
"""
Optimized Cross-Exchange Arbitrage Backtesting System

Enhanced backtesting framework with separate entry/exit logic for cross-exchange 
arbitrage strategies. Implements optimized signal generation with proper position 
tracking, profit targets, and risk management.

Key Improvements:
- Separate entry/exit spread calculations
- Position-based P&L tracking with profit targets
- Multiple exit criteria (profit target, time limit, stop loss)
- Enhanced risk management and position sizing

Strategy Flow:
1. Entry: Buy MEXC spot when spread vs Gate.io futures > threshold
2. Transfer: Simulate 10-minute transfer delay
3. Exit: Sell Gate.io spot when profit target hit or other exit criteria met

Usage:
    backtest = OptimizedCrossArbitrageBacktest()
    results = await backtest.run_backtest("BTC_USDT", days=7)
    print(backtest.format_report(results))
"""

import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional, NamedTuple, Literal
from dataclasses import dataclass
from enum import Enum
import matplotlib.pyplot as plt
import sys
import os

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from trading.research.arbitrage_analyzer import ArbitrageAnalyzer


class PositionStatus(Enum):
    """Enhanced position lifecycle status."""
    OPEN = "OPEN"
    WAITING_TRANSFER = "WAITING_TRANSFER"
    READY_TO_EXIT = "READY_TO_EXIT"
    CLOSED = "CLOSED"


@dataclass
class OptimizedPosition:
    """Enhanced position tracking with profit targeting."""
    entry_time: datetime
    entry_price_mexc: float
    entry_price_gateio_futures: float
    entry_spread: float
    entry_signal_reason: str
    
    # Position tracking
    status: PositionStatus = PositionStatus.OPEN
    transfer_complete_time: Optional[datetime] = None
    
    # Exit tracking
    exit_time: Optional[datetime] = None
    exit_price_gateio_spot: Optional[float] = None
    exit_price_gateio_futures: Optional[float] = None
    exit_spread: Optional[float] = None
    exit_signal_reason: Optional[str] = None
    
    # P&L tracking
    pnl: Optional[float] = None
    pnl_percentage: Optional[float] = None
    holding_period_minutes: Optional[int] = None
    max_profit_during_hold: float = 0.0
    min_profit_during_hold: float = 0.0


@dataclass
class OptimizedBacktestConfig:
    """Enhanced backtesting configuration."""
    symbol: str = "BTC_USDT"
    days: int = 7
    timeframe: str = "5m"
    
    # Transfer simulation
    min_transfer_time_minutes: int = 10
    
    # Entry criteria
    entry_percentile: int = 15  # Top 15% of historical spreads
    min_entry_spread: float = -0.25  # Realistic minimum based on data analysis
    
    # Exit criteria
    profit_target: float = 0.5  # Exit at 0.5% profit
    stop_loss: float = -0.5  # Stop loss at -0.5%
    max_position_hours: int = 4  # Force close after 4 hours
    exit_percentile: int = 85  # Top 15% of historical exit spreads for dynamic thresholds
    
    # Fees and costs
    trading_fees_bps: float = 10.0  # 0.1% trading fees
    transfer_fee_bps: float = 5.0   # 0.05% transfer cost
    spread_cost_bps: float = 5.0    # 0.05% bid/ask spread cost
    
    # Position management
    position_size_usd: float = 1000.0
    max_concurrent_positions: int = 2
    
    @property
    def total_fees_bps(self) -> float:
        """Total cost per round trip."""
        return self.trading_fees_bps + self.transfer_fee_bps + self.spread_cost_bps


class OptimizedPerformanceMetrics(NamedTuple):
    """Enhanced performance metrics."""
    total_pnl: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_pnl_per_trade: float
    avg_winning_trade: float
    avg_losing_trade: float
    max_drawdown: float
    sharpe_ratio: float
    profit_factor: float
    avg_holding_period_minutes: float
    max_concurrent_positions: int
    
    # Enhanced metrics
    profit_target_hits: int
    stop_loss_hits: int
    time_limit_exits: int
    favorable_spread_exits: int
    max_profit_achieved: float
    avg_max_profit_during_hold: float


class OptimizedCrossArbitrageBacktest:
    """
    Enhanced backtesting system with optimized entry/exit logic.
    
    Key improvements:
    - Separate entry/exit spread calculations
    - Profit target-based exits
    - Enhanced position tracking
    - Multiple exit criteria
    """
    
    def __init__(self, config: Optional[OptimizedBacktestConfig] = None, cache_dir: str = "cache"):
        """Initialize enhanced backtester."""
        self.config = config or OptimizedBacktestConfig()
        self.cache_dir = Path(__file__).parent / cache_dir
        self.cache_dir.mkdir(exist_ok=True)
        
        # Initialize data analyzer
        self.analyzer = ArbitrageAnalyzer(cache_dir=str(self.cache_dir))
        
        # Enhanced position tracking
        self.positions: List[OptimizedPosition] = []
        self.open_positions: List[OptimizedPosition] = []
        
        # Historical data for signal generation
        self.historical_entry_spreads: List[float] = []
        self.historical_exit_spreads: List[float] = []
    
    async def run_backtest(self, symbol: Optional[str] = None, days: Optional[int] = None) -> Dict[str, Any]:
        """
        Run optimized backtest with enhanced signal logic.
        """
        # Update config
        if symbol:
            self.config.symbol = symbol
        if days:
            self.config.days = days
        
        print(f"🚀 Starting optimized cross-arbitrage backtest for {self.config.symbol} ({self.config.days} days)")
        print(f"📊 Enhanced Config: Profit target={self.config.profit_target}%, "
              f"Stop loss={self.config.stop_loss}%, Transfer delay={self.config.min_transfer_time_minutes}min")
        
        # Load and prepare data
        df = await self._load_and_prepare_data()
        
        # Run enhanced simulation
        df_with_signals = self._simulate_optimized_trading(df)
        
        # Calculate enhanced metrics
        performance = self._calculate_enhanced_metrics()
        
        # Prepare results
        results = {
            'config': self.config,
            'performance': performance,
            'positions': self.positions,
            'df': df_with_signals,
            'total_periods': len(df_with_signals),
            'backtest_start': df_with_signals['timestamp'].min(),
            'backtest_end': df_with_signals['timestamp'].max()
        }
        
        # Save results
        self._save_results(results)
        
        return results
    
    async def _load_and_prepare_data(self) -> pd.DataFrame:
        """Load data with enhanced spread calculations."""
        print(f"📥 Loading enhanced data for {self.config.symbol}...")
        
        # Use existing analyzer but enhance the data
        df, _ = await self.analyzer.run_analysis(self.config.symbol, self.config.days)
        
        # Ensure timestamp
        if 'timestamp' not in df.columns:
            df['timestamp'] = pd.to_datetime(df['datetime'])
        else:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Sort by timestamp
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        # Add optimized spread calculations
        df = self._calculate_optimized_spreads(df)
        
        print(f"✅ Enhanced data loaded: {len(df)} periods")
        return df
    
    def _calculate_optimized_spreads(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate separate entry and exit spreads."""
        # Entry spread: MEXC spot vs Gate.io futures (what we evaluate for entry)
        df['entry_spread'] = (
            (df['gateio_futures_bid_price'] - df['mexc_spot_ask_price']) /
            df['gateio_futures_bid_price'] * 100
        )
        
        # Exit spread: Gate.io spot vs futures (what we evaluate for exit)
        df['exit_spread'] = (
            (df['gateio_spot_bid_price'] - df['gateio_futures_ask_price']) /
            df['gateio_spot_bid_price'] * 100
        )
        
        # Net entry spread after costs
        df['entry_spread_net'] = df['entry_spread'] - (self.config.total_fees_bps / 100)
        
        # Net exit spread after costs
        df['exit_spread_net'] = df['exit_spread'] - (self.config.trading_fees_bps / 100)
        
        return df
    
    def _simulate_optimized_trading(self, df: pd.DataFrame) -> pd.DataFrame:
        """Run enhanced simulation with optimized signal logic."""
        print("🔄 Running optimized trading simulation...")
        
        # Initialize tracking columns
        df['signal'] = 'HOLD'
        df['position_action'] = None
        df['active_positions'] = 0
        df['cumulative_pnl'] = 0.0
        df['current_position_pnl'] = 0.0
        
        cumulative_pnl = 0.0
        
        for idx, row in df.iterrows():
            current_time = row['timestamp']
            
            # Update historical spreads for thresholds
            self._update_historical_spreads(row)
            
            # Update position statuses and track P&L
            self._update_positions_and_pnl(current_time, row)
            
            # Generate optimized signals (now returns list of signals)
            signals, reason = self._generate_optimized_signal(row)
            df.at[idx, 'signal'] = '|'.join(signals) if signals else 'HOLD'
            
            # Execute optimized trading logic for each signal
            actions = []
            for signal in signals:
                action = self._execute_optimized_logic(current_time, row, signal, reason)
                if action:
                    actions.append(action)
            
            df.at[idx, 'position_action'] = '|'.join(actions) if actions else None
            df.at[idx, 'active_positions'] = len(self.open_positions)
            
            # Update P&L tracking
            period_pnl = sum(pos.pnl for pos in self.positions 
                           if pos.pnl is not None and pos.exit_time == current_time)
            cumulative_pnl += period_pnl
            df.at[idx, 'cumulative_pnl'] = cumulative_pnl
            
            # Current unrealized P&L
            current_unrealized = sum(self._calculate_current_pnl(pos, row) 
                                   for pos in self.open_positions)
            df.at[idx, 'current_position_pnl'] = current_unrealized
        
        print(f"✅ Enhanced simulation complete: {len(self.positions)} total positions")
        return df
    
    def _update_historical_spreads(self, row: pd.Series):
        """Update historical spread arrays for threshold calculation."""
        self.historical_entry_spreads.append(row['entry_spread_net'])
        self.historical_exit_spreads.append(row['exit_spread_net'])
        
        # Keep last 1000 periods for threshold calculation
        max_history = 1000
        if len(self.historical_entry_spreads) > max_history:
            self.historical_entry_spreads = self.historical_entry_spreads[-max_history:]
            self.historical_exit_spreads = self.historical_exit_spreads[-max_history:]
    
    def _generate_optimized_signal(self, row: pd.Series) -> Tuple[List[str], str]:
        """Generate optimized entry/exit signals matching the new TA module logic.
        
        Returns:
            Tuple of (signals_list, reason_string)
        """
        if len(self.historical_entry_spreads) < 50:  # Reduced from 100
            return [], 'Insufficient history'
        
        current_entry_spread = row['entry_spread_net']
        current_exit_spread = row['exit_spread_net']
        
        signals = []
        reasons = []
        
        # REALISTIC ENTRY LOGIC based on data analysis
        # Use all historical data for percentile calculation
        if len(self.historical_entry_spreads) >= 50:
            # Use percentile of all historical spreads (85th percentile = top 15%)
            entry_threshold = np.percentile(self.historical_entry_spreads, 
                                          100 - self.config.entry_percentile)
        else:
            # Fallback threshold based on data analysis
            entry_threshold = -0.25
        
        # Use configured minimum
        min_profitable_spread = self.config.min_entry_spread
        
        # DYNAMIC EXIT LOGIC with percentile-based thresholds
        # Calculate dynamic exit threshold
        if len(self.historical_exit_spreads) >= 50:
            # Use percentile of all historical exit spreads (85th percentile = top 15%)
            exit_threshold = np.percentile(self.historical_exit_spreads, 
                                         self.config.exit_percentile)
        else:
            # Fallback threshold based on data analysis
            exit_threshold = 0.1
        
        # Check for EXIT signal first (like the new TA module)
        # Note: EXIT is triggered when spread falls BELOW the threshold (unfavorable)
        ready_positions = [p for p in self.open_positions 
                          if p.status == PositionStatus.READY_TO_EXIT]
        
        if ready_positions and current_exit_spread < exit_threshold:
            signals.append('EXIT')
            reasons.append(f'Exit spread {current_exit_spread:.3f}% < threshold {exit_threshold:.3f}%')
        
        # Check for ENTRY signal (can occur simultaneously with EXIT)
        if (current_entry_spread > entry_threshold and 
            current_entry_spread > min_profitable_spread and
            current_entry_spread > 0.1 and  # Minimum 0.1% profit after fees (matching TA module)
            len(self.open_positions) < self.config.max_concurrent_positions):
            signals.append('ENTER')
            reasons.append(f'Entry spread {current_entry_spread:.3f}% > threshold {entry_threshold:.3f}%')
        
        # Build reason string
        if signals:
            reason = ' | '.join(reasons)
        else:
            reason = f'Entry: {current_entry_spread:.3f}% (thresh: {entry_threshold:.3f}%), Exit: {current_exit_spread:.3f}% (thresh: {exit_threshold:.3f}%)'
        
        return signals, reason
    
    def _execute_optimized_logic(self, current_time: datetime, row: pd.Series, 
                                signal: str, reason: str) -> Optional[str]:
        """Execute optimized position management."""
        action = None
        
        # Entry logic
        if signal == 'ENTER':
            action = self._open_optimized_position(current_time, row, reason)
        
        # Exit logic  
        elif signal == 'EXIT':
            action = self._close_ready_positions(current_time, row, reason)
        
        # Check profit targets and stop losses
        self._check_profit_targets_and_stops(current_time, row)
        
        # Force close expired positions
        self._force_close_expired_positions(current_time, row)
        
        return action
    
    def _open_optimized_position(self, current_time: datetime, row: pd.Series, reason: str) -> str:
        """Open enhanced position with tracking."""
        position = OptimizedPosition(
            entry_time=current_time,
            entry_price_mexc=row['mexc_spot_ask_price'],
            entry_price_gateio_futures=row['gateio_futures_bid_price'],
            entry_spread=row['entry_spread_net'],
            entry_signal_reason=reason,
            status=PositionStatus.WAITING_TRANSFER
        )
        
        self.positions.append(position)
        self.open_positions.append(position)
        
        return f"OPEN_OPTIMIZED_{len(self.positions)}"
    
    def _update_positions_and_pnl(self, current_time: datetime, row: pd.Series):
        """Update position statuses and track unrealized P&L."""
        for position in self.open_positions:
            # Update transfer status
            if position.status == PositionStatus.WAITING_TRANSFER:
                minutes_elapsed = (current_time - position.entry_time).total_seconds() / 60
                if minutes_elapsed >= self.config.min_transfer_time_minutes:
                    position.status = PositionStatus.READY_TO_EXIT
                    position.transfer_complete_time = current_time
            
            # Track max/min P&L during hold
            if position.status == PositionStatus.READY_TO_EXIT:
                current_pnl_pct = self._calculate_current_pnl_percentage(position, row)
                position.max_profit_during_hold = max(position.max_profit_during_hold, current_pnl_pct)
                position.min_profit_during_hold = min(position.min_profit_during_hold, current_pnl_pct)
    
    def _calculate_current_pnl(self, position: OptimizedPosition, row: pd.Series) -> float:
        """Calculate current P&L for open position."""
        if position.status != PositionStatus.READY_TO_EXIT:
            return 0.0
        
        # Current exit prices
        current_spot_price = row['gateio_spot_bid_price']
        current_futures_price = row['gateio_futures_ask_price']
        
        # P&L calculation (spot profit + futures hedge)
        spot_pnl = (current_spot_price - position.entry_price_mexc) / position.entry_price_mexc
        futures_pnl = (position.entry_price_gateio_futures - current_futures_price) / position.entry_price_gateio_futures
        
        total_pnl_pct = (spot_pnl + futures_pnl) * 100
        return total_pnl_pct * self.config.position_size_usd / 100
    
    def _calculate_current_pnl_percentage(self, position: OptimizedPosition, row: pd.Series) -> float:
        """Calculate current P&L percentage."""
        pnl_usd = self._calculate_current_pnl(position, row)
        return (pnl_usd / self.config.position_size_usd) * 100
    
    def _check_profit_targets_and_stops(self, current_time: datetime, row: pd.Series):
        """Check profit targets and stop losses for ready positions."""
        ready_positions = [p for p in self.open_positions 
                          if p.status == PositionStatus.READY_TO_EXIT]
        
        for position in ready_positions[:]:  # Copy list to avoid modification during iteration
            current_pnl_pct = self._calculate_current_pnl_percentage(position, row)
            
            # Check profit target
            if current_pnl_pct >= self.config.profit_target:
                self._close_position(position, current_time, row, 
                                   f"PROFIT_TARGET_HIT_{current_pnl_pct:.2f}%")
            
            # Check stop loss
            elif current_pnl_pct <= self.config.stop_loss:
                self._close_position(position, current_time, row, 
                                   f"STOP_LOSS_HIT_{current_pnl_pct:.2f}%")
    
    def _close_ready_positions(self, current_time: datetime, row: pd.Series, reason: str) -> str:
        """Close ready positions on exit signal."""
        ready_positions = [p for p in self.open_positions 
                          if p.status == PositionStatus.READY_TO_EXIT]
        
        if not ready_positions:
            return None
        
        closed_count = 0
        for position in ready_positions:
            self._close_position(position, current_time, row, reason)
            closed_count += 1
        
        return f"CLOSE_SIGNAL_{closed_count}_POSITIONS"
    
    def _force_close_expired_positions(self, current_time: datetime, row: pd.Series):
        """Force close positions held too long."""
        max_duration = timedelta(hours=self.config.max_position_hours)
        
        expired_positions = [
            p for p in self.open_positions
            if (current_time - p.entry_time) > max_duration
        ]
        
        for position in expired_positions:
            self._close_position(position, current_time, row, "FORCE_CLOSE_TIME_LIMIT")
    
    def _close_position(self, position: OptimizedPosition, current_time: datetime, 
                       row: pd.Series, reason: str):
        """Close position with enhanced P&L calculation."""
        # Exit prices
        exit_spot_price = row['gateio_spot_bid_price']
        exit_futures_price = row['gateio_futures_ask_price']
        
        # Calculate final P&L
        spot_pnl = (exit_spot_price - position.entry_price_mexc) / position.entry_price_mexc
        futures_pnl = (position.entry_price_gateio_futures - exit_futures_price) / position.entry_price_gateio_futures
        
        total_pnl_pct = (spot_pnl + futures_pnl) * 100
        pnl_usd = total_pnl_pct * self.config.position_size_usd / 100
        
        # Update position
        position.exit_time = current_time
        position.exit_price_gateio_spot = exit_spot_price
        position.exit_price_gateio_futures = exit_futures_price
        position.exit_spread = row['exit_spread_net']
        position.exit_signal_reason = reason
        position.pnl = pnl_usd
        position.pnl_percentage = total_pnl_pct
        position.holding_period_minutes = int((current_time - position.entry_time).total_seconds() / 60)
        position.status = PositionStatus.CLOSED
        
        # Remove from open positions
        self.open_positions.remove(position)
    
    def _calculate_enhanced_metrics(self) -> OptimizedPerformanceMetrics:
        """Calculate enhanced performance metrics."""
        closed_positions = [p for p in self.positions if p.pnl is not None]
        
        if not closed_positions:
            return OptimizedPerformanceMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        
        # Basic metrics
        pnls = [p.pnl for p in closed_positions]
        winning_trades = [p for p in closed_positions if p.pnl > 0]
        losing_trades = [p for p in closed_positions if p.pnl <= 0]
        
        total_pnl = sum(pnls)
        total_trades = len(closed_positions)
        win_rate = len(winning_trades) / total_trades * 100
        avg_pnl_per_trade = total_pnl / total_trades
        
        # Win/Loss metrics
        avg_winning_trade = sum(p.pnl for p in winning_trades) / len(winning_trades) if winning_trades else 0
        avg_losing_trade = sum(p.pnl for p in losing_trades) / len(losing_trades) if losing_trades else 0
        
        # Risk metrics
        cumulative_pnl = np.cumsum(pnls)
        peak = np.maximum.accumulate(cumulative_pnl)
        drawdown = cumulative_pnl - peak
        max_drawdown = abs(min(drawdown)) if len(drawdown) > 0 else 0
        
        # Ratios
        pnl_std = np.std(pnls) if len(pnls) > 1 else 0
        sharpe_ratio = (avg_pnl_per_trade / pnl_std) * np.sqrt(252) if pnl_std > 0 else 0
        
        gross_profit = sum(p.pnl for p in winning_trades)
        gross_loss = abs(sum(p.pnl for p in losing_trades))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # Enhanced metrics
        profit_target_hits = len([p for p in closed_positions 
                                if 'PROFIT_TARGET' in p.exit_signal_reason])
        stop_loss_hits = len([p for p in closed_positions 
                            if 'STOP_LOSS' in p.exit_signal_reason])
        time_limit_exits = len([p for p in closed_positions 
                              if 'TIME_LIMIT' in p.exit_signal_reason])
        favorable_exits = len([p for p in closed_positions 
                             if 'EXIT' in p.exit_signal_reason and 'FORCE' not in p.exit_signal_reason])
        
        max_profit_achieved = max(p.max_profit_during_hold for p in closed_positions)
        avg_max_profit = np.mean([p.max_profit_during_hold for p in closed_positions])
        
        avg_holding_period = np.mean([p.holding_period_minutes for p in closed_positions])
        max_concurrent = max([len(self.open_positions)]) if self.positions else 0
        
        return OptimizedPerformanceMetrics(
            total_pnl=total_pnl,
            total_trades=total_trades,
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            win_rate=win_rate,
            avg_pnl_per_trade=avg_pnl_per_trade,
            avg_winning_trade=avg_winning_trade,
            avg_losing_trade=avg_losing_trade,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            profit_factor=profit_factor,
            avg_holding_period_minutes=avg_holding_period,
            max_concurrent_positions=max_concurrent,
            profit_target_hits=profit_target_hits,
            stop_loss_hits=stop_loss_hits,
            time_limit_exits=time_limit_exits,
            favorable_spread_exits=favorable_exits,
            max_profit_achieved=max_profit_achieved,
            avg_max_profit_during_hold=avg_max_profit
        )
    
    def _save_results(self, results: Dict[str, Any]):
        """Save enhanced results."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save detailed results
        results_file = self.cache_dir / f"optimized_arbitrage_backtest_{self.config.symbol}_{self.config.days}d_{timestamp}.csv"
        results['df'].to_csv(results_file, index=False)
        
        # Save enhanced positions
        if self.positions:
            positions_data = []
            for i, pos in enumerate(self.positions):
                positions_data.append({
                    'position_id': i + 1,
                    'entry_time': pos.entry_time,
                    'exit_time': pos.exit_time,
                    'entry_spread': pos.entry_spread,
                    'exit_spread': pos.exit_spread,
                    'pnl_usd': pos.pnl,
                    'pnl_percentage': pos.pnl_percentage,
                    'holding_period_minutes': pos.holding_period_minutes,
                    'max_profit_during_hold': pos.max_profit_during_hold,
                    'min_profit_during_hold': pos.min_profit_during_hold,
                    'status': pos.status.value,
                    'entry_reason': pos.entry_signal_reason,
                    'exit_reason': pos.exit_signal_reason
                })
            
            positions_df = pd.DataFrame(positions_data)
            positions_file = self.cache_dir / f"optimized_arbitrage_positions_{self.config.symbol}_{self.config.days}d_{timestamp}.csv"
            positions_df.to_csv(positions_file, index=False)
        
        print(f"💾 Enhanced results saved to: {results_file}")
    
    def format_report(self, results: Dict[str, Any]) -> str:
        """Format enhanced report."""
        config = results['config']
        perf = results['performance']
        
        report = f"""
🎯 OPTIMIZED CROSS-ARBITRAGE BACKTEST REPORT
{'='*80}

📊 ENHANCED STRATEGY CONFIGURATION:
  Symbol: {config.symbol}
  Period: {config.days} days ({results['backtest_start']} to {results['backtest_end']})
  Position Size: ${config.position_size_usd:,.0f}
  Transfer Delay: {config.min_transfer_time_minutes} minutes
  
📈 PROFIT TARGETING:
  Profit Target: {config.profit_target}%
  Stop Loss: {config.stop_loss}%
  Max Position Duration: {config.max_position_hours} hours
  Entry Threshold: Top {config.entry_percentile}% of spreads

🚀 ENHANCED PERFORMANCE:
  Total P&L: ${perf.total_pnl:,.2f}
  Total Trades: {perf.total_trades}
  Win Rate: {perf.win_rate:.1f}% ({perf.winning_trades}W / {perf.losing_trades}L)
  Average P&L per Trade: ${perf.avg_pnl_per_trade:.2f}
  
🎯 EXIT ANALYSIS:
  Profit Target Hits: {perf.profit_target_hits}
  Stop Loss Hits: {perf.stop_loss_hits}
  Time Limit Exits: {perf.time_limit_exits}
  Favorable Spread Exits: {perf.favorable_spread_exits}
  
📈 ENHANCED METRICS:
  Max Profit Achieved: {perf.max_profit_achieved:.2f}%
  Avg Max Profit During Hold: {perf.avg_max_profit_during_hold:.2f}%
  Average Holding Period: {perf.avg_holding_period_minutes:.1f} minutes
  Profit Factor: {perf.profit_factor:.2f}

⚠️  RISK METRICS:
  Maximum Drawdown: ${perf.max_drawdown:.2f}
  Sharpe Ratio: {perf.sharpe_ratio:.2f}
  Max Concurrent Positions: {perf.max_concurrent_positions}
  
💡 OPTIMIZATION INSIGHTS:
  • Separate entry/exit spread calculations improve accuracy
  • Profit targeting reduces holding time and risk
  • Enhanced exit criteria capture more profit opportunities
  • Risk management prevents large losses
"""
        
        if perf.total_trades > 0:
            roi_pct = (perf.total_pnl / config.position_size_usd) * 100
            annualized_roi = roi_pct * (365 / config.days)
            
            report += f"""
💰 RETURN ANALYSIS:
  Total ROI: {roi_pct:.2f}%
  Annualized ROI: {annualized_roi:.2f}%
  Daily Average: ${perf.total_pnl / config.days:.2f}
  
🎯 PROFIT TARGET EFFECTIVENESS:
  Profit Targets Hit: {(perf.profit_target_hits / perf.total_trades * 100):.1f}% of trades
  Stop Loss Rate: {(perf.stop_loss_hits / perf.total_trades * 100):.1f}% of trades
"""
        
        return report


async def main():
    """Example usage of optimized backtest."""
    print("🚀 Optimized Cross-Arbitrage Backtesting System")
    print("=" * 60)
    
    # Create enhanced config
    config = OptimizedBacktestConfig(
        symbol="F_USDT",
        days=3,
        profit_target=0.5,
        stop_loss=-0.5,
        min_transfer_time_minutes=10,
        max_position_hours=4,
        position_size_usd=1000,
        max_concurrent_positions=2
    )
    
    backtest = OptimizedCrossArbitrageBacktest(config)
    
    try:
        # Run enhanced backtest
        results = await backtest.run_backtest()
        
        # Print enhanced report
        print(backtest.format_report(results))
        
        print(f"\n✅ Optimized backtest completed successfully!")
        print(f"📁 Results saved in: {backtest.cache_dir}")
        
    except Exception as e:
        print(f"❌ Enhanced backtest failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())