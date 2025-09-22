"""
Concrete Logging Backends

Implements specific backends for file, Prometheus, console, etc.
Each backend handles its own formatting for optimal performance.

HFT COMPLIANT: Async operations, minimal blocking.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional, TextIO
import aiofiles

from .interfaces import LogBackend, LogRecord, LogLevel, LogType


class FileBackend(LogBackend):
    """
    File logging backend for warnings, errors, and audit logs.
    
    Handles text formatting and file rotation.
    """
    
    def __init__(self, name: str, config: Dict[str, Any] = None):
        super().__init__(name, config)
        self.file_path = config.get('file_path', 'logs/app.log')
        self.format_type = config.get('format', 'text')  # 'text' or 'json'
        self.min_level = LogLevel(config.get('min_level', LogLevel.WARNING))
        self.include_types = set(config.get('include_types', [LogType.TEXT, LogType.AUDIT]))
        
        # Ensure log directory exists
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
    
    def should_handle(self, record: LogRecord) -> bool:
        """Handle warnings/errors and audit logs."""
        if not self.enabled:
            return False
        
        # Check level
        if record.level < self.min_level:
            return False
        
        # Check type
        if record.log_type not in self.include_types:
            return False
        
        return True
    
    async def write(self, record: LogRecord) -> None:
        """Write formatted record to file."""
        try:
            if self.format_type == 'json':
                formatted = self._format_json(record)
            else:
                formatted = self._format_text(record)
            
            async with aiofiles.open(self.file_path, 'a') as f:
                await f.write(formatted + '\n')
        except Exception as e:
            # Fallback to console if file write fails
            print(f"FileBackend write error: {e}")
    
    async def flush(self) -> None:
        """File is flushed automatically by aiofiles."""
        pass
    
    def _format_text(self, record: LogRecord) -> str:
        """Format record as human-readable text."""
        dt = datetime.fromtimestamp(record.timestamp)
        timestamp_str = dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        
        level_str = record.level.name
        
        # Base message
        message = f"{timestamp_str} {level_str:8} {record.logger_name}: {record.message}"
        
        # Add context
        if record.context:
            context_parts = []
            for k, v in record.context.items():
                context_parts.append(f"{k}={v}")
            message += f" | {', '.join(context_parts)}"
        
        # Add correlation info
        correlation_parts = []
        if record.correlation_id:
            correlation_parts.append(f"correlation_id={record.correlation_id}")
        if record.exchange:
            correlation_parts.append(f"exchange={record.exchange}")
        if record.symbol:
            correlation_parts.append(f"symbol={record.symbol}")
        
        if correlation_parts:
            message += f" | {', '.join(correlation_parts)}"
        
        return message
    
    def _format_json(self, record: LogRecord) -> str:
        """Format record as JSON for structured logging."""
        data = {
            'timestamp': record.timestamp,
            'level': record.level.name,
            'type': record.log_type.name,
            'logger': record.logger_name,
            'message': record.message,
            'context': record.context
        }
        
        # Add optional fields
        if record.correlation_id:
            data['correlation_id'] = record.correlation_id
        if record.exchange:
            data['exchange'] = record.exchange
        if record.symbol:
            data['symbol'] = record.symbol
        
        return json.dumps(data, separators=(',', ':'))


class PrometheusBackend(LogBackend):
    """
    Prometheus metrics backend for numeric data.
    
    Handles metrics, counters, and latency measurements.
    """
    
    def __init__(self, name: str, config: Dict[str, Any] = None):
        super().__init__(name, config)
        self.push_gateway = config.get('push_gateway')
        self.job_name = config.get('job_name', 'hft_arbitrage')
        self.metrics_prefix = config.get('prefix', 'hft_')
        self.batch_size = config.get('batch_size', 100)
        self.flush_interval = config.get('flush_interval', 5.0)  # seconds
        
        # Buffer for batching metrics
        self._metrics_buffer = []
        self._last_flush = time.time()
    
    def should_handle(self, record: LogRecord) -> bool:
        """Handle only metric records."""
        if not self.enabled:
            return False
        
        return record.log_type == LogType.METRIC and record.metric_name is not None
    
    async def write(self, record: LogRecord) -> None:
        """Buffer metric for batch sending."""
        metric_data = {
            'name': f"{self.metrics_prefix}{record.metric_name}",
            'value': record.metric_value,
            'tags': record.metric_tags or {},
            'timestamp': record.timestamp
        }
        
        # Add standard tags
        if record.exchange:
            metric_data['tags']['exchange'] = record.exchange
        if record.symbol:
            metric_data['tags']['symbol'] = record.symbol
        
        self._metrics_buffer.append(metric_data)
        
        # Auto-flush if buffer is full or time elapsed
        if (len(self._metrics_buffer) >= self.batch_size or 
            time.time() - self._last_flush > self.flush_interval):
            await self.flush()
    
    async def flush(self) -> None:
        """Send buffered metrics to Prometheus."""
        if not self._metrics_buffer:
            return
        
        try:
            # In real implementation, send to Prometheus push gateway
            # For now, just print (replace with actual Prometheus client)
            print(f"[PROMETHEUS] Flushing {len(self._metrics_buffer)} metrics")
            for metric in self._metrics_buffer[:3]:  # Show first 3
                print(f"  {metric['name']}={metric['value']} {metric['tags']}")
            
            self._metrics_buffer.clear()
            self._last_flush = time.time()
            
        except Exception as e:
            print(f"PrometheusBackend flush error: {e}")


class ConsoleBackend(LogBackend):
    """
    Console logging backend for development.
    
    Uses Python's standard logging for compatibility.
    """
    
    def __init__(self, name: str, config: Dict[str, Any] = None):
        super().__init__(name, config)
        self.environment = config.get('environment', 'dev')
        self.min_level = LogLevel(config.get('min_level', LogLevel.DEBUG))
        self.color_enabled = config.get('color', True)
        
        # Only enable in development
        self.enabled = self.environment.lower() in ('dev', 'development', 'local')
    
    def should_handle(self, record: LogRecord) -> bool:
        """Handle all text logs in development environment."""
        if not self.enabled:
            return False
        
        if record.level < self.min_level:
            return False
        
        # Handle text logs (not metrics)
        return record.log_type in (LogType.TEXT, LogType.DEBUG, LogType.AUDIT)
    
    async def write(self, record: LogRecord) -> None:
        """Write to console using Python logging."""
        try:
            # Get or create Python logger
            py_logger = logging.getLogger(record.logger_name)
            
            # Convert our level to Python logging level
            py_level = self._convert_level(record.level)
            
            # Format message with context
            message = record.message
            if record.context:
                context_str = ' | '.join(f"{k}={v}" for k, v in record.context.items())
                message += f" | {context_str}"
            
            # Log to Python logger (will use existing console handlers)
            py_logger.log(py_level, message)
            
        except Exception as e:
            # Fallback to print
            print(f"ConsoleBackend error: {e}")
            print(f"{record.level.name}: {record.message}")
    
    async def flush(self) -> None:
        """Console flushes automatically."""
        pass
    
    def _convert_level(self, level: LogLevel) -> int:
        """Convert our LogLevel to Python logging level."""
        mapping = {
            LogLevel.DEBUG: logging.DEBUG,
            LogLevel.INFO: logging.INFO,
            LogLevel.WARNING: logging.WARNING,
            LogLevel.ERROR: logging.ERROR,
            LogLevel.CRITICAL: logging.CRITICAL
        }
        return mapping.get(level, logging.INFO)


class ElasticsearchBackend(LogBackend):
    """
    Elasticsearch backend for searchable structured logs.
    
    For audit trails and complex log analysis.
    """
    
    def __init__(self, name: str, config: Dict[str, Any] = None):
        super().__init__(name, config)
        self.elasticsearch_url = config.get('url')
        self.index_prefix = config.get('index_prefix', 'hft-logs')
        self.include_types = set(config.get('include_types', [LogType.AUDIT, LogType.TEXT]))
        self.min_level = LogLevel(config.get('min_level', LogLevel.INFO))
        
        # Buffer for batch indexing
        self._doc_buffer = []
        self.batch_size = config.get('batch_size', 50)
    
    def should_handle(self, record: LogRecord) -> bool:
        """Handle audit and structured logs."""
        if not self.enabled or not self.elasticsearch_url:
            return False
        
        if record.level < self.min_level:
            return False
        
        return record.log_type in self.include_types
    
    async def write(self, record: LogRecord) -> None:
        """Buffer document for batch indexing."""
        doc = {
            '@timestamp': datetime.fromtimestamp(record.timestamp).isoformat(),
            'level': record.level.name,
            'type': record.log_type.name,
            'logger': record.logger_name,
            'message': record.message,
            'context': record.context,
            'correlation_id': record.correlation_id,
            'exchange': record.exchange,
            'symbol': record.symbol
        }
        
        self._doc_buffer.append(doc)
        
        if len(self._doc_buffer) >= self.batch_size:
            await self.flush()
    
    async def flush(self) -> None:
        """Send buffered documents to Elasticsearch."""
        if not self._doc_buffer:
            return
        
        try:
            # In real implementation, use elasticsearch-py client
            print(f"[ELASTICSEARCH] Indexing {len(self._doc_buffer)} documents")
            self._doc_buffer.clear()
            
        except Exception as e:
            print(f"ElasticsearchBackend flush error: {e}")


class DatadogBackend(LogBackend):
    """
    Datadog backend for metrics and logs.
    
    Handles both metrics and log ingestion.
    """
    
    def __init__(self, name: str, config: Dict[str, Any] = None):
        super().__init__(name, config)
        self.api_key = config.get('api_key')
        self.service_name = config.get('service', 'hft-arbitrage')
        self.environment = config.get('environment', 'production')
        
    def should_handle(self, record: LogRecord) -> bool:
        """Handle metrics and high-level logs."""
        if not self.enabled or not self.api_key:
            return False
        
        # Handle metrics and important logs
        return (record.log_type == LogType.METRIC or 
                record.level >= LogLevel.ERROR)
    
    async def write(self, record: LogRecord) -> None:
        """Send to Datadog API."""
        try:
            if record.log_type == LogType.METRIC:
                # Send as Datadog metric
                print(f"[DATADOG METRIC] {record.metric_name}={record.metric_value}")
            else:
                # Send as Datadog log
                print(f"[DATADOG LOG] {record.level.name}: {record.message}")
                
        except Exception as e:
            print(f"DatadogBackend error: {e}")
    
    async def flush(self) -> None:
        """Datadog handles batching internally."""
        pass