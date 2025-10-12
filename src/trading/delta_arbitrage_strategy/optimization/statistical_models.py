"""
Statistical Models for Delta Arbitrage Parameter Optimization

This module implements statistical analysis functions for mean reversion,
autocorrelation analysis, and optimal threshold calculation used in
delta-neutral arbitrage parameter optimization.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Tuple, Optional
from scipy import stats
import warnings

# Suppress scipy warnings for cleaner output
warnings.filterwarnings('ignore', category=RuntimeWarning)


@dataclass
class ThresholdResult:
    """Result from optimal threshold calculation"""
    entry_threshold: float      # Optimized entry threshold
    exit_threshold: float       # Optimized exit threshold
    expected_hit_rate: float    # Expected success rate
    expected_trades_per_day: float  # Expected daily trading frequency
    confidence_score: float     # Confidence in threshold selection


@dataclass
class MeanReversionMetrics:
    """Mean reversion characteristics of spreads"""
    half_life: float               # Time for 50% reversion (hours)
    reversion_speed: float         # Speed coefficient  
    long_term_mean: float          # Long-term spread equilibrium
    volatility_clustering: bool    # Whether volatility clusters
    adf_statistic: float          # Augmented Dickey-Fuller test result
    p_value: float                # P-value for stationarity test


def calculate_autocorrelation(spreads: pd.Series, max_lags: int = 50) -> np.ndarray:
    """
    Calculate autocorrelation function for spread time series.
    
    This function computes the sample autocorrelation function which measures
    the correlation between spread values at different time lags. High positive
    autocorrelation at lag 1 indicates momentum (trending), while negative
    autocorrelation indicates mean reversion.
    
    Args:
        spreads: Time series of spread values
        max_lags: Maximum number of lags to calculate
        
    Returns:
        Array of autocorrelation coefficients [lag0, lag1, lag2, ...]
    """
    try:
        # Remove NaN values and ensure sufficient data
        clean_spreads = spreads.dropna()
        if len(clean_spreads) < max_lags * 2:
            # Not enough data for reliable autocorrelation
            return np.zeros(max_lags + 1)
        
        # Calculate autocorrelation using numpy correlation
        autocorr = np.zeros(max_lags + 1)
        autocorr[0] = 1.0  # Lag 0 is always 1.0
        
        spread_array = clean_spreads.values
        n = len(spread_array)
        mean_spread = np.mean(spread_array)
        variance = np.var(spread_array)
        
        if variance == 0:
            # No variance means constant values
            return autocorr
        
        # Calculate autocorrelation for each lag
        for lag in range(1, min(max_lags + 1, n // 2)):
            # Pearson correlation between series and lagged series
            if lag < n:
                covariance = np.mean((spread_array[:-lag] - mean_spread) * (spread_array[lag:] - mean_spread))
                autocorr[lag] = covariance / variance
            
        return autocorr
        
    except Exception as e:
        print(f"Warning: Autocorrelation calculation failed: {e}")
        return np.zeros(max_lags + 1)


def estimate_half_life(spreads: pd.Series) -> float:
    """
    Estimate mean reversion half-life using Ornstein-Uhlenbeck process.
    
    This function fits an AR(1) model to the spread data to estimate the
    mean reversion speed. The half-life represents the time it takes for
    50% of a spread deviation to revert to the mean.
    
    Args:
        spreads: Time series of spread values
        
    Returns:
        Half-life in time periods (hours if spreads are hourly)
    """
    try:
        # Remove NaN values and ensure sufficient data
        clean_spreads = spreads.dropna()
        if len(clean_spreads) < 20:
            # Default to moderate half-life if insufficient data
            return 6.0  # 6 hours default
        
        # Calculate first differences for AR(1) estimation
        y = clean_spreads.diff().dropna()
        x = clean_spreads.shift(1).dropna()
        
        # Align the series
        min_length = min(len(y), len(x))
        if min_length < 10:
            return 6.0  # Default fallback
            
        y = y.iloc[:min_length]
        x = x.iloc[:min_length]
        
        # Estimate AR(1) coefficient using OLS regression
        # Model: Δy_t = α + β * y_{t-1} + ε_t
        # where β = -λ (reversion speed)
        
        # Add constant term for regression
        X = np.column_stack([np.ones(len(x)), x.values])
        
        try:
            # Use least squares to estimate coefficients
            coefficients = np.linalg.lstsq(X, y.values, rcond=None)[0]
            beta = coefficients[1]  # AR(1) coefficient
            
            # Calculate reversion speed λ = -β
            reversion_speed = -beta
            
            # Ensure reversion speed is positive for mean reversion
            if reversion_speed <= 0:
                # No mean reversion detected, return large half-life
                return 24.0  # 24 hours
            
            # Calculate half-life: t_half = ln(2) / λ
            half_life = np.log(2) / reversion_speed
            
            # Bound half-life to reasonable range (0.5 to 48 hours)
            half_life = np.clip(half_life, 0.5, 48.0)
            
            return float(half_life)
            
        except np.linalg.LinAlgError:
            # Singular matrix, fallback to autocorrelation method
            autocorr = calculate_autocorrelation(clean_spreads, max_lags=10)
            if len(autocorr) > 1 and autocorr[1] > 0:
                # Approximate half-life from AR(1) coefficient
                return -np.log(2) / np.log(max(autocorr[1], 0.01))
            else:
                return 6.0  # Default fallback
            
    except Exception as e:
        print(f"Warning: Half-life estimation failed: {e}")
        return 6.0  # Conservative default


def calculate_optimal_thresholds(spreads: pd.Series, 
                               target_hit_rate: float = 0.7,
                               entry_percentile_range: Tuple[int, int] = (75, 85),
                               exit_percentile_range: Tuple[int, int] = (25, 35),
                               min_trades_per_day: int = 5) -> ThresholdResult:
    """
    Calculate optimal entry/exit thresholds using statistical analysis.
    
    This function analyzes the spread distribution to determine optimal
    entry and exit thresholds that maximize expected profitability while
    maintaining the target success rate.
    
    Args:
        spreads: Time series of spread values (entry cost percentages)
        target_hit_rate: Target success rate (0.0 to 1.0)
        entry_percentile_range: Percentile range for entry threshold selection
        exit_percentile_range: Percentile range for exit threshold selection
        min_trades_per_day: Minimum required trades per day
        
    Returns:
        ThresholdResult with optimized parameters
    """
    try:
        # Remove NaN values and ensure sufficient data
        clean_spreads = spreads.dropna()
        if len(clean_spreads) < 50:
            # Insufficient data, return conservative defaults
            return ThresholdResult(
                entry_threshold=0.5,     # 0.5% entry threshold
                exit_threshold=0.1,      # 0.1% exit threshold
                expected_hit_rate=0.6,   # Conservative estimate
                expected_trades_per_day=3.0,
                confidence_score=0.3     # Low confidence due to insufficient data
            )
        
        # Calculate spread statistics
        spread_mean = clean_spreads.mean()
        spread_std = clean_spreads.std()
        
        # Handle edge case of zero variance
        if spread_std == 0:
            return ThresholdResult(
                entry_threshold=max(0.5, abs(spread_mean)),
                exit_threshold=max(0.1, abs(spread_mean) * 0.2),
                expected_hit_rate=0.5,
                expected_trades_per_day=1.0,
                confidence_score=0.2
            )
        
        # Calculate percentiles for threshold selection
        # Entry threshold: Use negative spreads (favorable for entry)
        negative_spreads = clean_spreads[clean_spreads < 0]
        if len(negative_spreads) > 10:
            # Use negative spreads for entry threshold calculation
            entry_p_low, entry_p_high = entry_percentile_range
            entry_threshold_low = abs(np.percentile(negative_spreads, entry_p_low))
            entry_threshold_high = abs(np.percentile(negative_spreads, entry_p_high))
            entry_threshold = (entry_threshold_low + entry_threshold_high) / 2
        else:
            # Fallback to positive spread analysis
            entry_threshold = abs(spread_mean) + 0.5 * spread_std
        
        # Exit threshold: Use smaller positive spreads (easier to achieve)
        positive_spreads = clean_spreads[clean_spreads > 0]
        if len(positive_spreads) > 10:
            exit_p_low, exit_p_high = exit_percentile_range
            exit_threshold_low = np.percentile(positive_spreads, exit_p_low)
            exit_threshold_high = np.percentile(positive_spreads, exit_p_high)
            exit_threshold = (exit_threshold_low + exit_threshold_high) / 2
        else:
            # Fallback based on spread statistics
            exit_threshold = max(0.05, abs(spread_mean) - 0.3 * spread_std)
        
        # Ensure reasonable threshold relationships
        entry_threshold = max(0.1, entry_threshold)  # Minimum 0.1% entry
        exit_threshold = max(0.05, exit_threshold)   # Minimum 0.05% exit
        exit_threshold = min(exit_threshold, entry_threshold * 0.8)  # Exit < 80% of entry
        
        # Estimate trading frequency based on threshold levels
        # Count how often spreads would trigger entry
        entry_opportunities = len(clean_spreads[abs(clean_spreads) >= entry_threshold])
        total_periods = len(clean_spreads)
        
        if total_periods > 0:
            # Estimate trades per day (assuming hourly data)
            opportunity_rate = entry_opportunities / total_periods
            estimated_trades_per_day = opportunity_rate * 24  # 24 hours per day
        else:
            estimated_trades_per_day = 1.0
        
        # Calculate expected hit rate based on historical data
        # This is a simplified model - actual hit rate depends on market dynamics
        if len(negative_spreads) > 0 and len(positive_spreads) > 0:
            # Estimate hit rate based on spread reversion patterns
            reversion_count = 0
            entry_positions = 0
            
            for i in range(len(clean_spreads) - 1):
                current_spread = clean_spreads.iloc[i]
                next_spread = clean_spreads.iloc[i + 1]
                
                # Simulate entry condition
                if abs(current_spread) >= entry_threshold:
                    entry_positions += 1
                    # Check if next period would allow profitable exit
                    if abs(next_spread) <= exit_threshold:
                        reversion_count += 1
            
            if entry_positions > 0:
                estimated_hit_rate = reversion_count / entry_positions
            else:
                estimated_hit_rate = target_hit_rate
        else:
            estimated_hit_rate = target_hit_rate * 0.8  # Conservative estimate
        
        # Calculate confidence score based on data quality
        data_points = len(clean_spreads)
        if data_points >= 500:
            confidence_score = 0.9
        elif data_points >= 200:
            confidence_score = 0.8
        elif data_points >= 100:
            confidence_score = 0.7
        else:
            confidence_score = 0.5
        
        # Adjust confidence based on hit rate alignment with target
        hit_rate_alignment = 1 - abs(estimated_hit_rate - target_hit_rate)
        confidence_score *= max(0.5, hit_rate_alignment)
        
        return ThresholdResult(
            entry_threshold=float(entry_threshold),
            exit_threshold=float(exit_threshold),
            expected_hit_rate=float(np.clip(estimated_hit_rate, 0.0, 1.0)),
            expected_trades_per_day=float(max(0.1, estimated_trades_per_day)),
            confidence_score=float(np.clip(confidence_score, 0.0, 1.0))
        )
        
    except Exception as e:
        print(f"Warning: Threshold optimization failed: {e}")
        # Return safe defaults
        return ThresholdResult(
            entry_threshold=0.5,
            exit_threshold=0.1,
            expected_hit_rate=0.6,
            expected_trades_per_day=3.0,
            confidence_score=0.3
        )


def calculate_mean_reversion_metrics(spreads: pd.Series) -> MeanReversionMetrics:
    """
    Calculate comprehensive mean reversion metrics for spread analysis.
    
    Args:
        spreads: Time series of spread values
        
    Returns:
        MeanReversionMetrics with statistical properties
    """
    try:
        # Remove NaN values
        clean_spreads = spreads.dropna()
        if len(clean_spreads) < 10:
            # Insufficient data for analysis
            return MeanReversionMetrics(
                half_life=6.0,
                reversion_speed=0.1,
                long_term_mean=0.0,
                volatility_clustering=False,
                adf_statistic=0.0,
                p_value=1.0
            )
        
        # Calculate half-life and reversion speed
        half_life = estimate_half_life(clean_spreads)
        reversion_speed = np.log(2) / half_life if half_life > 0 else 0.1
        
        # Calculate long-term mean
        long_term_mean = clean_spreads.mean()
        
        # Test for volatility clustering using absolute returns
        abs_returns = clean_spreads.diff().abs().dropna()
        volatility_clustering = False
        if len(abs_returns) > 10:
            # Simple test: correlation between current and lagged absolute returns
            autocorr_abs = calculate_autocorrelation(abs_returns, max_lags=5)
            if len(autocorr_abs) > 1 and autocorr_abs[1] > 0.1:
                volatility_clustering = True
        
        # Augmented Dickey-Fuller test for stationarity
        adf_statistic = 0.0
        p_value = 1.0
        
        try:
            from statsmodels.tsa.stattools import adfuller
            adf_result = adfuller(clean_spreads.values, autolag='AIC')
            adf_statistic = adf_result[0]
            p_value = adf_result[1]
        except ImportError:
            # Fallback if statsmodels not available
            # Use simple variance ratio test
            if len(clean_spreads) > 20:
                # Calculate variance ratio as proxy for stationarity
                first_half = clean_spreads[:len(clean_spreads)//2]
                second_half = clean_spreads[len(clean_spreads)//2:]
                var_ratio = second_half.var() / first_half.var() if first_half.var() > 0 else 1.0
                
                # Convert to ADF-like statistic (negative values indicate stationarity)
                adf_statistic = -abs(1 - var_ratio) * 10
                p_value = 0.05 if abs(var_ratio - 1) < 0.5 else 0.1
        except Exception:
            # Fallback to default values
            pass
        
        return MeanReversionMetrics(
            half_life=float(half_life),
            reversion_speed=float(reversion_speed),
            long_term_mean=float(long_term_mean),
            volatility_clustering=volatility_clustering,
            adf_statistic=float(adf_statistic),
            p_value=float(p_value)
        )
        
    except Exception as e:
        print(f"Warning: Mean reversion metrics calculation failed: {e}")
        # Return default metrics
        return MeanReversionMetrics(
            half_life=6.0,
            reversion_speed=0.1,
            long_term_mean=0.0,
            volatility_clustering=False,
            adf_statistic=0.0,
            p_value=1.0
        )


def detect_regime_changes(spreads: pd.Series, 
                         window_hours: int = 6, 
                         threshold_std: float = 2.0) -> int:
    """
    Detect regime changes in spread behavior using rolling statistics.
    
    Args:
        spreads: Time series of spread values
        window_hours: Window size for regime detection
        threshold_std: Standard deviation threshold for regime change
        
    Returns:
        Number of detected regime changes
    """
    try:
        clean_spreads = spreads.dropna()
        if len(clean_spreads) < window_hours * 2:
            return 0
        
        # Calculate rolling mean and std
        rolling_mean = clean_spreads.rolling(window=window_hours).mean()
        rolling_std = clean_spreads.rolling(window=window_hours).std()
        
        # Detect significant changes in mean
        mean_changes = rolling_mean.diff().abs()
        std_threshold = rolling_std.shift(1) * threshold_std
        
        # Count regime changes
        regime_changes = (mean_changes > std_threshold).sum()
        
        return int(regime_changes)
        
    except Exception:
        return 0