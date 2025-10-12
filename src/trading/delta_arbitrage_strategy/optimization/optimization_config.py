"""
Configuration for Delta Arbitrage Parameter Optimization

This module provides configuration classes for the statistical mean reversion
optimization engine used in delta-neutral arbitrage trading.
"""

from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class OptimizationConfig:
    """Configuration parameters for delta arbitrage optimization"""
    
    # Target performance metrics
    target_hit_rate: float = 0.7              # Target 70% success rate
    min_trades_per_day: int = 5               # Minimum daily trading opportunities
    max_drawdown_tolerance: float = 0.02      # Maximum 2% drawdown tolerance
    
    # Statistical analysis parameters  
    autocorrelation_max_lags: int = 50        # Maximum lags for autocorrelation analysis
    min_data_points: int = 100               # Minimum data points for reliable optimization
    confidence_threshold: float = 0.6        # Minimum confidence score for optimization
    
    # Parameter safety constraints
    max_entry_threshold: float = 1.0          # Never enter above 1% spread
    min_exit_threshold: float = 0.05         # Never exit below 0.05% spread
    max_threshold_ratio: float = 10.0        # Entry threshold / exit threshold max ratio
    
    # Mean reversion analysis
    half_life_max_hours: float = 24.0        # Maximum acceptable half-life
    stationarity_p_value_threshold: float = 0.05  # P-value threshold for stationarity tests
    volatility_clustering_threshold: float = 0.1  # Threshold for volatility clustering detection
    
    # Percentile-based threshold calculation
    entry_percentile_range: tuple = (75, 85)  # Entry threshold percentile range
    exit_percentile_range: tuple = (25, 35)   # Exit threshold percentile range
    
    # Performance optimization
    optimization_timeout_seconds: float = 30.0  # Maximum optimization time
    cache_size: int = 1000                   # Cache size for repeated calculations
    
    # Regime detection parameters
    regime_window_hours: int = 6             # Window for regime change detection
    regime_change_threshold: float = 2.0     # Standard deviations for regime change
    
    def validate(self) -> bool:
        """Validate configuration parameters"""
        validations = [
            (0.0 < self.target_hit_rate <= 1.0, "target_hit_rate must be between 0 and 1"),
            (self.min_trades_per_day > 0, "min_trades_per_day must be positive"),
            (0.0 < self.max_drawdown_tolerance <= 1.0, "max_drawdown_tolerance must be between 0 and 1"),
            (self.autocorrelation_max_lags > 0, "autocorrelation_max_lags must be positive"),
            (self.min_data_points >= 50, "min_data_points must be at least 50"),
            (0.0 < self.confidence_threshold <= 1.0, "confidence_threshold must be between 0 and 1"),
            (self.max_entry_threshold > self.min_exit_threshold, "max_entry_threshold must be > min_exit_threshold"),
            (self.max_threshold_ratio > 1.0, "max_threshold_ratio must be > 1.0"),
            (self.half_life_max_hours > 0, "half_life_max_hours must be positive"),
            (0.0 < self.stationarity_p_value_threshold <= 1.0, "stationarity_p_value_threshold must be between 0 and 1"),
            (self.optimization_timeout_seconds > 0, "optimization_timeout_seconds must be positive"),
        ]
        
        for condition, message in validations:
            if not condition:
                raise ValueError(f"Configuration validation failed: {message}")
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return {
            'target_hit_rate': self.target_hit_rate,
            'min_trades_per_day': self.min_trades_per_day,
            'max_drawdown_tolerance': self.max_drawdown_tolerance,
            'autocorrelation_max_lags': self.autocorrelation_max_lags,
            'min_data_points': self.min_data_points,
            'confidence_threshold': self.confidence_threshold,
            'max_entry_threshold': self.max_entry_threshold,
            'min_exit_threshold': self.min_exit_threshold,
            'max_threshold_ratio': self.max_threshold_ratio,
            'half_life_max_hours': self.half_life_max_hours,
            'stationarity_p_value_threshold': self.stationarity_p_value_threshold,
            'volatility_clustering_threshold': self.volatility_clustering_threshold,
            'entry_percentile_range': self.entry_percentile_range,
            'exit_percentile_range': self.exit_percentile_range,
            'optimization_timeout_seconds': self.optimization_timeout_seconds,
            'cache_size': self.cache_size,
            'regime_window_hours': self.regime_window_hours,
            'regime_change_threshold': self.regime_change_threshold,
        }
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'OptimizationConfig':
        """Create configuration from dictionary"""
        return cls(**config_dict)


# Default configuration for HFT arbitrage
DEFAULT_OPTIMIZATION_CONFIG = OptimizationConfig()

# Conservative configuration for lower risk tolerance
CONSERVATIVE_CONFIG = OptimizationConfig(
    target_hit_rate=0.8,              # Higher success rate requirement
    min_trades_per_day=3,             # Fewer trades acceptable
    max_drawdown_tolerance=0.01,      # Lower drawdown tolerance
    entry_percentile_range=(80, 90),  # More conservative entry thresholds
    exit_percentile_range=(15, 25),   # More conservative exit thresholds
)

# Aggressive configuration for higher frequency trading
AGGRESSIVE_CONFIG = OptimizationConfig(
    target_hit_rate=0.6,              # Lower success rate acceptable
    min_trades_per_day=10,            # More trades required
    max_drawdown_tolerance=0.03,      # Higher drawdown tolerance
    entry_percentile_range=(70, 80),  # More aggressive entry thresholds
    exit_percentile_range=(30, 40),   # More aggressive exit thresholds
)