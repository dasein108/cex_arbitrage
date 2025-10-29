"""Arbitrage signal generation based on statistical thresholds."""

from typing import Dict, Tuple, Union
from dataclasses import dataclass
import numpy as np

from trading.analysis.structs import Signal


@dataclass
class ArbStats:
    """Statistics for arbitrage spreads."""
    min_25pct: float  # 25th percentile of minimum values
    max_25pct: float  # 25th percentile of maximum values
    mean: float
    current: float
    

@dataclass
class ArbSignal:
    """Arbitrage trading signal."""
    signal: Signal
    mexc_vs_gateio_futures: ArbStats
    gateio_spot_vs_futures: ArbStats


def calculate_arb_signals(
    mexc_vs_gateio_futures_history: Union[np.ndarray, list],
    gateio_spot_vs_futures_history: Union[np.ndarray, list],
    current_mexc_vs_gateio_futures: float,
    current_gateio_spot_vs_futures: float,
    window_size: int = 10
) -> ArbSignal:
    """
    Calculate arbitrage entry/exit signals based on statistical thresholds.
    
    Entry Signal: When mexc_vs_gateio_futures < 25th percentile of minimums
    Exit Signal: When gateio_spot_vs_futures > 25th percentile of maximums
    
    Args:
        mexc_vs_gateio_futures_history: Historical spread between MEXC spot and Gate.io futures (numpy array or list)
        gateio_spot_vs_futures_history: Historical spread between Gate.io spot and futures (numpy array or list)
        current_mexc_vs_gateio_futures: Current MEXC vs Gate.io futures spread
        current_gateio_spot_vs_futures: Current Gate.io spot vs futures spread
        window_size: Rolling window size for calculating statistics
        
    Returns:
        ArbSignal with entry/exit/hold signal and statistics
    """
    # Convert to numpy arrays if not already (zero-copy if already numpy array)
    mexc_gateio_array = np.asarray(mexc_vs_gateio_futures_history, dtype=np.float64)
    gateio_array = np.asarray(gateio_spot_vs_futures_history, dtype=np.float64)
    
    # Early return if insufficient data
    if len(mexc_gateio_array) < window_size or len(gateio_array) < window_size:
        mexc_gateio_stats = ArbStats(
            min_25pct=current_mexc_vs_gateio_futures,
            max_25pct=current_mexc_vs_gateio_futures,
            mean=current_mexc_vs_gateio_futures,
            current=current_mexc_vs_gateio_futures
        )
        gateio_stats = ArbStats(
            min_25pct=current_gateio_spot_vs_futures,
            max_25pct=current_gateio_spot_vs_futures,
            mean=current_gateio_spot_vs_futures,
            current=current_gateio_spot_vs_futures
        )
        return ArbSignal(
            signal=Signal.HOLD,
            mexc_vs_gateio_futures=mexc_gateio_stats,
            gateio_spot_vs_futures=gateio_stats
        )
    
    # Vectorized rolling window operations using numpy strides for better performance
    step = window_size // 2
    
    # Calculate rolling minimums for mexc_vs_gateio_futures using broadcasting
    mexc_windows = np.lib.stride_tricks.sliding_window_view(mexc_gateio_array, window_size)[::step]
    mexc_gateio_mins = np.min(mexc_windows, axis=1)
    
    # Calculate rolling maximums for gateio_spot_vs_futures using broadcasting  
    gateio_windows = np.lib.stride_tricks.sliding_window_view(gateio_array, window_size)[::step]
    gateio_maxs = np.max(gateio_windows, axis=1)
    mexc_gateio_maxs = np.max(mexc_windows, axis=1)
    gateio_mins = np.min(gateio_windows, axis=1)
    
    # Calculate 25th percentiles using vectorized operations
    mexc_gateio_min_25pct = np.percentile(mexc_gateio_mins, 25)
    mexc_gateio_max_25pct = np.percentile(mexc_gateio_maxs, 25)
    gateio_min_25pct = np.percentile(gateio_mins, 25)
    gateio_max_25pct = np.percentile(gateio_maxs, 25)
    
    # Calculate means using vectorized operations
    mexc_gateio_mean = np.mean(mexc_gateio_array)
    gateio_mean = np.mean(gateio_array)



    # Create stats objects with vectorized statistics
    mexc_gateio_stats = ArbStats(
        min_25pct=mexc_gateio_min_25pct,
        max_25pct=mexc_gateio_max_25pct,
        mean=mexc_gateio_mean,
        current=current_mexc_vs_gateio_futures
    )
    
    gateio_stats = ArbStats(
        min_25pct=gateio_min_25pct,
        max_25pct=gateio_max_25pct,
        mean=gateio_mean,
        current=current_gateio_spot_vs_futures
    )
    
    # Generate signal
    signal = Signal.HOLD
    
    # Check ENTER condition: mexc_vs_gateio_futures < 25th percentile of minimums
    if current_mexc_vs_gateio_futures < mexc_gateio_min_25pct:
        signal = Signal.ENTER
    
    # Check EXIT condition: gateio_spot_vs_futures > 25th percentile of maximums
    elif current_gateio_spot_vs_futures > gateio_max_25pct:
        signal = Signal.EXIT
    
    return ArbSignal(
        signal=signal,
        mexc_vs_gateio_futures=mexc_gateio_stats,
        gateio_spot_vs_futures=gateio_stats
    )


def calculate_arb_signals_simple(
    mexc_vs_gateio_futures_history: Union[np.ndarray, list],
    gateio_spot_vs_futures_history: Union[np.ndarray, list],
    current_mexc_vs_gateio_futures: float,
    current_gateio_spot_vs_futures: float
) -> Tuple[Signal, Dict[str, float]]:
    """
    Simplified version returning just signal and thresholds.
    
    Returns:
        Tuple of (Signal, dict with thresholds)
    """
    result = calculate_arb_signals(
        mexc_vs_gateio_futures_history,
        gateio_spot_vs_futures_history,
        current_mexc_vs_gateio_futures,
        current_gateio_spot_vs_futures
    )
    
    thresholds = {
        "mexc_gateio_min_25pct": result.mexc_vs_gateio_futures.min_25pct,
        "gateio_max_25pct": result.gateio_spot_vs_futures.max_25pct,
        "mexc_gateio_current": current_mexc_vs_gateio_futures,
        "gateio_current": current_gateio_spot_vs_futures
    }
    
    return result.signal, thresholds