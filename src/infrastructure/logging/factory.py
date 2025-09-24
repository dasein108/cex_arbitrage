"""
Logging Factory for HFT System

Creates and configures logger instances using struct-based configuration.
Provides factory pattern injection for all components to use as self.logger.

HFT COMPLIANT: Fast logger creation, optimized backend selection.
"""

import os
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
    RouterConfig, BackendConfig
)


class LoggerFactory:
    """
    Factory for creating configured HFT loggers using struct-based configuration.
    
    All configuration is done through msgspec.Struct types for type safety,
    performance, and validation. No dictionary-based configuration is accepted.
    """
    
    # Cached instances for reuse
    _cached_loggers: Dict[str, HFTLoggerInterface] = {}
    _cached_backends: Dict[str, LogBackend] = {}
    _default_config: Optional[LoggingConfig] = None
    
    @classmethod
    def create_logger(cls, 
                     name: str,
                     config: Optional[LoggingConfig] = None,
                     force_new: bool = False) -> HFTLoggerInterface:
        """
        Create or retrieve cached logger instance using struct configuration.
        
        Args:
            name: Logger name (component identifier)
            config: Optional LoggingConfig struct override
            force_new: Force creation of new instance
            
        Returns:
            Configured HFTLogger instance
        """
        # Use struct-based configuration only
        if config is None:
            config = cls._get_default_config()
        
        cache_key = f"{name}_{id(config)}"
        
        if not force_new and cache_key in cls._cached_loggers:
            return cls._cached_loggers[cache_key]
        
        # Create backends from struct config
        backends = cls._create_backends(config)
        
        # Create router from struct config
        router = cls._create_router(backends, config)
        
        # Use performance config from struct
        perf_config = config.performance or PerformanceConfig()
        
        logger = HFTLogger(
            name=name,
            backends=list(backends.values()),
            router=router,
            config=perf_config
        )
        
        # Cache and return
        cls._cached_loggers[cache_key] = logger
        return logger
    
    @classmethod
    def create_component_logger(cls, component_name: str) -> HFTLoggerInterface:
        """
        Create logger for specific component using default configuration.
        
        Args:
            component_name: Name of component (e.g., 'mexc.ws.public')
            
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
            component: Optional component name (e.g., 'ws.public')
            
        Returns:
            Configured logger with exchange context
        """
        if component:
            name = f"{exchange}.{component}"
        else:
            name = exchange
        
        # Create exchange-specific configuration
        base_config = cls._get_default_config()
        config = LoggingConfig(
            environment=base_config.environment,
            console=base_config.console,
            file=base_config.file,
            prometheus=base_config.prometheus,
            audit=base_config.audit,
            performance=base_config.performance,
            router=base_config.router,
            default_context={'exchange': exchange}
        )
        
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
        
        # Create arbitrage-specific configuration
        base_config = cls._get_default_config()
        config = LoggingConfig(
            environment=base_config.environment,
            console=base_config.console,
            file=base_config.file,
            prometheus=base_config.prometheus,
            audit=base_config.audit,
            performance=base_config.performance,
            router=RouterConfig(
                environment=base_config.environment,
                correlation_tracking=True,
                default_backends=base_config.router.get_default_backends() if base_config.router else ["console", "file"]
            ),
            default_context={'component': 'arbitrage', 'strategy': strategy}
        )
        
        return cls.create_logger(name, config)
    
    @classmethod
    def _create_backends(cls, config: LoggingConfig) -> Dict[str, LogBackend]:
        """Create and configure logging backends using struct configuration only."""
        backends = {}
        
        # Console backend
        if config.console and config.console.enabled:
            if config.console.color:
                backends['console'] = ColorConsoleBackend(config.console, 'console')
            else:
                backends['console'] = ConsoleBackend(config.console, 'console')
        
        # File backend
        if config.file and config.file.enabled:
            backends['file'] = FileBackend(config.file, 'file')
        
        # Prometheus backend
        if config.prometheus and config.prometheus.enabled:
            backends['prometheus'] = PrometheusBackend(config.prometheus, 'prometheus')
            
            # Add histogram backend if Prometheus is enabled
            backends['prometheus_histogram'] = PrometheusHistogramBackend(
                config.prometheus, 'prometheus_histogram'
            )
        
        # Audit backend
        if config.audit and config.audit.enabled:
            backends['audit'] = AuditFileBackend(config.audit, 'audit')

        return backends
    
    @classmethod
    def _create_router(cls, 
                      backends: Dict[str, LogBackend], 
                      config: LoggingConfig) -> LogRouter:
        """Create and configure message router using struct configuration."""
        router_config = config.router or RouterConfig(environment=config.environment)
        return create_router(backends, router_config)
    
    @classmethod
    def configure_defaults(cls, config: LoggingConfig) -> None:
        """
        Configure default settings for all loggers.
        
        Args:
            config: Default LoggingConfig struct to apply
        """
        cls._default_config = config
        
        # Clear cache to force reconfiguration
        cls._cached_loggers.clear()
        cls._cached_backends.clear()
    
    @classmethod
    def set_environment(cls, environment: str) -> None:
        """
        Set environment for all future logger creation.
        
        Args:
            environment: Environment name (dev, prod, test, staging)
        """
        if cls._default_config:
            # Update existing config with new environment
            import msgspec
            data = msgspec.structs.asdict(cls._default_config)
            data['environment'] = environment
            cls._default_config = LoggingConfig.from_dict(data)
        else:
            # Create new config with specified environment
            if environment == 'prod':
                cls._default_config = LoggingConfig.default_production()
            else:
                cls._default_config = LoggingConfig.default_development()
                # Override environment
                import msgspec
                data = msgspec.structs.asdict(cls._default_config)
                data['environment'] = environment
                cls._default_config = LoggingConfig.from_dict(data)
    
    @classmethod
    def clear_cache(cls) -> None:
        """Clear cached logger instances."""
        cls._cached_loggers.clear()
        cls._cached_backends.clear()
    
    @classmethod
    def get_cached_loggers(cls) -> List[str]:
        """Get list of cached logger names."""
        return list(cls._cached_loggers.keys())
    
    @classmethod
    def _get_default_config(cls) -> LoggingConfig:
        """Get default configuration, creating if necessary."""
        if cls._default_config is None:
            # Try to load from config.yaml
            try:
                from infrastructure.config.config_manager import get_logging_config
                yaml_config = get_logging_config()
                cls._default_config = cls._yaml_to_struct_config(yaml_config)
            except Exception:
                # Fall back to default based on environment
                environment = os.getenv('ENVIRONMENT', 'dev')
                if environment == 'prod':
                    cls._default_config = LoggingConfig.default_production()
                else:
                    cls._default_config = LoggingConfig.default_development()
        return cls._default_config
    
    @classmethod
    def _yaml_to_struct_config(cls, yaml_config: Dict[str, Any]) -> LoggingConfig:
        """Convert YAML config dict to LoggingConfig struct."""
        # Build struct config from yaml
        config_dict = {
            'environment': yaml_config.get('environment', os.getenv('ENVIRONMENT', 'dev'))
        }
        
        # Console config
        if 'console' in yaml_config:
            console = yaml_config['console']
            config_dict['console'] = ConsoleBackendConfig(
                enabled=console.get('enabled', True),
                min_level=console.get('min_level', 'DEBUG'),
                environment=config_dict['environment'],
                color=console.get('color', True),
                include_context=console.get('include_context', True),
                max_message_length=console.get('max_message_length', 1000)
            )
        
        # File config
        if 'file' in yaml_config:
            file = yaml_config['file']
            config_dict['file'] = FileBackendConfig(
                enabled=file.get('enabled', True),
                min_level=file.get('min_level', 'INFO'),
                environment=config_dict['environment'],
                path=file.get('path', 'logs/hft.log'),
                format=file.get('format', 'text'),
                max_size_mb=file.get('max_size_mb', 100),
                backup_count=file.get('backup_count', 5),
                buffer_size=file.get('buffer_size', 1024),
                flush_interval=file.get('flush_interval', 1.0)
            )
        
        # Prometheus config
        if 'prometheus' in yaml_config:
            prom = yaml_config['prometheus']
            config_dict['prometheus'] = PrometheusBackendConfig(
                enabled=prom.get('enabled', False),
                min_level=prom.get('min_level', 'INFO'),
                environment=config_dict['environment'],
                push_gateway_url=prom.get('push_gateway_url', 'http://localhost:9091'),
                job_name=prom.get('job_name', 'hft_arbitrage'),
                batch_size=prom.get('batch_size', 100),
                flush_interval=prom.get('flush_interval', 5.0),
                histogram_buckets=prom.get('histogram_buckets')
            )
        
        # Audit config
        if 'audit' in yaml_config:
            audit = yaml_config['audit']
            config_dict['audit'] = AuditBackendConfig(
                enabled=audit.get('enabled', False),
                min_level=audit.get('min_level', 'INFO'),
                environment=config_dict['environment'],
                path=audit.get('path', 'logs/audit.log'),
                format='json',  # Always JSON for audit
                include_all_context=audit.get('include_all_context', True),
                immutable=audit.get('immutable', True)
            )
        
        # Performance config
        if 'performance' in yaml_config:
            perf = yaml_config['performance']
            config_dict['performance'] = PerformanceConfig(
                buffer_size=perf.get('buffer_size', 10000),
                batch_size=perf.get('batch_size', 50),
                dispatch_interval=perf.get('dispatch_interval', 0.1),
                max_queue_size=perf.get('max_queue_size', 50000),
                enable_sampling=perf.get('enable_sampling', False),
                sampling_rate=perf.get('sampling_rate', 1.0)
            )
        
        # Router config
        if 'router' in yaml_config:
            router = yaml_config['router']
            config_dict['router'] = RouterConfig(
                environment=config_dict['environment'],
                routing_rules=router.get('routing_rules'),
                default_backends=router.get('default_backends'),
                enable_smart_routing=router.get('enable_smart_routing', True),
                correlation_tracking=router.get('correlation_tracking', True)
            )
        
        return LoggingConfig.from_dict(config_dict)


# Convenience functions for common use cases

def get_logger(name: str, config: Optional[LoggingConfig] = None) -> HFTLoggerInterface:
    """
    Get logger instance using factory.
    
    Args:
        name: Logger name
        config: Optional LoggingConfig struct
        
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
    # Create configuration with tags
    base_config = LoggerFactory._get_default_config()
    config = LoggingConfig(
        environment=base_config.environment,
        console=base_config.console,
        file=base_config.file,
        prometheus=base_config.prometheus,
        audit=base_config.audit,
        performance=base_config.performance,
        router=RouterConfig(
            environment=base_config.environment,
            correlation_tracking=True,
            default_backends=base_config.router.get_default_backends() if base_config.router else ["console", "file"]
        ),
        default_context={
            "exchange": tags[0] if len(tags) > 0 else None,
            "api_type": tags[1] if len(tags) > 1 else None,
            "transport": tags[2] if len(tags) > 2 else None,
            "strategy_type": tags[3] if len(tags) > 3 else 'core',
            "component": "strategy"
        }
    )
    
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


def configure_logging_from_struct(config: LoggingConfig) -> None:
    """
    Configure global logging settings from LoggingConfig struct.
    
    Args:
        config: LoggingConfig struct
    """
    LoggerFactory.configure_defaults(config)


# Legacy function for backwards compatibility - converts dict to struct
def configure_logging(config: Dict[str, Any]) -> None:
    """
    Configure global logging settings (legacy function).
    
    Args:
        config: Global logging configuration dict (will be converted to LoggingConfig)
    """
    # Convert dict to LoggingConfig
    logging_config = LoggingConfig.from_dict(config)
    LoggerFactory.configure_defaults(logging_config)