"""
Advanced Backtesting Framework for Cross-Exchange Arbitrage

Includes multiple strategy implementations:
1. Mean Reversion (basic)
2. Spike Capture with Limit Orders
3. Triangular Arbitrage
4. Adaptive Threshold Strategy
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class ExitReason(Enum):
    PROFIT_TARGET = "profit_target"
    STOP_LOSS = "stop_loss"
    TIME_STOP = "time_stop"
    CORRELATION_STOP = "correlation_stop"
    TRAILING_STOP = "trailing_stop"


@dataclass
class Trade:
    """Single trade record"""
    entry_idx: int
    exit_idx: int
    entry_time: any
    exit_time: any
    hold_time: int
    entry_spread: float
    exit_spread: float
    entry_z_score: float
    exit_z_score: float
    raw_pnl_pct: float
    net_pnl_pct: float
    exit_reason: ExitReason
    direction: str
    entry_price_mexc: float
    entry_price_gateio: float
    exit_price_mexc: float
    exit_price_gateio: float


class AdvancedBacktester:
    """Advanced backtesting framework with multiple strategies"""
    
    def __init__(self, 
                 mexc_fee: float = 0.10,
                 gateio_fee: float = 0.15,
                 futures_fee: float = 0.05,
                 slippage_estimate: float = 0.05):
        """
        Initialize backtester with trading costs
        
        Args:
            mexc_fee: MEXC trading fee in %
            gateio_fee: Gate.io trading fee in %
            futures_fee: Futures trading fee in %
            slippage_estimate: Estimated slippage per leg in %
        """
        self.mexc_fee = mexc_fee
        self.gateio_fee = gateio_fee
        self.futures_fee = futures_fee
        self.slippage_estimate = slippage_estimate
        
        # Total round-trip costs
        self.total_entry_cost = mexc_fee + gateio_fee + futures_fee + 3 * slippage_estimate
        self.total_exit_cost = self.total_entry_cost
        
    def backtest_spike_capture(self, df: pd.DataFrame,
                               volatility_threshold: float = 1.3,
                               low_liq_threshold: float = 45,
                               z_score_threshold: float = 2.0,
                               profit_target_pct: float = 0.3,
                               stop_loss_pct: float = 0.4) -> Dict:
        """
        Backtest spike capture strategy using limit orders
        
        Strategy: Place limit orders on illiquid venue, market sell on liquid venue
        when price spikes occur
        
        Args:
            volatility_threshold: Minimum vol_ratio to trade
            low_liq_threshold: Minimum % static candles for low liquidity
            z_score_threshold: Minimum spread Z-score
            profit_target_pct: Take profit at this % spread contraction
            stop_loss_pct: Stop loss at this % adverse movement
        """
        
        mexc_c_col = df.attrs.get('mexc_c_col', 'mexc_close')
        gateio_c_col = df.attrs.get('gateio_c_col', 'gateio_close')
        
        position = None
        trades = []
        
        for idx in range(len(df)):
            if idx < 20:
                continue
                
            row = df.iloc[idx]
            
            if pd.isna(row['spread_z_score']) or pd.isna(row['vol_ratio']):
                continue
            
            current_spread = row['mexc_vs_gateio_pct']
            z_score = row['spread_z_score']
            
            # ENTRY: Spike detected on volatile venue with low liquidity
            if position is None:
                entry_signal = (
                    abs(z_score) > z_score_threshold and
                    row['vol_ratio'] > volatility_threshold and
                    row['mexc_static'] > low_liq_threshold and
                    abs(row['spread_velocity']) > 0.08  # Rapid movement
                )
                
                if entry_signal:
                    # Determine which venue is spiking
                    if current_spread > 0:
                        # MEXC more expensive - sell MEXC, buy Gate.io
                        direction = 'short_mexc'
                    else:
                        # Gate.io more expensive - sell Gate.io, buy MEXC
                        direction = 'long_mexc'
                    
                    position = {
                        'entry_idx': idx,
                        'entry_time': row.name if hasattr(row, 'name') else idx,
                        'entry_spread': current_spread,
                        'entry_z_score': z_score,
                        'entry_price_mexc': row[mexc_c_col],
                        'entry_price_gateio': row[gateio_c_col],
                        'direction': direction,
                        'max_favorable_spread': current_spread,
                    }
            
            # EXIT: Profit target or stop loss
            else:
                hold_time = idx - position['entry_idx']
                spread_change = abs(current_spread - position['entry_spread'])
                
                # Update max favorable for trailing stop
                if abs(current_spread) < abs(position['max_favorable_spread']):
                    position['max_favorable_spread'] = current_spread
                
                # Profit target: spread contracted enough
                profit_target = spread_change >= profit_target_pct
                
                # Stop loss: spread expanded (moved against us)
                stop_loss = abs(current_spread) > abs(position['entry_spread']) + stop_loss_pct
                
                # Time stop: quick exit strategy (10 minutes max)
                time_stop = hold_time > 10
                
                # Trailing stop: give back 50% of max profit
                trailing_stop = abs(current_spread - position['max_favorable_spread']) > profit_target_pct * 0.5
                
                exit_signal = profit_target or stop_loss or time_stop or trailing_stop
                
                if exit_signal:
                    raw_pnl = abs(position['entry_spread']) - abs(current_spread)
                    net_pnl = raw_pnl - self.total_entry_cost - self.total_exit_cost
                    
                    trade = Trade(
                        entry_idx=position['entry_idx'],
                        exit_idx=idx,
                        entry_time=position['entry_time'],
                        exit_time=row.name if hasattr(row, 'name') else idx,
                        hold_time=hold_time,
                        entry_spread=position['entry_spread'],
                        exit_spread=current_spread,
                        entry_z_score=position['entry_z_score'],
                        exit_z_score=z_score,
                        raw_pnl_pct=raw_pnl,
                        net_pnl_pct=net_pnl,
                        exit_reason=(
                            ExitReason.PROFIT_TARGET if profit_target else
                            ExitReason.STOP_LOSS if stop_loss else
                            ExitReason.TIME_STOP if time_stop else
                            ExitReason.TRAILING_STOP
                        ),
                        direction=position['direction'],
                        entry_price_mexc=position['entry_price_mexc'],
                        entry_price_gateio=position['entry_price_gateio'],
                        exit_price_mexc=row[mexc_c_col],
                        exit_price_gateio=row[gateio_c_col],
                    )
                    trades.append(trade)
                    position = None
        
        return self._calculate_metrics(trades, "Spike Capture")
    
    def backtest_triangular_arbitrage(self, df: pd.DataFrame,
                                     edge_threshold: float = 0.5,
                                     max_hold_time: int = 30) -> Dict:
        """
        Backtest triangular arbitrage: MEXC Spot + Gate.io Spot + Gate.io Futures
        
        Strategy: Trade when triangular edge (spot-spot spread + spot-futures spread) 
        exceeds costs
        
        Args:
            edge_threshold: Minimum triangular edge to enter (in %)
            max_hold_time: Maximum hold time in minutes
        """
        
        mexc_c_col = df.attrs.get('mexc_c_col', 'mexc_close')
        gateio_c_col = df.attrs.get('gateio_c_col', 'gateio_close')
        
        position = None
        trades = []
        
        # Triangular arbitrage needs all three legs
        min_edge = self.total_entry_cost + self.total_exit_cost + edge_threshold
        
        for idx in range(len(df)):
            if idx < 20:
                continue
                
            row = df.iloc[idx]
            
            if pd.isna(row['triangular_edge']):
                continue
            
            triangular_edge = row['triangular_edge']
            
            # ENTRY: Triangular edge exceeds minimum threshold
            if position is None:
                if abs(triangular_edge) > min_edge:
                    position = {
                        'entry_idx': idx,
                        'entry_time': row.name if hasattr(row, 'name') else idx,
                        'entry_edge': triangular_edge,
                        'entry_price_mexc': row[mexc_c_col],
                        'entry_price_gateio': row[gateio_c_col],
                        'direction': 'positive' if triangular_edge > 0 else 'negative',
                    }
            
            # EXIT: Edge disappeared or time stop
            else:
                hold_time = idx - position['entry_idx']
                
                # Edge convergence (profit target)
                edge_converged = abs(triangular_edge) < min_edge * 0.3
                
                # Time stop
                time_stop = hold_time > max_hold_time
                
                # Edge expanded (stop loss)
                edge_expanded = abs(triangular_edge) > abs(position['entry_edge']) * 1.2
                
                exit_signal = edge_converged or time_stop or edge_expanded
                
                if exit_signal:
                    raw_pnl = abs(position['entry_edge']) - abs(triangular_edge)
                    net_pnl = raw_pnl - self.total_entry_cost - self.total_exit_cost
                    
                    trade = Trade(
                        entry_idx=position['entry_idx'],
                        exit_idx=idx,
                        entry_time=position['entry_time'],
                        exit_time=row.name if hasattr(row, 'name') else idx,
                        hold_time=hold_time,
                        entry_spread=position['entry_edge'],
                        exit_spread=triangular_edge,
                        entry_z_score=0,  # N/A for triangular
                        exit_z_score=0,
                        raw_pnl_pct=raw_pnl,
                        net_pnl_pct=net_pnl,
                        exit_reason=(
                            ExitReason.PROFIT_TARGET if edge_converged else
                            ExitReason.STOP_LOSS if edge_expanded else
                            ExitReason.TIME_STOP
                        ),
                        direction=position['direction'],
                        entry_price_mexc=position['entry_price_mexc'],
                        entry_price_gateio=position['entry_price_gateio'],
                        exit_price_mexc=row[mexc_c_col],
                        exit_price_gateio=row[gateio_c_col],
                    )
                    trades.append(trade)
                    position = None
        
        return self._calculate_metrics(trades, "Triangular Arbitrage")
    
    def backtest_adaptive_threshold(self, df: pd.DataFrame) -> Dict:
        """
        Adaptive threshold strategy: Adjusts entry/exit thresholds based on 
        recent volatility and correlation
        
        Strategy: Use tighter thresholds in stable markets, wider in volatile markets
        """
        
        mexc_c_col = df.attrs.get('mexc_c_col', 'mexc_close')
        gateio_c_col = df.attrs.get('gateio_c_col', 'gateio_close')
        
        position = None
        trades = []
        
        for idx in range(len(df)):
            if idx < 20:
                continue
                
            row = df.iloc[idx]
            
            if pd.isna(row['spread_z_score']) or pd.isna(row['spread_std']):
                continue
            
            current_spread = row['mexc_vs_gateio_pct']
            z_score = row['spread_z_score']
            spread_std = row['spread_std']
            
            # Adaptive thresholds based on volatility
            # Low volatility: tighter thresholds (1.2x)
            # High volatility: wider thresholds (2.0x)
            volatility_multiplier = np.clip(spread_std / 0.2, 1.2, 2.5)
            
            entry_z_threshold = 1.3 * volatility_multiplier
            exit_z_threshold = 0.4 / volatility_multiplier
            stop_loss_pct = 0.4 * volatility_multiplier
            
            # ENTRY
            if position is None:
                entry_signal = (
                    abs(z_score) > entry_z_threshold and
                    row['spread_velocity'] < 0 and
                    row['rolling_corr'] > 0.75
                )
                
                if entry_signal:
                    position = {
                        'entry_idx': idx,
                        'entry_time': row.name if hasattr(row, 'name') else idx,
                        'entry_spread': current_spread,
                        'entry_z_score': z_score,
                        'entry_price_mexc': row[mexc_c_col],
                        'entry_price_gateio': row[gateio_c_col],
                        'direction': 'long' if current_spread > 0 else 'short',
                        'entry_volatility_mult': volatility_multiplier,
                    }
            
            # EXIT
            else:
                hold_time = idx - position['entry_idx']
                spread_change = current_spread - position['entry_spread']
                
                # Use entry volatility for consistent exit
                exit_z_thresh = 0.4 / position['entry_volatility_mult']
                stop_pct = 0.4 * position['entry_volatility_mult']
                
                profit_target = abs(z_score) < exit_z_thresh
                stop_loss = abs(spread_change) > stop_pct
                time_stop = hold_time > 90
                correlation_stop = row['rolling_corr'] < 0.65
                
                exit_signal = profit_target or stop_loss or time_stop or correlation_stop
                
                if exit_signal:
                    raw_pnl = position['entry_spread'] - current_spread
                    if position['direction'] == 'short':
                        raw_pnl = -raw_pnl
                    
                    net_pnl = raw_pnl - self.total_entry_cost - self.total_exit_cost
                    
                    trade = Trade(
                        entry_idx=position['entry_idx'],
                        exit_idx=idx,
                        entry_time=position['entry_time'],
                        exit_time=row.name if hasattr(row, 'name') else idx,
                        hold_time=hold_time,
                        entry_spread=position['entry_spread'],
                        exit_spread=current_spread,
                        entry_z_score=position['entry_z_score'],
                        exit_z_score=z_score,
                        raw_pnl_pct=raw_pnl,
                        net_pnl_pct=net_pnl,
                        exit_reason=(
                            ExitReason.PROFIT_TARGET if profit_target else
                            ExitReason.STOP_LOSS if stop_loss else
                            ExitReason.TIME_STOP if time_stop else
                            ExitReason.CORRELATION_STOP
                        ),
                        direction=position['direction'],
                        entry_price_mexc=position['entry_price_mexc'],
                        entry_price_gateio=position['entry_price_gateio'],
                        exit_price_mexc=row[mexc_c_col],
                        exit_price_gateio=row[gateio_c_col],
                    )
                    trades.append(trade)
                    position = None
        
        return self._calculate_metrics(trades, "Adaptive Threshold")
    
    def _calculate_metrics(self, trades: List[Trade], strategy_name: str) -> Dict:
        """Calculate performance metrics from trade list"""
        
        if not trades:
            return {
                'strategy': strategy_name,
                'total_trades': 0,
                'message': 'No trades generated'
            }
        
        trades_data = [{
            'entry_idx': t.entry_idx,
            'exit_idx': t.exit_idx,
            'entry_time': t.entry_time,
            'exit_time': t.exit_time,
            'hold_time': t.hold_time,
            'entry_spread': t.entry_spread,
            'exit_spread': t.exit_spread,
            'entry_z_score': t.entry_z_score,
            'exit_z_score': t.exit_z_score,
            'raw_pnl_pct': t.raw_pnl_pct,
            'net_pnl_pct': t.net_pnl_pct,
            'exit_reason': t.exit_reason.value,
            'direction': t.direction,
        } for t in trades]
        
        trades_df = pd.DataFrame(trades_data)
        
        winning_trades = trades_df[trades_df['net_pnl_pct'] > 0]
        losing_trades = trades_df[trades_df['net_pnl_pct'] <= 0]
        
        total_pnl = trades_df['net_pnl_pct'].sum()
        avg_pnl = trades_df['net_pnl_pct'].mean()
        median_pnl = trades_df['net_pnl_pct'].median()
        
        win_rate = len(winning_trades) / len(trades_df) * 100 if len(trades_df) > 0 else 0
        
        avg_win = winning_trades['net_pnl_pct'].mean() if len(winning_trades) > 0 else 0
        avg_loss = losing_trades['net_pnl_pct'].mean() if len(losing_trades) > 0 else 0
        
        profit_factor = (
            abs(winning_trades['net_pnl_pct'].sum() / losing_trades['net_pnl_pct'].sum())
            if len(losing_trades) > 0 and losing_trades['net_pnl_pct'].sum() != 0
            else float('inf') if len(winning_trades) > 0 else 0
        )
        
        avg_hold_time = trades_df['hold_time'].mean()
        
        # Sharpe ratio
        returns_std = trades_df['net_pnl_pct'].std()
        sharpe_ratio = (avg_pnl / returns_std * np.sqrt(252)) if returns_std > 0 else 0
        
        # Max drawdown
        cumulative_pnl = trades_df['net_pnl_pct'].cumsum()
        running_max = cumulative_pnl.expanding().max()
        drawdown = cumulative_pnl - running_max
        max_drawdown = drawdown.min()
        
        # Consecutive wins/losses
        trades_df['is_win'] = trades_df['net_pnl_pct'] > 0
        trades_df['streak'] = (trades_df['is_win'] != trades_df['is_win'].shift()).cumsum()
        max_consecutive_wins = trades_df[trades_df['is_win']].groupby('streak').size().max() if len(winning_trades) > 0 else 0
        max_consecutive_losses = trades_df[~trades_df['is_win']].groupby('streak').size().max() if len(losing_trades) > 0 else 0
        
        return {
            'strategy': strategy_name,
            'total_trades': len(trades_df),
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': win_rate,
            'total_pnl_pct': total_pnl,
            'avg_pnl_pct': avg_pnl,
            'median_pnl_pct': median_pnl,
            'avg_win_pct': avg_win,
            'avg_loss_pct': avg_loss,
            'profit_factor': profit_factor,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown_pct': max_drawdown,
            'avg_hold_time_minutes': avg_hold_time,
            'max_consecutive_wins': max_consecutive_wins,
            'max_consecutive_losses': max_consecutive_losses,
            'trades_df': trades_df,
            'entry_costs_pct': self.total_entry_cost,
            'exit_costs_pct': self.total_exit_cost,
        }
    
    @staticmethod
    def print_comparison(results_list: List[Dict]):
        """Compare multiple strategy results side by side"""
        
        print("\n" + "=" * 120)
        print("📊 STRATEGY COMPARISON")
        print("=" * 120)
        
        # Header
        strategies = [r['strategy'] for r in results_list if r['total_trades'] > 0]
        if not strategies:
            print("⚠️ No strategies generated trades")
            return
        
        print(f"\n{'Metric':<25}", end='')
        for strategy in strategies:
            print(f"{strategy:>20}", end='')
        print()
        print("-" * 120)
        
        # Metrics to compare
        metrics = [
            ('total_trades', 'Total Trades', '.0f'),
            ('win_rate', 'Win Rate %', '.1f'),
            ('total_pnl_pct', 'Total P&L %', '.3f'),
            ('avg_pnl_pct', 'Avg P&L %', '.3f'),
            ('profit_factor', 'Profit Factor', '.2f'),
            ('sharpe_ratio', 'Sharpe Ratio', '.2f'),
            ('max_drawdown_pct', 'Max DD %', '.3f'),
            ('avg_hold_time_minutes', 'Avg Hold (min)', '.1f'),
        ]
        
        for metric_key, metric_name, fmt in metrics:
            print(f"{metric_name:<25}", end='')
            for result in results_list:
                if result['total_trades'] > 0:
                    value = result.get(metric_key, 0)
                    if value == float('inf'):
                        print(f"{'∞':>20}", end='')
                    else:
                        print(f"{value:>20{fmt}}", end='')
            print()
        
        print("=" * 120)
