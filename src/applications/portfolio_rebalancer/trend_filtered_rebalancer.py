"""
Trend-filtered rebalancer that avoids rebalancing during strong trends.
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime
import numpy as np

from .config import (
    RebalanceConfig, PortfolioState, RebalanceAction, 
    RebalanceEvent, ActionType
)
from .portfolio_tracker import PortfolioTracker
from .rebalancer import ThresholdCascadeRebalancer


class TrendFilteredRebalancer(ThresholdCascadeRebalancer):
    """
    Enhanced rebalancer that filters out trades during strong trending conditions.
    
    Only rebalances during mean-reverting market conditions to improve win rate
    and reduce drawdowns.
    """
    
    def __init__(self, assets: List[str], config: RebalanceConfig, tracker: PortfolioTracker):
        """
        Initialize trend-filtered rebalancer.
        
        Args:
            assets: List of asset symbols to manage
            config: Rebalancing configuration
            tracker: Portfolio state tracker
        """
        super().__init__(assets, config, tracker)
        
        # Trend detection parameters
        self.trend_lookback_periods = 20  # Number of price points for trend analysis
        self.short_ma_periods = 5         # Short-term moving average
        self.trend_threshold = 0.03       # 3% threshold for strong trend detection
        self.mean_reversion_threshold = 0.05  # 5% threshold for mean reversion
        
        # Price history tracking for trend analysis
        self.price_history: Dict[str, List[float]] = {asset: [] for asset in assets}
        
        # Track trend filtering statistics
        self.trend_filter_stats = {
            'total_checks': 0,
            'trend_filtered': 0,
            'mean_reversion_allowed': 0,
            'insufficient_data': 0
        }
    
    def update_price_history(self, prices: Dict[str, float]):
        """
        Update price history for trend analysis.
        
        Args:
            prices: Current prices for all assets
        """
        for asset, price in prices.items():
            if asset in self.price_history:
                self.price_history[asset].append(price)
                
                # Keep only the required lookback period
                if len(self.price_history[asset]) > self.trend_lookback_periods:
                    self.price_history[asset] = self.price_history[asset][-self.trend_lookback_periods:]
    
    def calculate_trend_metrics(self, asset: str) -> Dict:
        """
        Calculate trend metrics for an asset.
        
        Args:
            asset: Asset symbol
            
        Returns:
            Dictionary with trend analysis metrics
        """
        if asset not in self.price_history or len(self.price_history[asset]) < self.short_ma_periods:
            return {
                'has_sufficient_data': False,
                'trend_strength': 0,
                'trend_direction': 'neutral',
                'distance_from_ma': 0,
                'is_mean_reverting': False
            }
        
        prices = np.array(self.price_history[asset])
        current_price = prices[-1]
        
        # Calculate moving averages
        if len(prices) >= self.trend_lookback_periods:
            ma_long = np.mean(prices)
            ma_short = np.mean(prices[-self.short_ma_periods:])
        else:
            # Use available data
            ma_long = np.mean(prices)
            ma_short = np.mean(prices[-min(self.short_ma_periods, len(prices)):])
        
        # Calculate trend strength and direction
        trend_strength = abs(ma_short - ma_long) / ma_long if ma_long > 0 else 0
        trend_direction = 'up' if ma_short > ma_long else 'down' if ma_short < ma_long else 'neutral'
        
        # Calculate distance from long-term MA
        distance_from_ma = abs(current_price - ma_long) / ma_long if ma_long > 0 else 0
        
        # Check if price is mean-reverting (moving back towards MA)
        is_mean_reverting = distance_from_ma < self.mean_reversion_threshold
        
        # Additional mean reversion check: price direction vs MA
        if len(prices) >= 3:
            price_momentum = (current_price - prices[-3]) / prices[-3] if prices[-3] > 0 else 0
            ma_momentum = (ma_short - ma_long) / ma_long if ma_long > 0 else 0
            
            # Mean reversion: price moving opposite to trend
            is_mean_reverting = is_mean_reverting or (price_momentum * ma_momentum < 0)
        
        return {
            'has_sufficient_data': True,
            'trend_strength': trend_strength,
            'trend_direction': trend_direction,
            'distance_from_ma': distance_from_ma,
            'is_mean_reverting': is_mean_reverting,
            'ma_long': ma_long,
            'ma_short': ma_short,
            'current_price': current_price
        }
    
    def should_allow_rebalance(self, asset: str, deviation: float, direction: str) -> Tuple[bool, str]:
        """
        Check if rebalancing should be allowed based on trend analysis.
        
        Args:
            asset: Asset symbol
            deviation: Price deviation from portfolio mean
            direction: 'upside' or 'downside' rebalancing direction
            
        Returns:
            Tuple of (allow_rebalance, reason)
        """
        self.trend_filter_stats['total_checks'] += 1
        
        trend_metrics = self.calculate_trend_metrics(asset)
        
        if not trend_metrics['has_sufficient_data']:
            self.trend_filter_stats['insufficient_data'] += 1
            return True, "Insufficient data for trend analysis"
        
        trend_strength = trend_metrics['trend_strength']
        trend_direction = trend_metrics['trend_direction']
        is_mean_reverting = trend_metrics['is_mean_reverting']
        
        # Check for strong trend - avoid rebalancing
        if trend_strength > self.trend_threshold:
            # Strong trend detected
            if direction == 'upside' and trend_direction == 'up':
                # Asset is outperforming AND trending up - might continue
                self.trend_filter_stats['trend_filtered'] += 1
                return False, f"Strong uptrend detected ({trend_strength:.2%}), avoiding sell"
            
            elif direction == 'downside' and trend_direction == 'down':
                # Asset is underperforming AND trending down - might continue
                self.trend_filter_stats['trend_filtered'] += 1
                return False, f"Strong downtrend detected ({trend_strength:.2%}), avoiding buy"
        
        # Check for mean reversion opportunity
        if is_mean_reverting:
            self.trend_filter_stats['mean_reversion_allowed'] += 1
            return True, f"Mean reversion opportunity detected"
        
        # Default: allow rebalancing if no strong trend against the direction
        return True, f"No strong trend conflict, proceeding with rebalance"
    
    def check_rebalance_needed(self, state: PortfolioState) -> Optional[Tuple[str, float, str]]:
        """
        Enhanced rebalance check with trend filtering.
        
        Args:
            state: Current portfolio state
            
        Returns:
            Tuple of (symbol, deviation, action) if rebalancing needed, None otherwise
        """
        # Update price history
        current_prices = {asset: asset_state.current_price for asset, asset_state in state.assets.items()}
        self.update_price_history(current_prices)
        
        # Get traditional rebalance trigger
        trigger = super().check_rebalance_needed(state)
        
        if not trigger:
            return None
        
        symbol, deviation, direction = trigger
        
        # Apply trend filter
        should_rebalance, reason = self.should_allow_rebalance(symbol, deviation, direction)
        
        if not should_rebalance:
            # Log the filtered rebalance
            print(f"  [TREND FILTER] {symbol} rebalance blocked: {reason}")
            return None
        
        print(f"  [TREND FILTER] {symbol} rebalance allowed: {reason}")
        return trigger
    
    def get_trend_statistics(self) -> Dict:
        """
        Get trend filtering statistics.
        
        Returns:
            Dictionary of trend filtering statistics
        """
        stats = self.trend_filter_stats.copy()
        
        if stats['total_checks'] > 0:
            stats['filter_rate'] = stats['trend_filtered'] / stats['total_checks']
            stats['mean_reversion_rate'] = stats['mean_reversion_allowed'] / stats['total_checks']
        else:
            stats['filter_rate'] = 0
            stats['mean_reversion_rate'] = 0
        
        return stats
    
    def get_current_trend_status(self) -> Dict:
        """
        Get current trend status for all assets.
        
        Returns:
            Dictionary of current trend metrics for each asset
        """
        trend_status = {}
        
        for asset in self.assets:
            metrics = self.calculate_trend_metrics(asset)
            
            if metrics['has_sufficient_data']:
                trend_status[asset] = {
                    'trend_direction': metrics['trend_direction'],
                    'trend_strength': f"{metrics['trend_strength']:.2%}",
                    'distance_from_ma': f"{metrics['distance_from_ma']:.2%}",
                    'is_mean_reverting': metrics['is_mean_reverting'],
                    'current_vs_ma': f"{((metrics['current_price'] / metrics['ma_long']) - 1):.2%}" if metrics['ma_long'] > 0 else "N/A"
                }
            else:
                trend_status[asset] = {
                    'status': 'Insufficient data for trend analysis'
                }
        
        return trend_status
    
    def get_statistics(self) -> Dict:
        """
        Get enhanced statistics including trend filtering.
        
        Returns:
            Dictionary of statistics
        """
        base_stats = super().get_statistics()
        trend_stats = self.get_trend_statistics()
        
        # Combine statistics
        enhanced_stats = {**base_stats, **trend_stats}
        
        return enhanced_stats