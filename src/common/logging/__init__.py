"""
HFT Logging Architecture

Ultra-high-performance logging system designed for sub-50ms trading operations.
Provides structured logging with zero-overhead in critical trading paths.

Key Features:
- Four-tier logging separation (trade, system, performance, general)  
- Zero-copy msgspec serialization for maximum performance
- ZeroMQ async transport to separate logging infrastructure
- Memory-mapped files with intelligent rotation
- Prometheus metrics integration
- Correlation IDs for distributed tracing

Usage:
    from common.logging import get_logger, LogLevel, LogType
    
    # Get specialized loggers
    trade_logger = get_logger(LogType.TRADE)
    perf_logger = get_logger(LogType.PERFORMANCE)
    
    # High-frequency trading operations
    await trade_logger.log_trade_execution(
        symbol="BTC_USDT",
        side=Side.BUY,
        quantity=1.0,
        price=50000.0,
        latency_us=1200,
        exchange="MEXC",
        profit_bps=25.4
    )
    
    # Performance monitoring
    await perf_logger.log_latency(
        operation="orderbook_update",
        latency_us=850,
        exchange="GATEIO"
    )
"""

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

__all__ = [
    # Core logging
    'LogType',
    'LogLevel',
    'HftLogger', 
    'get_logger',
    'configure_logging',
    'shutdown_logging',
    
    # Log structures
    'TradeLogEntry',
    'SystemLogEntry',
    'PerformanceLogEntry', 
    'GeneralLogEntry',
    'LogMetadata',
    
    # Transport
    'ZeroMQTransport',
    'FileTransport',
    'CompositeTransport',
    
    # Correlation
    'CorrelationManager',
    'generate_correlation_id',
    'get_current_correlation_id', 
    'set_correlation_context'
]