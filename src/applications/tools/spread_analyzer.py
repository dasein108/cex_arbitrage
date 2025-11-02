"""
Spread Analyzer for NEIROETH Arbitrage

Advanced spread analysis engine for cross-exchange arbitrage opportunities.
Provides real-time spread calculations, historical pattern analysis, and
statistical indicators for informed trading decisions.

Key Features:
- Cross-exchange spread monitoring
- Historical pattern recognition
- Statistical analysis (volatility, trends, percentiles)
- Arbitrage opportunity detection with configurable thresholds
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, NamedTuple
from statistics import mean, stdev, median
from collections import deque
import math
import logging

import msgspec
import numpy as np

try:
    from .data_fetcher import UnifiedSnapshot, MultiSymbolDataFetcher
except ImportError:
    from data_fetcher import UnifiedSnapshot, MultiSymbolDataFetcher

logger = logging.getLogger(__name__)


class SpreadOpportunity(msgspec.Struct):
    """
    Arbitrage opportunity identification.
    
    Represents a potential profit opportunity with risk assessment.
    """
    timestamp: datetime
    opportunity_type: str  # 'spot_arbitrage', 'delta_neutral', 'rebalance'
    
    # Opportunity details
    buy_exchange: str
    sell_exchange: str
    buy_price: float
    sell_price: float
    spread_abs: float
    spread_pct: float
    
    # Risk assessment
    confidence_score: float  # 0-1 scale
    max_quantity: float     # Based on order book depth
    estimated_profit: float # After fees and slippage
    
    # Additional context
    historical_percentile: Optional[float] = None
    volatility_score: Optional[float] = None
    duration_estimate: Optional[float] = None  # Expected opportunity duration in seconds


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
    Advanced spread analysis engine for multi-symbol arbitrage.
    
    Provides comprehensive spread monitoring and statistical analysis
    for optimal arbitrage timing and risk management across any trading symbol.
    """
    
    # Default arbitrage thresholds (configurable)
    DEFAULT_ENTRY_THRESHOLD = 0.1  # 0.1% spread to enter arbitrage
    DEFAULT_EXIT_THRESHOLD = 0.01  # 0.01% spread to exit arbitrage
    
    # Statistical analysis parameters
    VOLATILITY_WINDOW = 100  # Number of samples for volatility calculation
    TREND_WINDOW = 50       # Number of samples for trend analysis
    
    def __init__(
        self, 
        data_fetcher: MultiSymbolDataFetcher,
        entry_threshold_pct: float = DEFAULT_ENTRY_THRESHOLD,
        exit_threshold_pct: float = DEFAULT_EXIT_THRESHOLD
    ):
        self.data_fetcher = data_fetcher
        self.entry_threshold = entry_threshold_pct / 100.0  # Convert to decimal
        self.exit_threshold = exit_threshold_pct / 100.0
        self.logger = logger.getChild("SpreadAnalyzer")
        
        # Rolling windows for real-time analysis
        self._recent_spreads: Dict[str, deque] = {
            'gateio_mexc_spread': deque(maxlen=self.VOLATILITY_WINDOW),
            'spot_futures_spread': deque(maxlen=self.VOLATILITY_WINDOW),
            'arbitrage_score': deque(maxlen=self.TREND_WINDOW)
        }
        
        # Historical data cache (cleared periodically)
        self._historical_cache: Optional[List[UnifiedSnapshot]] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl_minutes = 30
    
    async def analyze_current_spreads(self) -> Dict[str, float]:
        """
        Analyze current spread conditions across all exchanges.
        
        Returns:
            Dictionary with current spread analysis
        """
        snapshot = await self.data_fetcher.get_latest_snapshots()
        if not snapshot:
            self.logger.warning("No current data available for spread analysis")
            return {}
            
        # Calculate all relevant spreads
        spreads = {}
        cross_spreads = snapshot.get_cross_exchange_spreads()
        
        # Primary arbitrage spreads
        if 'gateio_mexc_sell_buy' in cross_spreads:
            spreads['gateio_mexc_sell_buy_abs'] = cross_spreads['gateio_mexc_sell_buy']
            spreads['gateio_mexc_sell_buy_pct'] = self._calculate_spread_percentage(
                cross_spreads['gateio_mexc_sell_buy'],
                snapshot.gateio_spot_bid,  # Sell price (denominator)
                snapshot.mexc_spot_ask     # Buy price
            )
            
        if 'mexc_gateio_sell_buy' in cross_spreads:
            spreads['mexc_gateio_sell_buy_abs'] = cross_spreads['mexc_gateio_sell_buy']
            spreads['mexc_gateio_sell_buy_pct'] = self._calculate_spread_percentage(
                cross_spreads['mexc_gateio_sell_buy'],
                snapshot.mexc_spot_bid,     # Sell price (denominator)
                snapshot.gateio_spot_ask   # Buy price
            )
        
        # Delta neutral spreads
        if 'spot_futures_long_short' in cross_spreads:
            spreads['spot_futures_long_short_abs'] = cross_spreads['spot_futures_long_short']
            spreads['spot_futures_long_short_pct'] = self._calculate_spread_percentage(
                cross_spreads['spot_futures_long_short'],
                snapshot.gateio_spot_bid,    # Sell spot price (denominator)
                snapshot.gateio_futures_ask  # Buy futures price
            )
            
        # Individual exchange spreads
        exchange_spreads = snapshot.get_spreads()
        for exchange, spread in exchange_spreads.items():
            spreads[f'{exchange}_internal_spread'] = spread
            
            # Calculate percentage spread
            if exchange == 'gateio_spot' and snapshot.gateio_spot_bid and snapshot.gateio_spot_ask:
                mid_price = (snapshot.gateio_spot_bid + snapshot.gateio_spot_ask) / 2
                spreads[f'{exchange}_internal_spread_pct'] = (spread / mid_price) * 100
                
            elif exchange == 'gateio_futures' and snapshot.gateio_futures_bid and snapshot.gateio_futures_ask:
                mid_price = (snapshot.gateio_futures_bid + snapshot.gateio_futures_ask) / 2
                spreads[f'{exchange}_internal_spread_pct'] = (spread / mid_price) * 100
                
            elif exchange == 'mexc_spot' and snapshot.mexc_spot_bid and snapshot.mexc_spot_ask:
                mid_price = (snapshot.mexc_spot_bid + snapshot.mexc_spot_ask) / 2
                spreads[f'{exchange}_internal_spread_pct'] = (spread / mid_price) * 100
        
        # Update rolling windows for trend analysis
        if 'gateio_mexc_sell_buy_pct' in spreads:
            self._recent_spreads['gateio_mexc_spread'].append(spreads['gateio_mexc_sell_buy_pct'])
        
        if 'spot_futures_long_short_pct' in spreads:
            self._recent_spreads['spot_futures_spread'].append(spreads['spot_futures_long_short_pct'])
        
        self.logger.debug(f"Analyzed current spreads: {len(spreads)} metrics calculated")
        return spreads
    
    async def identify_opportunities(self) -> List[SpreadOpportunity]:
        """
        Identify current arbitrage opportunities based on spread analysis.
        
        Returns:
            List of SpreadOpportunity objects ranked by profit potential
        """
        snapshot = await self.data_fetcher.get_latest_snapshots()
        if not snapshot or not snapshot.is_complete():
            self.logger.warning("Incomplete data for opportunity identification")
            return []
            
        opportunities = []
        cross_spreads = snapshot.get_cross_exchange_spreads()
        
        # Spot arbitrage opportunities
        for spread_key, spread_value in cross_spreads.items():
            spread_pct = abs(spread_value / self._get_mid_price_for_spread(snapshot, spread_key)) * 100
            
            if spread_pct >= (self.entry_threshold * 100):
                opportunity = self._create_opportunity_from_spread(
                    snapshot, spread_key, spread_value, spread_pct
                )
                if opportunity:
                    opportunities.append(opportunity)
        
        # Calculate confidence scores and risk metrics
        if opportunities:
            await self._enhance_opportunities_with_analytics(opportunities)
        
        # Sort by estimated profit (highest first)
        opportunities.sort(key=lambda op: op.estimated_profit, reverse=True)
        
        self.logger.info(f"Identified {len(opportunities)} arbitrage opportunities")
        return opportunities
    
    async def get_historical_statistics(
        self, 
        hours_back: int = 24,
        spread_type: str = 'gateio_mexc'
    ) -> Optional[SpreadStatistics]:
        """
        Calculate historical spread statistics for pattern analysis.
        
        Args:
            hours_back: Number of hours of history to analyze
            spread_type: Type of spread ('gateio_mexc', 'spot_futures', 'all', 'auto')
            
        Returns:
            SpreadStatistics object with comprehensive analysis
        """
        # Check cache first
        if (self._historical_cache and self._cache_timestamp and 
            datetime.utcnow() - self._cache_timestamp < timedelta(minutes=self._cache_ttl_minutes)):
            snapshots = self._historical_cache
        else:
            snapshots = await self.data_fetcher.get_historical_snapshots(hours_back)
            self._historical_cache = snapshots
            self._cache_timestamp = datetime.utcnow()
        
        if not snapshots:
            self.logger.warning(f"No historical data for statistics calculation ({hours_back}h)")
            return None
        
        # Auto-detect best spread type if requested or if primary fails
        if spread_type == 'auto' or spread_type == 'gateio_mexc':
            spreads, actual_spread_type = self._extract_best_available_spreads(snapshots, spread_type)
        else:
            spreads, actual_spread_type = self._extract_spreads_by_type(snapshots, spread_type)
        
        if not spreads:
            # Try fallback to any available spread type
            self.logger.warning(f"No valid spreads found for {spread_type}, trying fallback...")
            spreads, actual_spread_type = self._extract_best_available_spreads(snapshots, 'auto')
            
        if not spreads:
            self.logger.warning(f"No valid spreads found in any analysis type")
            return None
        
        # Calculate statistics
        spreads_array = np.array(spreads)
        
        # Basic statistics
        mean_val = float(np.mean(spreads_array))
        median_val = float(np.median(spreads_array))
        std_val = float(np.std(spreads_array))
        min_val = float(np.min(spreads_array))
        max_val = float(np.max(spreads_array))
        
        # Percentiles
        percentiles = np.percentile(spreads_array, [25, 75, 90, 95, 99])
        
        # Trend analysis
        trend_direction = self._analyze_trend(spreads[-self.TREND_WINDOW:] if len(spreads) > self.TREND_WINDOW else spreads)
        volatility_regime = self._classify_volatility(std_val, mean_val)
        
        # Opportunity metrics
        profitable_opportunities = len([s for s in spreads if s >= (self.entry_threshold * 100)])
        opportunity_rate = profitable_opportunities / hours_back if hours_back > 0 else 0
        
        statistics = SpreadStatistics(
            period_start=snapshots[0].timestamp,
            period_end=snapshots[-1].timestamp,
            sample_count=len(spreads),
            mean_spread=mean_val,
            median_spread=median_val,
            std_deviation=std_val,
            min_spread=min_val,
            max_spread=max_val,
            p25=float(percentiles[0]),
            p75=float(percentiles[1]),
            p90=float(percentiles[2]),
            p95=float(percentiles[3]),
            p99=float(percentiles[4]),
            trend_direction=trend_direction,
            volatility_regime=volatility_regime,
            profitable_opportunities=profitable_opportunities,
            opportunity_rate=opportunity_rate
        )
        
        self.logger.info(f"Calculated {actual_spread_type} statistics over {hours_back}h: "
                        f"{len(spreads)} samples, {profitable_opportunities} opportunities")
        
        return statistics
    
    async def get_volatility_metrics(self) -> Dict[str, float]:
        """
        Calculate current volatility metrics for risk assessment.
        
        Returns:
            Dictionary with volatility indicators
        """
        metrics = {}
        
        # Calculate volatility for each spread type
        for spread_name, spread_data in self._recent_spreads.items():
            if len(spread_data) >= 10:  # Need minimum samples
                spread_array = np.array(list(spread_data))
                
                # Standard deviation
                metrics[f'{spread_name}_volatility'] = float(np.std(spread_array))
                
                # Rolling volatility (last 20 samples)
                if len(spread_data) >= 20:
                    recent = spread_array[-20:]
                    metrics[f'{spread_name}_recent_volatility'] = float(np.std(recent))
                
                # Volatility ratio (recent vs overall)
                if f'{spread_name}_recent_volatility' in metrics:
                    overall_vol = metrics[f'{spread_name}_volatility']
                    recent_vol = metrics[f'{spread_name}_recent_volatility']
                    if overall_vol > 0:
                        metrics[f'{spread_name}_volatility_ratio'] = recent_vol / overall_vol
        
        return metrics
    
    def _calculate_spread_percentage(self, spread_abs: float, sell_price: Optional[float], buy_price: Optional[float]) -> float:
        """Calculate spread as percentage of sell price (execution-based calculation)."""
        if not sell_price or not buy_price:
            return 0.0
        
        # Use the selling price as denominator for execution-based calculation
        # This represents the actual return percentage on capital deployed
        return abs(spread_abs / sell_price) * 100 if sell_price > 0 else 0.0
    
    def _get_mid_price_for_spread(self, snapshot: UnifiedSnapshot, spread_key: str) -> float:
        """Get appropriate mid price for spread calculation."""
        if 'gateio_mexc' in spread_key:
            if snapshot.gateio_spot_bid and snapshot.mexc_spot_ask:
                return (snapshot.gateio_spot_bid + snapshot.mexc_spot_ask) / 2
        elif 'spot_futures' in spread_key:
            if snapshot.gateio_spot_bid and snapshot.gateio_futures_ask:
                return (snapshot.gateio_spot_bid + snapshot.gateio_futures_ask) / 2
        
        # Fallback to Gate.io spot mid price
        if snapshot.gateio_spot_bid and snapshot.gateio_spot_ask:
            return (snapshot.gateio_spot_bid + snapshot.gateio_spot_ask) / 2
            
        return 1.0  # Fallback to avoid division by zero
    
    def _create_opportunity_from_spread(
        self, 
        snapshot: UnifiedSnapshot, 
        spread_key: str, 
        spread_value: float, 
        spread_pct: float
    ) -> Optional[SpreadOpportunity]:
        """Create SpreadOpportunity from spread analysis."""
        if spread_key == 'gateio_mexc_sell_buy' and spread_value > 0:
            return SpreadOpportunity(
                timestamp=snapshot.timestamp,
                opportunity_type='spot_arbitrage',
                buy_exchange='MEXC_SPOT',
                sell_exchange='GATEIO_SPOT',
                buy_price=snapshot.mexc_spot_ask or 0,
                sell_price=snapshot.gateio_spot_bid or 0,
                spread_abs=spread_value,
                spread_pct=spread_pct,
                confidence_score=0.7,  # Will be enhanced later
                max_quantity=min(snapshot.mexc_spot_ask_qty or 0, snapshot.gateio_spot_bid_qty or 0),
                estimated_profit=0.0  # Will be calculated later
            )
        elif spread_key == 'mexc_gateio_sell_buy' and spread_value > 0:
            return SpreadOpportunity(
                timestamp=snapshot.timestamp,
                opportunity_type='spot_arbitrage',
                buy_exchange='GATEIO_SPOT',
                sell_exchange='MEXC_SPOT',
                buy_price=snapshot.gateio_spot_ask or 0,
                sell_price=snapshot.mexc_spot_bid or 0,
                spread_abs=spread_value,
                spread_pct=spread_pct,
                confidence_score=0.7,
                max_quantity=min(snapshot.gateio_spot_ask_qty or 0, snapshot.mexc_spot_bid_qty or 0),
                estimated_profit=0.0
            )
        elif spread_key == 'spot_futures_long_short' and spread_value > 0:
            return SpreadOpportunity(
                timestamp=snapshot.timestamp,
                opportunity_type='delta_neutral',
                buy_exchange='GATEIO_SPOT',
                sell_exchange='GATEIO_FUTURES',
                buy_price=snapshot.gateio_spot_bid or 0,
                sell_price=snapshot.gateio_futures_ask or 0,
                spread_abs=spread_value,
                spread_pct=spread_pct,
                confidence_score=0.8,  # Higher confidence for same exchange
                max_quantity=min(snapshot.gateio_spot_bid_qty or 0, snapshot.gateio_futures_ask_qty or 0),
                estimated_profit=0.0
            )
        
        return None
    
    async def _enhance_opportunities_with_analytics(self, opportunities: List[SpreadOpportunity]):
        """Enhance opportunities with historical and volatility analysis."""
        if not opportunities:
            return
            
        # Get recent statistics for comparison
        stats = await self.get_historical_statistics(hours_back=24)
        volatility = await self.get_volatility_metrics()
        
        for opportunity in opportunities:
            # Calculate historical percentile
            if stats:
                if opportunity.spread_pct <= stats.p25:
                    opportunity.historical_percentile = 25.0
                elif opportunity.spread_pct <= stats.p75:
                    opportunity.historical_percentile = 75.0
                elif opportunity.spread_pct <= stats.p90:
                    opportunity.historical_percentile = 90.0
                else:
                    opportunity.historical_percentile = 95.0
            
            # Adjust confidence based on volatility
            if volatility:
                # Lower confidence in high volatility environments
                vol_key = f"{opportunity.opportunity_type}_volatility"
                if vol_key in volatility:
                    vol_factor = min(1.0, 0.5 / volatility[vol_key]) if volatility[vol_key] > 0 else 1.0
                    opportunity.confidence_score *= vol_factor
            
            # Estimate duration based on historical patterns
            if stats:
                # Higher spreads typically last longer
                base_duration = 30  # seconds
                spread_factor = opportunity.spread_pct / (stats.mean_spread if stats.mean_spread > 0 else 0.1)
                opportunity.duration_estimate = base_duration * math.log(1 + spread_factor)
    
    def _analyze_trend(self, values: List[float]) -> str:
        """Analyze trend direction in spread values."""
        if len(values) < 5:
            return 'insufficient_data'
            
        # Simple linear regression slope
        n = len(values)
        x = list(range(n))
        x_mean = mean(x)
        y_mean = mean(values)
        
        numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            return 'stable'
            
        slope = numerator / denominator
        
        if slope > 0.01:
            return 'expanding'
        elif slope < -0.01:
            return 'contracting'
        else:
            return 'stable'
    
    def _extract_best_available_spreads(self, snapshots, requested_type: str) -> Tuple[List[float], str]:
        """
        Extract spreads using the best available data in snapshots.
        
        Args:
            snapshots: List of UnifiedSnapshot objects
            requested_type: Originally requested spread type
            
        Returns:
            Tuple of (spreads_list, actual_spread_type_used)
        """
        # Try different spread types in order of preference
        spread_strategies = [
            ('gateio_mexc', self._extract_gateio_mexc_spreads),
            ('spot_futures', self._extract_spot_futures_spreads),
            ('internal_futures', self._extract_internal_futures_spreads),
            ('internal_spot', self._extract_internal_spot_spreads)
        ]
        
        # If specific type was requested and not auto, try it first
        if requested_type != 'auto':
            for strategy_name, strategy_func in spread_strategies:
                if strategy_name == requested_type:
                    spreads = strategy_func(snapshots)
                    if spreads:
                        return spreads, strategy_name
                    break
        
        # Try all strategies in order
        for strategy_name, strategy_func in spread_strategies:
            spreads = strategy_func(snapshots)
            if spreads:
                self.logger.info(f"Using {strategy_name} analysis (found {len(spreads)} valid spreads)")
                return spreads, strategy_name
        
        return [], 'none'
    
    def _extract_spreads_by_type(self, snapshots, spread_type: str) -> Tuple[List[float], str]:
        """Extract spreads for a specific type only."""
        if spread_type == 'gateio_mexc':
            spreads = self._extract_gateio_mexc_spreads(snapshots)
        elif spread_type == 'spot_futures':
            spreads = self._extract_spot_futures_spreads(snapshots)
        elif spread_type == 'internal_futures':
            spreads = self._extract_internal_futures_spreads(snapshots)
        elif spread_type == 'internal_spot':
            spreads = self._extract_internal_spot_spreads(snapshots)
        else:
            spreads = []
        
        return spreads, spread_type if spreads else 'none'
    
    def _extract_gateio_mexc_spreads(self, snapshots) -> List[float]:
        """Extract Gate.io vs MEXC arbitrage spreads."""
        spreads = []
        for snapshot in snapshots:
            cross_spreads = snapshot.get_cross_exchange_spreads()
            if 'gateio_mexc_sell_buy' in cross_spreads:
                spread_pct = abs(cross_spreads['gateio_mexc_sell_buy'] / 
                               self._get_mid_price_for_spread(snapshot, 'gateio_mexc_sell_buy')) * 100
                spreads.append(spread_pct)
        return spreads
    
    def _extract_spot_futures_spreads(self, snapshots) -> List[float]:
        """Extract Gate.io Spot vs Futures spreads."""
        spreads = []
        for snapshot in snapshots:
            cross_spreads = snapshot.get_cross_exchange_spreads()
            if 'spot_futures_long_short' in cross_spreads:
                spread_pct = abs(cross_spreads['spot_futures_long_short'] /
                               self._get_mid_price_for_spread(snapshot, 'spot_futures_long_short')) * 100
                spreads.append(spread_pct)
        return spreads
    
    def _extract_internal_futures_spreads(self, snapshots) -> List[float]:
        """Extract Gate.io Futures internal bid-ask spreads."""
        spreads = []
        for snapshot in snapshots:
            if snapshot.gateio_futures_bid and snapshot.gateio_futures_ask:
                spread_abs = snapshot.gateio_futures_ask - snapshot.gateio_futures_bid
                mid_price = (snapshot.gateio_futures_bid + snapshot.gateio_futures_ask) / 2
                if mid_price > 0:
                    spread_pct = (spread_abs / mid_price) * 100
                    spreads.append(spread_pct)
        return spreads
    
    def _extract_internal_spot_spreads(self, snapshots) -> List[float]:
        """Extract internal bid-ask spreads from available spot exchanges."""
        spreads = []
        for snapshot in snapshots:
            # Try Gate.io Spot first
            if snapshot.gateio_spot_bid and snapshot.gateio_spot_ask:
                spread_abs = snapshot.gateio_spot_ask - snapshot.gateio_spot_bid
                mid_price = (snapshot.gateio_spot_bid + snapshot.gateio_spot_ask) / 2
                if mid_price > 0:
                    spread_pct = (spread_abs / mid_price) * 100
                    spreads.append(spread_pct)
            # Try MEXC Spot if Gate.io not available
            elif snapshot.mexc_spot_bid and snapshot.mexc_spot_ask:
                spread_abs = snapshot.mexc_spot_ask - snapshot.mexc_spot_bid
                mid_price = (snapshot.mexc_spot_bid + snapshot.mexc_spot_ask) / 2
                if mid_price > 0:
                    spread_pct = (spread_abs / mid_price) * 100
                    spreads.append(spread_pct)
        return spreads
    
    def _classify_volatility(self, std_dev: float, mean_val: float) -> str:
        """Classify volatility regime based on coefficient of variation."""
        if mean_val == 0:
            return 'undefined'
            
        cv = std_dev / mean_val  # Coefficient of variation
        
        if cv < 0.1:
            return 'low'
        elif cv < 0.3:
            return 'medium'
        else:
            return 'high'