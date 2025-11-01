"""
Dynamic Parameters Optimizer for Maker Limit Strategy

Adjusts tick offsets and tolerances based on real-time market conditions.
"""

from typing import Dict, List
from .market_state_tracker import SimpleMarketState
from infrastructure.logging import get_logger


class DynamicParameters:
    """Optimizes strategy parameters based on market conditions."""
    
    def __init__(self, market_state: SimpleMarketState, base_config: Dict):
        """Initialize dynamic parameter optimizer.
        
        Args:
            market_state: Market state tracker instance
            base_config: Base configuration with default parameters
        """
        self.state = market_state
        self.logger = get_logger("DynamicParameters")
        
        # Base parameters from configuration
        self.base_tick_offset = base_config.get('ticks_offset', 2)
        self.base_tick_tolerance = base_config.get('tick_tolerance', 5)
        
        # Parameter adjustment ranges
        self.min_tick_offset = 1
        self.max_tick_offset = max(self.base_tick_offset + 3, 6)
        self.min_tick_tolerance = max(self.base_tick_tolerance - 2, 2)
        self.max_tick_tolerance = self.base_tick_tolerance + 5
        
        # Market condition thresholds
        self.low_volatility_threshold = 0.5  # 0.5%
        self.medium_volatility_threshold = 1.0  # 1.0%
        self.high_volatility_threshold = 2.0  # 2.0%
        
        # Trend detection parameters
        self.trend_detection_periods = 15  # 15 minutes for trend analysis
        self.trend_threshold = 0.002  # 0.2% price movement to detect trend
        
        # Logging control
        self.last_log_time = 0
        self.last_parameters = {}
        
    def get_dynamic_tick_offset(self) -> int:
        """Calculate optimal tick offset based on current market conditions.
        
        Returns:
            Optimized tick offset value
        """
        base = self.base_tick_offset
        
        # Get volatility assessment
        volatility_level = self._assess_volatility()
        
        if volatility_level == "low":
            # More aggressive in low volatility (smaller offset)
            adjustment = -1
        elif volatility_level == "medium":
            # Slightly more conservative
            adjustment = 1
        elif volatility_level == "high":
            # Much more conservative (larger offset)
            adjustment = 2
        else:
            # Unknown/insufficient data - use base
            adjustment = 0
        
        # Apply bounds
        optimized_offset = max(self.min_tick_offset, 
                              min(self.max_tick_offset, base + adjustment))
        
        return optimized_offset
    
    def get_dynamic_tick_tolerance(self) -> int:
        """Calculate optimal tick tolerance based on market movement patterns.
        
        Returns:
            Optimized tick tolerance value
        """
        base = self.base_tick_tolerance
        
        # Check if market is trending
        is_trending = self._is_trending_market()
        volatility_level = self._assess_volatility()
        
        adjustment = 0
        
        if is_trending:
            # Allow more movement in trending markets
            adjustment += 2
        
        if volatility_level == "high":
            # Allow more movement in volatile markets
            adjustment += 3
        elif volatility_level == "low":
            # Tighter tolerance in stable markets
            adjustment -= 1
        
        # Apply bounds
        optimized_tolerance = max(self.min_tick_tolerance,
                                 min(self.max_tick_tolerance, base + adjustment))
        
        return optimized_tolerance
    
    def _assess_volatility(self) -> str:
        """Assess current market volatility level.
        
        Returns:
            "low", "medium", "high", or "unknown"
        """
        recent_prices = self.state.get_recent_prices(minutes=20)
        
        if len(recent_prices['spot_prices']) < 10:
            return "unknown"
        
        spot_prices = recent_prices['spot_prices']
        
        # Calculate volatility as price range percentage
        price_range = max(spot_prices) - min(spot_prices)
        current_price = spot_prices[-1]
        volatility_pct = (price_range / current_price) * 100
        
        if volatility_pct <= self.low_volatility_threshold:
            return "low"
        elif volatility_pct <= self.medium_volatility_threshold:
            return "medium"
        elif volatility_pct <= self.high_volatility_threshold:
            return "high"
        else:
            return "extreme"  # Treat extreme as high
    
    def _is_trending_market(self) -> bool:
        """Detect if market is in trending mode using simple price slope.
        
        Returns:
            True if market appears to be trending
        """
        recent_prices = self.state.get_recent_prices(minutes=self.trend_detection_periods)
        
        if len(recent_prices['spot_prices']) < 10:
            return False
        
        prices = recent_prices['spot_prices']
        
        # Simple trend detection: compare first half vs second half
        mid_point = len(prices) // 2
        first_half_avg = sum(prices[:mid_point]) / mid_point
        second_half_avg = sum(prices[mid_point:]) / (len(prices) - mid_point)
        
        # Calculate trend strength
        trend_strength = abs(second_half_avg - first_half_avg) / first_half_avg
        
        return trend_strength > self.trend_threshold
    
    def _is_high_liquidity(self) -> bool:
        """Assess if current market has high liquidity (low spreads).
        
        Returns:
            True if market appears to have good liquidity
        """
        recent_spreads = self.state.get_recent_spreads(minutes=5)
        
        if not recent_spreads['spot_spreads']:
            return False
        
        avg_spot_spread = sum(recent_spreads['spot_spreads']) / len(recent_spreads['spot_spreads'])
        
        # Consider high liquidity if spot spread is below 0.1%
        return avg_spot_spread < 0.1
    
    def get_optimized_parameters(self) -> Dict[str, int]:
        """Get all optimized parameters in one call.
        
        Returns:
            Dict with optimized tick_offset and tick_tolerance
        """
        optimized = {
            'tick_offset': self.get_dynamic_tick_offset(),
            'tick_tolerance': self.get_dynamic_tick_tolerance()
        }
        
        # Log parameter changes
        self._log_parameter_changes(optimized)
        
        return optimized
    
    def get_market_assessment(self) -> Dict:
        """Get detailed market condition assessment.
        
        Returns:
            Dict with market condition analysis
        """
        return {
            'volatility_level': self._assess_volatility(),
            'is_trending': self._is_trending_market(),
            'high_liquidity': self._is_high_liquidity(),
            'data_points': len(self.state.spot_prices),
            'base_tick_offset': self.base_tick_offset,
            'base_tick_tolerance': self.base_tick_tolerance,
        }
    
    def _log_parameter_changes(self, new_parameters: Dict):
        """Log parameter changes for monitoring."""
        
        import time
        current_time = time.time()
        
        # Check if parameters changed or enough time passed for periodic log
        parameters_changed = new_parameters != self.last_parameters
        time_for_periodic_log = current_time - self.last_log_time > 600  # 10 minutes
        
        if parameters_changed or time_for_periodic_log:
            market_assessment = self.get_market_assessment()
            
            log_message = (f"📊 Dynamic Parameters: "
                          f"offset={new_parameters['tick_offset']} (base={self.base_tick_offset}), "
                          f"tolerance={new_parameters['tick_tolerance']} (base={self.base_tick_tolerance})")
            
            if parameters_changed:
                log_message += f" | Market: {market_assessment['volatility_level']} volatility"
                if market_assessment['is_trending']:
                    log_message += ", trending"
                if market_assessment['high_liquidity']:
                    log_message += ", high liquidity"
                
                self.logger.info(log_message)
            else:
                self.logger.debug(log_message)
            
            self.last_parameters = new_parameters.copy()
            self.last_log_time = current_time
    
    def force_parameter_update(self) -> Dict:
        """Force immediate parameter calculation and return detailed results."""
        
        optimized = self.get_optimized_parameters()
        assessment = self.get_market_assessment()
        
        return {
            'optimized_parameters': optimized,
            'market_assessment': assessment,
            'parameter_changes': {
                'tick_offset_change': optimized['tick_offset'] - self.base_tick_offset,
                'tick_tolerance_change': optimized['tick_tolerance'] - self.base_tick_tolerance
            }
        }