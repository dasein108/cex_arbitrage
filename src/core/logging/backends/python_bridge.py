"""
Python Logging Bridge Backend

Provides backwards compatibility with Python's logging system.
Routes messages to existing Python loggers for seamless integration.

HFT COMPLIANT: Minimal overhead, preserves existing logging behavior.
"""

import logging
import os
from typing import Dict, Any, Optional

from ..interfaces import LogBackend, LogRecord, LogLevel, LogType


class PythonLoggingBridge(LogBackend):
    """
    Backend that bridges to Python's logging system.
    
    Ensures 100% backwards compatibility with existing logging code
    while allowing new HFT logger features to coexist.
    """
    
    def __init__(self, name: str = "python_bridge", config: Dict[str, Any] = None):
        super().__init__(name, config)
        
        # Configuration
        config = config or {}
        min_level_config = config.get('min_level', LogLevel.DEBUG)
        if isinstance(min_level_config, str):
            self.min_level = LogLevel[min_level_config.upper()]
        else:
            self.min_level = LogLevel(min_level_config)
        self.include_context = config.get('include_context', True)
        self.max_context_length = config.get('max_context_length', 500)
        self.format_correlation = config.get('format_correlation', True)
        
        # Cache for Python loggers
        self._py_loggers: Dict[str, logging.Logger] = {}
        
        # Track which loggers we've seen for debugging
        self._seen_loggers = set()
    
    def should_handle(self, record: LogRecord) -> bool:
        """Handle all text-based log records."""
        if not self.enabled:
            return False
        
        # Check level threshold
        if record.level < self.min_level:
            return False
        
        # Handle text logs (not metrics which go to Prometheus)
        return record.log_type in (LogType.TEXT, LogType.DEBUG, LogType.AUDIT)
    
    async def write(self, record: LogRecord) -> None:
        """Write to Python logging system."""
        try:
            # Get Python logger for this component
            py_logger = self._get_python_logger(record.logger_name)
            
            # Convert level
            py_level = self._convert_level(record.level)
            
            # Format message
            message = self._format_message(record)
            
            # Use Python logger
            py_logger.log(py_level, message)
            
        except Exception as e:
            # Bridge should never fail
            print(f"PythonLoggingBridge error: {e}")
    
    async def flush(self) -> None:
        """Python logging handles flushing automatically."""
        # Ensure all handlers are flushed
        for logger in self._py_loggers.values():
            for handler in logger.handlers:
                try:
                    handler.flush()
                except Exception:
                    pass
    
    def _get_python_logger(self, name: str) -> logging.Logger:
        """Get or create Python logger for component."""
        if name not in self._py_loggers:
            self._py_loggers[name] = logging.getLogger(name)
            
            # Track new loggers for debugging
            if name not in self._seen_loggers:
                self._seen_loggers.add(name)
        
        return self._py_loggers[name]
    
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
    
    def _format_message(self, record: LogRecord) -> str:
        """Format message for Python logging."""
        message = record.message
        
        # Add context if enabled
        if self.include_context and record.context:
            context_str = self._format_context(record.context)
            if context_str:
                message += f" | {context_str}"
        
        # Add correlation info if enabled
        if self.format_correlation:
            correlation_str = self._format_correlation(record)
            if correlation_str:
                message += f" | {correlation_str}"
        
        # Add log type for non-text logs
        if record.log_type != LogType.TEXT:
            message += f" | type={record.log_type.name}"
        
        return message
    
    def _format_context(self, context: Dict[str, Any]) -> str:
        """Format context dictionary."""
        if not context:
            return ""
        
        context_parts = []
        total_length = 0
        
        for key, value in context.items():
            # Convert value to string
            if isinstance(value, dict):
                value_str = str(value)  # Keep simple for performance
            elif isinstance(value, (list, tuple)):
                value_str = f"[{len(value)} items]"  # Summarize collections
            else:
                value_str = str(value)
            
            # Limit individual value length
            if len(value_str) > 100:
                value_str = value_str[:100] + "..."
            
            part = f"{key}={value_str}"
            
            # Check total length limit
            if total_length + len(part) > self.max_context_length:
                context_parts.append("...")
                break
            
            context_parts.append(part)
            total_length += len(part) + 2  # +2 for ", "
        
        return ", ".join(context_parts)
    
    def _format_correlation(self, record: LogRecord) -> str:
        """Format correlation tracking info."""
        parts = []
        
        if record.correlation_id:
            parts.append(f"correlation_id={record.correlation_id}")
        if record.exchange:
            parts.append(f"exchange={record.exchange}")
        if record.symbol:
            parts.append(f"symbol={record.symbol}")
        
        return ", ".join(parts)
    
    def get_logger_names(self) -> list:
        """Get list of logger names we've seen."""
        return list(self._seen_loggers)
    
    def set_python_level(self, logger_name: str, level: int) -> None:
        """Set level on specific Python logger."""
        if logger_name in self._py_loggers:
            self._py_loggers[logger_name].setLevel(level)


class CompatibilityHandler(logging.Handler):
    """
    Python logging handler that forwards to HFT logger.
    
    Allows existing Python logging calls to be automatically
    routed through the new HFT logging system.
    """
    
    def __init__(self, hft_logger):
        super().__init__()
        self.hft_logger = hft_logger
    
    def emit(self, record: logging.LogRecord) -> None:
        """Forward Python log record to HFT logger."""
        try:
            # Convert Python level to our level
            level = self._convert_level(record.levelno)
            
            # Format message
            message = record.getMessage()
            
            # Extract context from record
            context = {}
            
            # Add extra fields if present
            if hasattr(record, '__dict__'):
                for key, value in record.__dict__.items():
                    if key not in ('name', 'msg', 'args', 'levelname', 'levelno', 
                                  'pathname', 'filename', 'module', 'lineno', 
                                  'funcName', 'created', 'msecs', 'relativeCreated',
                                  'thread', 'threadName', 'processName', 'process',
                                  'message', 'exc_info', 'exc_text', 'stack_info'):
                        context[key] = value
            
            # Add source info
            if record.filename:
                context['source_file'] = record.filename
            if record.lineno:
                context['source_line'] = record.lineno
            if record.funcName:
                context['source_func'] = record.funcName
            
            # Forward to HFT logger
            if level == LogLevel.DEBUG:
                self.hft_logger.debug(message, **context)
            elif level == LogLevel.INFO:
                self.hft_logger.info(message, **context)
            elif level == LogLevel.WARNING:
                self.hft_logger.warning(message, **context)
            elif level == LogLevel.ERROR:
                self.hft_logger.error(message, **context)
            elif level == LogLevel.CRITICAL:
                self.hft_logger.critical(message, **context)
                
        except Exception:
            # Handler must not raise exceptions
            pass
    
    def _convert_level(self, py_level: int) -> LogLevel:
        """Convert Python logging level to our LogLevel."""
        if py_level >= logging.CRITICAL:
            return LogLevel.CRITICAL
        elif py_level >= logging.ERROR:
            return LogLevel.ERROR
        elif py_level >= logging.WARNING:
            return LogLevel.WARNING
        elif py_level >= logging.INFO:
            return LogLevel.INFO
        else:
            return LogLevel.DEBUG


def install_compatibility_handler(hft_logger, logger_name: str = None) -> None:
    """
    Install compatibility handler to forward Python logging to HFT logger.
    
    Args:
        hft_logger: HFT logger instance
        logger_name: Specific logger name, or None for root logger
    """
    handler = CompatibilityHandler(hft_logger)
    
    if logger_name:
        logger = logging.getLogger(logger_name)
    else:
        logger = logging.getLogger()
    
    # Add handler
    logger.addHandler(handler)
    
    # Set level to ensure all messages are captured
    logger.setLevel(logging.DEBUG)


def remove_compatibility_handler(logger_name: str = None) -> None:
    """Remove compatibility handlers from Python logger."""
    if logger_name:
        logger = logging.getLogger(logger_name)
    else:
        logger = logging.getLogger()
    
    # Remove all CompatibilityHandler instances
    handlers_to_remove = [
        h for h in logger.handlers 
        if isinstance(h, CompatibilityHandler)
    ]
    
    for handler in handlers_to_remove:
        logger.removeHandler(handler)