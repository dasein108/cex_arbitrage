"""
Python Logging Bridge Backend

Provides backwards compatibility with Python's logging system.
Routes messages to existing Python loggers for seamless integration.

HFT COMPLIANT: Minimal overhead, preserves existing logging behavior.
"""

import logging
import os
from typing import Dict, Optional

from ..interfaces import LogBackend, LogRecord, LogLevel, LogType
from ..structs import BackendConfig


class PythonLoggingBridge(LogBackend):
    """
    Backend that bridges to Python's logging system.
    
    Ensures 100% backwards compatibility with existing logging code
    while allowing new HFT logger features to coexist.
    
    Accepts only BackendConfig struct for configuration.
    """
    
    def __init__(self, config: BackendConfig, name: str = "python_bridge"):
        """
        Initialize Python bridge backend with struct configuration.
        
        Args:
            name: Backend name
            config: BackendConfig struct (required)
        """
        if not isinstance(config, BackendConfig):
            raise TypeError(f"Expected BackendConfig, got {type(config)}")
        
        super().__init__(name, {})  # Empty dict for base class compatibility
        
        # Store struct config
        self.config = config
        
        # Configuration from struct
        if isinstance(config.min_level, str):
            self.min_level = LogLevel[config.min_level.upper()]
        else:
            self.min_level = LogLevel(config.min_level)
        
        # Enable based on struct config
        self.enabled = config.enabled
        
        # Fixed properties for Python bridge
        self.include_context = True
        self.max_context_length = 500
        self.format_correlation = True
        
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
            
            # Convert our level to Python logging level
            py_level = self._convert_level(record.level)
            
            # Format message with context and correlation
            message = self._format_message(record)
            
            # Log to Python logger
            py_logger.log(py_level, message)
            
        except Exception as e:
            # Fallback to print if Python logging fails
            print(f"PythonLoggingBridge error: {e}")
            print(f"{record.level.name}: {record.logger_name}: {record.message}")
    
    async def flush(self) -> None:
        """Python logging handles flushing automatically."""
        # Force flush all handlers
        for py_logger in self._py_loggers.values():
            for handler in py_logger.handlers:
                try:
                    handler.flush()
                except Exception:
                    pass
    
    def _get_python_logger(self, name: str) -> logging.Logger:
        """Get or create Python logger for component."""
        if name not in self._py_loggers:
            self._py_loggers[name] = logging.getLogger(name)
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
        """Format message with context and correlation info."""
        message = record.message
        
        # Add context if enabled and present
        if self.include_context and record.context:
            context_parts = []
            
            # Limit total context length
            total_length = 0
            for key, value in record.context.items():
                value_str = str(value)
                
                # Limit individual value length
                if len(value_str) > 100:
                    value_str = value_str[:100] + "..."
                
                context_part = f"{key}={value_str}"
                
                # Check total length
                if total_length + len(context_part) + 2 <= self.max_context_length:
                    context_parts.append(context_part)
                    total_length += len(context_part) + 2  # +2 for ", "
                else:
                    context_parts.append("...")
                    break
            
            if context_parts:
                message += f" | {', '.join(context_parts)}"
        
        # Add correlation info if enabled and present
        if self.format_correlation:
            correlation_parts = []
            
            if record.correlation_id:
                correlation_parts.append(f"correlation_id={record.correlation_id}")
            if record.exchange:
                correlation_parts.append(f"exchange={record.exchange}")
            if record.symbol:
                correlation_parts.append(f"symbol={record.symbol}")
            
            if correlation_parts:
                message += f" | {', '.join(correlation_parts)}"
        
        # Add log type prefix for non-text logs
        if record.log_type != LogType.TEXT:
            message = f"[{record.log_type.name}] {message}"
        
        return message
    
    def set_level(self, level: LogLevel) -> None:
        """Update minimum level filter."""
        self.min_level = level
    
    def get_seen_loggers(self) -> set:
        """Get set of logger names that have been used."""
        return self._seen_loggers.copy()
    
    def get_python_logger_count(self) -> int:
        """Get count of created Python loggers."""
        return len(self._py_loggers)