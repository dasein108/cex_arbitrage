"""
Core Logging Interfaces for HFT System

Defines lightweight interfaces for high-performance logging with
pluggable backends and zero-allocation patterns.

HFT COMPLIANT: Minimal overhead, async dispatch, no blocking.
"""

import time
from abc import ABC, abstractmethod
from enum import IntEnum
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field


class LogLevel(IntEnum):
    """Log levels with numeric values for fast comparison."""
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


class LogType(IntEnum):
    """Log types for routing decisions."""
    TEXT = 1      # Regular log messages
    METRIC = 2    # Numeric metrics (latency, counters)
    AUDIT = 3     # Audit trail messages
    DEBUG = 4     # Debug information


@dataclass
class LogRecord:
    """
    Lightweight log record for zero-allocation message passing.
    
    Formatting happens in backends, not here (performance).
    All fields designed for minimal memory footprint.
    """
    timestamp: float
    level: LogLevel
    log_type: LogType
    logger_name: str
    message: str
    context: Dict[str, Any] = field(default_factory=dict)
    
    # For metrics (optional, only used when log_type == METRIC)
    metric_name: Optional[str] = None
    metric_value: Optional[float] = None
    metric_tags: Optional[Dict[str, str]] = None
    
    # For correlation tracking
    correlation_id: Optional[str] = None
    exchange: Optional[str] = None
    symbol: Optional[str] = None
    
    @classmethod
    def create_text(cls, level: LogLevel, logger_name: str, message: str, **context) -> 'LogRecord':
        """Fast factory method for text log records."""
        return cls(
            timestamp=time.time(),
            level=level,
            log_type=LogType.TEXT,
            logger_name=logger_name,
            message=message,
            context=context
        )
    
    @classmethod
    def create_metric(cls, logger_name: str, metric_name: str, value: float, **tags) -> 'LogRecord':
        """Fast factory method for metric log records."""
        return cls(
            timestamp=time.time(),
            level=LogLevel.INFO,
            log_type=LogType.METRIC,
            logger_name=logger_name,
            message="",
            metric_name=metric_name,
            metric_value=value,
            metric_tags=tags
        )
    
    @classmethod
    def create_audit(cls, logger_name: str, event: str, **context) -> 'LogRecord':
        """Fast factory method for audit log records."""
        return cls(
            timestamp=time.time(),
            level=LogLevel.INFO,
            log_type=LogType.AUDIT,
            logger_name=logger_name,
            message=event,
            context=context
        )


class LogBackend(ABC):
    """
    Abstract composite for all logging backends.
    
    Each backend handles its own formatting and output logic.
    """
    
    def __init__(self, name: str, config: Dict[str, Any] = None):
        self.name = name
        self.config = config or {}
        self.enabled = True
        self._error_count = 0
        self._max_errors = 10  # Disable after too many failures
    
    @abstractmethod
    def should_handle(self, record: LogRecord) -> bool:
        """
        Fast check if this backend should process the record.
        
        This is called in hot path - must be very fast (<1μs).
        """
        pass
    
    @abstractmethod
    async def write(self, record: LogRecord) -> None:
        """
        Write log record to backend destination.
        
        Formatting happens here, not in logger (performance).
        Must handle errors gracefully without raising exceptions.
        """
        pass
    
    @abstractmethod
    async def flush(self) -> None:
        """Flush any buffered data."""
        pass
    
    def disable(self) -> None:
        """Disable this backend."""
        self.enabled = False
    
    def enable(self) -> None:
        """Enable this backend."""
        self.enabled = True
        self._error_count = 0
    
    def _handle_error(self, error: Exception) -> None:
        """Handle backend errors gracefully."""
        self._error_count += 1
        if self._error_count >= self._max_errors:
            self.enabled = False
            print(f"Backend {self.name} disabled after {self._max_errors} errors")


class LogRouter(ABC):
    """Routes log records to appropriate backends."""
    
    @abstractmethod
    def get_backends(self, record: LogRecord) -> List[LogBackend]:
        """Get list of backends that should handle this record."""
        pass


class HFTLoggerInterface(ABC):
    """
    Interface for HFT logger with multiple backends.
    
    This is what gets injected into composite classes via factory pattern.
    Designed for maximum performance with async dispatch.
    """
    
    @abstractmethod
    def debug(self, msg: str, **context) -> None:
        """Log debug message. Zero blocking, async dispatch."""
        pass
    
    @abstractmethod
    def info(self, msg: str, **context) -> None:
        """Log info message. Zero blocking, async dispatch."""
        pass
    
    @abstractmethod
    def warning(self, msg: str, **context) -> None:
        """Log warning message. Zero blocking, async dispatch."""
        pass
    
    @abstractmethod
    def error(self, msg: str, **context) -> None:
        """Log error message. Zero blocking, async dispatch."""
        pass
    
    @abstractmethod
    def critical(self, msg: str, **context) -> None:
        """Log critical message. Zero blocking, async dispatch."""
        pass
    
    @abstractmethod
    def metric(self, name: str, value: float, **tags) -> None:
        """Log metric value. Routes to Prometheus/monitoring."""
        pass
    
    @abstractmethod
    def latency(self, operation: str, duration_ms: float, **tags) -> None:
        """Log latency metric. Convenience method for timing."""
        pass
    
    @abstractmethod
    def counter(self, name: str, value: int = 1, **tags) -> None:
        """Log counter metric. Increment by value."""
        pass
    
    @abstractmethod
    def audit(self, event: str, **context) -> None:
        """Log audit event. For compliance and debugging."""
        pass
    
    @abstractmethod
    def set_context(self, **context) -> None:
        """Set persistent context for all logs from this logger."""
        pass
    
    @abstractmethod
    async def flush(self) -> None:
        """Flush all backends. Use sparingly."""
        pass
    
    # Python logging compatibility methods
    @abstractmethod
    def isEnabledFor(self, level: int) -> bool:
        """Check if logging is enabled for level (Python logging compatibility)."""
        pass
    
    @abstractmethod
    def log(self, level: int, msg: str, *args, **kwargs) -> None:
        """Generic log method (Python logging compatibility)."""
        pass


class PerformanceMonitor:
    """
    Lightweight performance monitoring for logging system.
    
    Tracks latency and throughput without impacting performance.
    """
    
    def __init__(self):
        self.call_count = 0
        self.total_latency = 0.0
        self.max_latency = 0.0
        self.last_reset = time.time()
    
    def record_call(self, latency_us: float) -> None:
        """Record a log call latency in microseconds."""
        self.call_count += 1
        self.total_latency += latency_us
        self.max_latency = max(self.max_latency, latency_us)
    
    def get_stats(self) -> Dict[str, float]:
        """Get performance statistics."""
        if self.call_count == 0:
            return {"calls": 0, "avg_latency_us": 0, "max_latency_us": 0, "calls_per_sec": 0}
        
        elapsed = time.time() - self.last_reset
        return {
            "calls": self.call_count,
            "avg_latency_us": self.total_latency / self.call_count,
            "max_latency_us": self.max_latency,
            "calls_per_sec": self.call_count / elapsed if elapsed > 0 else 0
        }
    
    def reset(self) -> None:
        """Reset statistics."""
        self.call_count = 0
        self.total_latency = 0.0
        self.max_latency = 0.0
        self.last_reset = time.time()