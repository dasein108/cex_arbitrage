#!/usr/bin/env python3
"""
Spread Calculator

High-precision spread calculation for arbitrage analysis.
Optimized for HFT systems with sub-millisecond performance.
"""

import logging
import statistics
from typing import List, Tuple, Dict, Optional
from msgspec import Struct
import numpy as np

# Add parent directories to path for imports
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from .data_loader import CandleData


class SpreadData(Struct):
    """Single spread calculation result"""
    timestamp: int
    mexc_price: float
    gateio_price: float
    spread_amount: float      # Absolute spread
    spread_percentage: float  # Percentage spread
    direction: str           # "mexc_higher" or "gateio_higher"


class SpreadCalculator:
    """
    High-precision spread calculator for arbitrage analysis.
    
    Features:
    - Sub-millisecond spread calculations
    - Multiple spread calculation methods
    - Statistical analysis of spread patterns
    - Direction and magnitude analysis
    """
    
    def __init__(self):
        """Initialize spread calculator"""
        self.logger = logging.getLogger(__name__)
    
    def calculate_spread(self, exchange1_candle: CandleData, exchange2_candle: CandleData, 
                        price_type: str = "close") -> SpreadData:
        """
        Calculate spread between two exchange candles.
        
        Args:
            exchange1_candle: First exchange candle data
            exchange2_candle: Second exchange candle data
            price_type: Price to use ("open", "close", "high", "low", "mid")
            
        Returns:
            SpreadData with calculation results
        """
        # Extract prices based on type
        exchange1_price = self._get_price(exchange1_candle, price_type)
        exchange2_price = self._get_price(exchange2_candle, price_type)
        
        if exchange1_price <= 0 or exchange2_price <= 0:
            raise ValueError(f"Invalid prices: Exchange1={exchange1_price}, Exchange2={exchange2_price}")
        
        # Calculate spread (Exchange2 - Exchange1)
        spread_amount = exchange2_price - exchange1_price
        spread_percentage = (spread_amount / exchange1_price) * 100
        
        # Determine direction (keeping legacy field names for compatibility)
        if spread_amount > 0:
            direction = "gateio_higher"  # Exchange2 higher
        elif spread_amount < 0:
            direction = "mexc_higher"    # Exchange1 higher
        else:
            direction = "equal"
        
        return SpreadData(
            timestamp=exchange1_candle.timestamp,
            mexc_price=exchange1_price,      # Legacy field name (Exchange1)
            gateio_price=exchange2_price,    # Legacy field name (Exchange2)
            spread_amount=abs(spread_amount),
            spread_percentage=abs(spread_percentage),
            direction=direction
        )
    
    def _get_price(self, candle: CandleData, price_type: str) -> float:
        """Extract specific price from candle data"""
        if price_type == "open":
            return candle.open_price
        elif price_type == "close":
            return candle.close_price
        elif price_type == "high":
            return candle.high_price
        elif price_type == "low":
            return candle.low_price
        elif price_type == "mid":
            return (candle.high_price + candle.low_price) / 2
        elif price_type == "typical":
            return (candle.high_price + candle.low_price + candle.close_price) / 3
        else:
            raise ValueError(f"Unknown price type: {price_type}")
    
    def calculate_batch_spreads(self, 
                               synchronized_pairs: List[Tuple[CandleData, CandleData]],
                               price_type: str = "close") -> List[SpreadData]:
        """
        Calculate spreads for a batch of synchronized candle pairs.
        
        Args:
            synchronized_pairs: List of (Exchange1, Exchange2) candle pairs
            price_type: Price type to use for calculations
            
        Returns:
            List of SpreadData results
        """
        spreads = []
        invalid_count = 0
        
        for exchange1_candle, exchange2_candle in synchronized_pairs:
            try:
                spread = self.calculate_spread(exchange1_candle, exchange2_candle, price_type)
                spreads.append(spread)
            except ValueError as e:
                invalid_count += 1
                self.logger.debug(f"Skipping invalid candle pair: {e}")
                continue
        
        if invalid_count > 0:
            self.logger.debug(f"Skipped {invalid_count} invalid candle pairs")
        
        return spreads
    
    def analyze_spread_patterns(self, spreads: List[SpreadData]) -> Dict[str, any]:
        """
        Analyze spread patterns for statistical insights.
        
        Args:
            spreads: List of spread calculations
            
        Returns:
            Dictionary with pattern analysis
        """
        if not spreads:
            return {'valid': False, 'reason': 'No spread data'}
        
        # Extract spread percentages for analysis
        spread_values = [s.spread_percentage for s in spreads]
        
        # Basic statistics
        basic_stats = {
            'count': len(spreads),
            'min_spread': min(spread_values),
            'max_spread': max(spread_values),
            'mean_spread': statistics.mean(spread_values),
            'median_spread': statistics.median(spread_values),
            'std_spread': statistics.stdev(spread_values) if len(spread_values) > 1 else 0
        }
        
        # Threshold analysis
        thresholds = [0.1, 0.3, 0.5, 1.0, 2.0]  # Percentage thresholds
        threshold_analysis = {}
        
        for threshold in thresholds:
            above_threshold = [s for s in spread_values if s >= threshold]
            threshold_analysis[f'above_{threshold}%'] = {
                'count': len(above_threshold),
                'percentage': len(above_threshold) / len(spreads) * 100
            }
        
        # Direction analysis (legacy field names maintained for compatibility)
        exchange1_higher_count = sum(1 for s in spreads if s.direction == "mexc_higher")
        exchange2_higher_count = sum(1 for s in spreads if s.direction == "gateio_higher")
        equal_count = sum(1 for s in spreads if s.direction == "equal")
        
        direction_analysis = {
            'exchange1_higher': {
                'count': exchange1_higher_count,
                'percentage': exchange1_higher_count / len(spreads) * 100
            },
            'exchange2_higher': {
                'count': exchange2_higher_count,
                'percentage': exchange2_higher_count / len(spreads) * 100
            },
            'equal': {
                'count': equal_count,
                'percentage': equal_count / len(spreads) * 100
            },
            # Legacy field names for backward compatibility
            'mexc_higher': {
                'count': exchange1_higher_count,
                'percentage': exchange1_higher_count / len(spreads) * 100
            },
            'gateio_higher': {
                'count': exchange2_higher_count,
                'percentage': exchange2_higher_count / len(spreads) * 100
            }
        }
        
        # Opportunity analysis (consecutive periods above threshold)
        opportunities = self._analyze_opportunities(spreads, threshold=0.3)
        
        return {
            'valid': True,
            'basic_stats': basic_stats,
            'threshold_analysis': threshold_analysis,
            'direction_analysis': direction_analysis,
            'opportunity_analysis': opportunities
        }
    
    def _analyze_opportunities(self, spreads: List[SpreadData], threshold: float) -> Dict[str, any]:
        """
        Analyze consecutive opportunities above threshold.
        
        Args:
            spreads: List of spread data
            threshold: Minimum spread percentage for opportunity
            
        Returns:
            Opportunity analysis results
        """
        if not spreads:
            return {}
        
        # Find consecutive periods above threshold
        opportunities = []
        current_opportunity = []
        
        for spread in spreads:
            if spread.spread_percentage >= threshold:
                current_opportunity.append(spread)
            else:
                if current_opportunity:
                    opportunities.append(current_opportunity)
                    current_opportunity = []
        
        # Don't forget the last opportunity if it ends at the data end
        if current_opportunity:
            opportunities.append(current_opportunity)
        
        if not opportunities:
            return {
                'opportunity_count': 0,
                'avg_duration_minutes': 0,
                'max_duration_minutes': 0,
                'total_opportunity_minutes': 0
            }
        
        # Calculate durations (each spread represents 1 minute)
        durations = [len(opp) for opp in opportunities]
        
        return {
            'opportunity_count': len(opportunities),
            'avg_duration_minutes': statistics.mean(durations),
            'max_duration_minutes': max(durations),
            'total_opportunity_minutes': sum(durations),
            'avg_spread_during_opportunities': statistics.mean([
                spread.spread_percentage 
                for opp in opportunities 
                for spread in opp
            ])
        }
    
    def calculate_volatility_during_spreads(self, spreads: List[SpreadData]) -> Dict[str, float]:
        """
        Calculate price volatility during spread periods.
        
        Args:
            spreads: List of spread data
            
        Returns:
            Volatility metrics
        """
        if len(spreads) < 2:
            return {'volatility': 0, 'price_stability': 100}
        
        # Calculate price changes (using legacy field names for compatibility)
        exchange1_prices = [s.mexc_price for s in spreads]    # Exchange1 prices
        exchange2_prices = [s.gateio_price for s in spreads]  # Exchange2 prices
        
        # Calculate returns (percentage change)
        exchange1_returns = [
            (exchange1_prices[i] - exchange1_prices[i-1]) / exchange1_prices[i-1] * 100
            for i in range(1, len(exchange1_prices))
        ]
        
        exchange2_returns = [
            (exchange2_prices[i] - exchange2_prices[i-1]) / exchange2_prices[i-1] * 100
            for i in range(1, len(exchange2_prices))
        ]
        
        # Calculate volatility (standard deviation of returns)
        exchange1_volatility = statistics.stdev(exchange1_returns) if exchange1_returns else 0
        exchange2_volatility = statistics.stdev(exchange2_returns) if exchange2_returns else 0
        avg_volatility = (exchange1_volatility + exchange2_volatility) / 2
        
        # Price stability score (inverse of volatility, scaled to 0-100)
        stability_score = max(0, 100 - (avg_volatility * 10))
        
        return {
            'exchange1_volatility': exchange1_volatility,
            'exchange2_volatility': exchange2_volatility,
            'avg_volatility': avg_volatility,
            'price_stability_score': stability_score,
            # Legacy field names for backward compatibility
            'mexc_volatility': exchange1_volatility,
            'gateio_volatility': exchange2_volatility
        }