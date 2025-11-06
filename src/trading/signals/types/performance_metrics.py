"""
Performance Metrics Struct for Strategy Signal Analysis

Type-safe performance metrics for internal position tracking within strategy signals_v2.
Provides comprehensive trading statistics and position analytics.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class PerformanceMetrics:
    """
    Comprehensive performance metrics for strategy signals_v2 with internal position tracking.
    
    Used by BaseStrategySignal.get_performance_metrics() to provide type-safe
    performance data instead of dictionaries.
    """
    
    # Position tracking metrics
    total_positions: int = 0
    open_positions: int = 0
    completed_trades: int = 0
    
    # P&L metrics
    total_pnl_usd: float = 0.0
    total_pnl_pct: float = 0.0
    unrealized_pnl_usd: float = 0.0
    unrealized_pnl_pct: float = 0.0
    realized_pnl_usd: float = 0.0
    realized_pnl_pct: float = 0.0
    
    # Trading performance
    win_rate: float = 0.0
    avg_win_usd: float = 0.0
    avg_loss_usd: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    
    # Position duration metrics
    avg_hold_time_minutes: float = 0.0
    max_hold_time_minutes: float = 0.0
    min_hold_time_minutes: float = 0.0
    
    # Risk metrics
    max_drawdown_usd: float = 0.0
    max_drawdown_pct: float = 0.0
    current_drawdown_usd: float = 0.0
    current_drawdown_pct: float = 0.0
    
    # Strategy-specific metrics
    strategy_type: str = ""
    signal_count: int = 0
    last_signal_time: Optional[datetime] = None


    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for backward compatibility.
        
        Returns:
            Dictionary representation of performance metrics
        """
        result = {}
        for field, value in self.__dict__.items():
            if isinstance(value, datetime):
                result[field] = value.isoformat() if value else None
            else:
                result[field] = value
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PerformanceMetrics':
        """
        Create PerformanceMetrics from dictionary.
        
        Args:
            data: Dictionary with performance metrics data
            
        Returns:
            PerformanceMetrics instance
        """
        # Handle datetime fields
        datetime_fields = ['creation_time', 'last_update_time', 'last_signal_time']
        for field in datetime_fields:
            if field in data and isinstance(data[field], str):
                try:
                    data[field] = datetime.fromisoformat(data[field])
                except (ValueError, TypeError):
                    data[field] = None
        
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
    
    def update_pnl_metrics(self, trades: List[Any]) -> None:
        """
        Update P&L metrics from completed trades.
        
        Args:
            trades: List of Trade objects or dictionaries
        """
        if not trades:
            return
        
        total_pnl = 0.0
        winning_pnl = 0.0
        losing_pnl = 0.0
        winning_count = 0
        losing_count = 0
        
        for trade in trades:
            # Handle both Trade objects and dictionaries
            if hasattr(trade, 'pnl_usd'):
                pnl = trade.pnl_usd
            elif isinstance(trade, dict):
                pnl = trade.get('pnl_usd', 0.0)
            else:
                continue
            
            total_pnl += pnl
            
            if pnl > 0:
                winning_pnl += pnl
                winning_count += 1
            elif pnl < 0:
                losing_pnl += abs(pnl)
                losing_count += 1
        
        self.realized_pnl_usd = total_pnl
        self.winning_trades = winning_count
        self.losing_trades = losing_count
        self.completed_trades = len(trades)
        
        # Calculate derived metrics
        if self.completed_trades > 0:
            self.win_rate = (winning_count / self.completed_trades) * 100
        
        if winning_count > 0:
            self.avg_win_usd = winning_pnl / winning_count
        
        if losing_count > 0:
            self.avg_loss_usd = losing_pnl / losing_count
        
        if losing_pnl > 0:
            self.profit_factor = winning_pnl / losing_pnl
        
        self.last_update_time = datetime.now()
    
    def update_position_metrics(self, open_positions: List[Any]) -> None:
        """
        Update position metrics from open positions.
        
        Args:
            open_positions: List of Position objects or dictionaries
        """
        self.open_positions = len(open_positions)
        
        unrealized_total = 0.0
        hold_times = []
        
        for position in open_positions:
            # Handle both Position objects and dictionaries
            if hasattr(position, 'unrealized_pnl_usd'):
                unrealized_total += position.unrealized_pnl_usd
            elif isinstance(position, dict):
                unrealized_total += position.get('unrealized_pnl_usd', 0.0)
            
            if hasattr(position, 'hold_time_minutes'):
                hold_times.append(position.hold_time_minutes)
            elif isinstance(position, dict) and 'hold_time_minutes' in position:
                hold_times.append(position['hold_time_minutes'])
        
        self.unrealized_pnl_usd = unrealized_total
        
        if hold_times:
            self.avg_hold_time_minutes = sum(hold_times) / len(hold_times)
            self.max_hold_time_minutes = max(hold_times)
            self.min_hold_time_minutes = min(hold_times)
        
        self.last_update_time = datetime.now()