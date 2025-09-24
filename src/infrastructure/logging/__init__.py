"""
HFT Logging System

High-performance logging system designed for high-frequency trading applications.
Configured automatically from config.yaml.

Usage:
    from infrastructure.logging import get_logger
    
    # Component logger
    logger = get_logger('my.component')
    logger.info("Component initialized")
    
    # Exchange logger with context
    logger = get_exchange_logger('mexc', 'ws.public')
    logger.debug("WebSocket connected", correlation_id="abc123")
    
    # Metrics logging
    logger.metric("latency", 1.23, operation="place_order")

HFT COMPLIANT: Zero-allocation hot paths, minimal overhead.
"""

# Core interfaces
from .interfaces import (
    LogLevel,
    LogType,
    LogRecord,
    LogBackend,
    LogRouter,
    HFTLoggerInterface
)

# Main logger implementation  
from .hft_logger import HFTLogger, LoggingTimer

# Factory for creating loggers (main entry point)
from .factory import (
    LoggerFactory,
    get_logger,
    get_exchange_logger,
    get_arbitrage_logger,
    get_strategy_logger,
    get_strategy_metrics_logger,
    configure_logging,
    configure_logging_from_struct
)

# Configuration structures
from .structs import (
    LoggingConfig,
    ConsoleBackendConfig,
    FileBackendConfig,
    PrometheusBackendConfig,
    AuditBackendConfig,
    PerformanceConfig,
    RouterConfig,
    LoggerComponentConfig,
    BackendConfig
)

# Router (simplified)
from .router import SimpleRouter, create_router

# Essential backends only
from .backends.console import ConsoleBackend, ColorConsoleBackend
from .backends.file import FileBackend, AuditFileBackend
from .backends.prometheus import PrometheusBackend, PrometheusHistogramBackend

# Version info
__version__ = "2.0.0"

__all__ = [
    # Core interfaces
    'LogLevel',
    'LogType', 
    'LogRecord',
    'LogBackend',
    'LogRouter',
    'HFTLoggerInterface',
    
    # Main logger
    'HFTLogger',
    'LoggingTimer',
    
    # Factory functions (main API)
    'LoggerFactory',
    'get_logger',
    'get_exchange_logger',
    'get_arbitrage_logger',
    'get_strategy_logger',
    'get_strategy_metrics_logger',
    'configure_logging',
    'configure_logging_from_struct',
    
    # Configuration structures
    'LoggingConfig',
    'ConsoleBackendConfig',
    'FileBackendConfig',
    'PrometheusBackendConfig',
    'AuditBackendConfig',
    'PerformanceConfig',
    'RouterConfig',
    'LoggerComponentConfig',
    'BackendConfig',
    
    # Router
    'SimpleRouter',
    'create_router',
    
    # Backends
    'ConsoleBackend',
    'ColorConsoleBackend',
    'FileBackend',
    'AuditFileBackend', 
    'PrometheusBackend',
    'PrometheusHistogramBackend',
]