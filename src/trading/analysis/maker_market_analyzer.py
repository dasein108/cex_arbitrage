"""
Market Analysis Framework for Maker Limit Strategy

Real-time market analysis using indicators extracted from maker_order_candidate_analyzer.py
Provides volatility metrics, correlation analysis, market regime detection, and liquidity assessment.
"""

import time
import numpy as np
from collections import deque
from dataclasses import dataclass
from typing import Dict, Optional, List, Tuple
from decimal import Decimal

from exchanges.structs import BookTicker
from infrastructure.logging import HFTLoggerInterface


@dataclass
class VolatilityMetrics:
    """Volatility analysis metrics from analyzer"""
    volatility_ratio: float  # Spot volatility / futures volatility
    spot_volatility: float
    futures_volatility: float
    spike_detected: bool  # 2.5 sigma event detected
    spike_intensity: float  # Magnitude relative to threshold
    intraday_volatility_ratio: float  # High-low range comparison
    
    @classmethod
    def default(cls) -> 'VolatilityMetrics':
        """Default metrics for insufficient data"""
        return cls(
            volatility_ratio=1.0,
            spot_volatility=0.0,
            futures_volatility=0.0,
            spike_detected=False,
            spike_intensity=0.0,
            intraday_volatility_ratio=1.0
        )


@dataclass
class CorrelationMetrics:
    """Spot-futures correlation analysis for hedge effectiveness"""
    correlation: float  # Pearson correlation coefficient
    basis_volatility: float  # Futures - spot volatility
    basis_mean: float  # Average basis
    basis_volatility_pct: float  # Basis volatility as % of price
    hedge_effectiveness: bool  # True if correlation > threshold
    
    @classmethod
    def default(cls) -> 'CorrelationMetrics':
        """Default metrics for insufficient data"""
        return cls(
            correlation=0.0,
            basis_volatility=0.0,
            basis_mean=0.0,
            basis_volatility_pct=0.0,
            hedge_effectiveness=False
        )


@dataclass
class RegimeMetrics:
    """Market regime detection metrics from analyzer"""
    rsi: float  # RSI indicator (0-100)
    trend_strength: float  # Trend strength (0-1)
    sma_slope: float  # SMA slope for trend direction
    bb_position: float  # Position within Bollinger Bands
    bb_width: float  # Bollinger Band width
    is_trending: bool  # Strong trend detected
    is_mean_reverting: bool  # Mean-reverting conditions
    is_high_volatility: bool  # High volatility regime
    regime_multiplier: float  # Offset adjustment factor
    
    @classmethod
    def default(cls) -> 'RegimeMetrics':
        """Default metrics for insufficient data"""
        return cls(
            rsi=50.0,
            trend_strength=0.0,
            sma_slope=0.0,
            bb_position=0.5,
            bb_width=0.05,
            is_trending=False,
            is_mean_reverting=True,
            is_high_volatility=False,
            regime_multiplier=1.0
        )


@dataclass
class LiquidityMetrics:
    """Liquidity assessment metrics"""
    spot_volume_ma: float  # Moving average spot volume
    futures_volume_ma: float  # Moving average futures volume
    volume_ratio: float  # Spot / futures volume ratio
    hourly_futures_volume: float  # Estimated hourly futures volume
    liquidity_tier: str  # ULTRA_LOW, LOW, MEDIUM, HIGH
    volume_deviation: float  # Current vs average volume
    
    @classmethod
    def default(cls) -> 'LiquidityMetrics':
        """Default metrics for insufficient data"""
        return cls(
            spot_volume_ma=0.0,
            futures_volume_ma=0.0,
            volume_ratio=1.0,
            hourly_futures_volume=0.0,
            liquidity_tier='MEDIUM',
            volume_deviation=0.0
        )


@dataclass
class MarketAnalysis:
    """Comprehensive market analysis result"""
    timestamp: float
    spot_price: float
    futures_price: float
    volatility_metrics: VolatilityMetrics
    correlation_metrics: CorrelationMetrics
    regime_metrics: RegimeMetrics
    liquidity_metrics: LiquidityMetrics
    
    def is_safe_to_trade(self, min_correlation: float, max_volatility: float) -> bool:
        """Check if market conditions are safe for trading"""
        return (
            self.correlation_metrics.hedge_effectiveness and
            self.correlation_metrics.correlation >= min_correlation and
            self.volatility_metrics.volatility_ratio <= max_volatility and
            not self.volatility_metrics.spike_detected
        )


class MakerMarketAnalyzer:
    """Real-time market analysis for maker limit strategy"""
    
    def __init__(self, lookback_periods: int = 100, logger: Optional[HFTLoggerInterface] = None):
        self.lookback_periods = lookback_periods
        self.logger = logger
        
        # Price and volume history tracking
        self.price_history: Dict[str, deque] = {
            'spot_prices': deque(maxlen=lookback_periods),
            'futures_prices': deque(maxlen=lookback_periods),
            'spot_volumes': deque(maxlen=lookback_periods),
            'futures_volumes': deque(maxlen=lookback_periods),
            'timestamps': deque(maxlen=lookback_periods)
        }
        
        # High-low tracking for intraday volatility
        self.hl_history: Dict[str, deque] = {
            'spot_highs': deque(maxlen=lookback_periods),
            'spot_lows': deque(maxlen=lookback_periods),
            'futures_highs': deque(maxlen=lookback_periods),
            'futures_lows': deque(maxlen=lookback_periods)
        }
        
        # Performance tracking
        self.analysis_count = 0
        self.last_analysis_time = 0
        
    async def update_market_data(self, spot_ticker: BookTicker, futures_ticker: BookTicker) -> MarketAnalysis:
        """Update real-time market data and calculate comprehensive analysis"""
        current_time = time.time()
        
        # Update price histories
        spot_mid_price = (spot_ticker.bid_price + spot_ticker.ask_price) / 2
        futures_mid_price = (futures_ticker.bid_price + futures_ticker.ask_price) / 2
        
        self.price_history['spot_prices'].append(float(spot_mid_price))
        self.price_history['futures_prices'].append(float(futures_mid_price))
        self.price_history['spot_volumes'].append(float(spot_ticker.bid_qty + spot_ticker.ask_qty))
        self.price_history['futures_volumes'].append(float(futures_ticker.bid_qty + futures_ticker.ask_qty))
        self.price_history['timestamps'].append(current_time)
        
        # Update high-low history (use bid/ask as proxy for high/low)
        self.hl_history['spot_highs'].append(float(spot_ticker.ask_price))
        self.hl_history['spot_lows'].append(float(spot_ticker.bid_price))
        self.hl_history['futures_highs'].append(float(futures_ticker.ask_price))
        self.hl_history['futures_lows'].append(float(futures_ticker.bid_price))
        
        # Calculate analysis metrics
        volatility_metrics = self._calculate_volatility_metrics()
        correlation_metrics = self._calculate_correlation_metrics()
        regime_metrics = self._detect_market_regime()
        liquidity_metrics = self._assess_liquidity_conditions()
        
        # Track performance
        self.analysis_count += 1
        analysis_time = (time.time() - current_time) * 1000
        
        if self.logger and analysis_time > 5:  # Log if analysis takes >5ms
            self.logger.warning(f"Slow market analysis: {analysis_time:.2f}ms")
        
        return MarketAnalysis(
            timestamp=current_time,
            spot_price=float(spot_mid_price),
            futures_price=float(futures_mid_price),
            volatility_metrics=volatility_metrics,
            correlation_metrics=correlation_metrics,
            regime_metrics=regime_metrics,
            liquidity_metrics=liquidity_metrics
        )
    
    def _calculate_volatility_metrics(self) -> VolatilityMetrics:
        """Calculate real-time volatility indicators adapted from analyzer"""
        if len(self.price_history['spot_prices']) < 20:
            return VolatilityMetrics.default()
        
        try:
            spot_prices = np.array(list(self.price_history['spot_prices']))
            futures_prices = np.array(list(self.price_history['futures_prices']))
            spot_highs = np.array(list(self.hl_history['spot_highs']))
            spot_lows = np.array(list(self.hl_history['spot_lows']))
            futures_highs = np.array(list(self.hl_history['futures_highs']))
            futures_lows = np.array(list(self.hl_history['futures_lows']))
            
            # Calculate returns
            spot_returns = np.diff(spot_prices) / spot_prices[:-1]
            futures_returns = np.diff(futures_prices) / futures_prices[:-1]
            
            # Volatility ratio (key indicator from analyzer)
            spot_volatility = np.std(spot_returns)
            futures_volatility = np.std(futures_returns)
            volatility_ratio = spot_volatility / futures_volatility if futures_volatility > 0 else 1.0
            
            # Spike detection (2.5 sigma events from analyzer)
            spike_threshold = np.std(spot_returns) * 2.5
            recent_returns = spot_returns[-10:] if len(spot_returns) >= 10 else spot_returns
            
            spike_detected = False
            spike_intensity = 0.0
            if len(recent_returns) > 0 and spike_threshold > 0:
                max_recent_return = np.max(np.abs(recent_returns))
                spike_intensity = max_recent_return / spike_threshold
                spike_detected = spike_intensity > 1.0
            
            # Intraday volatility (high-low ratio from analyzer)
            spot_hl_ratios = (spot_highs - spot_lows) / spot_prices
            futures_hl_ratios = (futures_highs - futures_lows) / futures_prices
            
            spot_hl_ratio = np.mean(spot_hl_ratios[spot_hl_ratios > 0])
            futures_hl_ratio = np.mean(futures_hl_ratios[futures_hl_ratios > 0])
            intraday_volatility_ratio = spot_hl_ratio / futures_hl_ratio if futures_hl_ratio > 0 else 1.0
            
            return VolatilityMetrics(
                volatility_ratio=volatility_ratio,
                spot_volatility=spot_volatility,
                futures_volatility=futures_volatility,
                spike_detected=spike_detected,
                spike_intensity=spike_intensity,
                intraday_volatility_ratio=intraday_volatility_ratio
            )
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error calculating volatility metrics: {e}")
            return VolatilityMetrics.default()
    
    def _calculate_correlation_metrics(self) -> CorrelationMetrics:
        """Calculate spot-futures correlation for hedge effectiveness"""
        if len(self.price_history['spot_prices']) < 20:
            return CorrelationMetrics.default()
        
        try:
            spot_prices = np.array(list(self.price_history['spot_prices']))
            futures_prices = np.array(list(self.price_history['futures_prices']))
            
            # Rolling correlation (key safety metric from analyzer)
            correlation = np.corrcoef(spot_prices, futures_prices)[0, 1]
            if np.isnan(correlation):
                correlation = 0.0
            
            # Basis analysis (from analyzer)
            basis = futures_prices - spot_prices
            basis_volatility = np.std(basis)
            basis_mean = np.mean(basis)
            
            # Basis volatility as percentage of price
            avg_price = np.mean(spot_prices)
            basis_volatility_pct = basis_volatility / avg_price if avg_price > 0 else 0.0
            
            # Hedge effectiveness (from analyzer criteria)
            hedge_effectiveness = correlation > 0.7
            
            return CorrelationMetrics(
                correlation=correlation,
                basis_volatility=basis_volatility,
                basis_mean=basis_mean,
                basis_volatility_pct=basis_volatility_pct,
                hedge_effectiveness=hedge_effectiveness
            )
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error calculating correlation metrics: {e}")
            return CorrelationMetrics.default()
    
    def _detect_market_regime(self) -> RegimeMetrics:
        """Detect trending vs mean-reverting regime from analyzer"""
        if len(self.price_history['spot_prices']) < 50:
            return RegimeMetrics.default()
        
        try:
            prices = np.array(list(self.price_history['spot_prices']))
            
            # RSI calculation (from analyzer)
            deltas = np.diff(prices)
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            
            # Use 14-period RSI
            period = min(14, len(gains))
            avg_gain = np.mean(gains[-period:]) if len(gains) >= period else np.mean(gains)
            avg_loss = np.mean(losses[-period:]) if len(losses) >= period else np.mean(losses)
            
            if avg_loss > 0:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
            else:
                rsi = 100 if avg_gain > 0 else 50
            
            # Trend analysis (from analyzer)
            sma_period = min(20, len(prices))
            sma_20 = np.mean(prices[-sma_period:])
            current_price = prices[-1]
            trend_strength = abs((current_price - sma_20) / sma_20)
            
            # SMA slope
            if len(prices) >= 10:
                sma_slope = (sma_20 - np.mean(prices[-10:])) / np.mean(prices[-10:])
            else:
                sma_slope = 0.0
            
            # Bollinger Bands (from analyzer)
            bb_period = min(20, len(prices))
            bb_middle = np.mean(prices[-bb_period:])
            bb_std_dev = np.std(prices[-bb_period:])
            bb_upper = bb_middle + (bb_std_dev * 2)
            bb_lower = bb_middle - (bb_std_dev * 2)
            
            bb_position = ((current_price - bb_lower) / (bb_upper - bb_lower)) if (bb_upper - bb_lower) > 0 else 0.5
            bb_width = ((bb_upper - bb_lower) / bb_middle) if bb_middle > 0 else 0.05
            
            # Regime classification (from analyzer logic)
            is_trending = trend_strength > 0.02  # 2% trend threshold
            is_mean_reverting = trend_strength < 0.01 and 30 < rsi < 70
            is_high_volatility = bb_width > 0.1  # 10% BB width
            
            # Calculate regime multiplier for offset adjustment
            if is_mean_reverting:
                regime_multiplier = 0.7  # Reduce offsets in mean-reverting markets
            elif is_trending:
                regime_multiplier = 1.5  # Increase offsets in trending markets
            else:
                regime_multiplier = 1.0
            
            return RegimeMetrics(
                rsi=rsi,
                trend_strength=trend_strength,
                sma_slope=sma_slope,
                bb_position=bb_position,
                bb_width=bb_width,
                is_trending=is_trending,
                is_mean_reverting=is_mean_reverting,
                is_high_volatility=is_high_volatility,
                regime_multiplier=regime_multiplier
            )
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error detecting market regime: {e}")
            return RegimeMetrics.default()
    
    def _assess_liquidity_conditions(self) -> LiquidityMetrics:
        """Assess current liquidity conditions"""
        if len(self.price_history['spot_volumes']) < 10:
            return LiquidityMetrics.default()
        
        try:
            spot_volumes = np.array(list(self.price_history['spot_volumes']))
            futures_volumes = np.array(list(self.price_history['futures_volumes']))
            timestamps = np.array(list(self.price_history['timestamps']))
            
            # Moving averages
            spot_volume_ma = np.mean(spot_volumes)
            futures_volume_ma = np.mean(futures_volumes)
            volume_ratio = spot_volume_ma / futures_volume_ma if futures_volume_ma > 0 else 1.0
            
            # Estimate hourly futures volume (from analyzer)
            if len(timestamps) >= 2:
                time_span_hours = (timestamps[-1] - timestamps[0]) / 3600
                hourly_futures_volume = futures_volume_ma * (60 / 1) if time_span_hours > 0 else 0  # Assume 1-minute samples
            else:
                hourly_futures_volume = 0
            
            # Liquidity tier classification (from analyzer)
            if hourly_futures_volume < 50000:
                liquidity_tier = 'ULTRA_LOW'
            elif hourly_futures_volume < 100000:
                liquidity_tier = 'LOW'
            elif hourly_futures_volume < 500000:
                liquidity_tier = 'MEDIUM'
            else:
                liquidity_tier = 'HIGH'
            
            # Volume deviation from average
            current_volume = futures_volumes[-1] if len(futures_volumes) > 0 else 0
            volume_deviation = (current_volume - futures_volume_ma) / futures_volume_ma if futures_volume_ma > 0 else 0
            
            return LiquidityMetrics(
                spot_volume_ma=spot_volume_ma,
                futures_volume_ma=futures_volume_ma,
                volume_ratio=volume_ratio,
                hourly_futures_volume=hourly_futures_volume,
                liquidity_tier=liquidity_tier,
                volume_deviation=volume_deviation
            )
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error assessing liquidity conditions: {e}")
            return LiquidityMetrics.default()
    
    def get_analysis_stats(self) -> Dict[str, any]:
        """Get analyzer performance statistics"""
        return {
            'analysis_count': self.analysis_count,
            'data_points': len(self.price_history['spot_prices']),
            'last_analysis_time': self.last_analysis_time,
            'lookback_periods': self.lookback_periods
        }