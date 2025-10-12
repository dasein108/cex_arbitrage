"""
Simplified Arbitrage Context for Delta-Neutral Strategy

This module provides a simplified context class for tracking the state
of the delta arbitrage strategy with dynamic parameter optimization.
"""

import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import sys
import os

from exchanges.structs import Symbol
from ..optimization.parameter_optimizer import OptimizationResult


@dataclass
class SimpleDeltaArbitrageContext:
    """
    Simplified context for delta arbitrage strategy.
    
    This context tracks only essential state information needed for
    the simplified PoC strategy, avoiding the complexity of the full
    MexcGateioFuturesStrategy context.
    """
    
    # Core strategy identification
    symbol: Symbol
    strategy_name: str = "SimpleDeltaArbitrage"
    
    # Current dynamic parameters (updated by optimizer)
    current_entry_threshold_pct: float = 0.5   # Current entry threshold
    current_exit_threshold_pct: float = 0.1    # Current exit threshold
    parameter_confidence_score: float = 0.5    # Confidence in current parameters
    
    # Simple position tracking
    spot_position: float = 0.0          # Current spot position (positive = long)
    futures_position: float = 0.0       # Current futures position (positive = long)
    spot_avg_price: float = 0.0         # Average spot position price
    futures_avg_price: float = 0.0      # Average futures position price
    
    # Delta tracking (for delta-neutral strategy)
    current_delta: float = 0.0          # Current delta exposure
    target_delta: float = 0.0           # Target delta (should be 0 for neutral)
    delta_tolerance: float = 0.05       # Acceptable delta deviation
    
    # Parameter update tracking
    last_parameter_update: float = 0.0          # Timestamp of last parameter update
    parameter_update_interval: int = 300        # Update interval in seconds (5 minutes)
    total_parameter_updates: int = 0            # Count of parameter updates
    
    # Trade performance tracking
    total_trades: int = 0               # Total number of trades executed
    winning_trades: int = 0             # Number of profitable trades
    total_pnl: float = 0.0              # Total realized P&L
    total_fees_paid: float = 0.0        # Total fees paid
    
    # Position timing
    position_entry_time: Optional[float] = None    # When current position was opened
    max_position_hold_time: float = 21600.0        # Max hold time in seconds (6 hours)
    
    # Risk management state
    emergency_stop_triggered: bool = False      # Emergency stop status
    max_drawdown_reached: float = 0.0          # Maximum drawdown experienced
    consecutive_losses: int = 0                # Count of consecutive losing trades
    
    # Strategy state
    is_active: bool = False             # Whether strategy is actively trading
    last_opportunity_check: float = 0.0    # Last time we checked for opportunities
    opportunity_check_interval: float = 0.1    # Check every 100ms
    
    # Optimization tracking
    last_optimization_result: Optional[OptimizationResult] = None
    optimization_history: list = field(default_factory=list)
    
    def update_parameters(self, optimization_result: OptimizationResult) -> None:
        """
        Update strategy parameters from optimization result.
        
        Args:
            optimization_result: Result from parameter optimizer
        """
        self.current_entry_threshold_pct = optimization_result.entry_threshold_pct
        self.current_exit_threshold_pct = optimization_result.exit_threshold_pct
        self.parameter_confidence_score = optimization_result.confidence_score
        self.last_parameter_update = time.time()
        self.total_parameter_updates += 1
        self.last_optimization_result = optimization_result
        
        # Keep optimization history (limit to last 50 results to manage memory)
        self.optimization_history.append(optimization_result)
        if len(self.optimization_history) > 50:
            self.optimization_history.pop(0)
    
    def should_update_parameters(self) -> bool:
        """
        Check if parameters should be updated based on time interval.
        
        Returns:
            True if parameters need updating
        """
        if self.last_parameter_update == 0.0:
            return True  # First update
        
        elapsed = time.time() - self.last_parameter_update
        return elapsed >= self.parameter_update_interval
    
    def update_positions(self, 
                        spot_position: float, 
                        futures_position: float,
                        spot_price: float = 0.0,
                        futures_price: float = 0.0) -> None:
        """
        Update position tracking with new position sizes.
        
        Args:
            spot_position: New spot position size
            futures_position: New futures position size
            spot_price: Current spot price (for average price calculation)
            futures_price: Current futures price (for average price calculation)
        """
        # Update positions
        old_spot = self.spot_position
        old_futures = self.futures_position
        
        self.spot_position = spot_position
        self.futures_position = futures_position
        
        # Update average prices if positions changed
        if spot_position != old_spot and spot_price > 0:
            if self.spot_position == 0:
                self.spot_avg_price = 0.0
            elif old_spot == 0:
                self.spot_avg_price = spot_price
            else:
                # Weighted average for partial fills/additions
                total_position = abs(self.spot_position)
                position_change = abs(spot_position - old_spot)
                if total_position > 0:
                    weight_old = abs(old_spot) / total_position
                    weight_new = position_change / total_position
                    self.spot_avg_price = (self.spot_avg_price * weight_old + 
                                         spot_price * weight_new)
        
        if futures_position != old_futures and futures_price > 0:
            if self.futures_position == 0:
                self.futures_avg_price = 0.0
            elif old_futures == 0:
                self.futures_avg_price = futures_price
            else:
                # Weighted average for partial fills/additions
                total_position = abs(self.futures_position)
                position_change = abs(futures_position - old_futures)
                if total_position > 0:
                    weight_old = abs(old_futures) / total_position
                    weight_new = position_change / total_position
                    self.futures_avg_price = (self.futures_avg_price * weight_old + 
                                            futures_price * weight_new)
        
        # Update delta calculation
        self.current_delta = self.spot_position - self.futures_position
        
        # Track position entry time
        if old_spot == 0 and old_futures == 0 and (spot_position != 0 or futures_position != 0):
            self.position_entry_time = time.time()
        elif spot_position == 0 and futures_position == 0:
            self.position_entry_time = None
    
    def record_trade_result(self, pnl: float, fees: float, is_winning: bool) -> None:
        """
        Record the result of a completed trade.
        
        Args:
            pnl: Realized P&L from the trade
            fees: Fees paid for the trade
            is_winning: Whether the trade was profitable
        """
        self.total_trades += 1
        self.total_pnl += pnl
        self.total_fees_paid += fees
        
        if is_winning:
            self.winning_trades += 1
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1
            
        # Update max drawdown
        if pnl < 0:
            current_drawdown = abs(pnl)
            if current_drawdown > self.max_drawdown_reached:
                self.max_drawdown_reached = current_drawdown
    
    def is_position_open(self) -> bool:
        """Check if any position is currently open."""
        return self.spot_position != 0.0 or self.futures_position != 0.0
    
    def get_position_hold_time(self) -> float:
        """Get current position hold time in seconds."""
        if self.position_entry_time is None:
            return 0.0
        return time.time() - self.position_entry_time
    
    def should_close_position_timeout(self) -> bool:
        """Check if position should be closed due to time limit."""
        if not self.is_position_open():
            return False
        return self.get_position_hold_time() >= self.max_position_hold_time
    
    def is_delta_neutral(self) -> bool:
        """Check if current delta is within tolerance."""
        return abs(self.current_delta) <= self.delta_tolerance
    
    def get_win_rate(self) -> float:
        """Calculate current win rate."""
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades
    
    def get_average_pnl(self) -> float:
        """Calculate average P&L per trade."""
        if self.total_trades == 0:
            return 0.0
        return self.total_pnl / self.total_trades
    
    def get_net_pnl(self) -> float:
        """Get net P&L after fees."""
        return self.total_pnl - self.total_fees_paid
    
    def should_check_opportunity(self) -> bool:
        """Check if it's time to look for new opportunities."""
        elapsed = time.time() - self.last_opportunity_check
        return elapsed >= self.opportunity_check_interval
    
    def mark_opportunity_checked(self) -> None:
        """Mark that we just checked for opportunities."""
        self.last_opportunity_check = time.time()
    
    def get_strategy_summary(self) -> Dict[str, Any]:
        """Get comprehensive strategy state summary."""
        return {
            'symbol': str(self.symbol),
            'strategy_name': self.strategy_name,
            'is_active': self.is_active,
            
            # Current parameters
            'parameters': {
                'entry_threshold_pct': self.current_entry_threshold_pct,
                'exit_threshold_pct': self.current_exit_threshold_pct,
                'confidence_score': self.parameter_confidence_score,
                'last_update': self.last_parameter_update,
                'total_updates': self.total_parameter_updates,
            },
            
            # Positions
            'positions': {
                'spot_position': self.spot_position,
                'futures_position': self.futures_position,
                'spot_avg_price': self.spot_avg_price,
                'futures_avg_price': self.futures_avg_price,
                'current_delta': self.current_delta,
                'is_delta_neutral': self.is_delta_neutral(),
                'position_hold_time_minutes': self.get_position_hold_time() / 60,
            },
            
            # Performance
            'performance': {
                'total_trades': self.total_trades,
                'winning_trades': self.winning_trades,
                'win_rate': self.get_win_rate(),
                'total_pnl': self.total_pnl,
                'total_fees': self.total_fees_paid,
                'net_pnl': self.get_net_pnl(),
                'average_pnl': self.get_average_pnl(),
                'max_drawdown': self.max_drawdown_reached,
                'consecutive_losses': self.consecutive_losses,
            },
            
            # Risk management
            'risk': {
                'emergency_stop_triggered': self.emergency_stop_triggered,
                'should_close_timeout': self.should_close_position_timeout(),
                'should_update_parameters': self.should_update_parameters(),
            }
        }
    
    def reset_positions(self) -> None:
        """Reset all position tracking (for emergency situations)."""
        self.spot_position = 0.0
        self.futures_position = 0.0
        self.spot_avg_price = 0.0
        self.futures_avg_price = 0.0
        self.current_delta = 0.0
        self.position_entry_time = None
    
    def trigger_emergency_stop(self, reason: str = "Unknown") -> None:
        """Trigger emergency stop and log reason."""
        self.emergency_stop_triggered = True
        self.is_active = False
        print(f"🚨 EMERGENCY STOP TRIGGERED: {reason}")
        
    def clear_emergency_stop(self) -> None:
        """Clear emergency stop (manual intervention required)."""
        self.emergency_stop_triggered = False
        print("✅ Emergency stop cleared - strategy can resume")