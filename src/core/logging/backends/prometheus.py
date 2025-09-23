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


class PrometheusBackend(LogBackend):
    """
    Prometheus metrics backend with batching for performance.
    
    Features:
    - Batched metric push for efficiency
    - Automatic push gateway integration
    - Metric name normalization
    - Label management
    - Error resilience with retry logic
    """
    
    def __init__(self, name: str = "prometheus", config: Dict[str, Any] = None):
        super().__init__(name, config)
        
        # Configuration
        config = config or {}
        self.push_gateway_url = config.get('push_gateway_url', 'http://localhost:9091')
        self.job_name = config.get('job_name', 'hft_arbitrage')
        self.instance_name = config.get('instance', 'hft_instance')
        self.metrics_prefix = config.get('prefix', 'hft_')
        self.batch_size = config.get('batch_size', 100)
        self.flush_interval = config.get('flush_interval', 5.0)  # seconds
        self.timeout = config.get('timeout', 10.0)  # HTTP timeout
        self.retry_count = config.get('retry_count', 3)
        
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
        """Handle only metric records."""
        if not self.enabled:
            return False
        
        return record.log_type == LogType.METRIC and record.metric_name is not None
    
    async def write(self, record: LogRecord) -> None:
        """Buffer metric for batch sending."""
        # Ensure flush task is started
        self._start_flush_task()
        
        try:
            # Normalize metric name
            metric_name = self._normalize_metric_name(record.metric_name)
            
            # Prepare metric data
            metric_data = {
                'name': f"{self.metrics_prefix}{metric_name}",
                'value': record.metric_value,
                'labels': self._prepare_labels(record),
                'timestamp': int(record.timestamp * 1000),  # Prometheus expects milliseconds
                'type': 'gauge'  # Default type, could be configurable
            }
            
            # Add to buffer
            async with self._lock:
                self._metrics_buffer.append(metric_data)
                
                # Auto-flush if buffer is full
                if len(self._metrics_buffer) >= self.batch_size:
                    await self._flush_buffer()
        
        except Exception as e:
            self._handle_error(e)
    
    async def flush(self) -> None:
        """Flush buffered metrics to Prometheus."""
        async with self._lock:
            await self._flush_buffer()
    
    async def _flush_buffer(self) -> None:
        """Internal method to flush metrics buffer."""
        if not self._metrics_buffer:
            return
        
        try:
            # Get session
            if self._session is None:
                self._session = aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                )
            
            # Prepare metrics for push gateway
            metrics_data = self._format_for_push_gateway(self._metrics_buffer)
            
            # Push to gateway with retry
            success = await self._push_with_retry(metrics_data)
            
            if success:
                self._metrics_sent += len(self._metrics_buffer)
            else:
                self._failures += 1
            
            # Clear buffer regardless of success (prevent memory growth)
            self._metrics_buffer.clear()
            self._last_flush = time.time()
            
        except Exception as e:
            self._handle_error(e)
            # Clear buffer to prevent memory issues
            self._metrics_buffer.clear()
    
    async def _push_with_retry(self, metrics_data: str) -> bool:
        """Push metrics with retry logic."""
        url = f"{self.push_gateway_url}/metrics/job/{self.job_name}/instance/{self.instance_name}"
        
        for attempt in range(self.retry_count):
            try:
                async with self._session.post(
                    url,
                    data=metrics_data,
                    headers={'Content-Type': 'text/plain; charset=utf-8'}
                ) as response:
                    if response.status == 200:
                        return True
                    else:
                        print(f"Prometheus push failed: HTTP {response.status}")
                        
            except Exception as e:
                print(f"Prometheus push attempt {attempt + 1} failed: {e}")
                
                if attempt < self.retry_count - 1:
                    # Wait before retry (exponential backoff)
                    await asyncio.sleep(2 ** attempt)
        
        return False
    
    def _format_for_push_gateway(self, metrics: List[Dict[str, Any]]) -> str:
        """Format metrics for Prometheus push gateway."""
        lines = []
        
        # Group metrics by name for efficiency
        grouped_metrics: Dict[str, List[Dict[str, Any]]] = {}
        for metric in metrics:
            name = metric['name']
            if name not in grouped_metrics:
                grouped_metrics[name] = []
            grouped_metrics[name].append(metric)
        
        # Format each metric group
        for metric_name, metric_list in grouped_metrics.items():
            # Add metric type hint
            lines.append(f"# TYPE {metric_name} gauge")
            
            # Add metric samples
            for metric in metric_list:
                labels_str = self._format_labels(metric['labels'])
                value = metric['value']
                timestamp = metric['timestamp']
                
                if labels_str:
                    line = f"{metric_name}{{{labels_str}}} {value} {timestamp}"
                else:
                    line = f"{metric_name} {value} {timestamp}"
                
                lines.append(line)
        
        return '\n'.join(lines) + '\n'
    
    def _format_labels(self, labels: Dict[str, str]) -> str:
        """Format labels for Prometheus format."""
        if not labels:
            return ""
        
        formatted_labels = []
        for key, value in labels.items():
            # Escape quotes and backslashes in values
            escaped_value = str(value).replace('\\', '\\\\').replace('"', '\\"')
            formatted_labels.append(f'{key}="{escaped_value}"')
        
        return ','.join(formatted_labels)
    
    def _prepare_labels(self, record: LogRecord) -> Dict[str, str]:
        """Prepare labels from record data."""
        labels = {}
        
        # Add metric tags
        if record.metric_tags:
            for key, value in record.metric_tags.items():
                # Normalize label names
                normalized_key = self._normalize_label_name(key)
                labels[normalized_key] = str(value)
        
        # Add standard labels
        if record.exchange:
            labels['exchange'] = record.exchange
        if record.symbol:
            labels['symbol'] = record.symbol
        if record.correlation_id:
            labels['correlation_id'] = record.correlation_id[:16]  # Limit length
        
        # Add instance labels
        labels['job'] = self.job_name
        labels['instance'] = self.instance_name
        
        return labels
    
    def _normalize_metric_name(self, name: str) -> str:
        """Normalize metric name for Prometheus."""
        # Replace invalid characters with underscores
        normalized = ""
        for char in name:
            if char.isalnum() or char == '_':
                normalized += char.lower()
            else:
                normalized += '_'
        
        # Ensure it starts with a letter or underscore
        if normalized and not (normalized[0].isalpha() or normalized[0] == '_'):
            normalized = f"metric_{normalized}"
        
        # Remove duplicate underscores
        while '__' in normalized:
            normalized = normalized.replace('__', '_')
        
        return normalized.strip('_')
    
    def _normalize_label_name(self, name: str) -> str:
        """Normalize label name for Prometheus."""
        # Similar to metric name but preserve case for readability
        normalized = ""
        for char in name:
            if char.isalnum() or char == '_':
                normalized += char
            else:
                normalized += '_'
        
        # Ensure it starts with a letter or underscore
        if normalized and not (normalized[0].isalpha() or normalized[0] == '_'):
            normalized = f"label_{normalized}"
        
        return normalized.strip('_')
    
    def _start_flush_task(self) -> None:
        """Start background flush task if event loop is available."""
        if self._task_started:
            return
            
        try:
            # Only start if there's a running event loop
            loop = asyncio.get_running_loop()
            if self._flush_task is None or self._flush_task.done():
                self._flush_task = loop.create_task(self._flush_loop())
                self._task_started = True
        except RuntimeError:
            # No event loop running - task will be started on first write
            pass
    
    async def _flush_loop(self) -> None:
        """Background task for periodic flushing."""
        try:
            while self.enabled:
                await asyncio.sleep(self.flush_interval)
                
                # Check if we need to flush
                async with self._lock:
                    if (self._metrics_buffer and 
                        time.time() - self._last_flush > self.flush_interval):
                        await self._flush_buffer()
                        
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Prometheus flush loop error: {e}")
    
    async def shutdown(self) -> None:
        """Graceful shutdown."""
        # Cancel flush task
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        
        # Flush remaining metrics
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
            'buffer_capacity': self.batch_size,
            'push_gateway_url': self.push_gateway_url,
            'session_active': self._session is not None
        }


class PrometheusHistogramBackend(PrometheusBackend):
    """
    Specialized Prometheus backend for histogram metrics.
    
    Automatically creates histogram buckets for latency measurements.
    """
    
    def __init__(self, name: str = "prometheus_histogram", config: Dict[str, Any] = None):
        super().__init__(name, config)
        
        # Histogram configuration
        config = config or {}
        self.histogram_buckets = config.get('histogram_buckets', [
            0.5, 1.0, 2.5, 5.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0
        ])
        
        # Patterns for histogram metrics (latency, duration, etc.)
        self.histogram_patterns = config.get('histogram_patterns', [
            'latency', 'duration', 'time', 'response_time'
        ])
    
    def _is_histogram_metric(self, metric_name: str) -> bool:
        """Check if metric should be treated as histogram."""
        name_lower = metric_name.lower()
        return any(pattern in name_lower for pattern in self.histogram_patterns)
    
    def _format_for_push_gateway(self, metrics: List[Dict[str, Any]]) -> str:
        """Enhanced formatting with histogram support."""
        lines = []
        
        # Separate histogram and regular metrics
        histogram_metrics = []
        regular_metrics = []
        
        for metric in metrics:
            if self._is_histogram_metric(metric['name']):
                histogram_metrics.append(metric)
            else:
                regular_metrics.append(metric)
        
        # Process regular metrics with parent method
        if regular_metrics:
            regular_data = super()._format_for_push_gateway(regular_metrics)
            lines.extend(regular_data.strip().split('\n'))
        
        # Process histogram metrics
        for metric in histogram_metrics:
            lines.extend(self._format_histogram_metric(metric))
        
        return '\n'.join(lines) + '\n'
    
    def _format_histogram_metric(self, metric: Dict[str, Any]) -> List[str]:
        """Format metric as Prometheus histogram."""
        name = metric['name']
        value = metric['value']
        labels = metric['labels']
        timestamp = metric['timestamp']
        
        lines = []
        
        # Histogram type
        lines.append(f"# TYPE {name} histogram")
        
        # Bucket counts
        total_count = 1  # We have one observation
        cumulative_count = 0
        
        for bucket in self.histogram_buckets:
            if value <= bucket:
                cumulative_count = total_count
            
            bucket_labels = {**labels, 'le': str(bucket)}
            labels_str = self._format_labels(bucket_labels)
            lines.append(f"{name}_bucket{{{labels_str}}} {cumulative_count} {timestamp}")
        
        # +Inf bucket
        inf_labels = {**labels, 'le': '+Inf'}
        labels_str = self._format_labels(inf_labels)
        lines.append(f"{name}_bucket{{{labels_str}}} {total_count} {timestamp}")
        
        # Count and sum
        count_labels_str = self._format_labels(labels)
        if count_labels_str:
            lines.append(f"{name}_count{{{count_labels_str}}} {total_count} {timestamp}")
            lines.append(f"{name}_sum{{{count_labels_str}}} {value} {timestamp}")
        else:
            lines.append(f"{name}_count {total_count} {timestamp}")
            lines.append(f"{name}_sum {value} {timestamp}")
        
        return lines