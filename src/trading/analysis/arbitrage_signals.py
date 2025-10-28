"""Arbitrage signal generation based on statistical thresholds."""

from typing import Dict, List, Tuple
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
    reason: str


def calculate_arb_signals(
    mexc_vs_gateio_futures_history: List[float],
    gateio_spot_vs_futures_history: List[float],
    current_mexc_vs_gateio_futures: float,
    current_gateio_spot_vs_futures: float
) -> ArbSignal:
    """
    Calculate arbitrage entry/exit signals based on statistical thresholds.
    
    Entry Signal: When mexc_vs_gateio_futures < 25th percentile of minimums
    Exit Signal: When gateio_spot_vs_futures > 25th percentile of maximums
    
    Args:
        mexc_vs_gateio_futures_history: Historical spread between MEXC spot and Gate.io futures
        gateio_spot_vs_futures_history: Historical spread between Gate.io spot and futures
        current_mexc_vs_gateio_futures: Current MEXC vs Gate.io futures spread
        current_gateio_spot_vs_futures: Current Gate.io spot vs futures spread
        
    Returns:
        ArbSignal with entry/exit/hold signal and statistics
    """
    # Calculate rolling min/max for windows (e.g., every 100 samples)
    window_size = min(100, len(mexc_vs_gateio_futures_history) // 10)
    if window_size < 10:
        window_size = 10
    
    # Get rolling minimums for mexc_vs_gateio_futures
    mexc_gateio_array = np.array(mexc_vs_gateio_futures_history)
    mexc_gateio_mins = []
    for i in range(0, len(mexc_gateio_array) - window_size + 1, window_size // 2):
        window = mexc_gateio_array[i:i + window_size]
        mexc_gateio_mins.append(np.min(window))
    
    # Get rolling maximums for gateio_spot_vs_futures  
    gateio_array = np.array(gateio_spot_vs_futures_history)
    gateio_maxs = []
    for i in range(0, len(gateio_array) - window_size + 1, window_size // 2):
        window = gateio_array[i:i + window_size]
        gateio_maxs.append(np.max(window))
    
    # Calculate 25th percentiles
    mexc_gateio_min_25pct = np.percentile(mexc_gateio_mins, 25) if mexc_gateio_mins else current_mexc_vs_gateio_futures
    gateio_max_25pct = np.percentile(gateio_maxs, 25) if gateio_maxs else current_gateio_spot_vs_futures
    
    # Calculate means
    mexc_gateio_mean = np.mean(mexc_vs_gateio_futures_history)
    gateio_mean = np.mean(gateio_spot_vs_futures_history)
    
    # Create stats objects
    mexc_gateio_stats = ArbStats(
        min_25pct=mexc_gateio_min_25pct,
        max_25pct=np.percentile([np.max(mexc_gateio_array[i:i + window_size]) 
                                 for i in range(0, len(mexc_gateio_array) - window_size + 1, window_size // 2)], 25) 
                  if len(mexc_gateio_array) >= window_size else current_mexc_vs_gateio_futures,
        mean=mexc_gateio_mean,
        current=current_mexc_vs_gateio_futures
    )
    
    gateio_stats = ArbStats(
        min_25pct=np.percentile([np.min(gateio_array[i:i + window_size]) 
                                 for i in range(0, len(gateio_array) - window_size + 1, window_size // 2)], 25)
                  if len(gateio_array) >= window_size else current_gateio_spot_vs_futures,
        max_25pct=gateio_max_25pct,
        mean=gateio_mean,
        current=current_gateio_spot_vs_futures
    )
    
    # Generate signal
    signal = Signal.HOLD
    reason = "No signal triggered"
    
    # Check ENTER condition: mexc_vs_gateio_futures < 25th percentile of minimums
    if current_mexc_vs_gateio_futures < mexc_gateio_min_25pct:
        signal = Signal.ENTER
        reason = f"MEXC vs Gate.io futures spread ({current_mexc_vs_gateio_futures:.4f}) < 25th percentile min ({mexc_gateio_min_25pct:.4f})"
    
    # Check EXIT condition: gateio_spot_vs_futures > 25th percentile of maximums
    elif current_gateio_spot_vs_futures > gateio_max_25pct:
        signal = Signal.EXIT
        reason = f"Gate.io spot vs futures spread ({current_gateio_spot_vs_futures:.4f}) > 25th percentile max ({gateio_max_25pct:.4f})"
    
    return ArbSignal(
        signal=signal,
        mexc_vs_gateio_futures=mexc_gateio_stats,
        gateio_spot_vs_futures=gateio_stats,
        reason=reason
    )


def calculate_arb_signals_simple(
    mexc_vs_gateio_futures_history: List[float],
    gateio_spot_vs_futures_history: List[float],
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