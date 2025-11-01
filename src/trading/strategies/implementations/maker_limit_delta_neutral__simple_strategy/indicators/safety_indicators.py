"""
Safety Indicators for Maker Limit Strategy

Core safety checks to prevent trading during adverse market conditions.
"""

from typing import Tuple, Dict, List
from .market_state_tracker import SimpleMarketState
from infrastructure.logging import get_logger


class SafetyIndicators:
    """Implements core safety checks for market making strategy."""
    
    def __init__(self, market_state: SimpleMarketState, config: Dict):
        """Initialize safety indicators.
        
        Args:
            market_state: Market state tracker instance
            config: Safety configuration dict
        """
        self.state = market_state
        self.logger = get_logger("SafetyIndicators")
        
        # Safety thresholds
        self.max_volatility_threshold = config.get('max_volatility_pct', 2.0)  # 2%
        self.max_spread_ratio = config.get('max_spread_ratio', 1.5)  # futures <= 1.5x spot
        self.min_data_points = config.get('min_data_points', 10)
        
        # Logging control
        self.last_log_time = 0
        self.log_interval = 300  # Log safety status every 5 minutes
        
    def is_safe_to_trade(self) -> Tuple[bool, str]:
        """Single method to check all safety conditions.
        
        Returns:
            Tuple of (is_safe: bool, reason: str)
        """
        
        # 1. Check if we have sufficient data
        if not self._has_sufficient_data():
            return True, "insufficient_data"
        
        # 2. Check spread inversion (most critical)
        if self._spreads_inverted():
            return False, "spreads_inverted"
        
        # 3. Check excessive volatility
        if self._is_too_volatile():
            return False, "high_volatility"
        
        # 4. Check for data freshness
        if not self._data_is_fresh():
            return False, "stale_data"
        
        # Periodic logging of safety status
        self._log_safety_status_periodic()
        
        return True, "safe"
    
    def _has_sufficient_data(self) -> bool:
        """Check if we have enough data points for analysis."""
        has_data = (self.state.initialized and 
                   len(self.state.spot_prices) >= self.min_data_points)
        
        if not has_data:
            self.logger.debug(f"Insufficient data: {len(self.state.spot_prices)}/{self.min_data_points} points")
        
        return has_data
    
    def _spreads_inverted(self) -> bool:
        """Check if futures spread is significantly wider than spot spread.
        
        Returns True if futures trading should be avoided due to wide spreads.
        """
        recent_spreads = self.state.get_recent_spreads(minutes=5)
        
        if not recent_spreads['spot_spreads'] or not recent_spreads['futures_spreads']:
            self.logger.warning("No spread data available, blocking trading")
            return True  # Conservative: block if no spread data
        
        # Calculate average spreads over last 5 minutes
        avg_spot_spread = sum(recent_spreads['spot_spreads']) / len(recent_spreads['spot_spreads'])
        avg_futures_spread = sum(recent_spreads['futures_spreads']) / len(recent_spreads['futures_spreads'])
        
        # Check if futures spread is too wide relative to spot
        spread_ratio = avg_futures_spread / avg_spot_spread if avg_spot_spread > 0 else float('inf')
        spreads_inverted = spread_ratio > self.max_spread_ratio
        
        if spreads_inverted:
            self.logger.warning(f"🚫 Spreads inverted: futures={avg_futures_spread:.4f}% vs "
                              f"spot={avg_spot_spread:.4f}% (ratio={spread_ratio:.2f})")
        
        return spreads_inverted
    
    def _is_too_volatile(self) -> bool:
        """Check if recent price volatility is too high.
        
        Returns True if volatility exceeds safe trading thresholds.
        """
        recent_prices = self.state.get_recent_prices(minutes=20)
        
        if len(recent_prices['spot_prices']) < 10:  # Need at least 10 minutes
            self.logger.debug("Insufficient price history for volatility check")
            return True  # Conservative: block if insufficient data
        
        spot_prices = recent_prices['spot_prices']
        
        # Calculate price range volatility
        price_range = max(spot_prices) - min(spot_prices)
        current_price = spot_prices[-1]
        volatility_pct = (price_range / current_price) * 100
        
        is_volatile = volatility_pct > self.max_volatility_threshold
        
        if is_volatile:
            self.logger.warning(f"⚠️ High volatility detected: {volatility_pct:.3f}% > {self.max_volatility_threshold}%")
        
        return is_volatile
    
    def _data_is_fresh(self) -> bool:
        """Check if market data is recent enough for trading decisions."""
        
        if not self.state.last_update:
            return False
        
        import time
        data_age = time.time() - self.state.last_update
        max_age = 300  # 5 minutes max age
        
        is_fresh = data_age < max_age
        
        if not is_fresh:
            self.logger.warning(f"🕐 Stale market data: {data_age:.0f}s old")
        
        return is_fresh
    
    def get_safety_metrics(self) -> Dict:
        """Get current safety metrics for monitoring."""
        
        recent_spreads = self.state.get_recent_spreads(minutes=5)
        recent_prices = self.state.get_recent_prices(minutes=20)
        
        metrics = {
            'data_points': len(self.state.spot_prices),
            'data_sufficient': self._has_sufficient_data(),
            'data_fresh': self._data_is_fresh(),
        }
        
        # Add spread metrics
        if recent_spreads['spot_spreads'] and recent_spreads['futures_spreads']:
            avg_spot_spread = sum(recent_spreads['spot_spreads']) / len(recent_spreads['spot_spreads'])
            avg_futures_spread = sum(recent_spreads['futures_spreads']) / len(recent_spreads['futures_spreads'])
            spread_ratio = avg_futures_spread / avg_spot_spread if avg_spot_spread > 0 else 0
            
            metrics.update({
                'avg_spot_spread_pct': avg_spot_spread,
                'avg_futures_spread_pct': avg_futures_spread,
                'spread_ratio': spread_ratio,
                'spreads_safe': spread_ratio <= self.max_spread_ratio
            })
        
        # Add volatility metrics
        if len(recent_prices['spot_prices']) >= 10:
            spot_prices = recent_prices['spot_prices']
            price_range = max(spot_prices) - min(spot_prices)
            current_price = spot_prices[-1]
            volatility_pct = (price_range / current_price) * 100
            
            metrics.update({
                'volatility_pct': volatility_pct,
                'volatility_safe': volatility_pct <= self.max_volatility_threshold
            })
        
        return metrics
    
    def _log_safety_status_periodic(self):
        """Log safety status periodically for monitoring."""
        
        import time
        current_time = time.time()
        
        if current_time - self.last_log_time < self.log_interval:
            return
        
        metrics = self.get_safety_metrics()
        
        self.logger.info(f"🛡️ Safety Status: "
                        f"Data: {metrics.get('data_points', 0)} points, "
                        f"Spreads: {metrics.get('spreads_safe', 'unknown')}, "
                        f"Volatility: {metrics.get('volatility_pct', 0):.3f}%, "
                        f"Fresh: {metrics.get('data_fresh', False)}")
        
        self.last_log_time = current_time
    
    def force_safety_check(self) -> Dict:
        """Force immediate safety check and return detailed results."""
        
        is_safe, reason = self.is_safe_to_trade()
        metrics = self.get_safety_metrics()
        
        return {
            'is_safe': is_safe,
            'reason': reason,
            'metrics': metrics,
            'timestamp': self.state.last_update
        }