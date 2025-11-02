"""
Simplified Adaptive Temporal Aggregation for High-Frequency Book Ticker Data

Core functionality:
- Multi-window statistics (short, medium, long-term)
- Simple 3-level signal confirmation 
- Noise filtering for microstructure effects
- Injection-ready for backtesting and real-time trading

Solves the 5-second timeframe performance degradation issue.
"""

import numpy as np
import pandas as pd
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union
from enum import Enum


class SignalLevel(Enum):
    LEVEL_1 = "level_1"  # Quick detection (30 seconds)
    LEVEL_2 = "level_2"  # Confirmation (2 minutes) 
    LEVEL_3 = "level_3"  # Validated execution (5+ minutes)


class SignalAction(Enum):
    HOLD = "HOLD"
    ENTER_LONG = "ENTER_LONG"
    ENTER_SHORT = "ENTER_SHORT" 
    EXIT = "EXIT"


@dataclass
class SignalResult:
    """Signal confirmation result with confidence and timing"""
    action: SignalAction
    confidence: float  # 0.0 to 1.0
    level: SignalLevel
    z_score_short: float
    z_score_medium: float
    z_score_long: float
    spread_filter_passed: bool
    reason: str


@dataclass
class BookTickerData:
    """Simplified book ticker data structure"""
    timestamp: datetime
    mexc_bid: float
    mexc_ask: float
    gateio_bid: float
    gateio_ask: float
    
    @property
    def mexc_mid(self) -> float:
        return (self.mexc_bid + self.mexc_ask) / 2
    
    @property
    def gateio_mid(self) -> float:
        return (self.gateio_bid + self.gateio_ask) / 2
    
    @property
    def price_differential(self) -> float:
        """MEXC vs Gate.io price differential as percentage"""
        if self.gateio_mid == 0:
            return 0.0
        return ((self.mexc_mid - self.gateio_mid) / self.gateio_mid) * 100
    
    @property
    def spread_quality_score(self) -> float:
        """Quality score based on spread tightness (higher = better)"""
        if self.mexc_mid == 0 or self.gateio_mid == 0:
            return 0.1
        mexc_spread = ((self.mexc_ask - self.mexc_bid) / self.mexc_mid) * 10000  # bps
        gateio_spread = ((self.gateio_ask - self.gateio_bid) / self.gateio_mid) * 10000  # bps
        avg_spread = (mexc_spread + gateio_spread) / 2
        if avg_spread == 0:
            return 1.0
        return max(0.1, min(1.0, 50 / avg_spread))  # Normalize to 0.1-1.0


class MultiWindowStatistics:
    """Maintains statistics across multiple temporal windows"""
    
    def __init__(self, 
                 short_window: int = 20,    # ~1.67 minutes at 5s
                 medium_window: int = 100,  # ~8.3 minutes at 5s
                 long_window: int = 240):   # ~20 minutes at 5s
        
        self.short_window = short_window
        self.medium_window = medium_window
        self.long_window = long_window
        
        # Use deques for efficient window management
        self.data = deque(maxlen=long_window)
        
        # Cached statistics
        self._last_stats = None
        self._last_update_size = 0
    
    def add_data_point(self, value: float) -> Dict[str, Dict[str, float]]:
        """Add new data point and return updated statistics"""
        self.data.append(value)
        
        # Only recalculate if we have new data
        if len(self.data) != self._last_update_size:
            self._last_stats = self._calculate_stats()
            self._last_update_size = len(self.data)
        
        return self._last_stats
    
    def _calculate_stats(self) -> Dict[str, Dict[str, float]]:
        """Calculate statistics for all windows"""
        if len(self.data) < self.short_window:
            return self._empty_stats()
        
        data_array = np.array(self.data)
        current_value = data_array[-1]
        
        stats = {}
        
        # Short window (spike detection)
        if len(data_array) >= self.short_window:
            short_data = data_array[-self.short_window:]
            stats['short'] = self._calc_window_stats(short_data, current_value)
        
        # Medium window (mean reversion)
        if len(data_array) >= self.medium_window:
            medium_data = data_array[-self.medium_window:]
            stats['medium'] = self._calc_window_stats(medium_data, current_value)
        
        # Long window (regime identification)
        if len(data_array) >= self.long_window:
            long_data = data_array[-self.long_window:]
            stats['long'] = self._calc_window_stats(long_data, current_value)
        
        return stats
    
    def _calc_window_stats(self, data: np.ndarray, current_value: float) -> Dict[str, float]:
        """Calculate statistics for a single window"""
        mean = np.mean(data)
        std = np.std(data)
        z_score = (current_value - mean) / std if std > 0 else 0.0
        
        return {
            'mean': mean,
            'std': std,
            'z_score': z_score,
            'current': current_value,
            'window_size': len(data)
        }
    
    def _empty_stats(self) -> Dict[str, Dict[str, float]]:
        """Return empty stats when insufficient data"""
        empty = {'mean': 0, 'std': 0, 'z_score': 0, 'current': 0, 'window_size': 0}
        return {'short': empty, 'medium': empty, 'long': empty}


class AdaptiveTemporalAggregator:
    """
    Simplified adaptive temporal aggregation for high-frequency trading
    
    Key features:
    - Multi-window statistics (short/medium/long term)
    - 3-level signal confirmation
    - Microstructure noise filtering
    - Simple volatility adaptation
    """
    
    def __init__(self,
                 base_timeframe_seconds: int = 5,
                 volatility_lookback: int = 60,  # 5 minutes for volatility calc
                 min_spread_quality: float = 0.3,  # Minimum spread quality score
                 confirmation_thresholds: Dict[str, float] = None):
        
        self.base_timeframe_seconds = base_timeframe_seconds
        self.volatility_lookback = volatility_lookback
        self.min_spread_quality = min_spread_quality
        
        # Signal confirmation thresholds
        self.thresholds = confirmation_thresholds or {
            'level_1': 1.0,  # Quick detection
            'level_2': 1.5,  # Confirmation
            'level_3': 2.0   # Strong signal
        }
        
        # Statistics engines
        self.price_diff_stats = MultiWindowStatistics()
        self.volatility_stats = MultiWindowStatistics(20, 60, 120)  # Shorter windows for vol
        
        # Signal history for persistence checking
        self.signal_history = deque(maxlen=24)  # 2 minutes of history at 5s
        
        # Performance tracking
        self.total_updates = 0
        self.filtered_signals = 0
        self.confirmed_signals = 0
    
    def process_update(self, book_ticker: BookTickerData) -> SignalResult:
        """Process new book ticker update and generate signal"""
        self.total_updates += 1
        
        # Extract price differential
        price_diff = book_ticker.price_differential
        
        # Update statistics
        diff_stats = self.price_diff_stats.add_data_point(price_diff)
        
        # Calculate volatility for adaptive thresholds
        volatility = self._calculate_recent_volatility()
        
        # Apply microstructure filters
        if not self._passes_microstructure_filters(book_ticker, diff_stats):
            self.filtered_signals += 1
            return SignalResult(
                action=SignalAction.HOLD,
                confidence=0.0,
                level=SignalLevel.LEVEL_1,
                z_score_short=diff_stats.get('short', {}).get('z_score', 0),
                z_score_medium=diff_stats.get('medium', {}).get('z_score', 0),
                z_score_long=diff_stats.get('long', {}).get('z_score', 0),
                spread_filter_passed=False,
                reason="microstructure_filter_rejected"
            )
        
        # Generate signal based on multi-window analysis
        signal = self._generate_confirmed_signal(diff_stats, volatility, book_ticker)
        
        # Track signal in history
        self.signal_history.append({
            'timestamp': book_ticker.timestamp,
            'signal': signal.action,
            'confidence': signal.confidence,
            'z_score': signal.z_score_short
        })
        
        if signal.action != SignalAction.HOLD:
            self.confirmed_signals += 1
        
        return signal
    
    def _calculate_recent_volatility(self) -> float:
        """Calculate recent volatility for adaptive thresholds"""
        if len(self.price_diff_stats.data) < self.volatility_lookback:
            return 1.0  # Default multiplier
        
        recent_data = list(self.price_diff_stats.data)[-self.volatility_lookback:]
        returns = np.diff(recent_data)
        volatility = np.std(returns) if len(returns) > 1 else 0.1
        
        # Return volatility multiplier (higher vol = more sensitive thresholds)
        baseline_vol = 0.1  # Baseline 0.1% volatility
        return max(0.5, min(2.0, volatility / baseline_vol))
    
    def _passes_microstructure_filters(self, 
                                     book_ticker: BookTickerData, 
                                     diff_stats: Dict) -> bool:
        """Simple microstructure noise filters"""
        
        # Filter 1: Minimum spread quality
        if book_ticker.spread_quality_score < self.min_spread_quality:
            return False
        
        # Filter 2: Minimum price differential
        if abs(book_ticker.price_differential) < 0.05:  # 0.05% minimum
            return False
        
        # Filter 3: Require some statistical significance in short window
        short_stats = diff_stats.get('short', {})
        if short_stats.get('window_size', 0) < 10:  # Need at least 10 data points
            return False
        
        return True
    
    def _generate_confirmed_signal(self, 
                                 diff_stats: Dict, 
                                 volatility_multiplier: float,
                                 book_ticker: BookTickerData) -> SignalResult:
        """Generate signal with 3-level confirmation"""
        
        # Extract z-scores from different windows
        z_short = diff_stats.get('short', {}).get('z_score', 0)
        z_medium = diff_stats.get('medium', {}).get('z_score', 0) 
        z_long = diff_stats.get('long', {}).get('z_score', 0)
        
        # Adjust thresholds for volatility
        adj_thresholds = {
            level: threshold / volatility_multiplier 
            for level, threshold in self.thresholds.items()
        }
        
        # Determine signal level and action
        level, action, confidence = self._evaluate_signal_levels(
            z_short, z_medium, z_long, adj_thresholds
        )
        
        # Add persistence bonus
        persistence_bonus = self._calculate_persistence_bonus()
        confidence = min(1.0, confidence + persistence_bonus)
        
        return SignalResult(
            action=action,
            confidence=confidence,
            level=level,
            z_score_short=z_short,
            z_score_medium=z_medium,
            z_score_long=z_long,
            spread_filter_passed=True,
            reason=f"confirmed_{level.value}_vol_{volatility_multiplier:.2f}"
        )
    
    def _evaluate_signal_levels(self, 
                               z_short: float, 
                               z_medium: float, 
                               z_long: float,
                               thresholds: Dict[str, float]) -> Tuple[SignalLevel, SignalAction, float]:
        """Evaluate signal across confirmation levels"""
        
        # Use absolute values for threshold comparison
        abs_z_short = abs(z_short)
        abs_z_medium = abs(z_medium)
        abs_z_long = abs(z_long)
        
        # Determine signal direction (positive = MEXC higher, negative = Gate.io higher)
        direction = 1 if z_short > 0 else -1
        
        # Level 3: Strong signal (all windows confirm)
        if (abs_z_short >= thresholds['level_3'] and 
            abs_z_medium >= thresholds['level_2'] and
            abs_z_long >= thresholds['level_1']):
            
            action = SignalAction.ENTER_SHORT if direction > 0 else SignalAction.ENTER_LONG
            confidence = min(1.0, (abs_z_short + abs_z_medium + abs_z_long) / 6.0)
            return SignalLevel.LEVEL_3, action, confidence
        
        # Level 2: Medium signal (short + medium confirm)
        elif (abs_z_short >= thresholds['level_2'] and 
              abs_z_medium >= thresholds['level_1']):
            
            action = SignalAction.ENTER_SHORT if direction > 0 else SignalAction.ENTER_LONG
            confidence = min(0.8, (abs_z_short + abs_z_medium) / 4.0)
            return SignalLevel.LEVEL_2, action, confidence
        
        # Level 1: Quick signal (short window only)
        elif abs_z_short >= thresholds['level_1']:
            
            action = SignalAction.ENTER_SHORT if direction > 0 else SignalAction.ENTER_LONG
            confidence = min(0.6, abs_z_short / 2.0)
            return SignalLevel.LEVEL_1, action, confidence
        
        # No signal
        return SignalLevel.LEVEL_1, SignalAction.HOLD, 0.0
    
    def _calculate_persistence_bonus(self) -> float:
        """Calculate bonus for persistent signals"""
        if len(self.signal_history) < 5:
            return 0.0
        
        recent_signals = [h['signal'] for h in list(self.signal_history)[-5:]]
        non_hold_signals = [s for s in recent_signals if s != SignalAction.HOLD]
        
        if len(non_hold_signals) >= 3:
            # Check if signals are in same direction
            if all(s == non_hold_signals[0] for s in non_hold_signals):
                return 0.1  # 10% confidence bonus for persistence
        
        return 0.0
    
    def get_performance_stats(self) -> Dict[str, Union[int, float]]:
        """Get aggregator performance statistics"""
        return {
            'total_updates': self.total_updates,
            'filtered_signals': self.filtered_signals,
            'confirmed_signals': self.confirmed_signals,
            'filter_rate': self.filtered_signals / max(1, self.total_updates),
            'signal_rate': self.confirmed_signals / max(1, self.total_updates),
            'current_data_points': len(self.price_diff_stats.data)
        }
    
    def reset(self):
        """Reset all statistics and history"""
        self.price_diff_stats = MultiWindowStatistics()
        self.volatility_stats = MultiWindowStatistics(20, 60, 120)
        self.signal_history.clear()
        self.total_updates = 0
        self.filtered_signals = 0
        self.confirmed_signals = 0


# Helper function for easy integration
def create_temporal_aggregator(timeframe_seconds: int = 5, 
                             conservative: bool = True) -> AdaptiveTemporalAggregator:
    """Create pre-configured temporal aggregator"""
    
    if conservative:
        # Conservative settings - fewer false positives
        thresholds = {'level_1': 1.2, 'level_2': 1.8, 'level_3': 2.5}
        min_spread_quality = 0.4
    else:
        # Aggressive settings - more signals
        thresholds = {'level_1': 0.8, 'level_2': 1.3, 'level_3': 1.8}
        min_spread_quality = 0.2
    
    return AdaptiveTemporalAggregator(
        base_timeframe_seconds=timeframe_seconds,
        min_spread_quality=min_spread_quality,
        confirmation_thresholds=thresholds
    )