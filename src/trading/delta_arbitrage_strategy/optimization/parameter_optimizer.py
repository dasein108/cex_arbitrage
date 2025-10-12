"""
Delta Arbitrage Parameter Optimizer

This module implements the core optimization engine for delta-neutral arbitrage
parameters using statistical mean reversion analysis. The optimizer dynamically
calculates optimal entry and exit thresholds based on historical spread data.
"""

import time
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Optional, Dict, Any
import warnings

from .optimization_config import OptimizationConfig, DEFAULT_OPTIMIZATION_CONFIG
from .spread_analyzer import SpreadAnalyzer, SpreadAnalysis
from .statistical_models import (
    calculate_optimal_thresholds,
    calculate_mean_reversion_metrics,
    MeanReversionMetrics,
    ThresholdResult
)

# Suppress warnings for cleaner output
warnings.filterwarnings('ignore', category=RuntimeWarning)


@dataclass
class OptimizationResult:
    """Result from parameter optimization analysis"""
    entry_threshold_pct: float      # Optimized entry threshold (e.g., 0.5 for 0.5%)
    exit_threshold_pct: float       # Optimized exit threshold (e.g., 0.1 for 0.1%)
    confidence_score: float         # Confidence in optimization (0.0-1.0)
    analysis_period_hours: int      # Hours of data analyzed
    mean_reversion_speed: float     # Half-life of spread convergence (hours)
    spread_volatility: float        # Standard deviation of spreads
    optimization_timestamp: float   # When optimization was performed


class DeltaArbitrageOptimizer:
    """
    Main optimization engine for delta arbitrage parameters.
    
    This class implements statistical mean reversion analysis to determine
    optimal entry and exit thresholds for delta-neutral arbitrage trading.
    The optimization is based on historical spread distributions and targets
    specific performance metrics.
    """
    
    def __init__(self, 
                 config: Optional[OptimizationConfig] = None):
        """
        Initialize the optimization engine.
        
        Args:
            config: Configuration parameters for optimization
        """
        self.config = config or DEFAULT_OPTIMIZATION_CONFIG
        self.config.validate()  # Ensure configuration is valid
        
        # Initialize components
        self.spread_analyzer = SpreadAnalyzer(cache_size=self.config.cache_size)
        
        # Performance tracking
        self._optimization_count = 0
        self._total_optimization_time = 0.0
        self._last_optimization_result: Optional[OptimizationResult] = None
        
        print(f"🚀 DeltaArbitrageOptimizer initialized")
        print(f"   • Target hit rate: {self.config.target_hit_rate:.1%}")
        print(f"   • Min trades/day: {self.config.min_trades_per_day}")
        print(f"   • Max drawdown: {self.config.max_drawdown_tolerance:.1%}")
    
    async def optimize_parameters(self, 
                                df: pd.DataFrame,
                                lookback_hours: int = 24) -> OptimizationResult:
        """
        Optimize entry/exit thresholds based on historical data.
        
        This is the main optimization method that analyzes historical spread
        data to determine optimal parameters for arbitrage trading.
        
        Args:
            df: Historical book ticker data with columns:
                ['timestamp', 'spot_ask_price', 'spot_bid_price', 
                 'fut_ask_price', 'fut_bid_price']
            lookback_hours: Hours of historical data to analyze
            
        Returns:
            OptimizationResult with optimized parameters
        """
        start_time = time.time()
        self._optimization_count += 1
        
        try:
            print(f"📈 Starting parameter optimization (run #{self._optimization_count})")
            print(f"   • Input data shape: {df.shape}")
            print(f"   • Lookback period: {lookback_hours} hours")
            
            # Validate input data
            validation_result = self._validate_input_data(df)
            if not validation_result['valid']:
                return self._create_fallback_result(validation_result['reason'])
            
            # Limit data to lookback period if specified
            if lookback_hours > 0 and 'timestamp' in df.columns:
                df_limited = self._limit_data_by_time(df, lookback_hours)
            else:
                df_limited = df.copy()
            
            print(f"   • Analysis data shape: {df_limited.shape}")
            
            # Perform comprehensive spread analysis
            spread_analysis = self.spread_analyzer.analyze_spread_characteristics(
                df_limited,
                window_hours=self.config.regime_window_hours,
                threshold_std=self.config.regime_change_threshold
            )
            
            # Calculate mean reversion metrics
            spreads = self.spread_analyzer.calculate_spread_time_series(df_limited)
            mean_reversion_metrics = calculate_mean_reversion_metrics(spreads)
            
            # Validate data quality for optimization
            if not self._validate_analysis_quality(spread_analysis, mean_reversion_metrics):
                return self._create_fallback_result("Insufficient data quality for reliable optimization")
            
            # Calculate optimal thresholds using statistical analysis
            threshold_result = calculate_optimal_thresholds(
                spreads,
                target_hit_rate=self.config.target_hit_rate,
                entry_percentile_range=self.config.entry_percentile_range,
                exit_percentile_range=self.config.exit_percentile_range,
                min_trades_per_day=self.config.min_trades_per_day
            )
            
            # Apply safety constraints
            validated_thresholds = self._apply_safety_constraints(threshold_result)
            
            # Calculate optimization confidence
            confidence_score = self._calculate_confidence_score(
                spread_analysis, mean_reversion_metrics, threshold_result, df_limited
            )
            
            # Create optimization result
            optimization_time = time.time() - start_time
            self._total_optimization_time += optimization_time
            
            result = OptimizationResult(
                entry_threshold_pct=validated_thresholds.entry_threshold,
                exit_threshold_pct=validated_thresholds.exit_threshold,
                confidence_score=confidence_score,
                analysis_period_hours=self._calculate_analysis_period(df_limited),
                mean_reversion_speed=1.0 / mean_reversion_metrics.half_life if mean_reversion_metrics.half_life > 0 else 0.1,
                spread_volatility=spread_analysis.std_spread,
                optimization_timestamp=time.time()
            )
            
            self._last_optimization_result = result
            
            print(f"✅ Optimization completed in {optimization_time*1000:.1f}ms")
            print(f"   • Entry threshold: {result.entry_threshold_pct:.4f}%")
            print(f"   • Exit threshold: {result.exit_threshold_pct:.4f}%")
            print(f"   • Confidence score: {result.confidence_score:.3f}")
            print(f"   • Expected hit rate: {threshold_result.expected_hit_rate:.1%}")
            print(f"   • Expected trades/day: {threshold_result.expected_trades_per_day:.1f}")
            
            return result
            
        except Exception as e:
            optimization_time = time.time() - start_time
            self._total_optimization_time += optimization_time
            
            print(f"❌ Optimization failed after {optimization_time*1000:.1f}ms: {e}")
            return self._create_fallback_result(f"Optimization error: {str(e)}")
    
    def analyze_spread_distribution(self, df: pd.DataFrame) -> SpreadAnalysis:
        """
        Analyze spread characteristics for optimization.
        
        Args:
            df: Market data DataFrame
            
        Returns:
            SpreadAnalysis with spread characteristics
        """
        try:
            return self.spread_analyzer.analyze_spread_characteristics(df)
        except Exception as e:
            print(f"Warning: Spread distribution analysis failed: {e}")
            # Return minimal valid analysis
            return SpreadAnalysis(
                mean_spread=0.0,
                std_spread=0.1,
                percentiles={50: 0.0},
                autocorrelation=[1.0, 0.0],
                half_life_hours=6.0,
                regime_changes=0
            )
    
    def validate_parameters(self, 
                          entry_threshold: float, 
                          exit_threshold: float) -> bool:
        """
        Validate that parameters meet safety constraints.
        
        Args:
            entry_threshold: Proposed entry threshold
            exit_threshold: Proposed exit threshold
            
        Returns:
            True if parameters are valid, False otherwise
        """
        try:
            # Basic range checks
            if entry_threshold <= 0 or exit_threshold <= 0:
                return False
            
            # Maximum threshold checks
            if entry_threshold > self.config.max_entry_threshold:
                return False
            
            if exit_threshold < self.config.min_exit_threshold:
                return False
            
            # Relationship checks
            if exit_threshold >= entry_threshold:
                return False
            
            # Ratio check
            threshold_ratio = entry_threshold / exit_threshold
            if threshold_ratio > self.config.max_threshold_ratio:
                return False
            
            return True
            
        except Exception:
            return False
    
    def get_optimization_stats(self) -> Dict[str, Any]:
        """
        Get optimization performance statistics.
        
        Returns:
            Dictionary with performance metrics
        """
        avg_time = (self._total_optimization_time / self._optimization_count 
                   if self._optimization_count > 0 else 0.0)
        
        return {
            'optimization_count': self._optimization_count,
            'total_optimization_time_seconds': self._total_optimization_time,
            'average_optimization_time_seconds': avg_time,
            'last_optimization_timestamp': (self._last_optimization_result.optimization_timestamp 
                                           if self._last_optimization_result else None),
            'cache_stats': self.spread_analyzer.get_cache_stats()
        }
    
    def _validate_input_data(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Validate input data quality."""
        try:
            required_columns = ['spot_ask_price', 'fut_bid_price']
            missing_cols = [col for col in required_columns if col not in df.columns]
            
            if missing_cols:
                return {'valid': False, 'reason': f"Missing columns: {missing_cols}"}
            
            if len(df) < self.config.min_data_points:
                return {'valid': False, 'reason': f"Insufficient data points: {len(df)} < {self.config.min_data_points}"}
            
            # Check for sufficient non-null data
            clean_data = df[required_columns].dropna()
            if len(clean_data) < self.config.min_data_points // 2:
                return {'valid': False, 'reason': "Too many null values in required columns"}
            
            return {'valid': True, 'reason': 'Data validation passed'}
            
        except Exception as e:
            return {'valid': False, 'reason': f"Validation error: {str(e)}"}
    
    def _limit_data_by_time(self, df: pd.DataFrame, lookback_hours: int) -> pd.DataFrame:
        """Limit data to specified lookback period."""
        try:
            if 'timestamp' not in df.columns:
                return df
            
            # Convert timestamp to datetime if needed
            df_copy = df.copy()
            if not pd.api.types.is_datetime64_any_dtype(df_copy['timestamp']):
                df_copy['timestamp'] = pd.to_datetime(df_copy['timestamp'])
            
            # Calculate cutoff time
            latest_time = df_copy['timestamp'].max()
            cutoff_time = latest_time - pd.Timedelta(hours=lookback_hours)
            
            # Filter data
            filtered_df = df_copy[df_copy['timestamp'] >= cutoff_time]
            
            print(f"   • Time filtering: {len(df)} → {len(filtered_df)} rows")
            print(f"   • Time range: {cutoff_time} to {latest_time}")
            
            return filtered_df
            
        except Exception as e:
            print(f"Warning: Time filtering failed: {e}")
            return df
    
    def _validate_analysis_quality(self, 
                                 spread_analysis: SpreadAnalysis,
                                 mean_reversion_metrics: MeanReversionMetrics) -> bool:
        """Validate quality of spread analysis for optimization."""
        try:
            # Check if we have meaningful spread data
            if spread_analysis.std_spread <= 0:
                print("Warning: Zero spread volatility detected")
                return False
            
            # Check for reasonable half-life
            if mean_reversion_metrics.half_life > self.config.half_life_max_hours:
                print(f"Warning: Half-life too large: {mean_reversion_metrics.half_life:.2f} hours")
                return False
            
            # Check for stationarity if p-value is available
            if (mean_reversion_metrics.p_value > 0 and 
                mean_reversion_metrics.p_value > self.config.stationarity_p_value_threshold):
                print(f"Warning: Spread series may not be stationary (p-value: {mean_reversion_metrics.p_value:.3f})")
                # Don't fail on stationarity, just warn
            
            return True
            
        except Exception as e:
            print(f"Warning: Analysis quality validation failed: {e}")
            return False
    
    def _apply_safety_constraints(self, threshold_result: ThresholdResult) -> ThresholdResult:
        """Apply safety constraints to threshold results."""
        try:
            entry_threshold = threshold_result.entry_threshold
            exit_threshold = threshold_result.exit_threshold
            
            # Apply maximum constraints
            entry_threshold = min(entry_threshold, self.config.max_entry_threshold)
            exit_threshold = max(exit_threshold, self.config.min_exit_threshold)
            
            # Ensure proper relationship
            if exit_threshold >= entry_threshold:
                exit_threshold = entry_threshold * 0.3  # 30% of entry threshold
            
            # Ensure reasonable ratio
            threshold_ratio = entry_threshold / exit_threshold if exit_threshold > 0 else float('inf')
            if threshold_ratio > self.config.max_threshold_ratio:
                exit_threshold = entry_threshold / self.config.max_threshold_ratio
            
            # Update result with constrained values
            return ThresholdResult(
                entry_threshold=entry_threshold,
                exit_threshold=exit_threshold,
                expected_hit_rate=threshold_result.expected_hit_rate,
                expected_trades_per_day=threshold_result.expected_trades_per_day,
                confidence_score=threshold_result.confidence_score
            )
            
        except Exception as e:
            print(f"Warning: Safety constraint application failed: {e}")
            return threshold_result
    
    def _calculate_confidence_score(self,
                                  spread_analysis: SpreadAnalysis,
                                  mean_reversion_metrics: MeanReversionMetrics,
                                  threshold_result: ThresholdResult,
                                  df: pd.DataFrame) -> float:
        """Calculate overall confidence score for optimization."""
        try:
            confidence_factors = []
            
            # Data quantity factor (more data = higher confidence)
            data_points = len(df.dropna())
            if data_points >= 1000:
                data_factor = 1.0
            elif data_points >= 500:
                data_factor = 0.9
            elif data_points >= 200:
                data_factor = 0.8
            else:
                data_factor = 0.6
            confidence_factors.append(data_factor)
            
            # Mean reversion quality factor
            if mean_reversion_metrics.half_life > 0 and mean_reversion_metrics.half_life < 12:
                reversion_factor = 0.9  # Good mean reversion
            elif mean_reversion_metrics.half_life < 24:
                reversion_factor = 0.7  # Acceptable mean reversion
            else:
                reversion_factor = 0.5  # Slow mean reversion
            confidence_factors.append(reversion_factor)
            
            # Threshold result confidence
            confidence_factors.append(threshold_result.confidence_score)
            
            # Spread volatility factor (moderate volatility is good)
            if 0.1 <= spread_analysis.std_spread <= 1.0:
                volatility_factor = 0.9  # Good volatility range
            elif spread_analysis.std_spread <= 2.0:
                volatility_factor = 0.7  # Acceptable volatility
            else:
                volatility_factor = 0.5  # High volatility
            confidence_factors.append(volatility_factor)
            
            # Stationarity factor
            if mean_reversion_metrics.p_value > 0:
                if mean_reversion_metrics.p_value <= 0.05:
                    stationarity_factor = 0.9  # Stationary
                elif mean_reversion_metrics.p_value <= 0.1:
                    stationarity_factor = 0.7  # Probably stationary
                else:
                    stationarity_factor = 0.5  # Non-stationary
            else:
                stationarity_factor = 0.7  # Unknown stationarity
            confidence_factors.append(stationarity_factor)
            
            # Calculate weighted average confidence
            overall_confidence = np.mean(confidence_factors)
            
            # Ensure confidence is within valid range
            return float(np.clip(overall_confidence, 0.0, 1.0))
            
        except Exception as e:
            print(f"Warning: Confidence calculation failed: {e}")
            return 0.5  # Default moderate confidence
    
    def _calculate_analysis_period(self, df: pd.DataFrame) -> int:
        """Calculate analysis period in hours."""
        try:
            if 'timestamp' in df.columns and len(df) > 1:
                timestamps = pd.to_datetime(df['timestamp'])
                time_span = timestamps.max() - timestamps.min()
                return int(time_span.total_seconds() / 3600)  # Convert to hours
            else:
                # Estimate based on data points (assume hourly data)
                return len(df)
        except Exception:
            return len(df)  # Fallback to row count
    
    def _create_fallback_result(self, reason: str) -> OptimizationResult:
        """Create fallback optimization result for error cases."""
        print(f"⚠️ Using fallback parameters: {reason}")
        
        return OptimizationResult(
            entry_threshold_pct=0.5,     # Conservative 0.5% entry
            exit_threshold_pct=0.1,      # Conservative 0.1% exit
            confidence_score=0.3,        # Low confidence
            analysis_period_hours=0,     # No analysis performed
            mean_reversion_speed=0.1,    # Slow reversion assumption
            spread_volatility=0.2,       # Moderate volatility assumption
            optimization_timestamp=time.time()
        )
    
    def clear_cache(self):
        """Clear all optimization caches."""
        self.spread_analyzer.clear_cache()
        print("🧹 Optimization caches cleared")