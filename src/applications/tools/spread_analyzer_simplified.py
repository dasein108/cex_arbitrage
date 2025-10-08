"""
Simplified Spread Analyzer for Historical Analysis

Streamlined spread analysis engine focused exclusively on historical
pattern analysis and statistical indicators for informed trading decisions.

Key Features:
- Historical pattern recognition
- Statistical analysis (volatility, trends, percentiles)
- Performance metrics calculation
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional
from statistics import mean, stdev, median
import math
import logging

import msgspec
import numpy as np

# Import from same directory/package
try:
    from .data_fetcher import UnifiedSnapshot, MultiSymbolDataFetcher
except ImportError:
    from data_fetcher import UnifiedSnapshot, MultiSymbolDataFetcher

logger = logging.getLogger(__name__)


class SpreadStatistics(msgspec.Struct):
    """
    Statistical analysis of spreads over time.
    """
    period_start: datetime
    period_end: datetime
    sample_count: int
    
    # Basic statistics
    mean_spread: float
    median_spread: float
    std_deviation: float
    min_spread: float
    max_spread: float
    
    # Percentiles
    p25: float
    p75: float
    p90: float
    p95: float
    p99: float
    
    # Trend analysis
    trend_direction: str  # 'expanding', 'contracting', 'stable'
    volatility_regime: str  # 'low', 'medium', 'high'
    
    # Opportunity metrics
    profitable_opportunities: int  # Count above threshold
    opportunity_rate: float       # Opportunities per hour


class SpreadAnalyzer:
    """
    Simplified spread analysis engine for historical arbitrage analysis.
    
    Provides focused statistical analysis for optimal arbitrage timing
    and risk management across any trading symbol.
    """
    
    # Default arbitrage threshold
    DEFAULT_ENTRY_THRESHOLD = 0.1  # 0.1% spread to identify opportunities
    
    def __init__(
        self, 
        data_fetcher: MultiSymbolDataFetcher,
        entry_threshold_pct: float = DEFAULT_ENTRY_THRESHOLD
    ):
        self.data_fetcher = data_fetcher
        self.entry_threshold = entry_threshold_pct / 100.0  # Convert to decimal
        self.logger = logger.getChild("SpreadAnalyzer")
    
    async def get_historical_statistics(
        self, 
        hours_back: int = 24,
        spread_type: str = 'auto'
    ) -> Optional[SpreadStatistics]:
        """
        Calculate comprehensive historical spread statistics.
        
        Args:
            hours_back: Number of hours to analyze
            spread_type: Type of spread analysis ('auto', 'gateio_mexc', 'internal_futures', etc.)
            
        Returns:
            SpreadStatistics object with comprehensive analysis
        """
        self.logger.info(f"Calculating historical statistics for {hours_back}h")
        
        try:
            # Get historical data
            snapshots = await self.data_fetcher.get_historical_snapshots(hours_back)
            if not snapshots:
                self.logger.warning("No historical data available")
                return None
            
            self.logger.info(f"Retrieved {len(snapshots)} historical {self.data_fetcher.symbol_str} snapshots ({hours_back}h)")
            
            # Auto-detect best spread type
            if spread_type == 'auto':
                spread_type = self._detect_best_spread_type(snapshots)
                self.logger.info(f"Auto-detected spread type: {spread_type}")
            
            # Extract spreads based on type
            spreads = self._extract_spreads_by_type(snapshots, spread_type)
            
            if not spreads:
                self.logger.warning(f"No valid {spread_type} spreads found in historical data")
                return None
            
            self.logger.info(f"Using {spread_type} analysis (found {len(spreads)} valid spreads)")
            
            # Calculate basic statistics
            spreads_array = np.array(spreads)
            
            # Basic stats
            mean_spread = float(np.mean(spreads_array))
            median_spread = float(np.median(spreads_array))
            std_deviation = float(np.std(spreads_array))
            min_spread = float(np.min(spreads_array))
            max_spread = float(np.max(spreads_array))
            
            # Percentiles
            p25 = float(np.percentile(spreads_array, 25))
            p75 = float(np.percentile(spreads_array, 75))
            p90 = float(np.percentile(spreads_array, 90))
            p95 = float(np.percentile(spreads_array, 95))
            p99 = float(np.percentile(spreads_array, 99))
            
            # Trend analysis
            trend_direction = self._analyze_trend(spreads)
            volatility_regime = self._determine_volatility_regime(std_deviation, mean_spread)
            
            # Opportunity analysis
            profitable_opportunities = len([s for s in spreads if s > self.entry_threshold])
            opportunity_rate = (profitable_opportunities / hours_back) if hours_back > 0 else 0
            
            # Period analysis
            period_start = snapshots[0].timestamp
            period_end = snapshots[-1].timestamp
            
            stats = SpreadStatistics(
                period_start=period_start,
                period_end=period_end,
                sample_count=len(spreads),
                mean_spread=mean_spread,
                median_spread=median_spread,
                std_deviation=std_deviation,
                min_spread=min_spread,
                max_spread=max_spread,
                p25=p25,
                p75=p75,
                p90=p90,
                p95=p95,
                p99=p99,
                trend_direction=trend_direction,
                volatility_regime=volatility_regime,
                profitable_opportunities=profitable_opportunities,
                opportunity_rate=opportunity_rate
            )
            
            self.logger.info(f"Calculated {spread_type} statistics over {hours_back}h: {len(spreads)} samples, {profitable_opportunities} opportunities")
            return stats
            
        except Exception as e:
            self.logger.error(f"Failed to calculate historical statistics: {e}")
            return None
    
    async def get_volatility_metrics(self) -> Dict:
        """
        Calculate volatility metrics for risk assessment.
        
        Returns:
            Dictionary with volatility analysis
        """
        try:
            # Get recent data for volatility calculation
            snapshots = await self.data_fetcher.get_historical_snapshots(6)  # 6 hours for volatility
            if not snapshots or len(snapshots) < 10:
                return {"error": "Insufficient data for volatility calculation"}
            
            # Extract spreads
            spreads = self._extract_spreads_by_type(snapshots, 'auto')
            if not spreads or len(spreads) < 10:
                return {"error": "Insufficient spread data for volatility calculation"}
            
            spreads_array = np.array(spreads)
            
            # Calculate volatility metrics
            volatility = float(np.std(spreads_array))
            mean_spread = float(np.mean(spreads_array))
            cv = volatility / mean_spread if mean_spread > 0 else 0  # Coefficient of variation
            
            # Rolling volatility (if enough data)
            if len(spreads) >= 20:
                # Calculate 20-period rolling volatility
                rolling_vol = []
                for i in range(19, len(spreads)):
                    window = spreads_array[i-19:i+1]
                    rolling_vol.append(float(np.std(window)))
                
                current_rolling_vol = rolling_vol[-1] if rolling_vol else volatility
                avg_rolling_vol = float(np.mean(rolling_vol)) if rolling_vol else volatility
            else:
                current_rolling_vol = volatility
                avg_rolling_vol = volatility
            
            return {
                "volatility": round(volatility, 6),
                "coefficient_of_variation": round(cv, 4),
                "current_rolling_volatility": round(current_rolling_vol, 6),
                "average_rolling_volatility": round(avg_rolling_vol, 6),
                "volatility_regime": self._determine_volatility_regime(volatility, mean_spread),
                "sample_count": len(spreads)
            }
            
        except Exception as e:
            self.logger.warning(f"Could not calculate volatility metrics: {e}")
            return {"error": str(e)}
    
    def _detect_best_spread_type(self, snapshots: List[UnifiedSnapshot]) -> str:
        """Detect the best spread type based on data availability."""
        # Count available data for each type
        gateio_mexc_count = 0
        internal_futures_count = 0
        
        for snapshot in snapshots[:100]:  # Sample first 100 snapshots
            # Check Gate.io vs MEXC arbitrage availability
            if (snapshot.gateio_spot_bid and snapshot.mexc_spot_ask and 
                snapshot.mexc_spot_bid and snapshot.gateio_spot_ask):
                gateio_mexc_count += 1
            
            # Check Gate.io internal futures spread availability
            if (snapshot.gateio_spot_bid and snapshot.gateio_futures_ask and
                snapshot.gateio_futures_bid and snapshot.gateio_spot_ask):
                internal_futures_count += 1
        
        # Return the type with the most available data
        if internal_futures_count > gateio_mexc_count:
            return 'internal_futures'
        elif gateio_mexc_count > 0:
            return 'gateio_mexc'
        else:
            return 'internal_futures'  # Fallback
    
    def _extract_spreads_by_type(self, snapshots: List[UnifiedSnapshot], spread_type: str) -> List[float]:
        """Extract spreads based on the specified type."""
        spreads = []
        
        for snapshot in snapshots:
            if spread_type == 'gateio_mexc':
                # Cross-exchange arbitrage spreads
                cross_spreads = snapshot.get_cross_exchange_spreads()
                
                # Use the better of the two directions
                spread1 = cross_spreads.get('gateio_mexc_sell_buy', 0)
                spread2 = cross_spreads.get('mexc_gateio_sell_buy', 0)
                
                if spread1 > 0 or spread2 > 0:
                    best_spread = max(spread1, spread2)
                    # Convert to percentage
                    if spread1 > spread2 and snapshot.gateio_spot_bid and snapshot.mexc_spot_ask:
                        mid_price = (snapshot.gateio_spot_bid + snapshot.mexc_spot_ask) / 2
                        spread_pct = (best_spread / mid_price) * 100
                        spreads.append(spread_pct)
                    elif spread2 > 0 and snapshot.mexc_spot_bid and snapshot.gateio_spot_ask:
                        mid_price = (snapshot.mexc_spot_bid + snapshot.gateio_spot_ask) / 2
                        spread_pct = (best_spread / mid_price) * 100
                        spreads.append(spread_pct)
                        
            elif spread_type == 'internal_futures':
                # Gate.io spot vs futures spread
                if (snapshot.gateio_spot_bid and snapshot.gateio_futures_ask and
                    snapshot.gateio_futures_bid and snapshot.gateio_spot_ask):
                    
                    # Calculate both directions
                    spread1 = snapshot.gateio_spot_bid - snapshot.gateio_futures_ask  # Long spot, short futures
                    spread2 = snapshot.gateio_futures_bid - snapshot.gateio_spot_ask  # Long futures, short spot
                    
                    # Use absolute value of the larger spread
                    best_spread = max(abs(spread1), abs(spread2))
                    
                    # Convert to percentage based on average mid price
                    spot_mid = (snapshot.gateio_spot_bid + snapshot.gateio_spot_ask) / 2
                    futures_mid = (snapshot.gateio_futures_bid + snapshot.gateio_futures_ask) / 2
                    avg_mid = (spot_mid + futures_mid) / 2
                    
                    if avg_mid > 0:
                        spread_pct = (best_spread / avg_mid) * 100
                        spreads.append(spread_pct)
                
                # Fallback: use any available Gate.io internal spread
                elif snapshot.gateio_spot_bid and snapshot.gateio_spot_ask:
                    spread_abs = snapshot.gateio_spot_ask - snapshot.gateio_spot_bid
                    mid_price = (snapshot.gateio_spot_bid + snapshot.gateio_spot_ask) / 2
                    if mid_price > 0:
                        spread_pct = (spread_abs / mid_price) * 100
                        spreads.append(spread_pct)
                        
                elif snapshot.gateio_futures_bid and snapshot.gateio_futures_ask:
                    spread_abs = snapshot.gateio_futures_ask - snapshot.gateio_futures_bid
                    mid_price = (snapshot.gateio_futures_bid + snapshot.gateio_futures_ask) / 2
                    if mid_price > 0:
                        spread_pct = (spread_abs / mid_price) * 100
                        spreads.append(spread_pct)
        
        return spreads
    
    def _analyze_trend(self, spreads: List[float]) -> str:
        """Analyze trend direction in spreads."""
        if len(spreads) < 10:
            return 'stable'
        
        # Compare first and last quartiles
        quarter_size = len(spreads) // 4
        first_quarter = spreads[:quarter_size]
        last_quarter = spreads[-quarter_size:]
        
        avg_first = mean(first_quarter)
        avg_last = mean(last_quarter)
        
        change_pct = ((avg_last - avg_first) / avg_first) * 100 if avg_first > 0 else 0
        
        if change_pct > 10:
            return 'expanding'
        elif change_pct < -10:
            return 'contracting'
        else:
            return 'stable'
    
    def _determine_volatility_regime(self, std_deviation: float, mean_spread: float) -> str:
        """Determine volatility regime based on coefficient of variation."""
        if mean_spread <= 0:
            return 'unknown'
        
        cv = std_deviation / mean_spread  # Coefficient of variation
        
        if cv > 0.5:
            return 'high'
        elif cv > 0.2:
            return 'medium'
        else:
            return 'low'
    
    def _calculate_spread_percentage(self, spread_abs: float, price1: float, price2: float) -> float:
        """Calculate spread as percentage of average price."""
        if not price1 or not price2:
            return 0.0
        
        avg_price = (price1 + price2) / 2
        return (abs(spread_abs) / avg_price) * 100 if avg_price > 0 else 0.0