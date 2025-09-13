#!/usr/bin/env python3
"""
Metrics Calculator

Comprehensive metrics calculation for arbitrage analysis.
Implements all 15 required metrics with HFT precision.
"""

import logging
import statistics
from typing import List, Dict, Any
from msgspec import Struct

# Add parent directories to path for imports
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from .spread_calculator import SpreadData
from .data_loader import CandleData


class MetricsCalculator:
    """
    Calculate comprehensive arbitrage metrics.
    
    Implements all 15 required metrics:
    - Basic spread statistics (max, avg, median)
    - Threshold analysis (>0.3%, >0.5%)
    - Opportunity characteristics (duration, frequency)
    - Scoring metrics (liquidity, execution, risk, profit)
    """
    
    def __init__(self):
        """Initialize metrics calculator"""
        self.logger = logging.getLogger(__name__)
    
    def calculate_all_metrics(self, 
                            symbol: str,
                            spreads: List[SpreadData],
                            mexc_candles: List[CandleData],
                            gateio_candles: List[CandleData],
                            analysis_days: int) -> Dict[str, Any]:
        """
        Calculate all required metrics for a trading pair.
        
        Args:
            symbol: Trading pair symbol
            spreads: List of spread calculations
            mexc_candles: MEXC candle data for volume analysis
            gateio_candles: Gate.io candle data for volume analysis
            analysis_days: Number of days in analysis period
            
        Returns:
            Dictionary with all 15 required metrics
        """
        if not spreads:
            return self._empty_metrics(symbol)
        
        # Basic spread statistics
        spread_values = [s.spread_percentage for s in spreads]
        
        basic_metrics = {
            'pair': symbol,
            'max_spread': max(spread_values),
            'avg_spread': statistics.mean(spread_values),
            'med_spread': statistics.median(spread_values)
        }
        
        # Threshold analysis
        threshold_metrics = self._calculate_threshold_metrics(spreads, analysis_days)
        
        # Opportunity characteristics
        opportunity_metrics = self._calculate_opportunity_metrics(spreads, analysis_days)
        
        # Scoring metrics
        scoring_metrics = self._calculate_scoring_metrics(
            spreads, mexc_candles, gateio_candles
        )
        
        # Combine all metrics
        all_metrics = {
            **basic_metrics,
            **threshold_metrics,
            **opportunity_metrics,
            **scoring_metrics
        }
        
        return all_metrics
    
    def _calculate_threshold_metrics(self, spreads: List[SpreadData], analysis_days: int) -> Dict[str, Any]:
        """Calculate threshold-based metrics"""
        spread_values = [s.spread_percentage for s in spreads]
        total_count = len(spreads)
        
        # Count spreads above thresholds
        count_03 = sum(1 for s in spread_values if s >= 0.3)
        count_05 = sum(1 for s in spread_values if s >= 0.5)
        
        return {
            'spread_>0.3%': (count_03 / total_count * 100) if total_count > 0 else 0,
            'count_>0.3%': count_03,
            'spread_>0.5%': (count_05 / total_count * 100) if total_count > 0 else 0,
            'count_>0.5%': count_05
        }
    
    def _calculate_opportunity_metrics(self, spreads: List[SpreadData], analysis_days: int) -> Dict[str, any]:
        """Calculate opportunity timing and duration metrics"""
        if not spreads:
            return {
                'opportunity_minutes_per_day': 0,
                'avg_duration_seconds': 0
            }
        
        # Find consecutive opportunities (>0.3% threshold)
        opportunities = []
        current_opportunity = []
        
        for spread in spreads:
            if spread.spread_percentage >= 0.3:
                current_opportunity.append(spread)
            else:
                if current_opportunity:
                    opportunities.append(current_opportunity)
                    current_opportunity = []
        
        # Don't forget the last opportunity
        if current_opportunity:
            opportunities.append(current_opportunity)
        
        # Calculate opportunity minutes per day
        total_opportunity_minutes = sum(len(opp) for opp in opportunities)
        opportunity_minutes_per_day = total_opportunity_minutes / max(1, analysis_days)
        
        # Calculate average duration in seconds (each candle = 1 minute = 60 seconds)
        if opportunities:
            durations_minutes = [len(opp) for opp in opportunities]
            avg_duration_minutes = statistics.mean(durations_minutes)
            avg_duration_seconds = avg_duration_minutes * 60
        else:
            avg_duration_seconds = 0
        
        return {
            'opportunity_minutes_per_day': opportunity_minutes_per_day,
            'avg_duration_seconds': avg_duration_seconds
        }
    
    def _calculate_scoring_metrics(self, 
                                 spreads: List[SpreadData],
                                 mexc_candles: List[CandleData],
                                 gateio_candles: List[CandleData]) -> Dict[str, any]:
        """Calculate scoring metrics (0-100 scale)"""
        
        # Liquidity Score (based on volume)
        liquidity_score = self._calculate_liquidity_score(mexc_candles, gateio_candles)
        
        # Execution Score (based on spread stability and frequency)
        execution_score = self._calculate_execution_score(spreads)
        
        # Risk Score (based on volatility and spread variability)
        risk_score = self._calculate_risk_score(spreads, mexc_candles, gateio_candles)
        
        # Profit Score (risk-adjusted profit potential)
        profit_score = self._calculate_profit_score(spreads, risk_score, execution_score)
        
        return {
            'liquidity_score': liquidity_score,
            'execution_score': execution_score,
            'risk_score': risk_score,
            'profit_score': profit_score,
            'composite_rank': 0  # Will be set during ranking
        }
    
    def _calculate_liquidity_score(self, mexc_candles: List[CandleData], gateio_candles: List[CandleData]) -> float:
        """
        Calculate liquidity score based on trading volume.
        Score: 0-100 (higher = better liquidity)
        """
        if not mexc_candles or not gateio_candles:
            return 0
        
        # Calculate average volumes
        mexc_avg_volume = statistics.mean([c.quote_volume for c in mexc_candles])
        gateio_avg_volume = statistics.mean([c.quote_volume for c in gateio_candles])
        
        # Combined average volume
        combined_volume = (mexc_avg_volume + gateio_avg_volume) / 2
        
        # Volume consistency (lower standard deviation = better)
        mexc_vol_std = statistics.stdev([c.quote_volume for c in mexc_candles]) if len(mexc_candles) > 1 else 0
        gateio_vol_std = statistics.stdev([c.quote_volume for c in gateio_candles]) if len(gateio_candles) > 1 else 0
        
        avg_vol_std = (mexc_vol_std + gateio_vol_std) / 2
        consistency_factor = 1 / (1 + avg_vol_std / max(combined_volume, 1))
        
        # Score based on volume level and consistency
        # Assume good liquidity starts at $100k average volume
        volume_score = min(100, (combined_volume / 100000) * 50)
        consistency_score = consistency_factor * 50
        
        return min(100, volume_score + consistency_score)
    
    def _calculate_execution_score(self, spreads: List[SpreadData]) -> float:
        """
        Calculate execution feasibility score.
        Score: 0-100 (higher = easier to execute)
        """
        if not spreads:
            return 0
        
        spread_values = [s.spread_percentage for s in spreads]
        
        # Frequency factor (more opportunities = better)
        profitable_spreads = [s for s in spread_values if s >= 0.3]
        frequency_factor = len(profitable_spreads) / len(spreads)
        
        # Spread size factor (larger spreads = better, but diminishing returns)
        if profitable_spreads:
            avg_profitable_spread = statistics.mean(profitable_spreads)
            spread_factor = min(1, avg_profitable_spread / 2.0)  # Cap at 2%
        else:
            spread_factor = 0
        
        # Consistency factor (lower spread volatility = better)
        if len(spread_values) > 1:
            spread_std = statistics.stdev(spread_values)
            spread_mean = statistics.mean(spread_values)
            consistency_factor = 1 / (1 + spread_std / max(spread_mean, 0.01))
        else:
            consistency_factor = 1
        
        # Combined execution score
        execution_score = (frequency_factor * 40 + spread_factor * 40 + consistency_factor * 20)
        
        return min(100, execution_score)
    
    def _calculate_risk_score(self, 
                            spreads: List[SpreadData],
                            mexc_candles: List[CandleData], 
                            gateio_candles: List[CandleData]) -> float:
        """
        Calculate risk score.
        Score: 0-100 (higher = more risky)
        """
        if not spreads or not mexc_candles or not gateio_candles:
            return 100  # Maximum risk if no data
        
        # Price volatility risk
        mexc_prices = [c.close_price for c in mexc_candles]
        gateio_prices = [c.close_price for c in gateio_candles]
        
        mexc_returns = [
            (mexc_prices[i] - mexc_prices[i-1]) / mexc_prices[i-1] * 100
            for i in range(1, len(mexc_prices))
        ] if len(mexc_prices) > 1 else [0]
        
        gateio_returns = [
            (gateio_prices[i] - gateio_prices[i-1]) / gateio_prices[i-1] * 100
            for i in range(1, len(gateio_prices))
        ] if len(gateio_prices) > 1 else [0]
        
        volatility_risk = (statistics.stdev(mexc_returns + gateio_returns) if mexc_returns + gateio_returns else 0) * 2
        
        # Spread variability risk
        spread_values = [s.spread_percentage for s in spreads]
        spread_variability = statistics.stdev(spread_values) if len(spread_values) > 1 else 0
        spread_risk = spread_variability * 10
        
        # Correlation breakdown risk (higher when prices move in opposite directions)
        if len(mexc_returns) == len(gateio_returns) and len(mexc_returns) > 5:
            correlation = self._calculate_correlation(mexc_returns, gateio_returns)
            correlation_risk = (1 - abs(correlation)) * 30
        else:
            correlation_risk = 15  # Moderate risk if insufficient data
        
        # Combined risk score
        total_risk = min(100, volatility_risk + spread_risk + correlation_risk)
        
        return total_risk
    
    def _calculate_profit_score(self, spreads: List[SpreadData], risk_score: float, execution_score: float) -> float:
        """
        Calculate risk-adjusted profit score.
        Score: 0-100 (higher = better profit potential)
        """
        if not spreads:
            return 0
        
        spread_values = [s.spread_percentage for s in spreads]
        
        # Raw profit potential (based on spread size and frequency)
        profitable_spreads = [s for s in spread_values if s >= 0.3]
        
        if profitable_spreads:
            avg_spread = statistics.mean(profitable_spreads)
            frequency = len(profitable_spreads) / len(spreads)
            raw_profit = avg_spread * frequency * 20  # Scale factor
        else:
            raw_profit = 0
        
        # Risk adjustment (lower risk = higher score)
        risk_adjustment = (100 - risk_score) / 100
        
        # Execution adjustment (higher execution score = higher profit)
        execution_adjustment = execution_score / 100
        
        # Combined profit score
        profit_score = raw_profit * risk_adjustment * execution_adjustment
        
        return min(100, profit_score)
    
    def _calculate_correlation(self, x_values: List[float], y_values: List[float]) -> float:
        """Calculate Pearson correlation coefficient"""
        if len(x_values) != len(y_values) or len(x_values) < 2:
            return 0
        
        n = len(x_values)
        sum_x = sum(x_values)
        sum_y = sum(y_values)
        sum_xy = sum(x * y for x, y in zip(x_values, y_values))
        sum_x2 = sum(x * x for x in x_values)
        sum_y2 = sum(y * y for y in y_values)
        
        denominator = ((n * sum_x2 - sum_x * sum_x) * (n * sum_y2 - sum_y * sum_y)) ** 0.5
        
        if denominator == 0:
            return 0
        
        correlation = (n * sum_xy - sum_x * sum_y) / denominator
        return correlation
    
    def _empty_metrics(self, symbol: str) -> Dict[str, any]:
        """Return empty metrics structure for symbols with no data"""
        return {
            'pair': symbol,
            'max_spread': 0,
            'avg_spread': 0,
            'med_spread': 0,
            'spread_>0.3%': 0,
            'count_>0.3%': 0,
            'spread_>0.5%': 0,
            'count_>0.5%': 0,
            'opportunity_minutes_per_day': 0,
            'avg_duration_seconds': 0,
            'liquidity_score': 0,
            'execution_score': 0,
            'risk_score': 100,
            'profit_score': 0,
            'composite_rank': 999
        }
    
    def rank_opportunities(self, metrics_list: List[Dict[str, any]]) -> List[Dict[str, any]]:
        """
        Rank opportunities by profit score and assign composite_rank.
        
        Args:
            metrics_list: List of metrics dictionaries
            
        Returns:
            Sorted list with composite_rank assigned
        """
        # Sort by profit_score (descending)
        sorted_metrics = sorted(metrics_list, key=lambda x: x['profit_score'], reverse=True)
        
        # Assign ranks
        for i, metrics in enumerate(sorted_metrics):
            metrics['composite_rank'] = i + 1
        
        return sorted_metrics