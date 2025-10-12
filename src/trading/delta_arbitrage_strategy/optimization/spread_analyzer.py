"""
Spread Analysis Engine for Delta Arbitrage Optimization

This module provides comprehensive spread analysis capabilities including
time series calculation, mean reversion measurement, distribution analysis,
and regime detection for delta-neutral arbitrage parameter optimization.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Dict, Tuple, Optional
import time

from .statistical_models import (
    calculate_autocorrelation, 
    estimate_half_life,
    detect_regime_changes,
    calculate_mean_reversion_metrics
)


@dataclass
class SpreadAnalysis:
    """Detailed spread distribution analysis"""
    mean_spread: float              # Average spread in percentage
    std_spread: float              # Standard deviation of spreads
    percentiles: Dict[int, float]  # Percentile distribution {25: -0.1, 50: 0.05, ...}
    autocorrelation: list          # Autocorrelation at different lags
    half_life_hours: float         # Mean reversion half-life
    regime_changes: int            # Number of detected regime changes


@dataclass
class RegimeAnalysis:
    """Analysis of spread regime characteristics"""
    regime_count: int              # Number of distinct regimes detected
    average_regime_duration: float # Average duration of each regime (hours)
    volatility_regimes: list       # List of volatility levels for each regime
    mean_reversion_speed_by_regime: list  # Mean reversion speed for each regime


class SpreadAnalyzer:
    """
    Comprehensive spread analysis engine for delta arbitrage optimization.
    
    This class provides methods to analyze spread time series, measure mean
    reversion characteristics, and detect market regime changes to optimize
    arbitrage parameters.
    """
    
    def __init__(self, cache_size: int = 1000):
        """
        Initialize spread analyzer.
        
        Args:
            cache_size: Size of calculation cache for performance optimization
        """
        self.cache_size = cache_size
        self._calculation_cache = {}
        
    def calculate_spread_time_series(self, df: pd.DataFrame) -> pd.Series:
        """
        Calculate spread time series from market data.
        
        This method computes the entry cost percentage which represents the cost
        to establish an arbitrage position. The formula matches the existing
        backtesting logic for consistency.
        
        Args:
            df: DataFrame with columns ['spot_ask_price', 'fut_bid_price', ...]
            
        Returns:
            Series of spread values (entry cost percentages)
        """
        try:
            # Validate required columns
            required_cols = ['spot_ask_price', 'fut_bid_price']
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                raise ValueError(f"Missing required columns: {missing_cols}")
            
            # Remove rows with NaN values in required columns
            clean_df = df[required_cols].dropna()
            if len(clean_df) == 0:
                return pd.Series(dtype=float, name='spread_pct')
            
            # Calculate entry cost percentage (matches backtesting logic)
            # Entry cost = ((spot_ask_price - fut_bid_price) / spot_ask_price) * 100
            spread_series = ((clean_df['spot_ask_price'] - clean_df['fut_bid_price']) / 
                           clean_df['spot_ask_price']) * 100.0
            
            spread_series.name = 'spread_pct'
            
            # Basic validation
            if spread_series.isna().all():
                return pd.Series(dtype=float, name='spread_pct')
            
            # Remove extreme outliers (beyond ±10% spread)
            spread_series = spread_series.clip(-10.0, 10.0)
            
            return spread_series
            
        except Exception as e:
            print(f"Warning: Spread calculation failed: {e}")
            return pd.Series(dtype=float, name='spread_pct')
    
    def measure_mean_reversion_speed(self, spreads: pd.Series) -> float:
        """
        Measure mean reversion speed of spread time series.
        
        This method calculates how quickly spreads revert to their mean value,
        which is crucial for determining optimal entry/exit timing.
        
        Args:
            spreads: Time series of spread values
            
        Returns:
            Mean reversion speed (higher values = faster reversion)
        """
        try:
            # Use cached result if available
            cache_key = f"reversion_speed_{len(spreads)}_{spreads.sum():.6f}"
            if cache_key in self._calculation_cache:
                return self._calculation_cache[cache_key]
            
            # Calculate half-life using statistical models
            half_life = estimate_half_life(spreads)
            
            # Convert half-life to reversion speed
            # Speed = ln(2) / half_life (higher speed = faster reversion)
            if half_life > 0:
                reversion_speed = np.log(2) / half_life
            else:
                reversion_speed = 0.1  # Default slow reversion
            
            # Cache result
            if len(self._calculation_cache) < self.cache_size:
                self._calculation_cache[cache_key] = reversion_speed
            
            return float(reversion_speed)
            
        except Exception as e:
            print(f"Warning: Mean reversion speed calculation failed: {e}")
            return 0.1  # Default conservative speed
    
    def analyze_distribution_percentiles(self, spreads: pd.Series) -> Dict[int, float]:
        """
        Analyze spread distribution using percentiles.
        
        This method calculates key percentiles that are used for threshold
        determination in the optimization process.
        
        Args:
            spreads: Time series of spread values
            
        Returns:
            Dictionary mapping percentile levels to values
        """
        try:
            # Remove NaN values
            clean_spreads = spreads.dropna()
            if len(clean_spreads) == 0:
                return {}
            
            # Calculate key percentiles for threshold optimization
            percentile_levels = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 
                               55, 60, 65, 70, 75, 80, 85, 90, 95]
            
            percentiles = {}
            for p in percentile_levels:
                try:
                    percentiles[p] = float(np.percentile(clean_spreads, p))
                except Exception:
                    percentiles[p] = 0.0
            
            return percentiles
            
        except Exception as e:
            print(f"Warning: Percentile analysis failed: {e}")
            return {}
    
    def detect_spread_regimes(self, spreads: pd.Series, 
                            window_hours: int = 6,
                            threshold_std: float = 2.0) -> RegimeAnalysis:
        """
        Detect regime changes in spread behavior.
        
        This method identifies periods where spread characteristics change
        significantly, which can affect optimal parameter selection.
        
        Args:
            spreads: Time series of spread values
            window_hours: Window size for regime detection
            threshold_std: Standard deviation threshold for regime changes
            
        Returns:
            RegimeAnalysis with detected regime characteristics
        """
        try:
            clean_spreads = spreads.dropna()
            if len(clean_spreads) < window_hours * 4:
                # Insufficient data for regime analysis
                return RegimeAnalysis(
                    regime_count=1,
                    average_regime_duration=float(len(clean_spreads)),
                    volatility_regimes=[clean_spreads.std() if len(clean_spreads) > 0 else 0.0],
                    mean_reversion_speed_by_regime=[self.measure_mean_reversion_speed(clean_spreads)]
                )
            
            # Detect regime changes
            regime_changes = detect_regime_changes(clean_spreads, window_hours, threshold_std)
            regime_count = max(1, regime_changes + 1)
            
            # Calculate average regime duration
            total_periods = len(clean_spreads)
            average_duration = total_periods / regime_count if regime_count > 0 else total_periods
            
            # Analyze volatility by regime (simplified approach)
            # Split data into roughly equal segments based on regime count
            segment_size = total_periods // regime_count
            volatility_regimes = []
            reversion_speeds = []
            
            for i in range(regime_count):
                start_idx = i * segment_size
                end_idx = start_idx + segment_size if i < regime_count - 1 else total_periods
                
                segment = clean_spreads.iloc[start_idx:end_idx]
                if len(segment) > 0:
                    volatility_regimes.append(float(segment.std()))
                    reversion_speeds.append(self.measure_mean_reversion_speed(segment))
                else:
                    volatility_regimes.append(0.0)
                    reversion_speeds.append(0.1)
            
            return RegimeAnalysis(
                regime_count=regime_count,
                average_regime_duration=float(average_duration),
                volatility_regimes=volatility_regimes,
                mean_reversion_speed_by_regime=reversion_speeds
            )
            
        except Exception as e:
            print(f"Warning: Regime detection failed: {e}")
            # Return single regime fallback
            return RegimeAnalysis(
                regime_count=1,
                average_regime_duration=float(len(spreads.dropna())),
                volatility_regimes=[spreads.std()],
                mean_reversion_speed_by_regime=[0.1]
            )
    
    def analyze_spread_characteristics(self, df: pd.DataFrame,
                                     window_hours: int = 6,
                                     threshold_std: float = 2.0) -> SpreadAnalysis:
        """
        Perform comprehensive spread analysis.
        
        This is the main analysis method that combines all spread analysis
        techniques to provide a complete picture of spread behavior.
        
        Args:
            df: Market data DataFrame
            window_hours: Window for regime detection
            threshold_std: Threshold for regime change detection
            
        Returns:
            SpreadAnalysis with comprehensive spread characteristics
        """
        start_time = time.time()
        
        try:
            # Calculate spread time series
            spreads = self.calculate_spread_time_series(df)
            
            if len(spreads.dropna()) == 0:
                # Return empty analysis for no data
                return SpreadAnalysis(
                    mean_spread=0.0,
                    std_spread=0.0,
                    percentiles={},
                    autocorrelation=[],
                    half_life_hours=6.0,
                    regime_changes=0
                )
            
            # Calculate basic statistics
            clean_spreads = spreads.dropna()
            mean_spread = float(clean_spreads.mean())
            std_spread = float(clean_spreads.std())
            
            # Calculate percentiles
            percentiles = self.analyze_distribution_percentiles(clean_spreads)
            
            # Calculate autocorrelation
            autocorr = calculate_autocorrelation(clean_spreads, max_lags=20)
            autocorrelation_list = [float(x) for x in autocorr]
            
            # Calculate half-life
            half_life = estimate_half_life(clean_spreads)
            
            # Detect regime changes
            regime_changes = detect_regime_changes(clean_spreads, window_hours, threshold_std)
            
            analysis_time = (time.time() - start_time) * 1000
            print(f"📊 Spread analysis completed in {analysis_time:.1f}ms:")
            print(f"   • Data points: {len(clean_spreads)}")
            print(f"   • Mean spread: {mean_spread:.4f}%")
            print(f"   • Std deviation: {std_spread:.4f}%")
            print(f"   • Half-life: {half_life:.2f} hours")
            print(f"   • Regime changes: {regime_changes}")
            
            return SpreadAnalysis(
                mean_spread=mean_spread,
                std_spread=std_spread,
                percentiles=percentiles,
                autocorrelation=autocorrelation_list,
                half_life_hours=float(half_life),
                regime_changes=int(regime_changes)
            )
            
        except Exception as e:
            print(f"Error in spread analysis: {e}")
            # Return minimal valid analysis
            return SpreadAnalysis(
                mean_spread=0.0,
                std_spread=0.1,
                percentiles={50: 0.0},
                autocorrelation=[1.0, 0.0],
                half_life_hours=6.0,
                regime_changes=0
            )
    
    def get_optimal_entry_threshold(self, spreads: pd.Series, 
                                  target_frequency: float = 0.1) -> float:
        """
        Calculate optimal entry threshold based on frequency targeting.
        
        Args:
            spreads: Time series of spread values
            target_frequency: Target frequency of entry opportunities (0.0-1.0)
            
        Returns:
            Optimal entry threshold value
        """
        try:
            clean_spreads = spreads.dropna()
            if len(clean_spreads) == 0:
                return 0.5  # Default threshold
            
            # Calculate threshold that gives desired frequency
            # Use absolute values to consider both positive and negative spreads
            abs_spreads = clean_spreads.abs()
            percentile = (1 - target_frequency) * 100
            threshold = np.percentile(abs_spreads, percentile)
            
            return max(0.1, float(threshold))  # Minimum 0.1% threshold
            
        except Exception:
            return 0.5
    
    def get_optimal_exit_threshold(self, spreads: pd.Series,
                                 entry_threshold: float,
                                 target_profit_ratio: float = 0.2) -> float:
        """
        Calculate optimal exit threshold based on entry threshold and profit target.
        
        Args:
            spreads: Time series of spread values
            entry_threshold: Entry threshold for reference
            target_profit_ratio: Target profit as ratio of entry threshold
            
        Returns:
            Optimal exit threshold value
        """
        try:
            # Exit threshold should be smaller than entry for profitability
            exit_threshold = entry_threshold * target_profit_ratio
            
            # Ensure minimum exit threshold
            exit_threshold = max(0.05, exit_threshold)
            
            # Ensure exit threshold is not too close to entry
            exit_threshold = min(exit_threshold, entry_threshold * 0.8)
            
            return float(exit_threshold)
            
        except Exception:
            return 0.1
    
    def clear_cache(self):
        """Clear calculation cache to free memory."""
        self._calculation_cache.clear()
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics for monitoring."""
        return {
            'cache_size': len(self._calculation_cache),
            'max_cache_size': self.cache_size
        }