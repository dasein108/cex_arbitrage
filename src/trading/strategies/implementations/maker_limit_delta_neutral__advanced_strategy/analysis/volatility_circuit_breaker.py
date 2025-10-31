"""
Volatility Circuit Breaker System for Maker Limit Strategy

Comprehensive circuit breaker system that monitors market conditions and
automatically halts trading when risk thresholds are exceeded. Provides
multiple safety mechanisms with configurable cooldown periods.
"""

import time
from collections import deque
from dataclasses import dataclass
from typing import List, Dict, Optional
from enum import Enum

from trading.strategies.implementations.maker_limit_delta_neutral__advanced_strategy.config.maker_limit_config import MakerLimitConfig
from trading.strategies.implementations.maker_limit_delta_neutral__advanced_strategy.analysis.maker_market_analyzer import MarketAnalysis
from infrastructure.logging import HFTLoggerInterface


class CircuitBreakerTrigger(Enum):
    """Circuit breaker trigger types"""
    VOLATILITY_SPIKE = "VOLATILITY_SPIKE"
    CORRELATION_BREAKDOWN = "CORRELATION_BREAKDOWN"
    VOLUME_DROUGHT = "VOLUME_DROUGHT"
    BASIS_INSTABILITY = "BASIS_INSTABILITY"
    EMERGENCY_SPIKE = "EMERGENCY_SPIKE"
    TREND_EMERGENCE = "TREND_EMERGENCE"
    RSI_EXTREME = "RSI_EXTREME"
    HEDGE_FAILURE = "HEDGE_FAILURE"


@dataclass
class CircuitBreakerResult:
    """Result of circuit breaker evaluation"""
    should_trigger: bool
    triggers: List[CircuitBreakerTrigger]
    recommended_action: str  # STOP_TRADING, REDUCE_POSITION, CONTINUE
    cooldown_period: int  # Seconds
    severity_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    
    def is_critical(self) -> bool:
        """Check if this is a critical circuit breaker event"""
        return self.severity_level == "CRITICAL"
    
    def requires_immediate_stop(self) -> bool:
        """Check if trading should stop immediately"""
        critical_triggers = {
            CircuitBreakerTrigger.EMERGENCY_SPIKE,
            CircuitBreakerTrigger.CORRELATION_BREAKDOWN,
            CircuitBreakerTrigger.HEDGE_FAILURE
        }
        return any(trigger in critical_triggers for trigger in self.triggers)


@dataclass
class CircuitBreakerEvent:
    """Historical circuit breaker event for tracking"""
    timestamp: float
    trigger: CircuitBreakerTrigger
    trigger_value: float
    threshold: float
    cooldown_until: float
    market_context: Dict[str, float]


class VolatilityCircuitBreaker:
    """Circuit breaker system for high volatility and risk conditions"""
    
    def __init__(self, config: MakerLimitConfig, logger: Optional[HFTLoggerInterface] = None):
        self.config = config
        self.logger = logger
        
        # Circuit breaker state
        self.breaker_active = False
        self.active_triggers: List[CircuitBreakerTrigger] = []
        self.last_check_time = time.time()
        self.cooldown_until = 0.0
        
        # Event tracking
        self.volatility_events: deque = deque(maxlen=50)  # Track last 50 events
        self.circuit_events: List[CircuitBreakerEvent] = []
        
        # Performance tracking
        self.check_count = 0
        self.trigger_count = 0
        
        # Adaptive thresholds (learned from market behavior)
        self.adaptive_thresholds = {
            'volatility_spike_multiplier': 1.0,
            'correlation_sensitivity': 1.0,
            'volume_sensitivity': 1.0
        }
        
    def check_circuit_conditions(self, market_analysis: MarketAnalysis) -> CircuitBreakerResult:
        """Comprehensive circuit breaker evaluation"""
        current_time = time.time()
        self.check_count += 1
        
        # Check if still in cooldown period
        if current_time < self.cooldown_until:
            return CircuitBreakerResult(
                should_trigger=True,
                triggers=self.active_triggers,
                recommended_action="WAIT_COOLDOWN",
                cooldown_period=int(self.cooldown_until - current_time),
                severity_level="MEDIUM"
            )
        
        # Evaluate all circuit breaker conditions
        triggers = []
        severity_scores = []
        
        # 1. Volatility spike check (from analyzer)
        volatility_trigger, volatility_severity = self._check_volatility_conditions(market_analysis)
        if volatility_trigger:
            triggers.append(volatility_trigger)
            severity_scores.append(volatility_severity)
        
        # 2. Correlation breakdown check
        correlation_trigger, correlation_severity = self._check_correlation_conditions(market_analysis)
        if correlation_trigger:
            triggers.append(correlation_trigger)
            severity_scores.append(correlation_severity)
        
        # 3. Volume conditions check
        volume_trigger, volume_severity = self._check_volume_conditions(market_analysis)
        if volume_trigger:
            triggers.append(volume_trigger)
            severity_scores.append(volume_severity)
        
        # 4. Basis stability check
        basis_trigger, basis_severity = self._check_basis_conditions(market_analysis)
        if basis_trigger:
            triggers.append(basis_trigger)
            severity_scores.append(basis_severity)
        
        # 5. Market regime checks
        regime_trigger, regime_severity = self._check_regime_conditions(market_analysis)
        if regime_trigger:
            triggers.append(regime_trigger)
            severity_scores.append(regime_severity)
        
        # Determine overall severity and action
        should_trigger = len(triggers) > 0
        if should_trigger:
            max_severity = max(severity_scores)
            severity_level = self._get_severity_level(max_severity)
            cooldown_period = self._calculate_cooldown_period(triggers, severity_level)
            action = self._determine_action(triggers, severity_level)
            
            # Update circuit breaker state
            self.breaker_active = True
            self.active_triggers = triggers
            self.cooldown_until = current_time + cooldown_period
            self.trigger_count += 1
            
            # Log circuit breaker activation
            self._log_circuit_activation(triggers, market_analysis, severity_level)
            
            # Record event for analysis
            self._record_circuit_event(triggers[0], max_severity, market_analysis)
            
        else:
            # Reset if no triggers
            if self.breaker_active:
                self._log_circuit_reset()
            self.breaker_active = False
            self.active_triggers = []
            severity_level = "LOW"
            cooldown_period = 0
            action = "CONTINUE"
        
        self.last_check_time = current_time
        
        return CircuitBreakerResult(
            should_trigger=should_trigger,
            triggers=triggers,
            recommended_action=action,
            cooldown_period=cooldown_period,
            severity_level=severity_level
        )
    
    def _check_volatility_conditions(self, analysis: MarketAnalysis) -> tuple[Optional[CircuitBreakerTrigger], float]:
        """Check volatility-based circuit breaker conditions"""
        vol_metrics = analysis.volatility_metrics
        
        # Emergency spike detection (3x sigma events)
        if vol_metrics.spike_detected and vol_metrics.spike_intensity > 3.0:
            return CircuitBreakerTrigger.EMERGENCY_SPIKE, vol_metrics.spike_intensity
        
        # Volatility ratio spike
        threshold = self.config.volatility_circuit_breaker * self.adaptive_thresholds['volatility_spike_multiplier']
        if vol_metrics.volatility_ratio > threshold:
            severity = vol_metrics.volatility_ratio / threshold
            return CircuitBreakerTrigger.VOLATILITY_SPIKE, severity
        
        return None, 0.0
    
    def _check_correlation_conditions(self, analysis: MarketAnalysis) -> tuple[Optional[CircuitBreakerTrigger], float]:
        """Check correlation breakdown conditions"""
        corr_metrics = analysis.correlation_metrics
        
        # Critical correlation breakdown
        threshold = self.config.correlation_circuit_breaker * self.adaptive_thresholds['correlation_sensitivity']
        if corr_metrics.correlation < threshold:
            severity = (threshold - corr_metrics.correlation) / threshold
            return CircuitBreakerTrigger.CORRELATION_BREAKDOWN, severity
        
        return None, 0.0
    
    def _check_volume_conditions(self, analysis: MarketAnalysis) -> tuple[Optional[CircuitBreakerTrigger], float]:
        """Check volume drought conditions"""
        liq_metrics = analysis.liquidity_metrics
        
        # Volume drought detection
        threshold = self.config.volume_circuit_breaker * self.adaptive_thresholds['volume_sensitivity']
        if liq_metrics.volume_deviation < -threshold:  # Negative deviation = volume drought
            severity = abs(liq_metrics.volume_deviation) / threshold
            return CircuitBreakerTrigger.VOLUME_DROUGHT, severity
        
        return None, 0.0
    
    def _check_basis_conditions(self, analysis: MarketAnalysis) -> tuple[Optional[CircuitBreakerTrigger], float]:
        """Check basis instability conditions"""
        corr_metrics = analysis.correlation_metrics
        
        # Basis volatility relative to price
        if corr_metrics.basis_volatility_pct > self.config.max_basis_volatility_pct:
            severity = corr_metrics.basis_volatility_pct / self.config.max_basis_volatility_pct
            return CircuitBreakerTrigger.BASIS_INSTABILITY, severity
        
        return None, 0.0
    
    def _check_regime_conditions(self, analysis: MarketAnalysis) -> tuple[Optional[CircuitBreakerTrigger], float]:
        """Check market regime conditions"""
        regime_metrics = analysis.regime_metrics
        
        # Strong trend emergence (from analyzer)
        if regime_metrics.trend_strength > self.config.trend_circuit_breaker:
            severity = regime_metrics.trend_strength / self.config.trend_circuit_breaker
            return CircuitBreakerTrigger.TREND_EMERGENCE, severity
        
        # Extreme RSI conditions
        if regime_metrics.rsi < 15 or regime_metrics.rsi > 85:
            severity = abs(regime_metrics.rsi - 50) / 50  # Distance from neutral
            return CircuitBreakerTrigger.RSI_EXTREME, severity
        
        return None, 0.0
    
    def _get_severity_level(self, max_severity: float) -> str:
        """Determine severity level based on maximum severity score"""
        if max_severity >= 3.0:
            return "CRITICAL"
        elif max_severity >= 2.0:
            return "HIGH"
        elif max_severity >= 1.5:
            return "MEDIUM"
        else:
            return "LOW"
    
    def _calculate_cooldown_period(self, triggers: List[CircuitBreakerTrigger], severity: str) -> int:
        """Calculate appropriate cooldown period"""
        base_cooldown = {
            "LOW": 60,
            "MEDIUM": 180,
            "HIGH": 300,
            "CRITICAL": 600
        }.get(severity, 180)
        
        # Adjust based on trigger types
        critical_triggers = {
            CircuitBreakerTrigger.EMERGENCY_SPIKE,
            CircuitBreakerTrigger.CORRELATION_BREAKDOWN
        }
        
        if any(trigger in critical_triggers for trigger in triggers):
            base_cooldown *= 2  # Double cooldown for critical triggers
        
        return base_cooldown
    
    def _determine_action(self, triggers: List[CircuitBreakerTrigger], severity: str) -> str:
        """Determine recommended action based on triggers and severity"""
        critical_triggers = {
            CircuitBreakerTrigger.EMERGENCY_SPIKE,
            CircuitBreakerTrigger.CORRELATION_BREAKDOWN,
            CircuitBreakerTrigger.HEDGE_FAILURE
        }
        
        if any(trigger in critical_triggers for trigger in triggers):
            return "STOP_TRADING"
        elif severity in ["HIGH", "CRITICAL"]:
            return "STOP_TRADING"
        elif severity == "MEDIUM":
            return "REDUCE_POSITION"
        else:
            return "MONITOR_CLOSELY"
    
    def _record_circuit_event(self, trigger: CircuitBreakerTrigger, severity: float, analysis: MarketAnalysis):
        """Record circuit breaker event for analysis"""
        event = CircuitBreakerEvent(
            timestamp=time.time(),
            trigger=trigger,
            trigger_value=severity,
            threshold=1.0,  # Normalized threshold
            cooldown_until=self.cooldown_until,
            market_context={
                'volatility_ratio': analysis.volatility_metrics.volatility_ratio,
                'correlation': analysis.correlation_metrics.correlation,
                'rsi': analysis.regime_metrics.rsi,
                'trend_strength': analysis.regime_metrics.trend_strength,
                'volume_deviation': analysis.liquidity_metrics.volume_deviation
            }
        )
        self.circuit_events.append(event)
        
        # Keep only last 100 events
        if len(self.circuit_events) > 100:
            self.circuit_events = self.circuit_events[-100:]
    
    def _log_circuit_activation(self, triggers: List[CircuitBreakerTrigger], 
                              analysis: MarketAnalysis, severity: str):
        """Log circuit breaker activation"""
        if self.logger:
            self.logger.warning("Circuit breaker activated", extra={
                'triggers': [t.value for t in triggers],
                'severity': severity,
                'volatility_ratio': analysis.volatility_metrics.volatility_ratio,
                'correlation': analysis.correlation_metrics.correlation,
                'spike_detected': analysis.volatility_metrics.spike_detected,
                'cooldown_until': self.cooldown_until
            })
    
    def _log_circuit_reset(self):
        """Log circuit breaker reset"""
        if self.logger:
            self.logger.info("Circuit breaker reset - trading can resume")
    
    def register_hedge_failure(self, failure_details: Dict[str, any]):
        """Register hedge execution failure as circuit breaker trigger"""
        current_time = time.time()
        
        # Force circuit breaker activation for hedge failures
        self.breaker_active = True
        self.active_triggers = [CircuitBreakerTrigger.HEDGE_FAILURE]
        self.cooldown_until = current_time + self.config.emergency_cooldown_seconds
        
        if self.logger:
            self.logger.critical("Hedge failure circuit breaker activated", extra=failure_details)
    
    def force_reset(self):
        """Manually reset circuit breaker (admin function)"""
        self.breaker_active = False
        self.active_triggers = []
        self.cooldown_until = 0.0
        
        if self.logger:
            self.logger.info("Circuit breaker manually reset")
    
    def update_adaptive_thresholds(self, market_stats: Dict[str, float]):
        """Update adaptive thresholds based on market behavior"""
        # Simple adaptive adjustment based on market volatility
        avg_volatility = market_stats.get('avg_volatility_ratio', 1.0)
        
        if avg_volatility > 1.5:
            # More volatile market - increase sensitivity
            self.adaptive_thresholds['volatility_spike_multiplier'] = 0.8
        elif avg_volatility < 0.8:
            # Less volatile market - decrease sensitivity
            self.adaptive_thresholds['volatility_spike_multiplier'] = 1.2
        else:
            # Normal market
            self.adaptive_thresholds['volatility_spike_multiplier'] = 1.0
    
    def get_circuit_stats(self) -> Dict[str, any]:
        """Get circuit breaker statistics"""
        return {
            'check_count': self.check_count,
            'trigger_count': self.trigger_count,
            'trigger_rate': self.trigger_count / self.check_count if self.check_count > 0 else 0,
            'currently_active': self.breaker_active,
            'active_triggers': [t.value for t in self.active_triggers],
            'cooldown_remaining': max(0, self.cooldown_until - time.time()),
            'recent_events': len(self.circuit_events),
            'adaptive_thresholds': self.adaptive_thresholds
        }