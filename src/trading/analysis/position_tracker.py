"""
Enhanced Position Tracking System

Provides accurate position and trade tracking for arbitrage strategies with
complete entry/exit price recording, P&L calculation, and performance metrics.

Key Features:
- Real trade tracking with entry/exit points
- Accurate P&L calculation based on actual prices
- Position state management for live trading
- Vectorized operations for backtesting performance
- Support for all arbitrage strategy types
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any
from collections import deque

import msgspec

from trading.analysis.signal_types import Signal


class Trade(msgspec.Struct):
    """Complete trade record with all metrics."""
    entry_time: datetime
    exit_time: datetime
    strategy_type: str
    # Entry/exit prices for both legs of arbitrage
    entry_sell_price: float  # Price we sell at (bid price)
    entry_buy_price: float   # Price we buy at (ask price)
    exit_sell_price: float   # Price we sell at (bid price)
    exit_buy_price: float    # Price we buy at (ask price)
    quantity: float
    pnl_usd: float
    pnl_pct: float
    hold_time_minutes: float
    entry_spread: float
    exit_spread: float
    fees_usd: float
    
    # Additional context
    entry_signal_strength: Optional[float] = None
    exit_reason: Optional[str] = None  # 'signal', 'stop_loss', 'take_profit'


class Position(msgspec.Struct):
    """Current position state."""
    entry_time: datetime
    strategy_type: str
    # Entry prices for both legs of arbitrage
    entry_sell_price: float  # Price we sell at (bid price)
    entry_buy_price: float   # Price we buy at (ask price)
    entry_spread: float
    quantity: float
    unrealized_pnl_usd: float
    unrealized_pnl_pct: float
    hold_time_minutes: float
    
    # Risk management
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None


class PerformanceMetrics(msgspec.Struct):
    """Comprehensive performance metrics."""
    total_trades: int
    winning_trades: int
    losing_trades: int
    total_pnl_usd: float
    total_pnl_pct: float
    win_rate_pct: float
    avg_pnl_per_trade: float
    avg_winning_trade: float
    avg_losing_trade: float
    avg_hold_time_minutes: float
    max_consecutive_wins: int
    max_consecutive_losses: int
    max_drawdown_pct: float
    sharpe_ratio: float
    profit_factor: float  # Total profits / Total losses


class PositionTracker:
    """
    Accurate position and trade tracking for arbitrage strategies.
    
    Supports both vectorized backtesting and real-time position management
    with precise entry/exit price recording and P&L calculation.
    """
    
    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.positions: List[Position] = []
        self.completed_trades: List[Trade] = []
        self.current_position: Optional[Position] = None
        
        # Performance tracking
        self.equity_curve: deque = deque(maxlen=10000)  # Rolling equity history
        self.drawdown_curve: deque = deque(maxlen=10000)
        
        # Strategy-specific configuration
        # Arbitrage strategy configurations based on arbitrage_analyzer.py patterns
        self.strategy_configs = {
            'reverse_delta_neutral': {
                # MEXC vs Gate.io Futures arbitrage (mexc_gateio_futures spread)
                'sell_exchange': 'MEXC_SPOT',
                'buy_exchange': 'GATEIO_FUTURES',
                'type': 'mexc_gateio_sell_buy'
            },
            'inventory_spot': {
                # Gate.io Spot vs Gate.io Futures arbitrage (spot_futures spread)
                'sell_exchange': 'GATEIO_SPOT', 
                'buy_exchange': 'GATEIO_FUTURES',
                'type': 'spot_futures_long_short'
            },
            'volatility_harvesting': {
                # Gate.io vs MEXC cross-exchange arbitrage
                'sell_exchange': 'GATEIO_SPOT',
                'buy_exchange': 'MEXC_SPOT',
                'type': 'gateio_mexc_sell_buy'
            }
        }
    
    def track_positions_vectorized(self, df: pd.DataFrame, strategy_config: dict) -> Tuple[List[Position], List[Trade]]:
        """
        Track positions using vectorized DataFrame operations.
        
        Args:
            df: DataFrame with market data and signals
            strategy_config: Strategy configuration with type and parameters
            
        Returns:
            Tuple of (positions_history, completed_trades)
        """
        if df.empty or 'signal' not in df.columns:
            return [], []
        
        strategy_type = strategy_config['type']
        params = strategy_config['params']
        
        positions_history = []
        trades = []
        current_position = None
        
        # Vectorized signal changes for efficiency
        signal_changes = df['signal'].ne(df['signal'].shift())
        signal_points = df[signal_changes].copy()
        
        for idx, row in signal_points.iterrows():
            current_time = idx
            
            if row['signal'] == Signal.ENTER.value and current_position is None:
                # Open new position
                entry_price = self._get_entry_price(row, strategy_type)
                entry_spread = self._get_current_spread(row, strategy_type)
                
                current_position = Position(
                    entry_time=current_time,
                    strategy_type=strategy_type,
                    entry_sell_price=entry_price,  # Sell price from entry
                    entry_buy_price=0.0,  # Will be set when we exit
                    entry_spread=entry_spread,
                    quantity=params.get('position_size_usd', 1000.0),
                    unrealized_pnl_usd=0.0,
                    unrealized_pnl_pct=0.0,
                    hold_time_minutes=0.0
                )
                positions_history.append(current_position)
                
            elif row['signal'] == Signal.EXIT.value and current_position is not None:
                # Close current position
                exit_price = self._get_exit_price(row, strategy_type)
                exit_spread = self._get_current_spread(row, strategy_type)
                hold_time = (current_time - current_position.entry_time).total_seconds() / 60
                
                # Calculate actual P&L using arbitrage logic (sell price - buy price)
                pnl_pct = self._calculate_pnl_percentage(
                    current_position.entry_sell_price,  # entry_sell_price
                    exit_price  # exit_buy_price
                )
                pnl_usd = current_position.quantity * pnl_pct / 100
                fees = self._calculate_fees(current_position.quantity, strategy_type)
                net_pnl_usd = pnl_usd - fees
                
                trade = Trade(
                    entry_time=current_position.entry_time,
                    exit_time=current_time,
                    strategy_type=strategy_type,
                    entry_sell_price=current_position.entry_sell_price,
                    entry_buy_price=0.0,  # For arbitrage, we track the spread, not individual buy prices
                    exit_sell_price=0.0,  # For arbitrage, we track the spread, not individual sell prices  
                    exit_buy_price=exit_price,
                    quantity=current_position.quantity,
                    pnl_usd=net_pnl_usd,
                    pnl_pct=pnl_pct,
                    hold_time_minutes=hold_time,
                    entry_spread=current_position.entry_spread,
                    exit_spread=exit_spread,
                    fees_usd=fees,
                    entry_signal_strength=abs(current_position.entry_spread),
                    exit_reason='signal'
                )
                trades.append(trade)
                
                # Update capital tracking
                self.current_capital += net_pnl_usd
                current_position = None
        
        return positions_history, trades
    
    def update_position_realtime(self, signal: Signal, market_data: dict, strategy_config: dict) -> Optional[Trade]:
        """
        Update position state in real-time trading.
        
        Args:
            signal: Current signal (ENTER, EXIT, HOLD)
            market_data: Current market data
            strategy_config: Strategy configuration
            
        Returns:
            Completed trade if position was closed, None otherwise
        """
        strategy_type = strategy_config['type']
        params = strategy_config['params']
        current_time = datetime.now(timezone.utc)
        
        if signal == Signal.ENTER and self.current_position is None:
            # Open new position
            entry_price = self._get_entry_price_from_market_data(market_data, strategy_type)
            entry_spread = self._get_spread_from_market_data(market_data, strategy_type)
            
            self.current_position = Position(
                entry_time=current_time,
                strategy_type=strategy_type,
                entry_sell_price=entry_price,  # Sell price from entry
                entry_buy_price=0.0,  # Will be set when we exit
                entry_spread=entry_spread,
                quantity=params.get('position_size_usd', 1000.0),
                unrealized_pnl_usd=0.0,
                unrealized_pnl_pct=0.0,
                hold_time_minutes=0.0
            )
            self.positions.append(self.current_position)
            return None
            
        elif signal == Signal.EXIT and self.current_position is not None:
            # Close current position
            exit_price = self._get_exit_price_from_market_data(market_data, strategy_type)
            exit_spread = self._get_spread_from_market_data(market_data, strategy_type)
            hold_time = (current_time - self.current_position.entry_time).total_seconds() / 60
            
            # Calculate P&L using arbitrage logic (sell price - buy price)
            pnl_pct = self._calculate_pnl_percentage(
                self.current_position.entry_sell_price,  # entry_sell_price
                exit_price  # exit_buy_price
            )
            pnl_usd = self.current_position.quantity * pnl_pct / 100
            fees = self._calculate_fees(self.current_position.quantity, strategy_type)
            net_pnl_usd = pnl_usd - fees
            
            trade = Trade(
                entry_time=self.current_position.entry_time,
                exit_time=current_time,
                strategy_type=strategy_type,
                entry_sell_price=self.current_position.entry_sell_price,
                entry_buy_price=0.0,  # For arbitrage, we track the spread, not individual buy prices
                exit_sell_price=0.0,  # For arbitrage, we track the spread, not individual sell prices
                exit_buy_price=exit_price,
                quantity=self.current_position.quantity,
                pnl_usd=net_pnl_usd,
                pnl_pct=pnl_pct,
                hold_time_minutes=hold_time,
                entry_spread=self.current_position.entry_spread,
                exit_spread=exit_spread,
                fees_usd=fees,
                entry_signal_strength=abs(self.current_position.entry_spread),
                exit_reason='signal'
            )
            
            self.completed_trades.append(trade)
            self.current_capital += net_pnl_usd
            self._update_equity_curve()
            self.current_position = None
            
            return trade
        
        # Update unrealized P&L for current position
        elif self.current_position is not None:
            self._update_unrealized_pnl(market_data, strategy_type)
        
        return None
    
    def _get_entry_price(self, row: pd.Series, strategy_type: str) -> float:
        """Get actual entry price for arbitrage based on sell price (following arbitrage_analyzer.py pattern)."""
        config = self.strategy_configs[strategy_type]
        sell_exchange = config['sell_exchange']
        
        # Entry price is the sell price (what we receive when selling)
        if sell_exchange == 'MEXC_SPOT':
            return row.get('MEXC_SPOT_bid_price', row.get('MEXC_bid_price', 0))
        elif sell_exchange == 'GATEIO_SPOT':
            return row.get('GATEIO_SPOT_bid_price', row.get('GATEIO_bid_price', 0))
        elif sell_exchange == 'GATEIO_FUTURES':
            return row.get('GATEIO_FUTURES_bid_price', 0)
        
        return 0
    
    def _get_exit_price(self, row: pd.Series, strategy_type: str) -> float:
        """Get actual exit price for arbitrage based on buy price (following arbitrage_analyzer.py pattern)."""
        config = self.strategy_configs[strategy_type]
        buy_exchange = config['buy_exchange']
        
        # Exit price is the buy price (what we pay when buying back to close)
        if buy_exchange == 'MEXC_SPOT':
            return row.get('MEXC_SPOT_ask_price', row.get('MEXC_ask_price', 0))
        elif buy_exchange == 'GATEIO_SPOT':
            return row.get('GATEIO_SPOT_ask_price', row.get('GATEIO_ask_price', 0))
        elif buy_exchange == 'GATEIO_FUTURES':
            return row.get('GATEIO_FUTURES_ask_price', 0)
        
        return 0
    
    def _get_current_spread(self, row: pd.Series, strategy_type: str) -> float:
        """Calculate current arbitrage spread exactly like arbitrage_analyzer.py."""
        config = self.strategy_configs[strategy_type]
        arb_type = config['type']
        
        if arb_type == 'mexc_gateio_sell_buy':
            # MEXC bid - Gate.io futures ask (sell MEXC, buy Gate.io futures)
            mexc_bid = row.get('MEXC_SPOT_bid_price', row.get('MEXC_bid_price', 0))
            futures_ask = row.get('GATEIO_FUTURES_ask_price', 0)
            if mexc_bid > 0 and futures_ask > 0:
                return mexc_bid - futures_ask
                
        elif arb_type == 'spot_futures_long_short':
            # Gate.io spot bid - Gate.io futures ask (long spot, short futures)
            spot_bid = row.get('GATEIO_SPOT_bid_price', row.get('GATEIO_bid_price', 0))
            futures_ask = row.get('GATEIO_FUTURES_ask_price', 0)
            if spot_bid > 0 and futures_ask > 0:
                return spot_bid - futures_ask
                
        elif arb_type == 'gateio_mexc_sell_buy':
            # Gate.io bid - MEXC ask (sell Gate.io, buy MEXC)
            gateio_bid = row.get('GATEIO_SPOT_bid_price', row.get('GATEIO_bid_price', 0))
            mexc_ask = row.get('MEXC_SPOT_ask_price', row.get('MEXC_ask_price', 0))
            if gateio_bid > 0 and mexc_ask > 0:
                return gateio_bid - mexc_ask
        
        return 0.0
    
    def _get_mid_price(self, row: pd.Series, exchange: str) -> float:
        """Get mid price for exchange."""
        if exchange == 'MEXC':
            ask = row.get('MEXC_SPOT_ask_price', row.get('MEXC_ask_price', 0))
            bid = row.get('MEXC_SPOT_bid_price', row.get('MEXC_bid_price', 0))
        elif exchange == 'GATEIO':
            ask = row.get('GATEIO_SPOT_ask_price', row.get('GATEIO_ask_price', 0))
            bid = row.get('GATEIO_SPOT_bid_price', row.get('GATEIO_bid_price', 0))
        else:
            return 0
        
        return (ask + bid) / 2 if ask > 0 and bid > 0 else 0
    
    def _get_arbitrage_type(self, strategy_type: str) -> str:
        """Get arbitrage type for the strategy."""
        return self.strategy_configs[strategy_type]['type']
    
    def _calculate_pnl_percentage(self, entry_sell_price: float, exit_buy_price: float) -> float:
        """Calculate arbitrage P&L percentage using execution-based calculation (sell price as denominator)."""
        if entry_sell_price <= 0:
            return 0.0
            
        # Arbitrage P&L = (sell_price - buy_price) / sell_price * 100
        # This represents the profit margin on the arbitrage trade
        return ((entry_sell_price - exit_buy_price) / entry_sell_price) * 100
    
    def _calculate_fees(self, quantity: float, strategy_type: str) -> float:
        """Calculate trading fees based on strategy and exchanges used."""
        # Standard exchange fees
        mexc_fee_rate = 0.001  # 0.1%
        gateio_spot_fee_rate = 0.0015  # 0.15%
        gateio_futures_fee_rate = 0.0005  # 0.05%
        
        if strategy_type == 'reverse_delta_neutral':
            # MEXC spot + Gate.io futures
            return quantity * (mexc_fee_rate + gateio_futures_fee_rate)
        elif strategy_type == 'inventory_spot':
            # Gate.io spot + Gate.io futures
            return quantity * (gateio_spot_fee_rate + gateio_futures_fee_rate)
        elif strategy_type == 'volatility_harvesting':
            # Multiple exchanges
            return quantity * (mexc_fee_rate + gateio_spot_fee_rate)
        
        return quantity * 0.002  # Default 0.2% total fees
    
    def _calculate_stop_loss(self, entry_sell_price: float, strategy_type: str, params: dict) -> Optional[float]:
        """Calculate stop loss for arbitrage (exit when spread becomes unfavorable)."""
        stop_loss_pct = params.get('stop_loss_pct')
        if not stop_loss_pct:
            return None
            
        # For arbitrage, stop loss means the buy price goes too high
        # Stop loss = entry_sell_price * (1 + stop_loss_pct/100)
        return entry_sell_price * (1 + stop_loss_pct / 100)
    
    def _calculate_take_profit(self, entry_sell_price: float, strategy_type: str, params: dict) -> Optional[float]:
        """Calculate take profit for arbitrage (exit when favorable spread achieved)."""
        take_profit_pct = params.get('take_profit_pct')
        if not take_profit_pct:
            return None
            
        # For arbitrage, take profit means the buy price goes lower
        # Take profit = entry_sell_price * (1 - take_profit_pct/100)
        return entry_sell_price * (1 - take_profit_pct / 100)
    
    def _get_entry_price_from_market_data(self, market_data: dict, strategy_type: str) -> float:
        """Get entry sell price from real-time market data (following arbitrage_analyzer.py pattern)."""
        config = self.strategy_configs[strategy_type]
        sell_exchange = config['sell_exchange']
        
        # Entry price is the sell price (what we receive when selling)
        if sell_exchange == 'MEXC_SPOT' and 'MEXC' in market_data.get('spot_exchanges', {}):
            return market_data['spot_exchanges']['MEXC']['bid_price']
        elif sell_exchange == 'GATEIO_SPOT' and 'GATEIO' in market_data.get('spot_exchanges', {}):
            return market_data['spot_exchanges']['GATEIO']['bid_price']
        elif sell_exchange == 'GATEIO_FUTURES' and 'GATEIO' in market_data.get('futures_exchanges', {}):
            return market_data['futures_exchanges']['GATEIO']['bid_price']
        
        return 0
    
    def _get_exit_price_from_market_data(self, market_data: dict, strategy_type: str) -> float:
        """Get exit buy price from real-time market data (following arbitrage_analyzer.py pattern)."""
        config = self.strategy_configs[strategy_type]
        buy_exchange = config['buy_exchange']
        
        # Exit price is the buy price (what we pay when buying back to close)
        if buy_exchange == 'MEXC_SPOT' and 'MEXC' in market_data.get('spot_exchanges', {}):
            return market_data['spot_exchanges']['MEXC']['ask_price']
        elif buy_exchange == 'GATEIO_SPOT' and 'GATEIO' in market_data.get('spot_exchanges', {}):
            return market_data['spot_exchanges']['GATEIO']['ask_price']
        elif buy_exchange == 'GATEIO_FUTURES' and 'GATEIO' in market_data.get('futures_exchanges', {}):
            return market_data['futures_exchanges']['GATEIO']['ask_price']
        
        return 0
    
    def _get_spread_from_market_data(self, market_data: dict, strategy_type: str) -> float:
        """Calculate arbitrage spread from real-time market data (following arbitrage_analyzer.py pattern)."""
        config = self.strategy_configs[strategy_type]
        arb_type = config['type']
        
        spot_exchanges = market_data.get('spot_exchanges', {})
        futures_exchanges = market_data.get('futures_exchanges', {})
        
        if arb_type == 'mexc_gateio_sell_buy':
            # MEXC bid - Gate.io futures ask (sell MEXC, buy Gate.io futures)
            if 'MEXC' in spot_exchanges and 'GATEIO' in futures_exchanges:
                mexc_bid = spot_exchanges['MEXC']['bid_price']
                futures_ask = futures_exchanges['GATEIO']['ask_price']
                if mexc_bid > 0 and futures_ask > 0:
                    return mexc_bid - futures_ask
                    
        elif arb_type == 'spot_futures_long_short':
            # Gate.io spot bid - Gate.io futures ask (long spot, short futures)
            if 'GATEIO' in spot_exchanges and 'GATEIO' in futures_exchanges:
                spot_bid = spot_exchanges['GATEIO']['bid_price']
                futures_ask = futures_exchanges['GATEIO']['ask_price']
                if spot_bid > 0 and futures_ask > 0:
                    return spot_bid - futures_ask
                    
        elif arb_type == 'gateio_mexc_sell_buy':
            # Gate.io bid - MEXC ask (sell Gate.io, buy MEXC)
            if 'GATEIO' in spot_exchanges and 'MEXC' in spot_exchanges:
                gateio_bid = spot_exchanges['GATEIO']['bid_price']
                mexc_ask = spot_exchanges['MEXC']['ask_price']
                if gateio_bid > 0 and mexc_ask > 0:
                    return gateio_bid - mexc_ask
        
        return 0.0
    
    def _update_unrealized_pnl(self, market_data: dict, strategy_type: str):
        """Update unrealized P&L for current position."""
        if not self.current_position:
            return
            
        current_price = self._get_exit_price_from_market_data(market_data, strategy_type)
        if current_price <= 0:
            return
            
        pnl_pct = self._calculate_pnl_percentage(
            self.current_position.entry_sell_price,  # entry_sell_price
            current_price  # current_buy_price
        )
        
        self.current_position.unrealized_pnl_pct = pnl_pct
        self.current_position.unrealized_pnl_usd = self.current_position.quantity * pnl_pct / 100
        
        # Update hold time
        current_time = datetime.now(timezone.utc)
        self.current_position.hold_time_minutes = (
            (current_time - self.current_position.entry_time).total_seconds() / 60
        )
    
    def _update_equity_curve(self):
        """Update equity curve for drawdown calculation."""
        self.equity_curve.append(self.current_capital)
        
        # Calculate drawdown
        if len(self.equity_curve) > 1:
            peak = max(self.equity_curve)
            current_drawdown = (peak - self.current_capital) / peak * 100
            self.drawdown_curve.append(current_drawdown)
    
    def calculate_performance_metrics(self) -> PerformanceMetrics:
        """Calculate comprehensive performance metrics from completed trades."""
        if not self.completed_trades:
            return PerformanceMetrics(
                total_trades=0, winning_trades=0, losing_trades=0,
                total_pnl_usd=0, total_pnl_pct=0, win_rate_pct=0,
                avg_pnl_per_trade=0, avg_winning_trade=0, avg_losing_trade=0,
                avg_hold_time_minutes=0, max_consecutive_wins=0, max_consecutive_losses=0,
                max_drawdown_pct=0, sharpe_ratio=0, profit_factor=0
            )
        
        # Basic metrics
        total_trades = len(self.completed_trades)
        winning_trades = len([t for t in self.completed_trades if t.pnl_usd > 0])
        losing_trades = total_trades - winning_trades
        
        total_pnl_usd = sum(t.pnl_usd for t in self.completed_trades)
        total_pnl_pct = sum(t.pnl_pct for t in self.completed_trades)
        win_rate_pct = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        avg_pnl_per_trade = total_pnl_usd / total_trades
        
        winning_pnls = [t.pnl_usd for t in self.completed_trades if t.pnl_usd > 0]
        losing_pnls = [t.pnl_usd for t in self.completed_trades if t.pnl_usd <= 0]
        
        avg_winning_trade = np.mean(winning_pnls) if winning_pnls else 0
        avg_losing_trade = np.mean(losing_pnls) if losing_pnls else 0
        
        avg_hold_time_minutes = np.mean([t.hold_time_minutes for t in self.completed_trades])
        
        # Consecutive wins/losses
        max_consecutive_wins = max_consecutive_losses = 0
        current_consecutive_wins = current_consecutive_losses = 0
        
        for trade in self.completed_trades:
            if trade.pnl_usd > 0:
                current_consecutive_wins += 1
                current_consecutive_losses = 0
                max_consecutive_wins = max(max_consecutive_wins, current_consecutive_wins)
            else:
                current_consecutive_losses += 1
                current_consecutive_wins = 0
                max_consecutive_losses = max(max_consecutive_losses, current_consecutive_losses)
        
        # Drawdown
        max_drawdown_pct = max(self.drawdown_curve) if self.drawdown_curve else 0
        
        # Sharpe ratio (simplified)
        pnl_returns = [t.pnl_pct for t in self.completed_trades]
        sharpe_ratio = (
            (np.mean(pnl_returns) / np.std(pnl_returns)) if len(pnl_returns) > 1 and np.std(pnl_returns) > 0 else 0
        )
        
        # Profit factor
        total_profits = sum(winning_pnls) if winning_pnls else 0
        total_losses = abs(sum(losing_pnls)) if losing_pnls else 0
        profit_factor = (total_profits / total_losses) if total_losses > 0 else float('inf') if total_profits > 0 else 0
        
        return PerformanceMetrics(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            total_pnl_usd=total_pnl_usd,
            total_pnl_pct=total_pnl_pct,
            win_rate_pct=win_rate_pct,
            avg_pnl_per_trade=avg_pnl_per_trade,
            avg_winning_trade=avg_winning_trade,
            avg_losing_trade=avg_losing_trade,
            avg_hold_time_minutes=avg_hold_time_minutes,
            max_consecutive_wins=max_consecutive_wins,
            max_consecutive_losses=max_consecutive_losses,
            max_drawdown_pct=max_drawdown_pct,
            sharpe_ratio=sharpe_ratio,
            profit_factor=profit_factor
        )
    
    def get_current_metrics(self) -> dict:
        """Get current performance metrics for real-time monitoring."""
        metrics = self.calculate_performance_metrics()
        
        return {
            'total_trades': metrics.total_trades,
            'total_pnl_usd': metrics.total_pnl_usd,
            'win_rate_pct': metrics.win_rate_pct,
            'current_position': self.current_position,
            'current_capital': self.current_capital,
            'total_return_pct': ((self.current_capital - self.initial_capital) / self.initial_capital * 100),
            'max_drawdown_pct': metrics.max_drawdown_pct,
            'profit_factor': metrics.profit_factor
        }
    
    def reset(self):
        """Reset tracker state for new backtesting session."""
        self.current_capital = self.initial_capital
        self.positions.clear()
        self.completed_trades.clear()
        self.current_position = None
        self.equity_curve.clear()
        self.drawdown_curve.clear()