"""
Prometheus Backend for Metrics Collection

High-performance metrics backend with batching and push gateway support.
Routes numeric metrics to Prometheus for monitoring and alerting.

HFT COMPLIANT: Batched dispatch, minimal overhead, async processing.
"""

import asyncio
import json
import time
from typing import Dict, Any, List, Optional
import aiohttp

from ..interfaces import LogBackend, LogRecord, LogLevel, LogType
from ..structs import PrometheusBackendConfig


class PrometheusBackend(LogBackend):
    """
    Prometheus metrics backend with batching for performance.
    
    Features:
    - Batched metric push for efficiency
    - Automatic push gateway integration
    - Metric name normalization
    - Label management
    - Error resilience with retry logic
    
    Accepts only PrometheusBackendConfig struct for configuration.
    """
    
    def __init__(self, config: PrometheusBackendConfig, name: str = "prometheus"):
        """
        Initialize Prometheus backend with struct configuration.
        
        Args:
            name: Backend name
            config: PrometheusBackendConfig struct (required)
        """
        if not isinstance(config, PrometheusBackendConfig):
            raise TypeError(f"Expected PrometheusBackendConfig, got {type(config)}")
        
        super().__init__(name, {})  # Empty dict for composite class compatibility
        
        # Store struct config
        self.config = config
        
        # Configuration from struct
        self.push_gateway_url = config.push_gateway_url
        self.job_name = config.job_name
        self.instance_name = "hft_instance"  # Fixed default
        self.metrics_prefix = "hft_"  # Fixed default
        self.batch_size = config.batch_size
        self.flush_interval = config.flush_interval
        self.timeout = 10.0  # Fixed default
        self.retry_count = 3  # Fixed default
        self.histogram_buckets = config.get_histogram_buckets()
        
        # Enable based on struct config
        self.enabled = config.enabled
        
        # Buffer for batching metrics
        self._metrics_buffer: List[Dict[str, Any]] = []
        self._last_flush = time.time()
        self._lock = asyncio.Lock()
        
        # HTTP session for push gateway
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Performance tracking
        self._metrics_sent = 0
        self._failures = 0
        
        # Auto-flush task (will be started when needed)
        self._flush_task: Optional[asyncio.Task] = None
        self._task_started = False
    
    def should_handle(self, record: LogRecord) -> bool:
        """
        Handle metric records only.
        
        Fast filtering - called in hot path.
        """
        if not self.enabled:
            return False
        
        # Only handle metrics
        return record.log_type == LogType.METRIC
    
    async def write(self, record: LogRecord) -> None:
        """Async write with batching for performance."""
        if not self.enabled or record.log_type != LogType.METRIC:
            return
        
        # Start auto-flush task if not already running
        if not self._task_started:
            await self._start_flush_task()
        
        async with self._lock:
            # Convert to Prometheus format
            metric_data = self._format_metric(record)
            if metric_data:
                self._metrics_buffer.append(metric_data)
            
            # Flush if buffer is full
            if len(self._metrics_buffer) >= self.batch_size:
                await self._flush_metrics()
    
    async def flush(self) -> None:
        """Force flush of buffered metrics."""
        if not self.enabled:
            return
        
        async with self._lock:
            await self._flush_metrics()
    
    async def _flush_metrics(self) -> None:
        """Internal metrics flush implementation."""
        if not self._metrics_buffer:
            return
        
        try:
            # Prepare push gateway payload
            payload = self._prepare_payload(self._metrics_buffer.copy())
            
            # Send to push gateway
            await self._push_to_gateway(payload)
            
            # Clear buffer and update stats
            self._metrics_sent += len(self._metrics_buffer)
            self._metrics_buffer.clear()
            self._last_flush = time.time()
            
        except Exception as e:
            self._failures += 1
            print(f"PrometheusBackend flush error: {e}")
    
    def _format_metric(self, record: LogRecord) -> Optional[Dict[str, Any]]:
        """Convert log record to Prometheus metric format."""
        if not hasattr(record, 'metric_name') or not hasattr(record, 'metric_value'):
            return None
        
        # Normalize metric name
        metric_name = self._normalize_name(record.metric_name)
        
        # Prepare labels
        labels = {}
        if hasattr(record, 'metric_tags') and record.metric_tags:
            labels.update(record.metric_tags)
        
        # Add context as labels
        if record.context:
            for key, value in record.context.items():
                labels[self._normalize_label(key)] = str(value)
        
        # Add correlation labels
        if record.exchange:
            labels['exchange'] = record.exchange
        if record.symbol:
            labels['symbol'] = record.symbol
        
        return {
            'name': f"{self.metrics_prefix}{metric_name}",
            'value': float(record.metric_value),
            'labels': labels,
            'timestamp': record.timestamp
        }
    
    def _normalize_name(self, name: str) -> str:
        """Normalize metric name for Prometheus."""
        # Replace invalid characters
        normalized = ""
        for char in name.lower():
            if char.isalnum() or char == '_':
                normalized += char
            else:
                normalized += '_'
        
        # Ensure starts with letter or underscore
        if normalized and not (normalized[0].isalpha() or normalized[0] == '_'):
            normalized = f"_{normalized}"
        
        return normalized or "unknown_metric"
    
    def _normalize_label(self, label: str) -> str:
        """Normalize label name for Prometheus."""
        return self._normalize_name(label)
    
    def _prepare_payload(self, metrics: List[Dict[str, Any]]) -> str:
        """Prepare Prometheus push gateway payload."""
        lines = []
        
        for metric in metrics:
            # Build label string
            label_parts = []
            for key, value in metric['labels'].items():
                # Escape label values
                escaped_value = str(value).replace('\\', '\\\\').replace('"', '\\"')
                label_parts.append(f'{key}="{escaped_value}"')
            
            label_string = '{' + ','.join(label_parts) + '}' if label_parts else ''
            
            # Format metric line
            line = f"{metric['name']}{label_string} {metric['value']}"
            lines.append(line)
        
        return '\n'.join(lines)
    
    async def _push_to_gateway(self, payload: str) -> None:
        """Push metrics to Prometheus push gateway."""
        if not self._session:
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
            )
        
        url = f"{self.push_gateway_url}/metrics/job/{self.job_name}/instance/{self.instance_name}"
        
        for attempt in range(self.retry_count):
            try:
                async with self._session.post(
                    url,
                    data=payload,
                    headers={'Content-Type': 'text/plain'}
                ) as response:
                    if response.status == 200:
                        return
                    else:
                        raise aiohttp.ClientError(f"Push gateway returned {response.status}")
                        
            except Exception as e:
                if attempt == self.retry_count - 1:
                    raise
                await asyncio.sleep(0.5 * (2 ** attempt))  # Exponential backoff
    
    async def _start_flush_task(self) -> None:
        """Start the auto-flush background task."""
        if self._task_started:
            return
        
        self._task_started = True
        self._flush_task = asyncio.create_task(self._auto_flush_loop())
    
    async def _auto_flush_loop(self) -> None:
        """Background task for automatic flushing."""
        while self.enabled:
            try:
                await asyncio.sleep(self.flush_interval)
                
                # Check if flush is needed
                current_time = time.time()
                if (self._metrics_buffer and 
                    (current_time - self._last_flush) >= self.flush_interval):
                    async with self._lock:
                        await self._flush_metrics()
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"PrometheusBackend auto-flush error: {e}")
    
    async def close(self) -> None:
        """Close the backend and cleanup resources."""
        self.enabled = False
        
        # Cancel flush task
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        
        # Final flush
        await self.flush()
        
        # Close HTTP session
        if self._session:
            await self._session.close()
            self._session = None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get backend statistics."""
        return {
            'metrics_sent': self._metrics_sent,
            'failures': self._failures,
            'buffer_size': len(self._metrics_buffer),
            'enabled': self.enabled
        }


class PrometheusHistogramBackend(PrometheusBackend):
    """
    Specialized Prometheus backend for histogram metrics.
    
    Automatically creates histogram buckets for latency measurements.
    Accepts only PrometheusBackendConfig struct for configuration.
    """
    
    def __init__(self, config: PrometheusBackendConfig, name: str = "prometheus_histogram"):
        """
        Initialize histogram backend with struct configuration.
        
        Args:
            name: Backend name
            config: PrometheusBackendConfig struct (required)
        """
        super().__init__(config, name)
        
        # Use histogram buckets from config
        self.histogram_buckets = config.get_histogram_buckets()
        
        # Patterns for histogram metrics (latency, duration, etc.)
        self.histogram_patterns = [
            'latency', 'duration', 'time', 'response_time'
        ]
    
    def _format_metric(self, record: LogRecord) -> Optional[Dict[str, Any]]:
        """Convert to histogram format if applicable."""
        base_metric = super()._format_metric(record)
        if not base_metric:
            return None
        
        # Check if this should be a histogram
        metric_name = base_metric['name'].lower()
        is_histogram = any(pattern in metric_name for pattern in self.histogram_patterns)
        
        if is_histogram:
            return self._format_histogram(base_metric)
        else:
            return base_metric
    
    def _format_histogram(self, metric: Dict[str, Any]) -> Dict[str, Any]:
        """Format as histogram with buckets."""
        value = metric['value']
        base_name = metric['name']
        labels = metric['labels'].copy()
        
        # Create histogram buckets
        histogram_metrics = []
        cumulative_count = 0
        
        for bucket in self.histogram_buckets:
            if value <= bucket:
                cumulative_count += 1
            
            bucket_labels = labels.copy()
            bucket_labels['le'] = str(bucket)
            
            histogram_metrics.append({
                'name': f"{base_name}_bucket",
                'value': cumulative_count,
                'labels': bucket_labels,
                'timestamp': metric['timestamp']
            })
        
        # Add +Inf bucket
        inf_labels = labels.copy()
        inf_labels['le'] = '+Inf'
        histogram_metrics.append({
            'name': f"{base_name}_bucket",
            'value': 1,  # Always 1 for +Inf
            'labels': inf_labels,
            'timestamp': metric['timestamp']
        })
        
        # Add count and sum
        histogram_metrics.extend([
            {
                'name': f"{base_name}_count",
                'value': 1,
                'labels': labels,
                'timestamp': metric['timestamp']
            },
            {
                'name': f"{base_name}_sum",
                'value': value,
                'labels': labels,
                'timestamp': metric['timestamp']
            }
        ])
        
        # Return first metric (will be batched)
        return histogram_metrics[0] if histogram_metrics else metric