"""
Console Backend for Development Environment

Provides console output using Python's logging system for full compatibility.
Only enabled in development environment to avoid production noise.

HFT COMPLIANT: Fast filtering, async dispatch.
"""

import logging
import os
from typing import Dict, Optional

from ..interfaces import LogBackend, LogRecord, LogLevel, LogType
from ..structs import ConsoleBackendConfig


class ConsoleBackend(LogBackend):
    """
    Console logging backend for development environment.
    
    Uses Python's standard logging for full compatibility with existing
    console handlers, formatters, and log management tools.
    
    Accepts only ConsoleBackendConfig struct for configuration.
    """
    
    def __init__(self, config: ConsoleBackendConfig, name: str = "console"):
        """
        Initialize console backend with struct configuration.
        
        Args:
            name: Backend name
            config: ConsoleBackendConfig struct (required)
        """
        if not isinstance(config, ConsoleBackendConfig):
            raise TypeError(f"Expected ConsoleBackendConfig, got {type(config)}")
        
        super().__init__(name, {})  # Empty dict for base class compatibility
        
        # Store struct config
        self.config = config
        
        # Configuration from struct
        self.environment = config.environment or os.getenv('ENVIRONMENT', 'dev')
        if isinstance(config.min_level, str):
            self.min_level = LogLevel[config.min_level.upper()]
        else:
            self.min_level = LogLevel(config.min_level)
        self.color_enabled = config.color
        self.include_context = config.include_context
        self.max_message_length = config.max_message_length
        
        # Enable based on struct config
        self.enabled = config.enabled
        
        # Cache for Python loggers (one per logger name)
        self._py_loggers: Dict[str, logging.Logger] = {}
        
        # Initialize Python logging if not already configured
        if self.enabled:
            self._ensure_python_logging_configured()
    
    def should_handle(self, record: LogRecord) -> bool:
        """
        Handle text logs in development environment only.
        
        Fast filtering - called in hot path.
        """
        if not self.enabled:
            return False
        
        # Check level threshold
        if record.level < self.min_level:
            return False
        
        # Handle text logs and debug info (not metrics)
        return record.log_type in (LogType.TEXT, LogType.DEBUG, LogType.AUDIT)
    
    async def write(self, record: LogRecord) -> None:
        """Write to console using Python logging system."""
        self.write_sync(record)
    
    def write_sync(self, record: LogRecord) -> None:
        """Synchronous write for non-async environments."""
        try:
            # Get or create Python logger for this component
            py_logger = self._get_python_logger(record.logger_name)
            
            # Convert our level to Python logging level
            py_level = self._convert_level(record.level)
            
            # Format message with context
            message = self._format_message(record)
            
            # Log to Python logger (uses existing console handlers)
            py_logger.log(py_level, message)
            
        except Exception as e:
            # Fallback to print if Python logging fails
            print(f"ConsoleBackend error: {e}")
            print(f"{record.level.name}: {record.logger_name}: {record.message}")
    
    async def flush(self) -> None:
        """Console output flushes automatically."""
        # Python logging handles console flushing
        pass
    
    def _ensure_python_logging_configured(self) -> None:
        """Ensure Python logging is configured for console output."""
        # Check if root logger has any handlers
        root_logger = logging.getLogger()
        if not root_logger.handlers:
            # Configure basic console output
            console_handler = logging.StreamHandler()
            # Use simple format for clean console output
            if self.color_enabled:
                # Color format for better readability
                formatter = logging.Formatter(
                    '%(levelname)-8s %(name)-20s %(message)s'
                )
            else:
                formatter = logging.Formatter(
                    '%(levelname)s - %(name)s - %(message)s'
                )
            console_handler.setFormatter(formatter)
            
            # Set level based on min_level config
            py_level = self._convert_level(self.min_level)
            console_handler.setLevel(py_level)
            root_logger.setLevel(py_level)
            
            # Add handler to root logger
            root_logger.addHandler(console_handler)
    
    def _get_python_logger(self, name: str) -> logging.Logger:
        """Get or create Python logger for component."""
        if name not in self._py_loggers:
            self._py_loggers[name] = logging.getLogger(name)
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
        """Format message with optional context."""
        message = record.message
        
        # Truncate very long messages
        if len(message) > self.max_message_length:
            message = message[:self.max_message_length] + "..."
        
        # Add context if enabled and present
        if self.include_context and record.context:
            context_parts = []
            
            # Add standard context items
            for key, value in record.context.items():
                # Limit context value length
                value_str = str(value)
                if len(value_str) > 100:
                    value_str = value_str[:100] + "..."
                context_parts.append(f"{key}={value_str}")
            
            if context_parts:
                message += f" | {', '.join(context_parts)}"
        
        # Add correlation info if present
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
    
    def enable_color(self, enabled: bool = True) -> None:
        """Enable/disable color output."""
        self.color_enabled = enabled
    
    def set_environment(self, environment: str) -> None:
        """Update environment setting."""
        self.environment = environment
        self.enabled = environment.lower() in ('dev', 'development', 'local', 'test')


class ColorConsoleBackend(ConsoleBackend):
    """
    Console backend with color support for better readability.
    
    Adds ANSI color codes based on log level.
    Accepts only ConsoleBackendConfig struct for configuration.
    """
    
    # ANSI color codes
    COLORS = {
        LogLevel.DEBUG: '\033[36m',    # Cyan
        LogLevel.INFO: '\033[37m',     # White  
        LogLevel.WARNING: '\033[33m',  # Yellow
        LogLevel.ERROR: '\033[31m',    # Red
        LogLevel.CRITICAL: '\033[35m', # Magenta
    }
    RESET = '\033[0m'
    
    def __init__(self, config: ConsoleBackendConfig, name: str = "color_console"):
        """
        Initialize color console backend with struct configuration.
        
        Args:
            name: Backend name
            config: ConsoleBackendConfig struct (required)
        """
        super().__init__(config, name)
        
        # Check if colors are supported
        self.colors_supported = (
            os.getenv('TERM') != 'dumb' and 
            hasattr(os.sys.stdout, 'isatty') and 
            os.sys.stdout.isatty()
        )
        
        # Only use colors if explicitly enabled and supported
        self.use_colors = (
            self.color_enabled and 
            self.colors_supported
        )
    
    def _format_message(self, record: LogRecord) -> str:
        """Format message with color codes."""
        message = super()._format_message(record)
        
        if self.use_colors and record.level in self.COLORS:
            color = self.COLORS[record.level]
            message = f"{color}{message}{self.RESET}"
        
        return message


class StructuredConsoleBackend(ConsoleBackend):
    """
    Console backend that outputs structured data (JSON) for analysis.
    
    Useful for development debugging and log parsing.
    Accepts only ConsoleBackendConfig struct for configuration.
    """
    
    def __init__(self, config: ConsoleBackendConfig, name: str = "structured_console"):
        """
        Initialize structured console backend with struct configuration.
        
        Args:
            name: Backend name
            config: ConsoleBackendConfig struct (required)
        """
        super().__init__(config, name)
        self.include_raw_data = False  # Fixed property for structured output
    
    def _format_message(self, record: LogRecord) -> str:
        """Format as JSON structure."""
        import json
        
        data = {
            'timestamp': record.timestamp,
            'level': record.level.name,
            'type': record.log_type.name,
            'logger': record.logger_name,
            'message': record.message
        }
        
        # Add context
        if record.context:
            data['context'] = record.context
        
        # Add correlation info
        if record.correlation_id:
            data['correlation_id'] = record.correlation_id
        if record.exchange:
            data['exchange'] = record.exchange
        if record.symbol:
            data['symbol'] = record.symbol
        
        # Add metric info for metrics
        if record.log_type == LogType.METRIC:
            data['metric'] = {
                'name': record.metric_name,
                'value': record.metric_value,
                'tags': record.metric_tags
            }
        
        try:
            return json.dumps(data, separators=(',', ':'))
        except Exception as e:
            # Fallback to simple format
            return f"JSON_ERROR: {e} | {super()._format_message(record)}"