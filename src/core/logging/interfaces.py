"""
Flexible Logging Interfaces for HFT System

Provides pluggable logging architecture with multiple backends
and selective routing based on message type and content.

HFT COMPLIANT: Zero-allocation hot paths, async dispatch.
"""

from abc import ABC, abstractmethod
from enum import IntEnum
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass
import time


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
    PERF = 5      # Performance metrics


@dataclass
class LogRecord:
    """
    Lightweight log record for fast creation.
    
    Formatting happens in backends, not here (performance).
    """
    timestamp: float
    level: LogLevel
    log_type: LogType
    logger_name: str
    message: str
    context: Dict[str, Any]
    
    # For metrics
    metric_name: Optional[str] = None
    metric_value: Optional[float] = None
    metric_tags: Optional[Dict[str, str]] = None
    
    # For correlation
    correlation_id: Optional[str] = None
    exchange: Optional[str] = None
    symbol: Optional[str] = None


class LogBackend(ABC):
    """Abstract base for all logging backends."""
    
    def __init__(self, name: str, config: Dict[str, Any] = None):
        self.name = name
        self.config = config or {}
        self.enabled = True
    
    @abstractmethod
    def should_handle(self, record: LogRecord) -> bool:
        """
        Fast check if this backend should process the record.
        
        This is called in hot path - must be very fast.
        """
        pass
    
    @abstractmethod
    async def write(self, record: LogRecord) -> None:
        """
        Write log record to backend.
        
        Formatting happens here, not in logger.
        """
        pass
    
    @abstractmethod
    async def flush(self) -> None:
        """Flush any buffered data."""
        pass
    
    def disable(self):
        """Disable this backend."""
        self.enabled = False
    
    def enable(self):
        """Enable this backend."""
        self.enabled = True


class LogRouter(ABC):
    """Routes log records to appropriate backends."""
    
    @abstractmethod
    def get_backends(self, record: LogRecord) -> List[LogBackend]:
        """Get list of backends that should handle this record."""
        pass


class HFTLoggerInterface(ABC):
    """
    Interface for HFT logger with multiple backends.
    
    This is what gets injected into base classes.
    """
    
    @abstractmethod
    def debug(self, msg: str, **context) -> None:
        """Log debug message."""
        pass
    
    @abstractmethod
    def info(self, msg: str, **context) -> None:
        """Log info message."""
        pass
    
    @abstractmethod
    def warning(self, msg: str, **context) -> None:
        """Log warning message."""
        pass
    
    @abstractmethod
    def error(self, msg: str, **context) -> None:
        """Log error message."""
        pass
    
    @abstractmethod
    def critical(self, msg: str, **context) -> None:
        """Log critical message."""
        pass
    
    @abstractmethod
    def metric(self, name: str, value: float, **tags) -> None:
        """Log metric value."""
        pass
    
    @abstractmethod
    def latency(self, operation: str, duration_ms: float, **tags) -> None:
        """Log latency metric."""
        pass
    
    @abstractmethod
    def counter(self, name: str, value: int = 1, **tags) -> None:
        """Log counter metric."""
        pass
    
    @abstractmethod
    def audit(self, event: str, **context) -> None:
        """Log audit event."""
        pass
    
    @abstractmethod
    def set_context(self, **context) -> None:
        """Set persistent context for all logs from this logger."""
        pass
    
    @abstractmethod
    async def flush(self) -> None:
        """Flush all backends."""
        pass