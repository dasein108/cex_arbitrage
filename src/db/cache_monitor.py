"""
Cache Performance Monitoring

Advanced monitoring and alerting for symbol cache performance.
Provides real-time metrics, alerting, and performance optimization recommendations.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import statistics
import threading

from .cache import get_symbol_cache, CacheStats
from .cache_operations import get_cache_stats, validate_cache_performance


logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class PerformanceThresholds:
    """Performance threshold configuration."""
    # Lookup time thresholds (microseconds)
    lookup_time_warning_us: float = 2.0
    lookup_time_critical_us: float = 5.0
    
    # Hit ratio thresholds
    hit_ratio_warning: float = 0.90
    hit_ratio_critical: float = 0.80
    
    # Request volume thresholds
    requests_per_second_warning: int = 10000
    requests_per_second_critical: int = 50000
    
    # Cache staleness thresholds
    staleness_warning_minutes: int = 10
    staleness_critical_minutes: int = 30


@dataclass
class PerformanceAlert:
    """Performance alert data."""
    level: AlertLevel
    timestamp: datetime
    metric: str
    current_value: float
    threshold_value: float
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PerformanceSnapshot:
    """Point-in-time performance snapshot."""
    timestamp: datetime
    avg_lookup_time_us: float
    hit_ratio: float
    total_requests: int
    cache_size: int
    requests_per_second: float
    last_refresh_age_minutes: float


class CachePerformanceMonitor:
    """
    Advanced cache performance monitoring system.
    
    Provides real-time performance tracking, alerting, and optimization
    recommendations for HFT cache operations.
    """
    
    def __init__(self, thresholds: PerformanceThresholds = None):
        """
        Initialize performance monitor.
        
        Args:
            thresholds: Performance thresholds for alerting
        """
        self._logger = logging.getLogger(f"{__name__}.CachePerformanceMonitor")
        self._thresholds = thresholds or PerformanceThresholds()
        
        # Performance history
        self._snapshots: List[PerformanceSnapshot] = []
        self._max_snapshots = 1000
        
        # Alert management
        self._alerts: List[PerformanceAlert] = []
        self._max_alerts = 100
        self._alert_callbacks: List[Callable[[PerformanceAlert], None]] = []
        
        # Monitoring state
        self._monitoring_active = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._monitor_interval = 1.0  # seconds
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Statistics tracking
        self._last_request_count = 0
        self._last_snapshot_time = time.time()
        
        self._logger.info("Cache performance monitor initialized")
    
    async def start_monitoring(self, interval_seconds: float = 1.0) -> None:
        """
        Start continuous performance monitoring.
        
        Args:
            interval_seconds: Monitoring interval in seconds
        """
        if self._monitoring_active:
            self._logger.warning("Performance monitoring already active")
            return
        
        self._monitor_interval = interval_seconds
        self._monitoring_active = True
        
        self._monitor_task = asyncio.create_task(self._monitoring_loop())
        self._logger.info(f"Started cache performance monitoring (interval: {interval_seconds}s)")
    
    async def stop_monitoring(self) -> None:
        """Stop continuous performance monitoring."""
        if not self._monitoring_active:
            return
        
        self._monitoring_active = False
        
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        self._logger.info("Stopped cache performance monitoring")
    
    async def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        while self._monitoring_active:
            try:
                await self._collect_snapshot()
                await self._check_performance_thresholds()
                await asyncio.sleep(self._monitor_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(self._monitor_interval)
    
    async def _collect_snapshot(self) -> None:
        """Collect a performance snapshot."""
        try:
            cache_stats = get_cache_stats()
            current_time = time.time()
            
            # Calculate requests per second
            requests_delta = cache_stats.total_requests - self._last_request_count
            time_delta = current_time - self._last_snapshot_time
            requests_per_second = requests_delta / time_delta if time_delta > 0 else 0
            
            # Calculate cache staleness
            if cache_stats.last_refresh:
                refresh_age = datetime.utcnow() - cache_stats.last_refresh
                staleness_minutes = refresh_age.total_seconds() / 60
            else:
                staleness_minutes = float('inf')
            
            snapshot = PerformanceSnapshot(
                timestamp=datetime.utcnow(),
                avg_lookup_time_us=cache_stats.avg_lookup_time_us,
                hit_ratio=cache_stats.hit_ratio,
                total_requests=cache_stats.total_requests,
                cache_size=cache_stats.cache_size,
                requests_per_second=requests_per_second,
                last_refresh_age_minutes=staleness_minutes
            )
            
            with self._lock:
                self._snapshots.append(snapshot)
                
                # Keep only recent snapshots
                if len(self._snapshots) > self._max_snapshots:
                    self._snapshots = self._snapshots[-self._max_snapshots:]
                
                # Update tracking variables
                self._last_request_count = cache_stats.total_requests
                self._last_snapshot_time = current_time
            
        except Exception as e:
            self._logger.error(f"Failed to collect performance snapshot: {e}")
    
    async def _check_performance_thresholds(self) -> None:
        """Check performance against thresholds and generate alerts."""
        if not self._snapshots:
            return
        
        latest = self._snapshots[-1]
        
        # Check lookup time
        if latest.avg_lookup_time_us >= self._thresholds.lookup_time_critical_us:
            await self._create_alert(
                AlertLevel.CRITICAL,
                "lookup_time",
                latest.avg_lookup_time_us,
                self._thresholds.lookup_time_critical_us,
                f"Critical lookup time: {latest.avg_lookup_time_us:.3f}μs (threshold: {self._thresholds.lookup_time_critical_us}μs)"
            )
        elif latest.avg_lookup_time_us >= self._thresholds.lookup_time_warning_us:
            await self._create_alert(
                AlertLevel.WARNING,
                "lookup_time",
                latest.avg_lookup_time_us,
                self._thresholds.lookup_time_warning_us,
                f"High lookup time: {latest.avg_lookup_time_us:.3f}μs (threshold: {self._thresholds.lookup_time_warning_us}μs)"
            )
        
        # Check hit ratio
        if latest.hit_ratio <= self._thresholds.hit_ratio_critical:
            await self._create_alert(
                AlertLevel.CRITICAL,
                "hit_ratio",
                latest.hit_ratio,
                self._thresholds.hit_ratio_critical,
                f"Critical hit ratio: {latest.hit_ratio:.1%} (threshold: {self._thresholds.hit_ratio_critical:.1%})"
            )
        elif latest.hit_ratio <= self._thresholds.hit_ratio_warning:
            await self._create_alert(
                AlertLevel.WARNING,
                "hit_ratio",
                latest.hit_ratio,
                self._thresholds.hit_ratio_warning,
                f"Low hit ratio: {latest.hit_ratio:.1%} (threshold: {self._thresholds.hit_ratio_warning:.1%})"
            )
        
        # Check request volume
        if latest.requests_per_second >= self._thresholds.requests_per_second_critical:
            await self._create_alert(
                AlertLevel.CRITICAL,
                "request_volume",
                latest.requests_per_second,
                self._thresholds.requests_per_second_critical,
                f"Critical request volume: {latest.requests_per_second:.0f} req/s (threshold: {self._thresholds.requests_per_second_critical})"
            )
        elif latest.requests_per_second >= self._thresholds.requests_per_second_warning:
            await self._create_alert(
                AlertLevel.WARNING,
                "request_volume",
                latest.requests_per_second,
                self._thresholds.requests_per_second_warning,
                f"High request volume: {latest.requests_per_second:.0f} req/s (threshold: {self._thresholds.requests_per_second_warning})"
            )
        
        # Check cache staleness
        if latest.last_refresh_age_minutes >= self._thresholds.staleness_critical_minutes:
            await self._create_alert(
                AlertLevel.CRITICAL,
                "staleness",
                latest.last_refresh_age_minutes,
                self._thresholds.staleness_critical_minutes,
                f"Critical cache staleness: {latest.last_refresh_age_minutes:.1f} minutes (threshold: {self._thresholds.staleness_critical_minutes})"
            )
        elif latest.last_refresh_age_minutes >= self._thresholds.staleness_warning_minutes:
            await self._create_alert(
                AlertLevel.WARNING,
                "staleness",
                latest.last_refresh_age_minutes,
                self._thresholds.staleness_warning_minutes,
                f"Cache staleness: {latest.last_refresh_age_minutes:.1f} minutes (threshold: {self._thresholds.staleness_warning_minutes})"
            )
    
    async def _create_alert(
        self,
        level: AlertLevel,
        metric: str,
        current_value: float,
        threshold_value: float,
        message: str
    ) -> None:
        """Create and process a performance alert."""
        alert = PerformanceAlert(
            level=level,
            timestamp=datetime.utcnow(),
            metric=metric,
            current_value=current_value,
            threshold_value=threshold_value,
            message=message
        )
        
        with self._lock:
            self._alerts.append(alert)
            
            # Keep only recent alerts
            if len(self._alerts) > self._max_alerts:
                self._alerts = self._alerts[-self._max_alerts:]
        
        # Log alert
        log_level = {
            AlertLevel.INFO: logging.INFO,
            AlertLevel.WARNING: logging.WARNING,
            AlertLevel.CRITICAL: logging.CRITICAL
        }[level]
        
        self._logger.log(log_level, f"Performance Alert [{level.value.upper()}]: {message}")
        
        # Trigger callbacks
        for callback in self._alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                self._logger.error(f"Error in alert callback: {e}")
    
    def add_alert_callback(self, callback: Callable[[PerformanceAlert], None]) -> None:
        """
        Add callback function for alerts.
        
        Args:
            callback: Function to call when alerts are generated
        """
        self._alert_callbacks.append(callback)
        self._logger.debug(f"Added alert callback: {callback.__name__}")
    
    def remove_alert_callback(self, callback: Callable[[PerformanceAlert], None]) -> None:
        """Remove alert callback function."""
        if callback in self._alert_callbacks:
            self._alert_callbacks.remove(callback)
            self._logger.debug(f"Removed alert callback: {callback.__name__}")
    
    def get_current_performance(self) -> Optional[PerformanceSnapshot]:
        """Get the most recent performance snapshot."""
        with self._lock:
            return self._snapshots[-1] if self._snapshots else None
    
    def get_performance_history(self, minutes: int = 60) -> List[PerformanceSnapshot]:
        """
        Get performance history for specified time period.
        
        Args:
            minutes: Number of minutes of history to return
            
        Returns:
            List of performance snapshots
        """
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
        
        with self._lock:
            return [
                snapshot for snapshot in self._snapshots
                if snapshot.timestamp >= cutoff_time
            ]
    
    def get_recent_alerts(self, minutes: int = 60) -> List[PerformanceAlert]:
        """
        Get recent alerts for specified time period.
        
        Args:
            minutes: Number of minutes of alerts to return
            
        Returns:
            List of performance alerts
        """
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
        
        with self._lock:
            return [
                alert for alert in self._alerts
                if alert.timestamp >= cutoff_time
            ]
    
    def get_performance_summary(self, minutes: int = 60) -> Dict[str, Any]:
        """
        Get performance summary for specified time period.
        
        Args:
            minutes: Number of minutes to summarize
            
        Returns:
            Dictionary with performance summary
        """
        history = self.get_performance_history(minutes)
        alerts = self.get_recent_alerts(minutes)
        
        if not history:
            return {"error": "No performance data available"}
        
        # Calculate statistics
        lookup_times = [s.avg_lookup_time_us for s in history]
        hit_ratios = [s.hit_ratio for s in history]
        request_rates = [s.requests_per_second for s in history]
        
        summary = {
            "time_period_minutes": minutes,
            "data_points": len(history),
            
            "lookup_time_stats": {
                "current_us": history[-1].avg_lookup_time_us,
                "min_us": min(lookup_times),
                "max_us": max(lookup_times),
                "avg_us": statistics.mean(lookup_times),
                "median_us": statistics.median(lookup_times)
            },
            
            "hit_ratio_stats": {
                "current": history[-1].hit_ratio,
                "min": min(hit_ratios),
                "max": max(hit_ratios),
                "avg": statistics.mean(hit_ratios)
            },
            
            "request_rate_stats": {
                "current_per_sec": history[-1].requests_per_second,
                "min_per_sec": min(request_rates),
                "max_per_sec": max(request_rates),
                "avg_per_sec": statistics.mean(request_rates)
            },
            
            "cache_info": {
                "size": history[-1].cache_size,
                "total_requests": history[-1].total_requests,
                "staleness_minutes": history[-1].last_refresh_age_minutes
            },
            
            "alerts": {
                "total": len(alerts),
                "critical": len([a for a in alerts if a.level == AlertLevel.CRITICAL]),
                "warning": len([a for a in alerts if a.level == AlertLevel.WARNING]),
                "info": len([a for a in alerts if a.level == AlertLevel.INFO])
            }
        }
        
        return summary
    
    def clear_alerts(self) -> None:
        """Clear all stored alerts."""
        with self._lock:
            self._alerts.clear()
        self._logger.info("Cleared all performance alerts")
    
    def clear_history(self) -> None:
        """Clear all stored performance history."""
        with self._lock:
            self._snapshots.clear()
        self._logger.info("Cleared all performance history")
    
    @property
    def is_monitoring_active(self) -> bool:
        """Check if monitoring is currently active."""
        return self._monitoring_active


# Global performance monitor instance
_performance_monitor: Optional[CachePerformanceMonitor] = None


def get_cache_performance_monitor() -> CachePerformanceMonitor:
    """
    Get global cache performance monitor instance.
    
    Returns:
        CachePerformanceMonitor singleton instance
    """
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = CachePerformanceMonitor()
    return _performance_monitor


# Convenience functions
async def start_cache_monitoring(interval_seconds: float = 1.0) -> None:
    """Start cache performance monitoring."""
    monitor = get_cache_performance_monitor()
    await monitor.start_monitoring(interval_seconds)


async def stop_cache_monitoring() -> None:
    """Stop cache performance monitoring."""
    monitor = get_cache_performance_monitor()
    await monitor.stop_monitoring()


def get_cache_performance_summary(minutes: int = 60) -> Dict[str, Any]:
    """Get cache performance summary."""
    monitor = get_cache_performance_monitor()
    return monitor.get_performance_summary(minutes)


def get_cache_recent_alerts(minutes: int = 60) -> List[PerformanceAlert]:
    """Get recent cache performance alerts."""
    monitor = get_cache_performance_monitor()
    return monitor.get_recent_alerts(minutes)