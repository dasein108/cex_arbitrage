#!/usr/bin/env python3
"""
Hedged Cross-Arbitrage Backtesting System

Comprehensive backtesting framework for hedged cross-exchange arbitrage strategies
between MEXC spot and Gate.io futures with complete cycle simulation including
transfer delays, exit via Gate.io spot, and detailed performance analytics.

Strategy Overview:
1. Entry: Buy MEXC spot + Sell Gate.io futures (hedged position)
2. Transfer: Wait minimum 10 minutes (simulating inter-exchange transfer)
3. Exit: Sell Gate.io spot + Buy Gate.io futures (close positions)

Usage:
    backtest = HedgedCrossArbitrageBacktest()
    results = await backtest.run_backtest("F_USDT", days=7)
    print(backtest.format_report(results))
"""

import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, NamedTuple, Tuple
from dataclasses import dataclass
from enum import Enum
import matplotlib.pyplot as plt
import sys
import os

from config.config_manager import get_arbitrage_config
from db import get_database_manager
from exchanges.structs import Symbol, AssetName
from exchanges.structs.enums import KlineInterval

# Add src to path for imports
src_path = os.path.join(os.path.dirname(__file__), 'src')
sys.path.insert(0, src_path)

from trading.analysis.structs import Signal
from trading.research.cross_arbitrage.arbitrage_analyzer import ArbitrageAnalyzer, AnalyzerKeys
from trading.analysis.arbitrage_signals import ArbSignal, ArbStats, Signal, calculate_arb_signals


class PositionStatus(Enum):
    """Position lifecycle status."""
    OPEN = "OPEN"
    WAITING_TRANSFER = "WAITING_TRANSFER"
    READY_TO_EXIT = "READY_TO_EXIT"
    CLOSED = "CLOSED"


@dataclass
class Position:
    """Represents a unified bidirectional hedged arbitrage position."""
    entry_time: datetime
    direction: str  # "MEXC_TO_GATEIO" or "GATEIO_TO_MEXC"
    entry_spread: float
    entry_signal_reason: str
    
    # Unified role-based pricing
    source_spot_entry: float      # Buy source spot
    hedge_futures_entry: float    # Sell Gate.io futures (hedge)
    dest_spot_exit: Optional[float] = None      # Sell destination spot
    hedge_futures_exit: Optional[float] = None  # Buy Gate.io futures (close hedge)
    
    # Exchange identification
    source_exchange: str = ""     # "MEXC" or "GATEIO"
    dest_exchange: str = ""       # "GATEIO" or "MEXC" 
    hedge_exchange: str = "GATEIO_FUTURES"  # Always Gate.io futures
    
    # Position lifecycle
    status: PositionStatus = PositionStatus.OPEN
    transfer_complete_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    exit_spread: Optional[float] = None
    exit_signal_reason: Optional[str] = None
    pnl: Optional[float] = None
    holding_period_minutes: Optional[int] = None
    
    # Cost tracking
    entry_cost_usd: Optional[float] = None
    exit_cost_usd: Optional[float] = None


@dataclass
class BacktestConfig:
    """Backtesting configuration parameters."""
    symbol: Symbol = Symbol(AssetName("F"), AssetName("USDT"))
    days: int = 3
    timeframe: str = "5m"
    min_transfer_time_minutes: int = 10
    entry_threshold_percentile: float = 25.0  # Use 25th percentile for entry
    exit_threshold_percentile: float = 75.0   # Use 75th percentile for exit
    max_position_duration_hours: int = 24     # Force close after 24 hours
    fees_bps: float = 25.0                    # Total fees in basis points (0.2%)
    spread_bps: float = 5.0                   # Bid/ask spread assumption
    position_size_usd: float = 1000.0         # Position size for PnL calculation
    max_concurrent_positions: int = 3          # Limit concurrent positions


class PerformanceMetrics(NamedTuple):
    """Performance calculation results."""
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
    sortino_ratio: float
    profit_factor: float
    avg_holding_period_minutes: float
    max_concurrent_positions: int


class HedgedCrossArbitrageBacktest:
    """
    Comprehensive backtesting system for hedged cross-arbitrage strategies.
    
    Simulates the complete arbitrage cycle:
    1. Entry signal detection
    2. Position opening (MEXC spot buy + Gate.io futures sell)
    3. Transfer delay simulation (minimum 10 minutes)
    4. Exit signal detection
    5. Position closing (Gate.io spot sell + Gate.io futures buy)
    """
    
    def __init__(self, config: Optional[BacktestConfig] = None, cache_dir: str = "cache"):
        """Initialize backtester with configuration."""
        self.config = config or BacktestConfig()
        self.cache_dir = Path(__file__).parent / cache_dir
        self.cache_dir.mkdir(exist_ok=True)
        
        # Initialize data analyzer with new constructor
        self.analyzer = ArbitrageAnalyzer(use_db_book_tickers=True, tf=KlineInterval.MINUTE_5) #KlineInterval.MINUTE_1

        
        # Track positions and state
        self.positions: List[Position] = []
        self.open_positions: List[Position] = []
        self.historical_spreads = {
            'mexc_vs_gateio_futures': np.array([], dtype=np.float64),
            'gateio_spot_vs_futures': np.array([], dtype=np.float64)
        }
    
    async def run_backtest(self, symbol: Optional[Symbol] = None, days: Optional[int] = None,
                           df_data: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
        """
        Run complete backtest for specified symbol and period.
        
        Args:
            symbol: Trading symbol (e.g., "F_USDT")
            days: Number of days to backtest
            
        Returns:
            Comprehensive backtest results dictionary
        """
        # Update config if parameters provided
        if symbol:
            self.config.symbol = symbol
        if days:
            self.config.days = days
            
        print(f"🚀 Starting hedged cross-arbitrage backtest for {self.config.symbol} ({self.config.days} days)")
        print(f"📊 Configuration: Transfer delay={self.config.min_transfer_time_minutes}min, "
              f"Fees={self.config.fees_bps}bps, Position size=${self.config.position_size_usd}")

        # Load and prepare data
        df = await self._load_and_prepare_data(df_data=df_data)

        # Run simulation
        df_with_signals = self._simulate_trading(df)
        
        # Calculate performance metrics
        performance = self._calculate_performance_metrics()
        
        # Prepare comprehensive results
        results = {
            'config': self.config,
            'performance': performance,
            'positions': self.positions,
            'df': df_with_signals,
            'total_periods': len(df_with_signals),
            'backtest_start': df_with_signals.index.min(),
            'backtest_end': df_with_signals.index.max()
        }
        
        # Save results
        self._save_results(results)
        
        return results
    
    async def _load_and_prepare_data(self, df_data: Optional[pd.DataFrame]= None) -> pd.DataFrame:
        """Load candle data and calculate arbitrage spreads."""
        print(f"📥 Loading {self.config.symbol} data for {self.config.days} days...")
        
        # Use existing analyzer to get prepared data
        df, _ = await self.analyzer.run_analysis(self.config.symbol, self.config.days, df_data=df_data)
        
        print(f"✅ Loaded {len(df)} periods from {df.index.min()} to {df.index.max()}")
        
        return df

    def _simulate_trading(self, df: pd.DataFrame) -> pd.DataFrame:
        """Simulate the complete trading strategy on historical data."""
        print(f"🔄 Simulating trading strategy...")
        
        # Initialize tracking columns
        df['signal'] = 'HOLD'
        df['direction'] = 'NONE'
        df['position_action'] = None
        df['active_positions'] = 0
        df['cumulative_pnl'] = 0.0
        
        cumulative_pnl = 0.0
        
        for idx, row in df.iterrows():
            current_time = idx
            
            # Update historical spreads for signal calculation using numpy arrays
            self.historical_spreads['mexc_vs_gateio_futures'] = np.append(
                self.historical_spreads['mexc_vs_gateio_futures'], 
                row[AnalyzerKeys.mexc_vs_gateio_futures_arb]
            )
            self.historical_spreads['gateio_spot_vs_futures'] = np.append(
                self.historical_spreads['gateio_spot_vs_futures'], 
                row[AnalyzerKeys.gateio_spot_vs_futures_arb]
            )
            
            # Keep only recent history (e.g., last 500 periods for signal calculation)
            max_history = 500
            if len(self.historical_spreads['mexc_vs_gateio_futures']) > max_history:
                self.historical_spreads['mexc_vs_gateio_futures'] = self.historical_spreads['mexc_vs_gateio_futures'][-max_history:]
                self.historical_spreads['gateio_spot_vs_futures'] = self.historical_spreads['gateio_spot_vs_futures'][-max_history:]
            
            # Update position statuses (check for transfer completion, forced exits)
            self._update_position_statuses(current_time)
            
            # Generate signals
            signal_result, direction = self._generate_signal(row)
            df.at[idx, 'signal'] = signal_result.signal.value
            df.at[idx, 'direction'] = direction or 'NONE'
            
            # Execute trading logic
            action = self._execute_trading_logic(current_time, row, signal_result, direction)
            df.at[idx, 'position_action'] = action
            df.at[idx, 'active_positions'] = len(self.open_positions)
            
            # Update cumulative PnL
            period_pnl = sum(pos.pnl for pos in self.positions if pos.pnl is not None and pos.exit_time == current_time)
            cumulative_pnl += period_pnl
            df.at[idx, 'cumulative_pnl'] = cumulative_pnl
        
        print(f"✅ Simulation complete: {len(self.positions)} total positions, {len([p for p in self.positions if p.pnl is not None])} closed")
        
        return df
    
    def _generate_signal(self, row: pd.Series) -> Tuple[Any, Optional[str]]:
        """Generate unified bidirectional signals."""
        
        # Ensure we have enough historical data
        if len(self.historical_spreads['mexc_vs_gateio_futures']) < 50:
            return ArbSignal(
                signal=Signal.HOLD,
                mexc_vs_gateio_futures=ArbStats(0, 0, 0, row[AnalyzerKeys.mexc_vs_gateio_futures_arb]),
                gateio_spot_vs_futures=ArbStats(0, 0, 0, row[AnalyzerKeys.gateio_spot_vs_futures_arb])
            ), None
        
        # Calculate arbitrage opportunities in both directions
        mexc_to_gateio_spread = row[AnalyzerKeys.mexc_vs_gateio_futures_arb]  # MEXC cheaper
        gateio_to_mexc_spread = -mexc_to_gateio_spread  # Gate.io cheaper (opposite)
        
        # Use existing signal calculation for both directions
        signal_result = calculate_arb_signals(
            mexc_vs_gateio_futures_history=self.historical_spreads['mexc_vs_gateio_futures'],
            gateio_spot_vs_futures_history=self.historical_spreads['gateio_spot_vs_futures'],
            current_mexc_vs_gateio_futures=mexc_to_gateio_spread,
            current_gateio_spot_vs_futures=row[AnalyzerKeys.gateio_spot_vs_futures_arb]
        )
        
        # Detect best direction based on spread magnitude
        mexc_opportunity = mexc_to_gateio_spread  # Negative = MEXC cheaper
        gateio_opportunity = gateio_to_mexc_spread  # Positive = Gate.io cheaper
        
        # Determine preferred direction
        direction = None
        if signal_result.signal == Signal.ENTER:
            # Choose direction based on which spread is more favorable
            if abs(mexc_opportunity) > abs(gateio_opportunity) and mexc_opportunity < 0:
                direction = "MEXC_TO_GATEIO"  # MEXC cheaper, buy MEXC
            elif abs(gateio_opportunity) > abs(mexc_opportunity) and gateio_opportunity > 0:
                direction = "GATEIO_TO_MEXC"  # Gate.io cheaper, buy Gate.io
            else:
                # Default to original direction if unclear
                direction = "MEXC_TO_GATEIO" if mexc_opportunity < 0 else "GATEIO_TO_MEXC"
        
        return signal_result, direction
    

    def _execute_trading_logic(self, current_time: datetime, row: pd.Series, signal_result: Any, direction: Optional[str]) -> Optional[str]:
        """Execute unified position management based on signals and direction."""
        action = None
        
        signal = signal_result.signal

        # Check for entry signals with direction
        if (signal == Signal.ENTER and direction and
            len(self.open_positions) < self.config.max_concurrent_positions):
            action = self._open_position(current_time, row, direction)
        
        # Check for exit signals on ready positions
        elif signal == Signal.EXIT:
            action = self._close_ready_positions(current_time, row)
        
        # Force close positions that have been open too long
        self._force_close_expired_positions(current_time, row)
        
        return action
    
    def _open_position(self, current_time: datetime, row: pd.Series, direction: str) -> str:
        """Open a unified bidirectional hedged arbitrage position."""
        
        if direction == "MEXC_TO_GATEIO":
            # Buy MEXC spot + Sell Gate.io futures → transfer to Gate.io
            source_spot_entry = row[AnalyzerKeys.mexc_ask]  # Buy MEXC spot
            hedge_futures_entry = row[AnalyzerKeys.gateio_futures_bid]  # Sell Gate.io futures
            source_exchange = "MEXC"
            dest_exchange = "GATEIO"
            entry_spread = row[AnalyzerKeys.mexc_vs_gateio_futures_arb]
            entry_cost = source_spot_entry - hedge_futures_entry
            
        elif direction == "GATEIO_TO_MEXC":
            # Buy Gate.io spot + Sell Gate.io futures → transfer to MEXC
            source_spot_entry = row[AnalyzerKeys.gateio_spot_ask]  # Buy Gate.io spot
            hedge_futures_entry = row[AnalyzerKeys.gateio_futures_bid]  # Sell Gate.io futures
            source_exchange = "GATEIO"
            dest_exchange = "MEXC"
            entry_spread = -row[AnalyzerKeys.mexc_vs_gateio_futures_arb]  # Reverse spread
            entry_cost = source_spot_entry - hedge_futures_entry
            
        else:
            raise ValueError(f"Unknown direction: {direction}")
        
        position = Position(
            entry_time=current_time,
            direction=direction,
            entry_spread=entry_spread,
            entry_signal_reason=f"ENTER signal triggered ({direction})",
            source_spot_entry=source_spot_entry,
            hedge_futures_entry=hedge_futures_entry,
            source_exchange=source_exchange,
            dest_exchange=dest_exchange,
            status=PositionStatus.WAITING_TRANSFER,
            entry_cost_usd=entry_cost
        )
        
        self.positions.append(position)
        self.open_positions.append(position)
        
        return f"OPEN_{direction}_{len(self.positions)}"
    
    def _update_position_statuses(self, current_time: datetime):
        """Update position statuses based on time elapsed."""
        for position in self.open_positions:
            if position.status == PositionStatus.WAITING_TRANSFER:
                minutes_elapsed = (current_time - position.entry_time).total_seconds() / 60
                if minutes_elapsed >= self.config.min_transfer_time_minutes:
                    position.status = PositionStatus.READY_TO_EXIT
                    position.transfer_complete_time = current_time
    
    def _close_ready_positions(self, current_time: datetime, row: pd.Series) -> Optional[str]:
        """Close positions that are ready to exit."""
        ready_positions = [p for p in self.open_positions if p.status == PositionStatus.READY_TO_EXIT]
        
        if not ready_positions:
            return None
        
        closed_count = 0
        for position in ready_positions:
            self._close_position(position, current_time, row, "EXIT signal triggered")
            closed_count += 1
        
        return f"CLOSE_{closed_count}_POSITIONS"
    
    def _force_close_expired_positions(self, current_time: datetime, row: pd.Series):
        """Force close positions that have been open too long."""
        max_duration = timedelta(hours=self.config.max_position_duration_hours)
        
        expired_positions = [
            p for p in self.open_positions 
            if (current_time - p.entry_time) > max_duration
        ]
        
        for position in expired_positions:
            self._close_position(position, current_time, row, "FORCED_CLOSE_EXPIRED")
    
    def _close_position(self, position: Position, current_time: datetime, row: pd.Series, reason: str):
        """Close a unified bidirectional hedged arbitrage position."""
        
        if position.direction == "MEXC_TO_GATEIO":
            # Close: Sell Gate.io spot + Buy Gate.io futures
            dest_spot_exit = row[AnalyzerKeys.gateio_spot_bid]  # Sell Gate.io spot
            hedge_futures_exit = row[AnalyzerKeys.gateio_futures_ask]  # Buy Gate.io futures
            exit_spread = row[AnalyzerKeys.gateio_spot_vs_futures_arb]
            exit_cost = hedge_futures_exit - dest_spot_exit
            
        elif position.direction == "GATEIO_TO_MEXC":
            # Close: Sell MEXC spot + Buy Gate.io futures  
            dest_spot_exit = row[AnalyzerKeys.mexc_bid]  # Sell MEXC spot
            hedge_futures_exit = row[AnalyzerKeys.gateio_futures_ask]  # Buy Gate.io futures
            exit_spread = -row[AnalyzerKeys.mexc_vs_gateio_futures_arb]  # Reverse spread
            exit_cost = hedge_futures_exit - dest_spot_exit
            
        else:
            raise ValueError(f"Unknown direction: {position.direction}")
        
        # THREE-EXCHANGE DELTA-NEUTRAL P&L CALCULATION
        # Gate.io Futures always provides hedging reference price
        # Calculate actual position values relative to current futures price
        
        current_futures_price = hedge_futures_exit  # Current Gate.io futures price
        
        # THREE-EXCHANGE DELTA-NEUTRAL P&L (Your Method)
        # Calculate P&L for each leg separately, then combine
        
        # Spot leg: What we get from selling vs what we paid for buying
        spot_pnl_per_unit = dest_spot_exit - position.source_spot_entry
        spot_pnl_usd = (spot_pnl_per_unit / position.source_spot_entry) * self.config.position_size_usd
        
        # Futures hedge leg: We sold futures at entry, buy back at current price
        futures_pnl_per_unit = position.hedge_futures_entry - hedge_futures_exit  # Profit when futures drops
        futures_pnl_usd = (futures_pnl_per_unit / position.hedge_futures_entry) * self.config.position_size_usd
        
        # Total delta-neutral P&L = spot + futures hedge
        gross_profit_usd = spot_pnl_usd + futures_pnl_usd
        
        # Apply fees (entry + exit + transfer fees)
        fee_cost = (self.config.fees_bps / 10000) * self.config.position_size_usd
        
        # Net profit after fees
        pnl_usd = gross_profit_usd - fee_cost
        
        # Update position with unified structure
        position.exit_time = current_time
        position.dest_spot_exit = dest_spot_exit
        position.hedge_futures_exit = hedge_futures_exit
        position.exit_spread = exit_spread
        position.exit_signal_reason = reason
        position.pnl = pnl_usd
        position.holding_period_minutes = int((current_time - position.entry_time).total_seconds() / 60)
        position.status = PositionStatus.CLOSED
        position.exit_cost_usd = exit_cost
        
        # Remove from open positions
        self.open_positions.remove(position)
    
    def _validate_arbitrage_opportunity(self, entry_spread: float, exit_spread: float) -> tuple[bool, float]:
        """Validate that arbitrage opportunity is theoretically profitable."""
        spread_improvement = exit_spread - entry_spread
        min_profitable_spread = (self.config.fees_bps + self.config.spread_bps) / 100
        
        is_profitable = spread_improvement > min_profitable_spread
        return is_profitable, spread_improvement
    
    def _calculate_performance_metrics(self) -> PerformanceMetrics:
        """Calculate comprehensive performance metrics."""
        closed_positions = [p for p in self.positions if p.pnl is not None]
        
        if not closed_positions:
            return PerformanceMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        
        pnls = [p.pnl for p in closed_positions]
        winning_trades = [p for p in closed_positions if p.pnl > 0]
        losing_trades = [p for p in closed_positions if p.pnl <= 0]
        
        # Basic metrics
        total_pnl = sum(pnls)
        total_trades = len(closed_positions)
        win_rate = len(winning_trades) / total_trades * 100 if total_trades > 0 else 0
        avg_pnl_per_trade = total_pnl / total_trades if total_trades > 0 else 0
        
        # Win/Loss metrics
        avg_winning_trade = sum(p.pnl for p in winning_trades) / len(winning_trades) if winning_trades else 0
        avg_losing_trade = sum(p.pnl for p in losing_trades) / len(losing_trades) if losing_trades else 0
        
        # Risk metrics
        cumulative_pnl = np.cumsum(pnls)
        peak = np.maximum.accumulate(cumulative_pnl)
        drawdown = (cumulative_pnl - peak)
        max_drawdown = abs(min(drawdown)) if len(drawdown) > 0 else 0
        
        # Ratios
        pnl_std = np.std(pnls) if len(pnls) > 1 else 0
        sharpe_ratio = (avg_pnl_per_trade / pnl_std) * np.sqrt(252) if pnl_std > 0 else 0  # Annualized
        
        downside_returns = [p for p in pnls if p < 0]
        downside_std = np.std(downside_returns) if len(downside_returns) > 1 else 0
        sortino_ratio = (avg_pnl_per_trade / downside_std) * np.sqrt(252) if downside_std > 0 else 0
        
        gross_profit = sum(p.pnl for p in winning_trades)
        gross_loss = abs(sum(p.pnl for p in losing_trades))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # Timing metrics
        avg_holding_period = np.mean([p.holding_period_minutes for p in closed_positions])
        
        # Position management
        max_concurrent = max(len(self.open_positions) for _ in range(len(self.positions))) if self.positions else 0
        
        return PerformanceMetrics(
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
            sortino_ratio=sortino_ratio,
            profit_factor=profit_factor,
            avg_holding_period_minutes=avg_holding_period,
            max_concurrent_positions=max_concurrent
        )
    
    def _save_results(self, results: Dict[str, Any]):
        """Save backtest results to files."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save detailed results
        results_file = self.cache_dir / f"hedged_arbitrage_backtest_{self.config.symbol}_{self.config.days}d_{timestamp}.csv"
        results['df'].to_csv(results_file, index=False)
        
        # Save positions summary
        if self.positions:
            positions_data = []
            for i, pos in enumerate(self.positions):
                positions_data.append({
                    'position_id': i + 1,
                    'direction': pos.direction,
                    'source_exchange': pos.source_exchange,
                    'dest_exchange': pos.dest_exchange,
                    'entry_time': pos.entry_time,
                    'exit_time': pos.exit_time,
                    'entry_spread': pos.entry_spread,
                    'exit_spread': pos.exit_spread,
                    'source_spot_entry': pos.source_spot_entry,
                    'hedge_futures_entry': pos.hedge_futures_entry,
                    'dest_spot_exit': getattr(pos, 'dest_spot_exit', None),
                    'hedge_futures_exit': getattr(pos, 'hedge_futures_exit', None),
                    'pnl_usd': pos.pnl,
                    'holding_period_minutes': pos.holding_period_minutes,
                    'status': pos.status.value,
                    'entry_reason': pos.entry_signal_reason,
                    'exit_reason': pos.exit_signal_reason
                })
            
            positions_df = pd.DataFrame(positions_data)
            positions_file = self.cache_dir / f"hedged_arbitrage_positions_{self.config.symbol}_{self.config.days}d_{timestamp}.csv"
            positions_df.to_csv(positions_file, index=False)
        
        print(f"💾 Results saved to: {results_file}")
    
    def format_report(self, results: Dict[str, Any]) -> str:
        """Format comprehensive backtest report."""
        config = results['config']
        perf = results['performance']
        
        report = f"""
🎯 HEDGED CROSS-ARBITRAGE BACKTEST REPORT
{'='*80}

📊 STRATEGY CONFIGURATION:
  Symbol: {config.symbol}
  Period: {config.days} days ({results['backtest_start']} to {results['backtest_end']})
  Position Size: ${config.position_size_usd:,.0f}
  Transfer Delay: {config.min_transfer_time_minutes} minutes
  Max Position Duration: {config.max_position_duration_hours} hours
  Fees: {config.fees_bps} bps | Spread: {config.spread_bps} bps
  Max Concurrent Positions: {config.max_concurrent_positions}

🚀 PERFORMANCE SUMMARY:
  Total P&L: ${perf.total_pnl:,.2f}
  Total Trades: {perf.total_trades}
  Win Rate: {perf.win_rate:.1f}% ({perf.winning_trades}W / {perf.losing_trades}L)
  Average P&L per Trade: ${perf.avg_pnl_per_trade:.2f}
  
📈 TRADE ANALYSIS:
  Average Winning Trade: ${perf.avg_winning_trade:.2f}
  Average Losing Trade: ${perf.avg_losing_trade:.2f}
  Profit Factor: {perf.profit_factor:.2f}
  Average Holding Period: {perf.avg_holding_period_minutes:.1f} minutes

⚠️  RISK METRICS:
  Maximum Drawdown: ${perf.max_drawdown:.2f}
  Sharpe Ratio: {perf.sharpe_ratio:.2f}
  Sortino Ratio: {perf.sortino_ratio:.2f}
  Max Concurrent Positions: {perf.max_concurrent_positions}

🔍 STRATEGY INSIGHTS:
  • Entry Strategy: Statistical threshold-based signal detection
  • Exit Strategy: Opposite signal or forced close after {config.max_position_duration_hours}h
  • Position Management: Max {config.max_concurrent_positions} concurrent positions
  • Risk Control: Transfer delay simulation and forced exit protection
  
📊 DATA QUALITY:
  Total Periods Analyzed: {results['total_periods']:,}
  Data Coverage: {results['total_periods'] * 5 / 60:.1f} hours of 5-minute data
  """
        
        if perf.total_trades > 0:
            roi_pct = (perf.total_pnl / config.position_size_usd) * 100
            annualized_roi = roi_pct * (365 / config.days)
            
            report += f"""
💰 RETURN ANALYSIS:
  Total ROI: {roi_pct:.2f}%
  Annualized ROI: {annualized_roi:.2f}%
  Daily Average: ${perf.total_pnl / config.days:.2f}
  """
        
        return report
    
    def create_visualizations(self, results: Dict[str, Any], save_plots: bool = True) -> Dict[str, plt.Figure]:
        """Create comprehensive visualization suite."""
        figs = {}
        
        # 1. Cumulative PnL Chart
        fig1, ax1 = plt.subplots(figsize=(12, 6))
        df = results['df']
        ax1.plot(df.index, df['cumulative_pnl'], linewidth=2, color='darkblue')
        ax1.set_title(f'Cumulative P&L - {results["config"].symbol}', fontsize=14, fontweight='bold')
        ax1.set_xlabel('Time')
        ax1.set_ylabel('Cumulative P&L ($)')
        ax1.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        plt.tight_layout()
        figs['cumulative_pnl'] = fig1
        
        # 2. Position Distribution
        closed_positions = [p for p in self.positions if p.pnl is not None]
        if closed_positions:
            fig2, (ax2a, ax2b) = plt.subplots(1, 2, figsize=(15, 6))
            
            # PnL distribution
            pnls = [p.pnl for p in closed_positions]
            ax2a.hist(pnls, bins=20, alpha=0.7, color='steelblue', edgecolor='black')
            ax2a.axvline(0, color='red', linestyle='--', alpha=0.7, label='Break-even')
            ax2a.set_title('P&L Distribution per Trade')
            ax2a.set_xlabel('P&L ($)')
            ax2a.set_ylabel('Frequency')
            ax2a.legend()
            ax2a.grid(True, alpha=0.3)
            
            # Holding period distribution
            holding_periods = [p.holding_period_minutes for p in closed_positions]
            ax2b.hist(holding_periods, bins=20, alpha=0.7, color='darkgreen', edgecolor='black')
            ax2b.axvline(self.config.min_transfer_time_minutes, color='red', linestyle='--', 
                        alpha=0.7, label=f'Min Transfer Time ({self.config.min_transfer_time_minutes}m)')
            ax2b.set_title('Holding Period Distribution')
            ax2b.set_xlabel('Holding Period (minutes)')
            ax2b.set_ylabel('Frequency')
            ax2b.legend()
            ax2b.grid(True, alpha=0.3)
            
            plt.tight_layout()
            figs['distributions'] = fig2
        
        # 3. Spread Analysis
        fig3, (ax3a, ax3b) = plt.subplots(2, 1, figsize=(15, 10))
        
        # MEXC vs Gate.io Futures spread
        ax3a.plot(df.index, df[AnalyzerKeys.mexc_vs_gateio_futures_arb], alpha=0.7, label='MEXC vs Gate.io Futures')
        ax3a.set_title('Arbitrage Spreads Over Time')
        ax3a.set_ylabel('Spread (%)')
        ax3a.legend()
        ax3a.grid(True, alpha=0.3)
        
        # Gate.io Spot vs Futures spread
        ax3b.plot(df.index, df[AnalyzerKeys.gateio_spot_vs_futures_arb], alpha=0.7, 
                 color='orange', label='Gate.io Spot vs Futures')
        ax3b.set_xlabel('Time')
        ax3b.set_ylabel('Spread (%)')
        ax3b.legend()
        ax3b.grid(True, alpha=0.3)
        
        # Mark entry/exit points
        entry_points = df[df['position_action'].str.contains('OPEN', na=False)]
        exit_points = df[df['position_action'].str.contains('CLOSE', na=False)]
        
        for idx, point in entry_points.iterrows():
            ax3a.axvline(idx, color='green', alpha=0.3, linestyle=':')
            ax3b.axvline(idx, color='green', alpha=0.3, linestyle=':')
            
        for idx, point in exit_points.iterrows():
            ax3a.axvline(idx, color='red', alpha=0.3, linestyle=':')
            ax3b.axvline(idx, color='red', alpha=0.3, linestyle=':')
        
        plt.xticks(rotation=45)
        plt.tight_layout()
        figs['spreads'] = fig3
        
        # Save plots if requested
        if save_plots:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            for name, fig in figs.items():
                filename = self.cache_dir / f"hedged_arbitrage_{name}_{results['config'].symbol}_{timestamp}.png"
                fig.savefig(filename, dpi=300, bbox_inches='tight')
                print(f"📊 Plot saved: {filename}")
        
        return figs


async def main():
    """Example usage and testing."""
    print("🚀 Hedged Cross-Arbitrage Backtesting System")
    print("=" * 60)
    await get_database_manager()
    # Create backtester with custom config
    config = BacktestConfig(
        symbol=Symbol(AssetName("FLK"), AssetName("USDT")),
        days=5,
        min_transfer_time_minutes=10,
        position_size_usd=1000,
        max_concurrent_positions=2
    )
    
    backtest = HedgedCrossArbitrageBacktest(config)
    
    try:
        # Run backtest (async if real data, sync if synthetic)
        results = await backtest.run_backtest()

        # Print report
        print(backtest.format_report(results))
        
        # Create visualizations
        plots = backtest.create_visualizations(results)
        
        print(f"\n✅ Backtest completed successfully!")
        print(f"📁 Results saved in: {backtest.cache_dir}")
        
    except Exception as e:
        print(f"❌ Backtest failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
