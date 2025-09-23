"""
Logging Factory for HFT System

Creates and configures logger instances with appropriate backends based on
environment and configuration. Provides factory pattern injection for all
components to use as self.logger.

HFT COMPLIANT: Fast logger creation, optimized backend selection.
"""

import os
from typing import Dict, Any, Optional, List
from .interfaces import HFTLoggerInterface, LogBackend, LogRouter
from .hft_logger import HFTLogger
from .router import SimpleRouter, create_router
from .backends.console import ConsoleBackend, ColorConsoleBackend
from .backends.file import FileBackend, AuditFileBackend
from .backends.prometheus import PrometheusBackend, PrometheusHistogramBackend
from .backends.python_bridge import PythonLoggingBridge
from core.config.config_manager import get_logging_config


class LoggerFactory:
    """
    Factory for creating configured HFT loggers.
    
    Provides standardized logger creation with appropriate backends
    based on environment and configuration requirements.
    """
    
    # Cached instances for reuse
    _cached_loggers: Dict[str, HFTLoggerInterface] = {}
    _cached_backends: Dict[str, LogBackend] = {}
    _default_config: Dict[str, Any] = {}
    
    @classmethod
    def create_logger(cls, 
                     name: str,
                     config: Dict[str, Any] = None,
                     force_new: bool = False) -> HFTLoggerInterface:
        """
        Create or retrieve cached logger instance.
        
        Args:
            name: Logger name (component identifier)
            config: Optional configuration override
            force_new: Force creation of new instance
            
        Returns:
            Configured HFTLogger instance
        """
        cache_key = f"{name}_{hash(str(sorted((config or {}).items())))}"
        
        if not force_new and cache_key in cls._cached_loggers:
            return cls._cached_loggers[cache_key]
        
        # Merge with default config
        effective_config = {**cls._default_config, **(config or {})}
        
        # Create backends
        backends = cls._create_backends(effective_config)
        
        # Create router
        router = cls._create_router(backends, effective_config)
        
        # Get performance settings from config.yaml
        yaml_config = get_logging_config()
        performance_config = yaml_config.get('performance', {})
        
        # Create logger with config.yaml settings
        logger_config = effective_config.get('logger_config', {})
        buffer_size = logger_config.get('buffer_size', 
                                       performance_config.get('buffer_size', 10000))
        batch_size = logger_config.get('batch_size', 
                                      performance_config.get('batch_size', 50))
        
        logger = HFTLogger(
            name=name,
            backends=list(backends.values()),
            router=router,
            buffer_size=buffer_size,
            batch_size=batch_size
        )
        
        # Cache and return
        cls._cached_loggers[cache_key] = logger
        return logger
    
    @classmethod
    def create_component_logger(cls, component_name: str) -> HFTLoggerInterface:
        """
        Create logger for specific component using default configuration.
        
        Args:
            component_name: Name of component (e.g., 'mexc.websocket.public')
            
        Returns:
            Configured logger instance
        """
        return cls.create_logger(component_name)
    
    @classmethod
    def create_exchange_logger(cls, 
                              exchange: str, 
                              component: str = None) -> HFTLoggerInterface:
        """
        Create logger for exchange component.
        
        Args:
            exchange: Exchange name (e.g., 'mexc', 'gateio')
            component: Optional component name (e.g., 'websocket.public')
            
        Returns:
            Configured logger with exchange context
        """
        if component:
            name = f"{exchange}.{component}"
        else:
            name = exchange
        
        # Add exchange-specific configuration
        config = {
            'default_context': {'exchange': exchange},
            'logger_config': {
                'default_exchange': exchange
            }
        }
        
        return cls.create_logger(name, config)
    
    @classmethod
    def create_arbitrage_logger(cls, strategy: str = None) -> HFTLoggerInterface:
        """
        Create logger for arbitrage components.
        
        Args:
            strategy: Optional strategy name
            
        Returns:
            Configured logger for arbitrage operations
        """
        name = f"arbitrage.{strategy}" if strategy else "arbitrage"
        
        config = {
            'default_context': {'component': 'arbitrage'},
            'logger_config': {
                'correlation_tracking': True,
                'performance_tracking': True
            }
        }
        
        return cls.create_logger(name, config)
    
    @classmethod
    def _create_backends(cls, config: Dict[str, Any]) -> Dict[str, LogBackend]:
        """Create and configure logging backends based on config.yaml."""
        backends = {}
        
        # Get configuration from config.yaml
        yaml_config = get_logging_config()
        
        # Merge with provided config (provided config takes precedence)
        environment = config.get('environment', os.getenv('ENVIRONMENT', 'dev'))
        
        # Console backend - ALWAYS enabled by default from config.yaml
        console_config = yaml_config.get('console', {})
        if console_config.get('enabled', True):  # Default to enabled
            console_backend_config = {
                'enabled': True,  # Explicitly pass enabled flag
                'environment': environment,
                'min_level': console_config.get('min_level', 'DEBUG'),
                'include_context': console_config.get('include_context', True),
                'color': console_config.get('color', True)
            }
            
            if console_backend_config.get('color', True):
                backends['console'] = ColorConsoleBackend('console', console_backend_config)
            else:
                backends['console'] = ConsoleBackend('console', console_backend_config)
        
        # File backend - configured from config.yaml
        file_config = yaml_config.get('file', {})
        if file_config.get('enabled', True):  # Default to enabled
            file_backend_config = {
                'file_path': file_config.get('path', 'logs/hft.log'),
                'format': file_config.get('format', 'text'),
                'min_level': file_config.get('min_level', 'INFO'),
                'max_file_size_mb': file_config.get('max_size_mb', 100),
                'backup_count': file_config.get('backup_count', 5)
            }
            backends['file'] = FileBackend('file', file_backend_config)
        
        # Prometheus backend - configured from config.yaml
        prometheus_config = yaml_config.get('prometheus', {})
        if prometheus_config.get('enabled', False):  # Disabled by default
            prometheus_backend_config = {
                'enabled': True,
                'push_gateway_url': prometheus_config.get('push_gateway_url', 'http://localhost:9091'),
                'job_name': prometheus_config.get('job_name', 'hft_arbitrage'),
                'batch_size': prometheus_config.get('batch_size', 100),
                'flush_interval': prometheus_config.get('flush_interval', 5.0)
            }
            backends['prometheus'] = PrometheusBackend('prometheus', prometheus_backend_config)
            
            # Add histogram backend if Prometheus is enabled
            backends['prometheus_histogram'] = PrometheusHistogramBackend(
                'prometheus_histogram', prometheus_backend_config
            )
        
        # Python logging bridge (always present for compatibility)
        backends['python_bridge'] = PythonLoggingBridge('python_bridge', {})
        
        return backends
    
    @classmethod
    def _create_router(cls, 
                      backends: Dict[str, LogBackend], 
                      config: Dict[str, Any]) -> LogRouter:
        """Create and configure message router."""
        environment = config.get('environment', os.getenv('ENVIRONMENT', 'dev'))
        return create_router(backends, environment)
    
    @classmethod
    def configure_defaults(cls, config: Dict[str, Any]) -> None:
        """
        Configure default settings for all loggers.
        
        Args:
            config: Default configuration to apply
        """
        cls._default_config.update(config)
        
        # Clear cache to force reconfiguration
        cls._cached_loggers.clear()
        cls._cached_backends.clear()
    
    @classmethod
    def set_environment(cls, environment: str) -> None:
        """
        Set environment for all future logger creation.
        
        Args:
            environment: Environment name (dev, prod, test)
        """
        cls.configure_defaults({'environment': environment})
    
    @classmethod
    def clear_cache(cls) -> None:
        """Clear cached logger instances."""
        cls._cached_loggers.clear()
        cls._cached_backends.clear()
    
    @classmethod
    def get_cached_loggers(cls) -> List[str]:
        """Get list of cached logger names."""
        return list(cls._cached_loggers.keys())


# Convenience functions for common use cases

def get_logger(name: str, config: Dict[str, Any] = None) -> HFTLoggerInterface:
    """
    Get logger instance using factory.
    
    Args:
        name: Logger name
        config: Optional configuration
        
    Returns:
        Configured logger instance
    """
    return LoggerFactory.create_logger(name, config)


def get_exchange_logger(exchange: str, component: str = None) -> HFTLoggerInterface:
    """
    Get logger for exchange component.
    
    Args:
        exchange: Exchange name
        component: Optional component name
        
    Returns:
        Exchange-specific logger
    """
    return LoggerFactory.create_exchange_logger(exchange, component)


def get_arbitrage_logger(strategy: str = None) -> HFTLoggerInterface:
    """
    Get logger for arbitrage operations.
    
    Args:
        strategy: Optional strategy name
        
    Returns:
        Arbitrage-specific logger
    """
    return LoggerFactory.create_arbitrage_logger(strategy)


def get_strategy_logger(strategy_path: str, tags: List[str]) -> HFTLoggerInterface:
    """
    Create strategy-specific logger with hierarchical tags.
    
    Args:
        strategy_path: Dot-separated strategy path (e.g., 'rest.auth.mexc.private')
        tags: Hierarchical tags [exchange, api_type, transport, strategy_type]
        
    Returns:
        HFTLogger with strategy-specific configuration
    """
    # Create configuration with default tags
    config = {
        'default_context': {
            "exchange": tags[0],
            "api_type": tags[1], 
            "transport": tags[2],
            "strategy_type": tags[3] if len(tags) > 3 else 'core',
            "component": "strategy"
        },
        'logger_config': {
            'strategy_path': strategy_path,
            'performance_tracking': True
        }
    }
    
    return LoggerFactory.create_logger(strategy_path, config)


def get_strategy_metrics_logger(exchange: str, api_type: str, transport: str) -> HFTLoggerInterface:
    """
    Create strategy metrics logger for performance tracking.
    
    Args:
        exchange: Exchange name (e.g., 'mexc', 'gateio')
        api_type: API type ('public' or 'private')
        transport: Transport type ('rest' or 'ws')
        
    Returns:
        Strategy metrics logger with performance focus
    """
    strategy_path = f'{transport}.metrics.{exchange}.{api_type}'
    tags = [exchange, api_type, transport, 'metrics']
    return get_strategy_logger(strategy_path, tags)


def configure_logging(config: Dict[str, Any]) -> None:
    """
    Configure global logging settings.
    
    Args:
        config: Global logging configuration
    """
    LoggerFactory.configure_defaults(config)


# Configuration is now loaded from config.yaml - no hardcoded configs needed


# Setup functions no longer needed - configuration is automatic from config.yaml