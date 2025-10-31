"""
Performance Monitoring System for Maker Limit Strategy

Comprehensive performance monitoring and analytics for the maker limit order strategy.
Tracks trading metrics, position analytics, risk metrics, and strategy performance
with real-time alerting and historical analysis capabilities.
"""

import time
import statistics
from collections import deque, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum

from trading.strategies.implementations.maker_limit_delta_neutral__advanced_strategy.config.maker_limit_config import MakerLimitConfig
from trading.strategies.implementations.maker_limit_delta_neutral__advanced_strategy.analysis.maker_market_analyzer import MarketAnalysis
from trading.strategies.implementations.maker_limit_delta_neutral__advanced_strategy.execution.maker_limit_engine import OrderFillEvent
from trading.strategies.implementations.maker_limit_delta_neutral__advanced_strategy.execution.delta_neutral_hedge_executor import HedgeResult
from infrastructure.logging import HFTLoggerInterface


class PerformanceAlert(Enum):
    """Performance alert types"""
    HIGH_SLIPPAGE = "HIGH_SLIPPAGE"
    POOR_HEDGE_RATE = "POOR_HEDGE_RATE"
    DELTA_DEVIATION = "DELTA_DEVIATION"
    LOW_FILL_RATE = "LOW_FILL_RATE"
    HIGH_CIRCUIT_TRIGGERS = "HIGH_CIRCUIT_TRIGGERS"
    SLOW_EXECUTION = "SLOW_EXECUTION"
    POSITION_IMBALANCE = "POSITION_IMBALANCE"


@dataclass
class TradeRecord:
    """Comprehensive trade record for analysis"""
    timestamp: float
    
    # Spot trade details
    spot_side: str  # BUY or SELL
    spot_price: float
    spot_quantity: float
    spot_order_id: str
    
    # Hedge execution details
    hedge_success: bool
    hedge_price: Optional[float] = None
    hedge_quantity: float = 0.0
    hedge_execution_time_ms: float = 0.0
    hedge_slippage_bps: float = 0.0
    
    # Position tracking
    net_delta_before: float = 0.0
    net_delta_after: float = 0.0
    delta_improvement: float = 0.0
    
    # Market context
    volatility_ratio: float = 0.0
    correlation: float = 0.0
    market_regime: str = ""
    
    # Profitability (estimated)
    estimated_pnl: float = 0.0
    fees_paid: float = 0.0
    net_pnl: float = 0.0
    
    def get_round_trip_time_ms(self) -> float:
        """Get total round trip execution time"""
        return self.hedge_execution_time_ms
    
    def is_profitable(self) -> bool:
        """Check if trade was profitable after fees"""
        return self.net_pnl > 0


@dataclass
class PerformanceMetrics:
    """Real-time performance metrics"""
    
    # Trading metrics
    total_trades: int = 0
    successful_hedges: int = 0
    failed_hedges: int = 0
    total_spot_volume: float = 0.0
    total_futures_volume: float = 0.0
    
    # Execution performance
    avg_hedge_time_ms: float = 0.0
    avg_slippage_bps: float = 0.0
    max_hedge_time_ms: float = 0.0
    max_slippage_bps: float = 0.0
    
    # Position tracking
    current_net_delta: float = 0.0
    max_delta_deviation: float = 0.0
    delta_neutral_ratio: float = 0.0  # % of time delta neutral
    
    # Profitability
    total_pnl: float = 0.0
    total_fees: float = 0.0
    net_pnl: float = 0.0
    avg_trade_pnl: float = 0.0
    win_rate: float = 0.0
    
    # Risk metrics
    max_position_size: float = 0.0
    avg_position_size: float = 0.0
    position_utilization: float = 0.0
    
    # Circuit breaker metrics
    circuit_breaker_triggers: int = 0
    circuit_breaker_rate: float = 0.0
    avg_downtime_minutes: float = 0.0
    
    # Market conditions
    avg_volatility_ratio: float = 0.0
    avg_correlation: float = 0.0
    favorable_market_ratio: float = 0.0
    
    def calculate_sharpe_ratio(self, risk_free_rate: float = 0.0) -> float:
        """Calculate Sharpe ratio for the strategy"""
        if self.total_trades < 10:
            return 0.0
        
        # Use daily returns approximation
        daily_return = self.net_pnl / max(self.total_spot_volume, 1.0)
        # Simplified Sharpe calculation - in production would need proper volatility
        return (daily_return - risk_free_rate) / max(daily_return * 0.1, 0.01)


class MakerPerformanceMonitor:
    """Comprehensive performance monitoring for maker strategy"""
    
    def __init__(self, config: MakerLimitConfig, logger: Optional[HFTLoggerInterface] = None):
        self.config = config
        self.logger = logger
        
        # Performance metrics
        self.metrics = PerformanceMetrics()
        self.trade_history: List[TradeRecord] = []
        
        # Real-time tracking
        self.execution_times: deque = deque(maxlen=100)  # Last 100 hedge executions
        self.slippage_history: deque = deque(maxlen=100)  # Last 100 slippage measurements
        self.delta_history: deque = deque(maxlen=1000)    # Last 1000 delta measurements
        self.loop_times: deque = deque(maxlen=500)        # Last 500 loop times
        
        # Market condition tracking
        self.market_condition_history: deque = deque(maxlen=500)
        self.circuit_breaker_events: List[Dict] = []
        
        # Alert tracking
        self.active_alerts: Dict[PerformanceAlert, float] = {}  # Alert -> timestamp
        self.alert_history: List[Dict] = []
        
        # Performance benchmarks (configurable)
        self.performance_thresholds = {
            'max_acceptable_hedge_time_ms': 150,
            'max_acceptable_slippage_bps': 50,
            'min_hedge_success_rate': 0.95,
            'max_delta_deviation_ratio': 0.05,  # 5% of position size
            'min_win_rate': 0.6,
            'max_circuit_breaker_rate': 0.1,  # 10% of time
            'min_correlation': 0.7
        }
        
        # Monitoring state
        self.last_metrics_calculation = time.time()
        self.last_alert_check = time.time()
        self.monitoring_start_time = time.time()
    
    async def record_trade(self, fill_event: OrderFillEvent, hedge_result: HedgeResult,
                         market_analysis: MarketAnalysis, net_delta_before: float,
                         net_delta_after: float):
        """Record a completed trade for performance analysis"""
        
        # Calculate delta improvement
        delta_improvement = abs(net_delta_before) - abs(net_delta_after)
        
        # Estimate PnL (simplified - in production would need more sophisticated calculation)
        estimated_pnl = self._estimate_trade_pnl(fill_event, hedge_result)
        
        # Estimate fees
        fees_paid = self._estimate_fees(fill_event, hedge_result)
        
        trade_record = TradeRecord(
            timestamp=time.time(),
            spot_side=fill_event.side.name,
            spot_price=fill_event.fill_price,
            spot_quantity=fill_event.fill_quantity,
            spot_order_id=fill_event.order.order_id,
            hedge_success=hedge_result.success,
            hedge_price=hedge_result.hedge_price,
            hedge_quantity=hedge_result.hedge_quantity,
            hedge_execution_time_ms=hedge_result.execution_time_ms,
            hedge_slippage_bps=hedge_result.slippage_bps,
            net_delta_before=net_delta_before,
            net_delta_after=net_delta_after,
            delta_improvement=delta_improvement,
            volatility_ratio=market_analysis.volatility_metrics.volatility_ratio,
            correlation=market_analysis.correlation_metrics.correlation,
            market_regime=str(market_analysis.regime_metrics.regime_multiplier),
            estimated_pnl=estimated_pnl,
            fees_paid=fees_paid,
            net_pnl=estimated_pnl - fees_paid
        )
        
        # Add to history
        self.trade_history.append(trade_record)
        
        # Maintain history size limit
        if len(self.trade_history) > self.config.trade_history_max_size:
            self.trade_history = self.trade_history[-self.config.trade_history_max_size:]
        
        # Update real-time tracking
        if hedge_result.success:
            self.execution_times.append(hedge_result.execution_time_ms)
            self.slippage_history.append(hedge_result.slippage_bps)
        
        self.delta_history.append(net_delta_after)
        
        # Update performance metrics
        await self._update_performance_metrics(trade_record)
        
        # Log trade completion
        if self.logger:
            self.logger.info("Trade recorded", extra={
                'trade_id': len(self.trade_history),
                'spot_side': trade_record.spot_side,
                'hedge_success': trade_record.hedge_success,
                'execution_time_ms': trade_record.hedge_execution_time_ms,
                'slippage_bps': trade_record.hedge_slippage_bps,
                'net_pnl': trade_record.net_pnl,
                'delta_improvement': trade_record.delta_improvement
            })
    
    async def record_loop_performance(self, loop_time_ms: float):
        """Record main loop performance"""
        self.loop_times.append(loop_time_ms)
        
        # Check for slow loops
        if loop_time_ms > self.performance_thresholds['max_acceptable_hedge_time_ms']:
            await self._trigger_alert(PerformanceAlert.SLOW_EXECUTION, {
                'loop_time_ms': loop_time_ms,
                'threshold_ms': self.performance_thresholds['max_acceptable_hedge_time_ms']
            })
    
    async def record_market_conditions(self, market_analysis: MarketAnalysis):
        """Record market conditions for analysis"""
        condition_snapshot = {
            'timestamp': time.time(),
            'volatility_ratio': market_analysis.volatility_metrics.volatility_ratio,
            'correlation': market_analysis.correlation_metrics.correlation,
            'regime_multiplier': market_analysis.regime_metrics.regime_multiplier,
            'liquidity_tier': market_analysis.liquidity_metrics.liquidity_tier,
            'spike_detected': market_analysis.volatility_metrics.spike_detected
        }
        
        self.market_condition_history.append(condition_snapshot)
    
    async def record_circuit_breaker_event(self, triggers: List[str], severity: str, 
                                         cooldown_period: int):
        """Record circuit breaker activation"""
        event = {
            'timestamp': time.time(),
            'triggers': triggers,
            'severity': severity,
            'cooldown_period': cooldown_period
        }
        
        self.circuit_breaker_events.append(event)
        
        # Update metrics
        self.metrics.circuit_breaker_triggers += 1
        
        # Check if circuit breaker rate is too high
        recent_events = [e for e in self.circuit_breaker_events 
                        if time.time() - e['timestamp'] < 3600]  # Last hour
        
        if len(recent_events) > 10:  # More than 10 circuit breakers per hour
            await self._trigger_alert(PerformanceAlert.HIGH_CIRCUIT_TRIGGERS, {
                'recent_triggers': len(recent_events),
                'severity': severity
            })
    
    async def _update_performance_metrics(self, trade_record: TradeRecord):
        """Update comprehensive performance metrics"""
        
        # Trading metrics
        self.metrics.total_trades += 1
        if trade_record.hedge_success:
            self.metrics.successful_hedges += 1
        else:
            self.metrics.failed_hedges += 1
        
        self.metrics.total_spot_volume += trade_record.spot_quantity
        self.metrics.total_futures_volume += trade_record.hedge_quantity
        
        # Execution performance
        if trade_record.hedge_success:
            self.metrics.avg_hedge_time_ms = statistics.mean(self.execution_times)
            self.metrics.avg_slippage_bps = statistics.mean(self.slippage_history)
            self.metrics.max_hedge_time_ms = max(self.execution_times)
            self.metrics.max_slippage_bps = max(self.slippage_history)
        
        # Position tracking
        self.metrics.current_net_delta = trade_record.net_delta_after
        
        if len(self.delta_history) > 0:
            delta_values = [abs(d) for d in self.delta_history]
            self.metrics.max_delta_deviation = max(delta_values)
            
            # Calculate delta neutral ratio
            neutral_count = sum(1 for d in delta_values if d <= 0.001)
            self.metrics.delta_neutral_ratio = neutral_count / len(delta_values)
        
        # Profitability
        self.metrics.total_pnl += trade_record.estimated_pnl
        self.metrics.total_fees += trade_record.fees_paid
        self.metrics.net_pnl += trade_record.net_pnl
        
        if self.metrics.total_trades > 0:
            self.metrics.avg_trade_pnl = self.metrics.net_pnl / self.metrics.total_trades
            
            profitable_trades = sum(1 for t in self.trade_history if t.is_profitable())
            self.metrics.win_rate = profitable_trades / len(self.trade_history)
        
        # Market conditions
        if len(self.market_condition_history) > 0:
            recent_conditions = list(self.market_condition_history)[-100:]  # Last 100
            self.metrics.avg_volatility_ratio = statistics.mean([c['volatility_ratio'] for c in recent_conditions])
            self.metrics.avg_correlation = statistics.mean([c['correlation'] for c in recent_conditions])
        
        # Check for performance alerts
        await self._check_performance_alerts()
    
    async def _check_performance_alerts(self):
        """Check for performance threshold violations and trigger alerts"""
        
        current_time = time.time()
        
        # Rate limit alert checks
        if current_time - self.last_alert_check < 60:  # Check every minute
            return
        
        self.last_alert_check = current_time
        
        # Check hedge success rate
        if self.metrics.total_trades >= 10:
            hedge_success_rate = self.metrics.successful_hedges / self.metrics.total_trades
            if hedge_success_rate < self.performance_thresholds['min_hedge_success_rate']:
                await self._trigger_alert(PerformanceAlert.POOR_HEDGE_RATE, {
                    'current_rate': hedge_success_rate,
                    'threshold': self.performance_thresholds['min_hedge_success_rate']
                })
        
        # Check average slippage
        if (len(self.slippage_history) >= 10 and 
            self.metrics.avg_slippage_bps > self.performance_thresholds['max_acceptable_slippage_bps']):
            await self._trigger_alert(PerformanceAlert.HIGH_SLIPPAGE, {
                'avg_slippage_bps': self.metrics.avg_slippage_bps,
                'threshold': self.performance_thresholds['max_acceptable_slippage_bps']
            })
        
        # Check delta deviation
        position_size_estimate = self.config.position_size_usd
        if (self.metrics.max_delta_deviation > 
            position_size_estimate * self.performance_thresholds['max_delta_deviation_ratio']):
            await self._trigger_alert(PerformanceAlert.DELTA_DEVIATION, {
                'max_delta_deviation': self.metrics.max_delta_deviation,
                'threshold_ratio': self.performance_thresholds['max_delta_deviation_ratio']
            })
        
        # Check win rate
        if (self.metrics.total_trades >= 20 and 
            self.metrics.win_rate < self.performance_thresholds['min_win_rate']):
            await self._trigger_alert(PerformanceAlert.LOW_FILL_RATE, {
                'current_win_rate': self.metrics.win_rate,
                'threshold': self.performance_thresholds['min_win_rate']
            })
        
        # Check correlation
        if (self.metrics.avg_correlation < self.performance_thresholds['min_correlation']):
            await self._trigger_alert(PerformanceAlert.POSITION_IMBALANCE, {
                'avg_correlation': self.metrics.avg_correlation,
                'threshold': self.performance_thresholds['min_correlation']
            })
    
    async def _trigger_alert(self, alert_type: PerformanceAlert, context: Dict):
        """Trigger performance alert with context"""
        
        current_time = time.time()
        
        # Avoid duplicate alerts within 10 minutes
        if (alert_type in self.active_alerts and 
            current_time - self.active_alerts[alert_type] < 600):
            return
        
        self.active_alerts[alert_type] = current_time
        
        alert_record = {
            'timestamp': current_time,
            'alert_type': alert_type.value,
            'context': context,
            'metrics_snapshot': self._get_metrics_snapshot()
        }
        
        self.alert_history.append(alert_record)
        
        # Log alert
        if self.logger:
            self.logger.warning(f"Performance alert: {alert_type.value}", extra={
                'alert_context': context,
                'alert_timestamp': current_time
            })
    
    def _estimate_trade_pnl(self, fill_event: OrderFillEvent, hedge_result: HedgeResult) -> float:
        """Estimate trade PnL (simplified calculation)"""
        if not hedge_result.success or not hedge_result.hedge_price:
            return 0.0
        
        # Simple spread capture estimation
        # In practice, this would be more sophisticated
        spot_price = fill_event.fill_price
        hedge_price = hedge_result.hedge_price
        
        if fill_event.side.name == 'BUY':
            # Bought spot, sold futures - profit if spot < futures
            spread = hedge_price - spot_price
        else:
            # Sold spot, bought futures - profit if spot > futures
            spread = spot_price - hedge_price
        
        # Estimate profit as spread * quantity
        profit = spread * fill_event.fill_quantity
        return profit
    
    def _estimate_fees(self, fill_event: OrderFillEvent, hedge_result: HedgeResult) -> float:
        """Estimate total fees paid"""
        # Simplified fee calculation - should use actual exchange fee schedules
        spot_fee_rate = 0.001  # 0.1%
        futures_fee_rate = 0.0005  # 0.05%
        
        spot_fees = fill_event.fill_price * fill_event.fill_quantity * spot_fee_rate
        
        if hedge_result.success and hedge_result.hedge_price:
            futures_fees = hedge_result.hedge_price * hedge_result.hedge_quantity * futures_fee_rate
        else:
            futures_fees = 0.0
        
        return spot_fees + futures_fees
    
    def _get_metrics_snapshot(self) -> Dict[str, any]:
        """Get current metrics snapshot for alerts"""
        return {
            'total_trades': self.metrics.total_trades,
            'hedge_success_rate': self.metrics.successful_hedges / max(self.metrics.total_trades, 1),
            'avg_hedge_time_ms': self.metrics.avg_hedge_time_ms,
            'avg_slippage_bps': self.metrics.avg_slippage_bps,
            'net_pnl': self.metrics.net_pnl,
            'win_rate': self.metrics.win_rate,
            'current_delta': self.metrics.current_net_delta
        }
    
    def get_comprehensive_report(self) -> Dict[str, any]:
        """Generate comprehensive performance report"""
        
        current_time = time.time()
        uptime_hours = (current_time - self.monitoring_start_time) / 3600
        
        return {
            'strategy_uptime_hours': uptime_hours,
            'metrics': {
                'total_trades': self.metrics.total_trades,
                'successful_hedges': self.metrics.successful_hedges,
                'failed_hedges': self.metrics.failed_hedges,
                'hedge_success_rate': self.metrics.successful_hedges / max(self.metrics.total_trades, 1),
                'avg_hedge_time_ms': self.metrics.avg_hedge_time_ms,
                'avg_slippage_bps': self.metrics.avg_slippage_bps,
                'total_volume_usd': self.metrics.total_spot_volume + self.metrics.total_futures_volume,
                'net_pnl_usd': self.metrics.net_pnl,
                'win_rate': self.metrics.win_rate,
                'sharpe_ratio': self.metrics.calculate_sharpe_ratio(),
                'delta_neutral_ratio': self.metrics.delta_neutral_ratio,
                'circuit_breaker_triggers': self.metrics.circuit_breaker_triggers
            },
            'recent_performance': {
                'avg_loop_time_ms': statistics.mean(self.loop_times) if self.loop_times else 0,
                'recent_execution_times': list(self.execution_times)[-10:],
                'recent_slippage': list(self.slippage_history)[-10:],
                'recent_delta_values': list(self.delta_history)[-20:]
            },
            'alerts': {
                'active_alerts': len(self.active_alerts),
                'total_alerts': len(self.alert_history),
                'recent_alerts': [a for a in self.alert_history if current_time - a['timestamp'] < 3600]
            },
            'market_conditions': {
                'avg_volatility_ratio': self.metrics.avg_volatility_ratio,
                'avg_correlation': self.metrics.avg_correlation,
                'favorable_conditions_ratio': self.metrics.favorable_market_ratio
            }
        }
    
    def clear_alerts(self):
        """Clear all active alerts (admin function)"""
        self.active_alerts.clear()
        if self.logger:
            self.logger.info("Performance alerts cleared")
    
    def reset_metrics(self):
        """Reset performance metrics (admin function)"""
        self.metrics = PerformanceMetrics()
        self.trade_history.clear()
        self.execution_times.clear()
        self.slippage_history.clear()
        self.delta_history.clear()
        self.monitoring_start_time = time.time()
        
        if self.logger:
            self.logger.info("Performance metrics reset")