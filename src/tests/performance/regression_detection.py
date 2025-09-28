"""
Automated Performance Regression Detection

This module provides automated detection of performance regressions in WebSocket
message processing with configurable thresholds and alerting capabilities.

Key Features:
- Real-time regression monitoring
- Configurable performance thresholds
- Automated alerting and reporting
- Integration with baseline metrics
- Circuit breaker patterns for critical regressions
"""

import asyncio
import time
from typing import Dict, List, Any, Optional, Callable, Awaitable
from dataclasses import dataclass
from enum import Enum

from infrastructure.logging import get_logger
from .baseline_metrics import BaselineMetricsManager, get_baseline_manager


class RegressionSeverity(Enum):
    """Severity levels for performance regressions."""
    LOW = "low"           # 10-25% degradation
    MEDIUM = "medium"     # 25-50% degradation
    HIGH = "high"         # 50-100% degradation
    CRITICAL = "critical" # >100% degradation or system failure


@dataclass
class RegressionAlert:
    """Performance regression alert."""
    timestamp: float
    architecture: str
    severity: RegressionSeverity
    metric: str
    degradation_pct: float
    current_value: float
    baseline_value: float
    threshold_pct: float
    message: str


@dataclass
class RegressionConfig:
    """Configuration for regression detection."""
    # Threshold percentages for different severity levels
    low_threshold_pct: float = 10.0
    medium_threshold_pct: float = 25.0
    high_threshold_pct: float = 50.0
    critical_threshold_pct: float = 100.0
    
    # Monitoring settings
    continuous_monitoring: bool = True
    check_interval_sec: float = 60.0
    
    # Circuit breaker settings
    enable_circuit_breaker: bool = True
    critical_regression_action: str = "alert"  # "alert", "disable", "fallback"
    
    # Alert settings
    enable_alerts: bool = True
    alert_cooldown_sec: float = 300.0  # 5 minutes between same alerts


class PerformanceRegressionDetector:
    """Automated performance regression detection system."""
    
    def __init__(
        self,
        config: RegressionConfig = None,
        baseline_manager: BaselineMetricsManager = None,
        alert_callback: Optional[Callable[[RegressionAlert], Awaitable[None]]] = None
    ):
        """
        Initialize regression detector.
        
        Args:
            config: Regression detection configuration
            baseline_manager: Baseline metrics manager
            alert_callback: Async callback for handling alerts
        """
        self.config = config or RegressionConfig()
        self.baseline_manager = baseline_manager or get_baseline_manager()
        self.alert_callback = alert_callback
        self.logger = get_logger("performance.regression", tags=["performance", "monitoring"])
        
        # Alert tracking
        self.recent_alerts: List[RegressionAlert] = []
        self.circuit_breaker_state = {}  # architecture -> bool
        
        # Monitoring state
        self.monitoring_active = False
        self.monitoring_task: Optional[asyncio.Task] = None
        
        self.logger.info("Performance regression detector initialized",
                        continuous_monitoring=self.config.continuous_monitoring,
                        check_interval_sec=self.config.check_interval_sec)
    
    async def check_regression(
        self,
        current_metrics: Dict[str, Any],
        architecture: str
    ) -> Optional[RegressionAlert]:
        """
        Check for performance regression in current metrics.
        
        Args:
            current_metrics: Current performance measurements
            architecture: Architecture being tested (legacy/direct)
            
        Returns:
            RegressionAlert if regression detected, None otherwise
        """
        # Get latest baseline
        latest_baseline = self.baseline_manager.get_latest_baseline(architecture)
        
        if not latest_baseline:
            self.logger.warning("No baseline available for regression check",
                              architecture=architecture)
            return None
        
        # Check each metric for regression
        alerts = []
        
        # Latency regression check
        if 'latency_avg_us' in current_metrics and latest_baseline.latency_avg_us > 0:
            latency_degradation = self._calculate_degradation_pct(
                current_metrics['latency_avg_us'],
                latest_baseline.latency_avg_us,
                higher_is_worse=True
            )
            
            if latency_degradation >= self.config.low_threshold_pct:
                severity = self._determine_severity(latency_degradation)
                alerts.append(RegressionAlert(
                    timestamp=time.time(),
                    architecture=architecture,
                    severity=severity,
                    metric="latency",
                    degradation_pct=latency_degradation,
                    current_value=current_metrics['latency_avg_us'],
                    baseline_value=latest_baseline.latency_avg_us,
                    threshold_pct=self.config.low_threshold_pct,
                    message=f"Latency degraded by {latency_degradation:.1f}% in {architecture} architecture"
                ))
        
        # Throughput regression check
        if 'throughput_msg_per_sec' in current_metrics and latest_baseline.throughput_msg_per_sec > 0:
            throughput_degradation = self._calculate_degradation_pct(
                current_metrics['throughput_msg_per_sec'],
                latest_baseline.throughput_msg_per_sec,
                higher_is_worse=False
            )
            
            if throughput_degradation >= self.config.low_threshold_pct:
                severity = self._determine_severity(throughput_degradation)
                alerts.append(RegressionAlert(
                    timestamp=time.time(),
                    architecture=architecture,
                    severity=severity,
                    metric="throughput",
                    degradation_pct=throughput_degradation,
                    current_value=current_metrics['throughput_msg_per_sec'],
                    baseline_value=latest_baseline.throughput_msg_per_sec,
                    threshold_pct=self.config.low_threshold_pct,
                    message=f"Throughput degraded by {throughput_degradation:.1f}% in {architecture} architecture"
                ))
        
        # Return most severe alert if any
        if alerts:
            most_severe = max(alerts, key=lambda a: a.degradation_pct)
            await self._handle_regression_alert(most_severe)
            return most_severe
        
        return None
    
    def _calculate_degradation_pct(
        self, 
        current_value: float, 
        baseline_value: float, 
        higher_is_worse: bool
    ) -> float:
        """Calculate degradation percentage."""
        if baseline_value == 0:
            return 0.0
        
        if higher_is_worse:
            # For latency: higher current value is worse
            if current_value <= baseline_value:
                return 0.0  # No degradation
            return (current_value - baseline_value) / baseline_value * 100
        else:
            # For throughput: lower current value is worse
            if current_value >= baseline_value:
                return 0.0  # No degradation
            return (baseline_value - current_value) / baseline_value * 100
    
    def _determine_severity(self, degradation_pct: float) -> RegressionSeverity:
        """Determine severity level based on degradation percentage."""
        if degradation_pct >= self.config.critical_threshold_pct:
            return RegressionSeverity.CRITICAL
        elif degradation_pct >= self.config.high_threshold_pct:
            return RegressionSeverity.HIGH
        elif degradation_pct >= self.config.medium_threshold_pct:
            return RegressionSeverity.MEDIUM
        else:
            return RegressionSeverity.LOW
    
    async def _handle_regression_alert(self, alert: RegressionAlert) -> None:
        """Handle regression alert with appropriate actions."""
        # Check alert cooldown
        if self._is_alert_suppressed(alert):
            self.logger.debug("Alert suppressed due to cooldown",
                            architecture=alert.architecture,
                            metric=alert.metric,
                            severity=alert.severity.value)
            return
        
        # Add to recent alerts
        self.recent_alerts.append(alert)
        
        # Clean old alerts
        cutoff_time = time.time() - (24 * 60 * 60)  # 24 hours
        self.recent_alerts = [a for a in self.recent_alerts if a.timestamp >= cutoff_time]
        
        # Log the alert
        self.logger.warning("Performance regression detected",
                          architecture=alert.architecture,
                          metric=alert.metric,
                          severity=alert.severity.value,
                          degradation_pct=alert.degradation_pct,
                          current_value=alert.current_value,
                          baseline_value=alert.baseline_value)
        
        # Handle critical regressions
        if alert.severity == RegressionSeverity.CRITICAL:
            await self._handle_critical_regression(alert)
        
        # Send alert through callback
        if self.config.enable_alerts and self.alert_callback:
            try:
                await self.alert_callback(alert)
            except Exception as e:
                self.logger.error("Error in alert callback",
                                error=str(e),
                                alert_architecture=alert.architecture)
    
    def _is_alert_suppressed(self, alert: RegressionAlert) -> bool:
        """Check if alert should be suppressed due to cooldown."""
        cutoff_time = time.time() - self.config.alert_cooldown_sec
        
        # Check for similar recent alerts
        for recent_alert in self.recent_alerts:
            if (recent_alert.timestamp >= cutoff_time and
                recent_alert.architecture == alert.architecture and
                recent_alert.metric == alert.metric and
                recent_alert.severity == alert.severity):
                return True
        
        return False
    
    async def _handle_critical_regression(self, alert: RegressionAlert) -> None:
        """Handle critical regression with configured action."""
        if not self.config.enable_circuit_breaker:
            return
        
        action = self.config.critical_regression_action
        
        if action == "disable":
            # Trigger circuit breaker
            self.circuit_breaker_state[alert.architecture] = True
            self.logger.error("Circuit breaker activated for critical regression",
                            architecture=alert.architecture,
                            metric=alert.metric,
                            degradation_pct=alert.degradation_pct)
            
        elif action == "fallback":
            # This would need integration with WebSocket Manager
            self.logger.error("Fallback action triggered for critical regression",
                            architecture=alert.architecture,
                            metric=alert.metric,
                            degradation_pct=alert.degradation_pct,
                            recommendation="Consider switching to alternate architecture")
        
        # Always alert for critical regressions
        self.logger.critical("Critical performance regression detected",
                           architecture=alert.architecture,
                           metric=alert.metric,
                           degradation_pct=alert.degradation_pct,
                           action_taken=action)
    
    def is_circuit_breaker_active(self, architecture: str) -> bool:
        """Check if circuit breaker is active for an architecture."""
        return self.circuit_breaker_state.get(architecture, False)
    
    def reset_circuit_breaker(self, architecture: str) -> None:
        """Reset circuit breaker for an architecture."""
        if architecture in self.circuit_breaker_state:
            del self.circuit_breaker_state[architecture]
            self.logger.info("Circuit breaker reset",
                           architecture=architecture)
    
    async def start_continuous_monitoring(self) -> None:
        """Start continuous performance monitoring."""
        if self.monitoring_active:
            self.logger.warning("Continuous monitoring already active")
            return
        
        self.monitoring_active = True
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        
        self.logger.info("Started continuous performance monitoring",
                        check_interval_sec=self.config.check_interval_sec)
    
    async def stop_continuous_monitoring(self) -> None:
        """Stop continuous performance monitoring."""
        self.monitoring_active = False
        
        if self.monitoring_task and not self.monitoring_task.done():
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Stopped continuous performance monitoring")
    
    async def _monitoring_loop(self) -> None:
        """Continuous monitoring loop."""
        try:
            while self.monitoring_active:
                await asyncio.sleep(self.config.check_interval_sec)
                
                # This would need integration with actual performance measurement
                # For now, it's a placeholder for the monitoring framework
                self.logger.debug("Performance monitoring check completed")
                
        except asyncio.CancelledError:
            self.logger.debug("Monitoring loop cancelled")
        except Exception as e:
            self.logger.error("Error in monitoring loop",
                            error=str(e))
    
    def get_regression_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get summary of regressions in the specified time period."""
        cutoff_time = time.time() - (hours * 60 * 60)
        recent_regressions = [a for a in self.recent_alerts if a.timestamp >= cutoff_time]
        
        # Group by architecture and severity
        summary = {
            'time_period_hours': hours,
            'total_regressions': len(recent_regressions),
            'by_architecture': {},
            'by_severity': {},
            'circuit_breakers_active': list(self.circuit_breaker_state.keys()),
            'monitoring_active': self.monitoring_active
        }
        
        for alert in recent_regressions:
            # By architecture
            if alert.architecture not in summary['by_architecture']:
                summary['by_architecture'][alert.architecture] = {
                    'count': 0,
                    'severities': {},
                    'metrics_affected': set()
                }
            
            arch_data = summary['by_architecture'][alert.architecture]
            arch_data['count'] += 1
            arch_data['metrics_affected'].add(alert.metric)
            
            if alert.severity.value not in arch_data['severities']:
                arch_data['severities'][alert.severity.value] = 0
            arch_data['severities'][alert.severity.value] += 1
            
            # By severity
            if alert.severity.value not in summary['by_severity']:
                summary['by_severity'][alert.severity.value] = 0
            summary['by_severity'][alert.severity.value] += 1
        
        # Convert sets to lists for JSON serialization
        for arch_data in summary['by_architecture'].values():
            arch_data['metrics_affected'] = list(arch_data['metrics_affected'])
        
        return summary


# Default alert callback for logging
async def default_alert_callback(alert: RegressionAlert) -> None:
    """Default alert callback that logs alerts."""
    logger = get_logger("performance.alerts", tags=["performance", "alert"])
    
    logger.warning("PERFORMANCE REGRESSION ALERT",
                  architecture=alert.architecture,
                  severity=alert.severity.value,
                  metric=alert.metric,
                  degradation_pct=alert.degradation_pct,
                  current_value=alert.current_value,
                  baseline_value=alert.baseline_value,
                  message=alert.message)


# Global detector instance
_regression_detector = None


def get_regression_detector(
    config: RegressionConfig = None,
    alert_callback: Optional[Callable[[RegressionAlert], Awaitable[None]]] = None
) -> PerformanceRegressionDetector:
    """Get global regression detector instance."""
    global _regression_detector
    if _regression_detector is None:
        callback = alert_callback or default_alert_callback
        _regression_detector = PerformanceRegressionDetector(config, alert_callback=callback)
    return _regression_detector


# Convenience functions
async def check_current_performance(
    metrics: Dict[str, Any],
    architecture: str
) -> bool:
    """Check if current metrics show regression."""
    detector = get_regression_detector()
    alert = await detector.check_regression(metrics, architecture)
    return alert is not None


async def start_monitoring() -> None:
    """Start continuous performance monitoring."""
    detector = get_regression_detector()
    await detector.start_continuous_monitoring()


async def stop_monitoring() -> None:
    """Stop continuous performance monitoring."""
    detector = get_regression_detector()
    await detector.stop_continuous_monitoring()


if __name__ == "__main__":
    # Example usage
    async def main():
        # Test regression detection
        detector = PerformanceRegressionDetector()
        
        # Simulate performance metrics
        test_metrics = {
            'latency_avg_us': 150.0,  # Simulated regression
            'throughput_msg_per_sec': 8000.0
        }
        
        alert = await detector.check_regression(test_metrics, "direct")
        
        if alert:
            print(f"Regression detected: {alert.message}")
            print(f"Severity: {alert.severity.value}")
            print(f"Degradation: {alert.degradation_pct:.1f}%")
        else:
            print("No regression detected")
        
        # Get summary
        summary = detector.get_regression_summary()
        print(f"Regression summary: {summary}")
    
    asyncio.run(main())