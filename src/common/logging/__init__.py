"""
HFT Logging Architecture

Ultra-high-performance logging system designed for sub-50ms trading operations.
Supports both simple and complex logging modes via configuration.

Logging Modes:
- SIMPLE: Drop-in replacement for standard logging (<10μs emit latency)
- COMPLEX: Four-tier HFT system with ZeroMQ transport and structured logging

Usage (Simple Mode):
    from common.logging import getLogger, configure_console
    
    # Configure for simple mode
    configure_console(enabled=True)
    logger = getLogger(__name__)
    logger.info("Message")

Usage (Complex Mode):
    from common.logging import get_logger, LogLevel, LogType
    
    # Get specialized loggers
    trade_logger = get_logger(LogType.TRADE)
    perf_logger = get_logger(LogType.PERFORMANCE)
"""

# Simple logger imports (drop-in replacement)
from .simple_logger import (
    getLogger,
    configure_console,
    shutdown_all_loggers,
    LogLevel as SimpleLogLevel
)

# Complex HFT logging system (optional import for advanced use)
try:
    from .core import (
        LogType,
        LogLevel, 
        HftLogger,
        get_logger,
        configure_logging,
        shutdown_logging
    )
    
    from .structures import (
        TradeLogEntry,
        SystemLogEntry, 
        PerformanceLogEntry,
        GeneralLogEntry,
        LogMetadata
    )
    
    from .transport import (
        ZeroMQTransport,
        FileTransport,
        CompositeTransport
    )
    
    from .correlation import (
        CorrelationManager,
        generate_correlation_id,
        get_current_correlation_id,
        set_correlation_context
    )
    
    _COMPLEX_LOGGING_AVAILABLE = True
    
except ImportError:
    # Complex logging components not available, use simple logger only
    _COMPLEX_LOGGING_AVAILABLE = False
    LogType = None
    LogLevel = SimpleLogLevel
    HftLogger = None
    get_logger = getLogger
    configure_logging = None
    shutdown_logging = shutdown_all_loggers

__all__ = [
    # Simple logger (always available)
    'getLogger',
    'configure_console', 
    'shutdown_all_loggers',
    'SimpleLogLevel',
    
    # Complex logging (conditional)
    'LogType',
    'LogLevel',
    'HftLogger', 
    'get_logger',
    'configure_logging',
    'shutdown_logging',
    
    # Log structures (conditional)
    'TradeLogEntry',
    'SystemLogEntry',
    'PerformanceLogEntry', 
    'GeneralLogEntry',
    'LogMetadata',
    
    # Transport (conditional)  
    'ZeroMQTransport',
    'FileTransport',
    'CompositeTransport',
    
    # Correlation (conditional)
    'CorrelationManager',
    'generate_correlation_id',
    'get_current_correlation_id', 
    'set_correlation_context'
]