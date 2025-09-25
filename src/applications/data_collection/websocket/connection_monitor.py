"""
Connection Monitor - Simplified Health Monitoring

Monitors WebSocket connection health and provides alerts.
Focuses on essential health checks without complex metrics.
"""

import asyncio
import time
from typing import Dict, Optional, List, Callable
from dataclasses import dataclass

from exchanges.structs import ExchangeEnum
from infrastructure.logging import get_logger


@dataclass
class HealthStatus:
    """Simple health status for connections."""
    exchange: ExchangeEnum
    is_healthy: bool
    last_message_time: float
    messages_per_minute: float
    issues: List[str]


class ConnectionMonitor:
    """
    Simplified connection health monitor.
    
    Responsibilities:
    - Monitor message flow from WebSocket manager
    - Detect stale connections
    - Trigger alerts for unhealthy connections
    """

    def __init__(self, message_timeout: int = 60):
        """Initialize connection monitor."""
        self.logger = get_logger('websocket.connection_monitor')
        self.message_timeout = message_timeout
        
        # Connection metrics: {exchange: {last_message_time, message_count}}
        self._connection_metrics: Dict[ExchangeEnum, Dict[str, float]] = {}
        self._alert_callbacks: List[Callable] = []
        self._monitoring_task: Optional[asyncio.Task] = None
        self._running = False

        self.logger.info("ConnectionMonitor initialized", 
                        message_timeout_seconds=message_timeout)

    def update_metrics(self, exchange: ExchangeEnum, message_count: int, last_message_time: float) -> None:
        """Update connection metrics."""
        self._connection_metrics[exchange] = {
            'message_count': message_count,
            'last_message_time': last_message_time,
            'last_update': time.time()
        }

    def start_monitoring(self, check_interval: int = 30) -> None:
        """Start health monitoring."""
        if self._monitoring_task:
            return
        
        self._running = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop(check_interval))
        self.logger.info("Connection monitoring started", check_interval=check_interval)

    async def _monitoring_loop(self, check_interval: int) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                await self._check_health()
                await asyncio.sleep(check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(5)

    async def _check_health(self) -> None:
        """Check health of all monitored connections."""
        current_time = time.time()

        for exchange, metrics in self._connection_metrics.items():
            health = self._assess_health(exchange, metrics, current_time)
            
            if not health.is_healthy:
                await self._trigger_alert(health)
            
            # Log health status
            self._log_health(health)

    def _assess_health(self, exchange: ExchangeEnum, metrics: Dict[str, float], current_time: float) -> HealthStatus:
        """Assess health of individual connection."""
        issues = []
        is_healthy = True

        last_message_time = metrics.get('last_message_time', 0)
        message_count = metrics.get('message_count', 0)
        last_update = metrics.get('last_update', 0)

        # Check message recency
        time_since_last_message = current_time - last_message_time
        if time_since_last_message > self.message_timeout:
            issues.append(f"No messages for {time_since_last_message:.1f}s")
            is_healthy = False

        # Calculate messages per minute (simplified)
        runtime_minutes = max((current_time - (current_time - 300)) / 60, 1)  # Last 5 minutes
        messages_per_minute = message_count / runtime_minutes

        if messages_per_minute < 1:  # Very low threshold for simplicity
            issues.append(f"Low message rate: {messages_per_minute:.1f}/min")
            is_healthy = False

        return HealthStatus(
            exchange=exchange,
            is_healthy=is_healthy,
            last_message_time=last_message_time,
            messages_per_minute=messages_per_minute,
            issues=issues
        )

    def _log_health(self, health: HealthStatus) -> None:
        """Log connection health status."""
        if health.is_healthy:
            self.logger.debug(f"{health.exchange.value} connection healthy",
                            messages_per_minute=health.messages_per_minute)
        else:
            self.logger.warning(f"{health.exchange.value} connection unhealthy: {', '.join(health.issues)}")

    async def _trigger_alert(self, health: HealthStatus) -> None:
        """Trigger alert for unhealthy connection."""
        alert_data = {
            "exchange": health.exchange.value,
            "issues": health.issues,
            "messages_per_minute": health.messages_per_minute
        }

        # Call alert callbacks
        for callback in self._alert_callbacks:
            try:
                await callback(alert_data)
            except Exception as e:
                self.logger.error(f"Error in alert callback: {e}")

        self.logger.error(f"ALERT: {health.exchange.value} connection unhealthy", **alert_data)

    def add_alert_callback(self, callback: Callable) -> None:
        """Add callback for health alerts."""
        self._alert_callbacks.append(callback)

    async def stop_monitoring(self) -> None:
        """Stop health monitoring."""
        self._running = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
            self._monitoring_task = None
        
        self.logger.info("Connection monitoring stopped")