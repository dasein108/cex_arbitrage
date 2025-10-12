"""
Configuration for Delta Arbitrage Live Trading Strategy

This module provides configuration classes for the simplified delta arbitrage
live trading strategy with dynamic parameter optimization.
"""

from dataclasses import dataclass
from typing import Optional
import sys
import os

from exchanges.structs import Symbol
from ..optimization.optimization_config import OptimizationConfig, DEFAULT_OPTIMIZATION_CONFIG


@dataclass
class DeltaArbitrageConfig:
    """Configuration for delta arbitrage strategy"""
    
    # Symbol configuration
    symbol: Symbol
    
    # Position sizing
    base_position_size: float = 100.0
    max_position_multiplier: float = 2.0
    
    # Optimization settings
    optimization_lookback_hours: int = 24
    parameter_update_interval_minutes: int = 5
    min_spread_data_points: int = 100
    
    # Safety constraints
    max_entry_threshold: float = 1.0  # Never enter above 1%
    min_exit_threshold: float = 0.05  # Never exit below 0.05%
    max_position_hold_minutes: int = 360  # 6 hours max hold
    
    # Performance targets
    target_hit_rate: float = 0.7
    min_daily_trades: int = 5
    max_drawdown_tolerance: float = 0.02
    
    # Exchange settings
    spot_fee: float = 0.0005  # 0.05% MEXC spot fee
    futures_fee: float = 0.0005  # 0.05% Gate.io futures fee
    
    # Risk management
    max_concurrent_positions: int = 1  # Keep it simple for PoC
    emergency_stop_loss_pct: float = 5.0  # 5% emergency stop
    
    # Optimization configuration
    optimization_config: OptimizationConfig = None
    
    def __post_init__(self):
        """Initialize optimization config if not provided"""
        if self.optimization_config is None:
            self.optimization_config = OptimizationConfig(
                target_hit_rate=self.target_hit_rate,
                min_trades_per_day=self.min_daily_trades,
                max_drawdown_tolerance=self.max_drawdown_tolerance,
                max_entry_threshold=self.max_entry_threshold,
                min_exit_threshold=self.min_exit_threshold
            )
    
    def validate(self) -> bool:
        """Validate configuration parameters"""
        validations = [
            (self.base_position_size > 0, "base_position_size must be positive"),
            (self.max_position_multiplier >= 1.0, "max_position_multiplier must be >= 1.0"),
            (self.optimization_lookback_hours > 0, "optimization_lookback_hours must be positive"),
            (self.parameter_update_interval_minutes > 0, "parameter_update_interval_minutes must be positive"),
            (self.min_spread_data_points >= 10, "min_spread_data_points must be >= 10"),
            (0.0 < self.max_entry_threshold <= 5.0, "max_entry_threshold must be between 0 and 5%"),
            (0.0 < self.min_exit_threshold <= 1.0, "min_exit_threshold must be between 0 and 1%"),
            (self.max_position_hold_minutes > 0, "max_position_hold_minutes must be positive"),
            (0.0 < self.target_hit_rate <= 1.0, "target_hit_rate must be between 0 and 1"),
            (self.min_daily_trades >= 0, "min_daily_trades must be non-negative"),
            (0.0 < self.max_drawdown_tolerance <= 1.0, "max_drawdown_tolerance must be between 0 and 1"),
            (0.0 <= self.spot_fee <= 0.01, "spot_fee must be between 0 and 1%"),
            (0.0 <= self.futures_fee <= 0.01, "futures_fee must be between 0 and 1%"),
            (self.max_concurrent_positions > 0, "max_concurrent_positions must be positive"),
            (self.emergency_stop_loss_pct > 0, "emergency_stop_loss_pct must be positive"),
        ]
        
        for condition, message in validations:
            if not condition:
                raise ValueError(f"Configuration validation failed: {message}")
        
        # Validate optimization config
        if self.optimization_config:
            self.optimization_config.validate()
        
        return True
    
    def get_total_fees(self) -> float:
        """Get total round-trip fees"""
        return self.spot_fee + self.futures_fee
    
    def get_minimum_profit_threshold(self) -> float:
        """Get minimum profit threshold to cover fees"""
        return self.get_total_fees() * 1.5  # 50% margin above fees
    
    def to_dict(self) -> dict:
        """Convert configuration to dictionary"""
        return {
            'symbol': str(self.symbol),
            'base_position_size': self.base_position_size,
            'max_position_multiplier': self.max_position_multiplier,
            'optimization_lookback_hours': self.optimization_lookback_hours,
            'parameter_update_interval_minutes': self.parameter_update_interval_minutes,
            'min_spread_data_points': self.min_spread_data_points,
            'max_entry_threshold': self.max_entry_threshold,
            'min_exit_threshold': self.min_exit_threshold,
            'max_position_hold_minutes': self.max_position_hold_minutes,
            'target_hit_rate': self.target_hit_rate,
            'min_daily_trades': self.min_daily_trades,
            'max_drawdown_tolerance': self.max_drawdown_tolerance,
            'spot_fee': self.spot_fee,
            'futures_fee': self.futures_fee,
            'max_concurrent_positions': self.max_concurrent_positions,
            'emergency_stop_loss_pct': self.emergency_stop_loss_pct,
            'optimization_config': self.optimization_config.to_dict() if self.optimization_config else None
        }


# Default configurations for different risk profiles

def create_conservative_config(symbol: Symbol) -> DeltaArbitrageConfig:
    """Create conservative configuration for lower risk trading"""
    return DeltaArbitrageConfig(
        symbol=symbol,
        base_position_size=50.0,           # Smaller position size
        max_position_multiplier=1.5,      # Conservative multiplier
        target_hit_rate=0.8,               # Higher success rate requirement
        min_daily_trades=3,                # Fewer trades acceptable
        max_drawdown_tolerance=0.01,       # Lower drawdown tolerance
        max_entry_threshold=0.8,           # More conservative entry
        min_exit_threshold=0.08,           # More conservative exit
        parameter_update_interval_minutes=10,  # More frequent updates
        emergency_stop_loss_pct=3.0,       # Tighter stop loss
    )


def create_aggressive_config(symbol: Symbol) -> DeltaArbitrageConfig:
    """Create aggressive configuration for higher frequency trading"""
    return DeltaArbitrageConfig(
        symbol=symbol,
        base_position_size=200.0,          # Larger position size
        max_position_multiplier=3.0,       # Aggressive multiplier
        target_hit_rate=0.6,               # Lower success rate acceptable
        min_daily_trades=10,               # More trades required
        max_drawdown_tolerance=0.03,       # Higher drawdown tolerance
        max_entry_threshold=1.2,           # More aggressive entry
        min_exit_threshold=0.05,           # More aggressive exit
        parameter_update_interval_minutes=3,   # More frequent updates
        emergency_stop_loss_pct=7.0,       # Looser stop loss
    )


def create_default_config(symbol: Symbol) -> DeltaArbitrageConfig:
    """Create default balanced configuration"""
    return DeltaArbitrageConfig(
        symbol=symbol,
        base_position_size=100.0,
        max_position_multiplier=2.0,
        target_hit_rate=0.7,
        min_daily_trades=5,
        max_drawdown_tolerance=0.02,
        max_entry_threshold=1.0,
        min_exit_threshold=0.05,
        parameter_update_interval_minutes=5,
        emergency_stop_loss_pct=5.0,
    )