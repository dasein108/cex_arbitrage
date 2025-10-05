"""
Logging Factory for HFT System

Creates and configures logger instances using struct-based configuration.
Provides direct method injection for all components to use as self.logger.

HFT COMPLIANT: Fast logger creation, optimized backend selection.
"""

import os
import traceback
from typing import Dict, Any, Optional, List
from .interfaces import HFTLoggerInterface, LogBackend, LogRouter
from .hft_logger import HFTLogger
from .router import create_router
from .backends.console import ConsoleBackend, ColorConsoleBackend
from .backends.file import FileBackend, AuditFileBackend
from .backends.prometheus import PrometheusBackend, PrometheusHistogramBackend
from .structs import (
    LoggingConfig, ConsoleBackendConfig, FileBackendConfig,
    PrometheusBackendConfig, AuditBackendConfig, PerformanceConfig,
    RouterConfig
)


class LoggerFactory:
    """Simplified logging factory - trust config, fail fast."""
    
    # Cached instances for reuse
    _cached_loggers: Dict[str, HFTLoggerInterface] = {}
    _default_config: Optional[LoggingConfig] = None
    
    @classmethod
    def create_logger(cls, name: str, config: Optional[LoggingConfig] = None) -> HFTLoggerInterface:
        """Create logger instance. Trust config, fail fast."""
        config = config or cls._get_default_config()
        
        # Simple caching by name only
        if name in cls._cached_loggers:
            return cls._cached_loggers[name]
        
        # Create backends directly
        backends = []
        if config.console and config.console.enabled:
            backend_class = ColorConsoleBackend if config.console.color else ConsoleBackend
            backends.append(backend_class(config.console, 'console'))
        
        if config.file and config.file.enabled:
            backends.append(FileBackend(config.file, 'file'))
        
        # Create router
        router = create_router({b.name: b for b in backends}, config.router or RouterConfig())
        
        logger = HFTLogger(
            name=name,
            backends=backends,
            router=router,
            config=config.performance or PerformanceConfig()
        )
        
        cls._cached_loggers[name] = logger
        return logger
    
    @classmethod  
    def get_default_config(cls) -> LoggingConfig:
        """Get default config for external use."""
        return cls._get_default_config()
    
    @classmethod
    def override_logger(cls, name: str, **overrides) -> bool:
        """
        Override logger configuration at runtime.

        Args:
            name: Logger name to override
            **overrides: Configuration overrides:
                - min_level: Change minimum log level (e.g., "ERROR", "WARNING")
                - enabled: Enable/disable the logger entirely
                - backend_enabled: Dict of backend names to enable/disable

        Returns:
            True if logger was found and modified, False otherwise

        Example:
            # Suppress noisy logger
            LoggerFactory.override_logger("mexc.websocket", min_level="ERROR")

            # Disable logger completely
            LoggerFactory.override_logger("debug.component", enabled=False)

            # Disable specific backend
            LoggerFactory.override_logger("trading", backend_enabled={"file": False})
        """
        if name not in cls._cached_loggers:
            return False

        logger = cls._cached_loggers[name]

        # Override minimum log level for all backends
        if "min_level" in overrides:
            from .interfaces import LogLevel
            level_str = overrides["min_level"].upper()
            level = LogLevel[level_str] if isinstance(overrides["min_level"], str) else overrides["min_level"]

            for backend in logger.backends:
                if hasattr(backend, 'min_level'):
                    backend.min_level = level

        # Enable/disable logger entirely (affects all backends)
        if "enabled" in overrides:
            enabled = overrides["enabled"]
            for backend in logger.backends:
                backend.enabled = enabled

        # Enable/disable specific backends
        if "backend_enabled" in overrides:
            backend_settings = overrides["backend_enabled"]
            for backend in logger.backends:
                if backend.name in backend_settings:
                    backend.enabled = backend_settings[backend.name]

        return True

    @classmethod
    def clear_cache(cls) -> None:
        """Clear cached logger instances."""
        cls._cached_loggers.clear()
        cls._default_config = None
    
    @classmethod
    def _get_default_config(cls) -> LoggingConfig:
        """Get default configuration, creating if necessary."""
        if cls._default_config is None:
            # Try to load from config.yaml
            try:
                cls._default_config = cls._load_default_config()
            except Exception as e:
                # Fall back to default based on environment
                environment = os.getenv('ENVIRONMENT', 'dev')
                traceback.print_exc()
                if environment == 'prod':
                    cls._default_config = LoggingConfig.default_production()
                else:
                    cls._default_config = LoggingConfig.default_development()
        return cls._default_config
    
    @classmethod
    def _load_default_config(cls) -> LoggingConfig:
        """Convert config manager format to LoggingConfig struct."""
        # Delayed import to avoid circular dependency
        try:
            from config import get_logging_config, HftConfig
            logging_config = get_logging_config()
            
            # Convert config manager format to struct format
            struct_data = {
                'environment': os.getenv('ENVIRONMENT', 'dev')
            }
            
            # Map backends to individual config objects
            backends = logging_config.get('backends', {})
            
            if 'console' in backends and backends['console'].get('enabled', False):
                struct_data['console'] = ConsoleBackendConfig(
                    enabled=True,
                    min_level=backends['console'].get('min_level', 'DEBUG'),
                    color=backends['console'].get('color', True),
                    include_context=backends['console'].get('include_context', True)
                )
            
            if 'file' in backends and backends['file'].get('enabled', False):
                struct_data['file'] = FileBackendConfig(
                    enabled=True,
                    min_level=backends['file'].get('min_level', 'INFO'),
                    path=backends['file'].get('path', 'logs/hft.log'),
                    format='text'
                )
            
            # Performance config from hft_settings
            hft_settings = logging_config.get('hft_settings', {})
            if hft_settings:
                struct_data['performance'] = PerformanceConfig(
                    buffer_size=hft_settings.get('ring_buffer_size', 10000),
                    batch_size=hft_settings.get('batch_size', 50)
                )
                
            return LoggingConfig(**struct_data)
            
        except ImportError as e:
            # If circular import occurs, fall back to environment-based default
            environment = os.getenv('ENVIRONMENT', 'dev')
            if environment == 'prod':
                return LoggingConfig.default_production()
            else:
                return LoggingConfig.default_development()


# Simplified convenience functions

def get_logger(name: str) -> HFTLoggerInterface:
    """Get logger instance. Simple, fast."""
    return LoggerFactory.create_logger(name)

def get_exchange_logger(exchange: str, component: str = None) -> HFTLoggerInterface:
    """Get exchange logger with optional component."""
    name = f"{exchange}.{component}" if component else exchange
    return get_logger(name)

def get_strategy_logger(strategy_path: str, tags: List[str] = None) -> HFTLoggerInterface:
    """Legacy function for backward compatibility. Use get_logger() directly in new code."""
    return get_logger(strategy_path)