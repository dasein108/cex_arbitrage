"""
Dynamic Offset Calculation Engine for Maker Limit Strategy

Calculates optimal order offsets based on multi-factor analysis including
volatility conditions, market regime, liquidity tier, and emergency adjustments.
Adapted from maker_order_candidate_analyzer.py logic.
"""

import math
from dataclasses import dataclass
from typing import Dict, Optional

from exchanges.structs import BookTicker, Side
from trading.strategies.implementations.maker_limit_delta_neutral__advanced_strategy.config.maker_limit_config import MakerLimitConfig
from trading.strategies.implementations.maker_limit_delta_neutral__advanced_strategy.analysis.maker_market_analyzer import MarketAnalysis
from infrastructure.logging import HFTLoggerInterface


@dataclass
class OffsetResult:
    """Result of dynamic offset calculation"""
    offset_ticks: int  # Number of ticks from best bid/ask
    offset_price: float  # Price offset amount
    target_price: float  # Final target price for order
    safety_score: float  # Safety score (0-1, higher = safer)
    
    # Breakdown of multipliers applied
    multipliers: Dict[str, float]
    
    # Additional context
    tick_size: float
    base_price: float  # Reference price (bid for buy, ask for sell)
    market_conditions: str  # Description of market conditions
    
    def get_distance_bps(self) -> float:
        """Get offset distance in basis points"""
        if self.base_price > 0:
            return (self.offset_price / self.base_price) * 10000
        return 0.0


class DynamicOffsetCalculator:
    """Calculate optimal order offsets based on market conditions"""
    
    def __init__(self, config: MakerLimitConfig, logger: Optional[HFTLoggerInterface] = None):
        self.config = config
        self.logger = logger
        
        # Offset calculation parameters (from analyzer)
        self.base_offset_ticks = config.base_offset_ticks
        self.max_offset_ticks = config.max_offset_ticks
        
        # Risk scaling factors
        self.volatility_scaling = {
            'low': 0.8,      # <0.8 volatility ratio
            'normal': 1.0,   # 0.8-1.2 volatility ratio  
            'high': 1.5,     # 1.2-2.0 volatility ratio
            'extreme': 2.0   # >2.0 volatility ratio
        }
        
        # Performance tracking
        self.calculation_count = 0
        self.last_calculation_time = 0
        
    def calculate_optimal_offset(self, market_analysis: MarketAnalysis, 
                               side: Side, current_book: BookTicker) -> OffsetResult:
        """Calculate dynamic offset adapted from analyzer logic"""
        
        try:
            self.calculation_count += 1
            
            # Base offset from config
            base_offset = self.base_offset_ticks
            
            # Get tick size and base price
            tick_size = self._estimate_tick_size(current_book)
            base_price = current_book.bid_price if side == Side.BUY else current_book.ask_price
            
            # Apply multi-factor adjustments
            multipliers = {}
            
            # 1. Volatility adjustment (key factor from analyzer)
            volatility_multiplier = self._calculate_volatility_multiplier(
                market_analysis.volatility_metrics
            )
            multipliers['volatility'] = volatility_multiplier
            
            # 2. Market regime adjustment (from analyzer)
            regime_multiplier = self._calculate_regime_multiplier(
                market_analysis.regime_metrics
            )
            multipliers['regime'] = regime_multiplier
            
            # 3. Liquidity tier adjustment (from analyzer)
            liquidity_multiplier = self._calculate_liquidity_multiplier(
                market_analysis.liquidity_metrics
            )
            multipliers['liquidity'] = liquidity_multiplier
            
            # 4. Emergency/spike adjustment
            emergency_multiplier = self._calculate_emergency_multiplier(
                market_analysis.volatility_metrics
            )
            multipliers['emergency'] = emergency_multiplier
            
            # 5. Correlation safety adjustment
            correlation_multiplier = self._calculate_correlation_multiplier(
                market_analysis.correlation_metrics
            )
            multipliers['correlation'] = correlation_multiplier
            
            # 6. Spread width adjustment (adaptive to current spread)
            spread_multiplier = self._calculate_spread_multiplier(current_book)
            multipliers['spread'] = spread_multiplier
            
            # Calculate final offset
            total_multiplier = (
                volatility_multiplier * 
                regime_multiplier * 
                liquidity_multiplier * 
                emergency_multiplier * 
                correlation_multiplier *
                spread_multiplier
            )
            
            final_offset_ticks = int(math.ceil(base_offset * total_multiplier))
            
            # Apply bounds (ensure within configured limits)
            final_offset_ticks = max(1, min(final_offset_ticks, self.max_offset_ticks))
            
            # Convert to price and calculate target
            offset_price = float(final_offset_ticks) * tick_size
            
            if side == Side.BUY:
                target_price = base_price - offset_price
            else:  # SELL
                target_price = base_price + offset_price
            
            # Ensure positive price
            target_price = max(target_price, tick_size)
            
            # Calculate safety score
            safety_score = self._calculate_safety_score(
                market_analysis, final_offset_ticks, total_multiplier
            )
            
            # Generate market conditions description
            market_conditions = self._describe_market_conditions(market_analysis)
            
            # Log calculation if significant adjustment
            if total_multiplier > 1.5 or total_multiplier < 0.7:
                self._log_offset_calculation(
                    side, final_offset_ticks, multipliers, market_conditions
                )
            
            return OffsetResult(
                offset_ticks=final_offset_ticks,
                offset_price=offset_price,
                target_price=target_price,
                safety_score=safety_score,
                multipliers=multipliers,
                tick_size=tick_size,
                base_price=base_price,
                market_conditions=market_conditions
            )
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error calculating offset: {e}")
            
            # Return conservative fallback
            return self._get_fallback_offset(side, current_book)
    
    def _calculate_volatility_multiplier(self, vol_metrics) -> float:
        """Calculate volatility-based offset multiplier from analyzer logic"""
        volatility_ratio = vol_metrics.volatility_ratio
        
        # Base volatility adjustment (from analyzer)
        if volatility_ratio > 2.0:
            multiplier = self.volatility_scaling['extreme']  # 2.0x
        elif volatility_ratio > 1.2:
            multiplier = self.volatility_scaling['high']     # 1.5x
        elif volatility_ratio < 0.8:
            multiplier = self.volatility_scaling['low']      # 0.8x
        else:
            multiplier = self.volatility_scaling['normal']   # 1.0x
        
        # Additional spike adjustment
        if vol_metrics.spike_detected:
            spike_multiplier = 1.0 + (vol_metrics.spike_intensity * 0.2)  # +20% per intensity unit
            multiplier *= min(spike_multiplier, 2.0)  # Cap at 2x additional
        
        return multiplier
    
    def _calculate_regime_multiplier(self, regime_metrics) -> float:
        """Calculate market regime offset multiplier from analyzer logic"""
        # Use regime multiplier directly from analyzer
        base_multiplier = regime_metrics.regime_multiplier
        
        # Additional RSI-based adjustment
        rsi = regime_metrics.rsi
        rsi_multiplier = 1.0
        
        if rsi < 20 or rsi > 80:  # Extreme RSI
            rsi_multiplier = 1.3  # Increase caution
        elif 30 <= rsi <= 70:  # Normal range
            rsi_multiplier = 0.9  # Slightly more aggressive
        
        # Bollinger Band position adjustment
        bb_position = regime_metrics.bb_position
        if bb_position < 0.1 or bb_position > 0.9:  # Near BB edges
            bb_multiplier = 1.2  # More conservative near extremes
        else:
            bb_multiplier = 1.0
        
        return base_multiplier * rsi_multiplier * bb_multiplier
    
    def _calculate_liquidity_multiplier(self, liq_metrics) -> float:
        """Calculate liquidity tier offset multiplier from analyzer logic"""
        liquidity_tier = liq_metrics.liquidity_tier
        
        # Base multiplier from config (matches analyzer logic)
        base_multiplier = self.config.get_liquidity_multiplier(liquidity_tier)
        
        # Volume deviation adjustment
        volume_deviation = liq_metrics.volume_deviation
        
        if volume_deviation < -0.5:  # Volume 50% below average
            volume_multiplier = 1.3  # More conservative
        elif volume_deviation > 0.5:  # Volume 50% above average
            volume_multiplier = 0.9  # Slightly more aggressive
        else:
            volume_multiplier = 1.0
        
        return base_multiplier * volume_multiplier
    
    def _calculate_emergency_multiplier(self, vol_metrics) -> float:
        """Calculate emergency adjustment multiplier"""
        # Emergency spike protection (from analyzer)
        if vol_metrics.spike_detected and vol_metrics.spike_intensity > 2.0:
            return self.config.emergency_multiplier  # 1.3x from config
        
        return 1.0
    
    def _calculate_correlation_multiplier(self, corr_metrics) -> float:
        """Calculate correlation-based safety multiplier"""
        correlation = corr_metrics.correlation
        
        # Poor correlation = more conservative offsets
        if correlation < 0.6:
            return 1.5  # Much more conservative
        elif correlation < 0.7:
            return 1.3  # More conservative
        elif correlation < 0.8:
            return 1.1  # Slightly conservative
        else:
            return 1.0  # Normal
    
    def _calculate_spread_multiplier(self, book: BookTicker) -> float:
        """Calculate spread-adaptive multiplier"""
        try:
            # Current spread
            current_spread = book.ask_price - book.bid_price
            mid_price = (book.ask_price + book.bid_price) / 2
            spread_bps = (current_spread / mid_price) * 10000
            
            # Adjust offset based on spread width
            if spread_bps > 50:  # Wide spread (>5 bps)
                return 0.8  # Can be more aggressive
            elif spread_bps < 10:  # Tight spread (<1 bp)
                return 1.2  # Need larger offset
            else:
                return 1.0  # Normal spread
                
        except:
            return 1.0  # Fallback
    
    def _estimate_tick_size(self, book: BookTicker) -> float:
        """Estimate tick size from current book"""
        try:
            # Simple estimation based on price level
            mid_price = (book.bid_price + book.ask_price) / 2
            
            if mid_price >= 1000:
                return 1.0
            elif mid_price >= 100:
                return 0.1
            elif mid_price >= 10:
                return 0.01
            elif mid_price >= 1:
                return 0.001
            else:
                return 0.00001
                
        except:
            return 0.00001  # Conservative fallback
    
    def _calculate_safety_score(self, analysis: MarketAnalysis, 
                              offset_ticks: int, total_multiplier: float) -> float:
        """Calculate safety score for the offset (0-1, higher = safer)"""
        score = 0.0
        
        # Base safety from offset size (larger offset = safer)
        offset_safety = min(offset_ticks / self.max_offset_ticks, 1.0)
        score += offset_safety * 0.3
        
        # Correlation safety
        correlation_safety = analysis.correlation_metrics.correlation
        score += correlation_safety * 0.3
        
        # Volatility safety (lower volatility = safer)
        vol_safety = 1.0 - min(analysis.volatility_metrics.volatility_ratio / 2.0, 1.0)
        score += vol_safety * 0.2
        
        # Regime safety
        regime_safety = 1.0 if analysis.regime_metrics.is_mean_reverting else 0.5
        score += regime_safety * 0.2
        
        return min(score, 1.0)
    
    def _describe_market_conditions(self, analysis: MarketAnalysis) -> str:
        """Generate human-readable market conditions description"""
        conditions = []
        
        # Volatility
        vol_ratio = analysis.volatility_metrics.volatility_ratio
        if vol_ratio > 1.5:
            conditions.append("HIGH_VOLATILITY")
        elif vol_ratio < 0.8:
            conditions.append("LOW_VOLATILITY")
        else:
            conditions.append("NORMAL_VOLATILITY")
        
        # Regime
        if analysis.regime_metrics.is_trending:
            conditions.append("TRENDING")
        elif analysis.regime_metrics.is_mean_reverting:
            conditions.append("MEAN_REVERTING")
        else:
            conditions.append("TRANSITIONAL")
        
        # Liquidity
        conditions.append(f"LIQUIDITY_{analysis.liquidity_metrics.liquidity_tier}")
        
        # Correlation
        if analysis.correlation_metrics.correlation > 0.9:
            conditions.append("STRONG_CORRELATION")
        elif analysis.correlation_metrics.correlation < 0.7:
            conditions.append("WEAK_CORRELATION")
        
        # Spikes
        if analysis.volatility_metrics.spike_detected:
            conditions.append("SPIKE_DETECTED")
        
        return "_".join(conditions)
    
    def _log_offset_calculation(self, side: Side, final_offset: int, 
                              multipliers: Dict[str, float], conditions: str):
        """Log significant offset calculations"""
        if self.logger:
            self.logger.info(f"Dynamic offset calculated: {side.name}", extra={
                'final_offset_ticks': final_offset,
                'multipliers': multipliers,
                'conditions': conditions,
                'total_multiplier': math.prod(multipliers.values())
            })
    
    def _get_fallback_offset(self, side: Side, book: BookTicker) -> OffsetResult:
        """Conservative fallback offset for error cases"""
        tick_size = self._estimate_tick_size(book)
        base_price = book.bid_price if side == Side.BUY else book.ask_price
        offset_price = float(self.base_offset_ticks) * tick_size
        
        if side == Side.BUY:
            target_price = base_price - offset_price
        else:
            target_price = base_price + offset_price
        
        return OffsetResult(
            offset_ticks=self.base_offset_ticks,
            offset_price=offset_price,
            target_price=max(target_price, tick_size),
            safety_score=0.5,
            multipliers={'fallback': 1.0},
            tick_size=tick_size,
            base_price=base_price,
            market_conditions="ERROR_FALLBACK"
        )
    
    def get_calculation_stats(self) -> Dict[str, any]:
        """Get offset calculation statistics"""
        return {
            'calculation_count': self.calculation_count,
            'base_offset_ticks': self.base_offset_ticks,
            'max_offset_ticks': self.max_offset_ticks,
            'volatility_scaling': self.volatility_scaling
        }