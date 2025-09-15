"""
HFT Logging Data Structures

msgspec-based structured logging for maximum performance and type safety.
All structures are designed for zero-copy serialization and HFT compliance.

Key Features:
- Frozen msgspec.Struct for zero-copy performance
- Microsecond timestamp precision for HFT timing
- Correlation IDs for distributed tracing
- Exchange-specific metadata fields
- Pre-validated enumerations for performance
"""

import time
from enum import IntEnum
from msgspec import Struct
from typing import Optional, Dict, Any, List

# Import existing structures for consistency
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from structs.exchange import Symbol, Side, OrderStatus, ExchangeName


class LogLevel(IntEnum):
    """Log levels optimized for HFT performance"""
    DEBUG = 1
    INFO = 2  
    WARN = 3
    ERROR = 4
    CRITICAL = 5


class LogType(IntEnum):
    """Logging categories for separated concerns"""
    TRADE = 1        # Trading operations, executions, P&L
    SYSTEM = 2       # System state, lifecycle, configuration  
    PERFORMANCE = 3  # Latency, throughput, resource usage
    GENERAL = 4      # Debugging, audit, development


class TradeOperation(IntEnum):
    """Trading operation types for structured logging"""
    ORDER_SUBMIT = 1
    ORDER_CANCEL = 2
    ORDER_MODIFY = 3
    TRADE_EXECUTION = 4
    POSITION_UPDATE = 5
    BALANCE_UPDATE = 6
    ARBITRAGE_OPPORTUNITY = 7
    ARBITRAGE_EXECUTION = 8
    PNL_CALCULATION = 9
    RISK_CHECK = 10


class SystemComponent(IntEnum):
    """System components for structured logging"""
    EXCHANGE_CLIENT = 1
    WEBSOCKET_CLIENT = 2
    REST_CLIENT = 3
    ORDER_MANAGER = 4
    POSITION_MANAGER = 5
    RISK_MANAGER = 6
    ARBITRAGE_ENGINE = 7
    CONFIG_MANAGER = 8
    RATE_LIMITER = 9
    CONNECTION_POOL = 10


class PerformanceOperation(IntEnum):
    """Performance monitoring operation types"""
    HTTP_REQUEST = 1
    WEBSOCKET_MESSAGE = 2
    ORDER_PROCESSING = 3
    ORDERBOOK_UPDATE = 4
    TRADE_PROCESSING = 5
    LATENCY_MEASUREMENT = 6
    THROUGHPUT_MEASUREMENT = 7
    MEMORY_USAGE = 8
    CPU_USAGE = 9
    NETWORK_IO = 10


class LogMetadata(Struct, frozen=True):
    """Common metadata for all log entries"""
    timestamp_us: int                    # Microsecond precision timestamp
    correlation_id: str                  # Distributed tracing ID
    exchange: Optional[ExchangeName] = None
    symbol: Optional[Symbol] = None
    session_id: Optional[str] = None     # Trading session identifier
    component: Optional[str] = None      # Source component name
    
    @classmethod
    def create(cls, 
               correlation_id: str,
               exchange: Optional[ExchangeName] = None,
               symbol: Optional[Symbol] = None,
               session_id: Optional[str] = None,
               component: Optional[str] = None) -> 'LogMetadata':
        """Create metadata with current timestamp"""
        return cls(
            timestamp_us=int(time.time_ns() // 1000),  # Microsecond precision
            correlation_id=correlation_id,
            exchange=exchange,
            symbol=symbol,
            session_id=session_id,
            component=component
        )


class TradeLogEntry(Struct, frozen=True):
    """
    Trade log entry for all trading operations.
    
    HFT CRITICAL: This structure is used in hot trading paths.
    Any changes must maintain zero-copy performance.
    """
    metadata: LogMetadata
    level: LogLevel
    operation: TradeOperation
    
    # Core trading data
    order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    side: Optional[Side] = None
    quantity: Optional[float] = None
    price: Optional[float] = None
    executed_quantity: Optional[float] = None
    executed_price: Optional[float] = None
    
    # Execution performance
    latency_us: Optional[int] = None     # Order-to-execution latency
    processing_time_us: Optional[int] = None
    
    # P&L and risk
    profit_loss_bps: Optional[float] = None  # Basis points
    commission_paid: Optional[float] = None
    slippage_bps: Optional[float] = None
    
    # Order status
    status: Optional[OrderStatus] = None
    fill_ratio: Optional[float] = None   # Percentage filled
    
    # Arbitrage specific
    counterparty_exchange: Optional[ExchangeName] = None
    spread_bps: Optional[float] = None
    opportunity_size: Optional[float] = None
    
    # Additional context
    message: Optional[str] = None
    error_code: Optional[str] = None
    additional_data: Optional[Dict[str, Any]] = None


class SystemLogEntry(Struct, frozen=True):
    """
    System log entry for application lifecycle and state changes.
    
    Used for monitoring system health, configuration changes,
    and component lifecycle management.
    """
    metadata: LogMetadata
    level: LogLevel
    component: SystemComponent
    
    # System state
    event_type: str                      # e.g., "startup", "shutdown", "config_change"
    message: str
    current_state: Optional[str] = None
    previous_state: Optional[str] = None
    
    # Configuration
    config_key: Optional[str] = None
    config_value: Optional[str] = None   # Sanitized for security
    
    # Connection status
    connection_status: Optional[str] = None
    endpoint: Optional[str] = None
    retry_count: Optional[int] = None
    
    # Resource usage
    memory_mb: Optional[float] = None
    cpu_percent: Optional[float] = None
    open_connections: Optional[int] = None
    
    # Error handling
    error_message: Optional[str] = None
    stack_trace: Optional[str] = None
    
    # Additional context
    additional_data: Optional[Dict[str, Any]] = None


class PerformanceLogEntry(Struct, frozen=True):
    """
    Performance log entry for latency and throughput monitoring.
    
    HFT CRITICAL: Used for sub-millisecond performance tracking.
    Optimized for high-frequency logging without performance impact.
    """
    metadata: LogMetadata
    operation: PerformanceOperation
    
    # Latency measurements (microseconds)
    latency_us: Optional[int] = None
    min_latency_us: Optional[int] = None
    max_latency_us: Optional[int] = None
    avg_latency_us: Optional[int] = None
    p95_latency_us: Optional[int] = None
    p99_latency_us: Optional[int] = None
    
    # Throughput measurements
    requests_per_second: Optional[float] = None
    bytes_per_second: Optional[float] = None
    messages_per_second: Optional[float] = None
    
    # Resource utilization
    cpu_percent: Optional[float] = None
    memory_mb: Optional[float] = None
    memory_percent: Optional[float] = None
    
    # Network performance
    network_bytes_in: Optional[int] = None
    network_bytes_out: Optional[int] = None
    packet_loss_percent: Optional[float] = None
    
    # Queue metrics  
    queue_depth: Optional[int] = None
    queue_processing_time_us: Optional[int] = None
    
    # Exchange-specific metrics
    rate_limit_remaining: Optional[int] = None
    api_weight_used: Optional[int] = None
    
    # Sample data for statistical analysis
    sample_count: Optional[int] = None
    sample_size: Optional[int] = None
    
    # Additional context
    details: Optional[Dict[str, Any]] = None


class GeneralLogEntry(Struct, frozen=True):
    """
    General purpose log entry for debugging and audit trails.
    
    Used for non-critical logging, development debugging,
    and audit requirements.
    """
    metadata: LogMetadata
    level: LogLevel
    
    # Core message
    message: str
    category: Optional[str] = None       # e.g., "audit", "debug", "business"
    
    # Source information
    module: Optional[str] = None
    function: Optional[str] = None
    line_number: Optional[int] = None
    
    # Error information
    exception_type: Optional[str] = None
    exception_message: Optional[str] = None
    stack_trace: Optional[str] = None
    
    # Business context
    user_id: Optional[str] = None
    api_endpoint: Optional[str] = None
    request_id: Optional[str] = None
    
    # Tags for filtering
    tags: Optional[List[str]] = None
    
    # Additional structured data
    data: Optional[Dict[str, Any]] = None


class LogBatch(Struct, frozen=True):
    """
    Batch of log entries for efficient transport.
    
    Used by ZeroMQ transport to send multiple log entries
    in a single message for improved performance.
    """
    batch_id: str
    batch_timestamp_us: int
    batch_size: int
    log_type: LogType
    
    # Union of all log entry types - only one will be populated
    trade_entries: Optional[List[TradeLogEntry]] = None
    system_entries: Optional[List[SystemLogEntry]] = None  
    performance_entries: Optional[List[PerformanceLogEntry]] = None
    general_entries: Optional[List[GeneralLogEntry]] = None
    
    @classmethod
    def create_trade_batch(cls, entries: List[TradeLogEntry], batch_id: str) -> 'LogBatch':
        """Create a batch of trade log entries"""
        return cls(
            batch_id=batch_id,
            batch_timestamp_us=int(time.time_ns() // 1000),
            batch_size=len(entries),
            log_type=LogType.TRADE,
            trade_entries=entries
        )
    
    @classmethod  
    def create_system_batch(cls, entries: List[SystemLogEntry], batch_id: str) -> 'LogBatch':
        """Create a batch of system log entries"""
        return cls(
            batch_id=batch_id,
            batch_timestamp_us=int(time.time_ns() // 1000),
            batch_size=len(entries),
            log_type=LogType.SYSTEM,
            system_entries=entries
        )
        
    @classmethod
    def create_performance_batch(cls, entries: List[PerformanceLogEntry], batch_id: str) -> 'LogBatch':
        """Create a batch of performance log entries"""
        return cls(
            batch_id=batch_id, 
            batch_timestamp_us=int(time.time_ns() // 1000),
            batch_size=len(entries),
            log_type=LogType.PERFORMANCE,
            performance_entries=entries
        )
        
    @classmethod
    def create_general_batch(cls, entries: List[GeneralLogEntry], batch_id: str) -> 'LogBatch':
        """Create a batch of general log entries"""
        return cls(
            batch_id=batch_id,
            batch_timestamp_us=int(time.time_ns() // 1000), 
            batch_size=len(entries),
            log_type=LogType.GENERAL,
            general_entries=entries
        )


class LogStatistics(Struct):
    """
    Runtime logging statistics for monitoring and optimization.
    
    Tracks logging performance and health metrics.
    """
    # Throughput metrics
    total_entries_logged: int = 0
    entries_per_second: float = 0.0
    bytes_per_second: float = 0.0
    
    # Performance metrics  
    avg_log_latency_us: float = 0.0
    max_log_latency_us: int = 0
    p99_log_latency_us: int = 0
    
    # Error metrics
    failed_entries: int = 0
    transport_errors: int = 0
    serialization_errors: int = 0
    
    # Resource usage
    memory_usage_mb: float = 0.0
    buffer_pool_utilization: float = 0.0
    
    # Queue metrics
    pending_entries: int = 0
    max_queue_depth: int = 0
    queue_overruns: int = 0
    
    # Transport metrics
    zmq_messages_sent: int = 0
    file_writes_completed: int = 0
    file_rotations: int = 0
    
    # Timing
    uptime_seconds: float = 0.0
    last_entry_timestamp_us: int = 0
    
    def reset(self) -> None:
        """Reset counters (useful for periodic reporting)"""
        self.total_entries_logged = 0
        self.entries_per_second = 0.0
        self.bytes_per_second = 0.0
        self.failed_entries = 0
        self.transport_errors = 0
        self.serialization_errors = 0
        self.pending_entries = 0
        self.queue_overruns = 0
        self.zmq_messages_sent = 0
        self.file_writes_completed = 0
        self.file_rotations = 0