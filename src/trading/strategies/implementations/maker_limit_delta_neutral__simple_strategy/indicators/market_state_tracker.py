"""
Market State Tracker for Maker Limit Strategy

Maintains rolling history of prices and spreads with real-time updates.
"""

import time
from collections import deque
from typing import Dict, List
from exchanges.structs import BookTicker
from infrastructure.logging import get_logger


class SimpleMarketState:
    """Tracks rolling market state with minimal memory footprint."""
    
    def __init__(self, max_history_minutes: int = 120):
        """Initialize market state tracker.
        
        Args:
            max_history_minutes: Maximum minutes of history to keep (default: 2 hours)
        """
        self.logger = get_logger("SimpleMarketState")
        
        # Price tracking for volatility calculation
        self.spot_prices = deque(maxlen=max_history_minutes)
        self.futures_prices = deque(maxlen=max_history_minutes)
        
        # Spread tracking for safety checks
        self.spot_spreads = deque(maxlen=max_history_minutes)
        self.futures_spreads = deque(maxlen=max_history_minutes)
        
        # Timestamps for data alignment
        self.timestamps = deque(maxlen=max_history_minutes)
        
        # Update control
        self.last_update = 0
        self.update_interval = 60  # Update indicators every 60 seconds
        
        # State flags
        self.initialized = False
        
    def load_initial_data(self, historical_data: Dict):
        """Load initial historical data from DB loader."""
        
        try:
            # Load historical data if available
            if historical_data['spot_prices']:
                self.spot_prices.extend(historical_data['spot_prices'])
                self.futures_prices.extend(historical_data['futures_prices'])
                self.spot_spreads.extend(historical_data['spot_spreads'])
                self.futures_spreads.extend(historical_data['futures_spreads'])
                self.timestamps.extend(historical_data['timestamps'])
                
                self.logger.info(f"✅ Loaded {len(self.spot_prices)} historical data points")
            else:
                self.logger.info("📊 Starting with empty history (real-time only mode)")
            
            self.initialized = True
            
        except Exception as e:
            self.logger.error(f"Error loading initial data: {e}")
            self.initialized = True  # Continue with empty state
    
    def update_real_time(self, spot_book: BookTicker, futures_book: BookTicker):
        """Update market state with real-time book ticker data."""
        
        current_time = time.time()
        
        # Rate limit updates to avoid noise
        if current_time - self.last_update < self.update_interval:
            return
        
        try:
            # Calculate mid prices
            spot_mid = (spot_book.bid_price + spot_book.ask_price) / 2
            futures_mid = (futures_book.bid_price + futures_book.ask_price) / 2
            
            # Calculate spread percentages
            spot_spread_pct = ((spot_book.ask_price - spot_book.bid_price) / spot_mid) * 100
            futures_spread_pct = ((futures_book.ask_price - futures_book.bid_price) / futures_mid) * 100
            
            # Append to rolling history
            self.spot_prices.append(spot_mid)
            self.futures_prices.append(futures_mid)
            self.spot_spreads.append(spot_spread_pct)
            self.futures_spreads.append(futures_spread_pct)
            self.timestamps.append(current_time)
            
            self.last_update = current_time
            
            # Log periodic updates
            if len(self.spot_prices) % 30 == 0:  # Every 30 minutes
                self.logger.debug(f"📊 Market state updated: {len(self.spot_prices)} data points, "
                                f"spot: {spot_mid:.6f}, futures: {futures_mid:.6f}")
                
        except Exception as e:
            self.logger.error(f"Error updating market state: {e}")
    
    def get_recent_prices(self, minutes: int = 20) -> Dict[str, List[float]]:
        """Get recent price data for analysis.
        
        Args:
            minutes: Number of recent minutes to return
            
        Returns:
            Dict with spot_prices and futures_prices lists
        """
        if not self.spot_prices:
            return {'spot_prices': [], 'futures_prices': []}
        
        # Return last N minutes of data
        n_points = min(minutes, len(self.spot_prices))
        
        return {
            'spot_prices': list(self.spot_prices)[-n_points:],
            'futures_prices': list(self.futures_prices)[-n_points:]
        }
    
    def get_recent_spreads(self, minutes: int = 5) -> Dict[str, List[float]]:
        """Get recent spread data for safety checks.
        
        Args:
            minutes: Number of recent minutes to return
            
        Returns:
            Dict with spot_spreads and futures_spreads lists  
        """
        if not self.spot_spreads:
            return {'spot_spreads': [], 'futures_spreads': []}
        
        # Return last N minutes of data
        n_points = min(minutes, len(self.spot_spreads))
        
        return {
            'spot_spreads': list(self.spot_spreads)[-n_points:],
            'futures_spreads': list(self.futures_spreads)[-n_points:]
        }
    
    def get_current_state(self) -> Dict:
        """Get current market state snapshot."""
        
        if not self.spot_prices:
            return {
                'spot_price': None,
                'futures_price': None,
                'spot_spread': None,
                'futures_spread': None,
                'data_points': 0,
                'initialized': self.initialized
            }
        
        return {
            'spot_price': self.spot_prices[-1],
            'futures_price': self.futures_prices[-1],
            'spot_spread': self.spot_spreads[-1],
            'futures_spread': self.futures_spreads[-1],
            'data_points': len(self.spot_prices),
            'initialized': self.initialized,
            'last_update': self.last_update
        }
    
    def has_sufficient_data(self, min_points: int = 10) -> bool:
        """Check if we have sufficient data for analysis."""
        return len(self.spot_prices) >= min_points
    
    def clear_old_data(self, max_age_hours: int = 24):
        """Clear data older than specified hours (optional cleanup)."""
        
        if not self.timestamps:
            return
        
        current_time = time.time()
        cutoff_time = current_time - (max_age_hours * 3600)
        
        # Find first index to keep
        keep_from = 0
        for i, timestamp in enumerate(self.timestamps):
            if timestamp >= cutoff_time:
                keep_from = i
                break
        
        if keep_from > 0:
            # Convert deques to lists, slice, and recreate deques
            self.spot_prices = deque(list(self.spot_prices)[keep_from:], maxlen=self.spot_prices.maxlen)
            self.futures_prices = deque(list(self.futures_prices)[keep_from:], maxlen=self.futures_prices.maxlen)
            self.spot_spreads = deque(list(self.spot_spreads)[keep_from:], maxlen=self.spot_spreads.maxlen)
            self.futures_spreads = deque(list(self.futures_spreads)[keep_from:], maxlen=self.futures_spreads.maxlen)
            self.timestamps = deque(list(self.timestamps)[keep_from:], maxlen=self.timestamps.maxlen)
            
            self.logger.info(f"🧹 Cleaned old data, kept {len(self.spot_prices)} recent points")