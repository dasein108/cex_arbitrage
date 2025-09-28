"""
WebSocket Configuration Constants

Centralized configuration constants for WebSocket interfaces in the HFT trading system.
Provides performance tuning parameters, buffer sizes, and timing configurations
optimized for sub-millisecond trading operations.

Architecture compliance:
- HFT performance requirements
- Configurable parameters for different environments
- Type-safe constant definitions
- Clear separation of concerns by domain
"""

from typing import Final


# Performance and Buffer Configuration
class PerformanceConstants:
    """Constants for HFT performance optimization."""
    
    # Ring buffer sizes for different use cases
    DEFAULT_RING_BUFFER_SIZE: Final[int] = 1000
    LARGE_RING_BUFFER_SIZE: Final[int] = 5000  # For high-volume exchanges
    SMALL_RING_BUFFER_SIZE: Final[int] = 500   # For low-latency requirements
    
    # Time conversion constants
    MICROSECOND_MULTIPLIER: Final[int] = 1_000_000
    MILLISECOND_MULTIPLIER: Final[int] = 1_000
    
    # Performance monitoring intervals
    THROUGHPUT_WINDOW_SECONDS: Final[float] = 60.0
    METRICS_COLLECTION_INTERVAL_MS: Final[int] = 100
    
    # HFT latency targets (in microseconds)
    TARGET_MESSAGE_PROCESSING_LATENCY_US: Final[float] = 1000.0  # 1ms
    WARNING_MESSAGE_PROCESSING_LATENCY_US: Final[float] = 5000.0  # 5ms
    CRITICAL_MESSAGE_PROCESSING_LATENCY_US: Final[float] = 10000.0  # 10ms


class ConnectionConstants:
    """Constants for WebSocket connection management."""
    
    # Connection timeout settings
    CONNECTION_TIMEOUT_SECONDS: Final[int] = 10
    INITIALIZATION_TIMEOUT_SECONDS: Final[int] = 30
    CLOSE_TIMEOUT_SECONDS: Final[int] = 5
    
    # Retry and backoff configuration
    MAX_RECONNECTION_ATTEMPTS: Final[int] = 5
    INITIAL_RECONNECT_DELAY_SECONDS: Final[float] = 1.0
    MAX_RECONNECT_DELAY_SECONDS: Final[float] = 60.0
    RECONNECT_BACKOFF_MULTIPLIER: Final[float] = 2.0
    
    # Heartbeat and keepalive
    HEARTBEAT_INTERVAL_SECONDS: Final[int] = 30
    PING_INTERVAL_SECONDS: Final[int] = 20
    PONG_TIMEOUT_SECONDS: Final[int] = 10


class MessageConstants:
    """Constants for message processing and routing."""
    
    # Message batch processing
    MAX_MESSAGE_BATCH_SIZE: Final[int] = 100
    MESSAGE_QUEUE_SIZE: Final[int] = 10000
    
    # Message validation
    MAX_MESSAGE_SIZE_BYTES: Final[int] = 1024 * 1024  # 1MB
    MAX_SYMBOL_LENGTH: Final[int] = 20
    
    # Subscription management
    MAX_SYMBOLS_PER_SUBSCRIPTION: Final[int] = 100
    MAX_CHANNELS_PER_CONNECTION: Final[int] = 50


class DomainConstants:
    """Constants specific to public and private domains."""
    
    class Public:
        """Constants for public market data domain."""
        
        # Orderbook constants
        MAX_ORDERBOOK_LEVELS: Final[int] = 100
        ORDERBOOK_UPDATE_BATCH_SIZE: Final[int] = 50
        
        # Trade feed constants
        MAX_TRADES_PER_BATCH: Final[int] = 200
        TRADE_BUFFER_SIZE: Final[int] = 1000
        
        # Ticker update constants
        TICKER_UPDATE_INTERVAL_MS: Final[int] = 100
        BOOK_TICKER_UPDATE_INTERVAL_MS: Final[int] = 50
    
    class Private:
        """Constants for private trading operations domain."""
        
        # Order management constants
        MAX_PENDING_ORDERS: Final[int] = 1000
        ORDER_UPDATE_BATCH_SIZE: Final[int] = 100
        
        # Balance tracking constants
        BALANCE_UPDATE_DEBOUNCE_MS: Final[int] = 10
        MIN_BALANCE_CHANGE_THRESHOLD: Final[float] = 0.00000001  # 8 decimal places
        
        # Execution tracking constants
        EXECUTION_HISTORY_SIZE: Final[int] = 10000
        MAX_EXECUTIONS_PER_BATCH: Final[int] = 50


class LoggingConstants:
    """Constants for WebSocket logging configuration."""
    
    # Log level thresholds based on performance
    PERFORMANCE_DEBUG_THRESHOLD_US: Final[float] = 100.0  # 0.1ms
    PERFORMANCE_INFO_THRESHOLD_US: Final[float] = 1000.0  # 1ms
    PERFORMANCE_WARNING_THRESHOLD_US: Final[float] = 5000.0  # 5ms
    PERFORMANCE_ERROR_THRESHOLD_US: Final[float] = 10000.0  # 10ms
    
    # Batch logging for high-frequency events
    LOG_BATCH_SIZE: Final[int] = 100
    LOG_FLUSH_INTERVAL_MS: Final[int] = 1000
    
    # Metrics logging intervals
    METRICS_LOG_INTERVAL_SECONDS: Final[int] = 60
    PERFORMANCE_SUMMARY_INTERVAL_SECONDS: Final[int] = 300


class ExchangeSpecificConstants:
    """Exchange-specific configuration constants."""
    
    class MEXC:
        """MEXC-specific constants."""
        
        # Connection limits
        MAX_CONNECTIONS_PER_IP: Final[int] = 5
        MAX_SUBSCRIPTIONS_PER_CONNECTION: Final[int] = 200
        
        # Rate limiting
        SUBSCRIPTION_RATE_LIMIT_PER_SECOND: Final[int] = 10
        MESSAGE_RATE_LIMIT_PER_SECOND: Final[int] = 1000
        
        # Protocol buffer optimization
        PROTOBUF_BUFFER_SIZE: Final[int] = 64 * 1024  # 64KB


class MexcConstants:
    """MEXC WebSocket-specific configuration constants."""
    
    # Connection settings optimized for MEXC (minimal headers to avoid blocking)
    PING_INTERVAL_SECONDS: Final[int] = 30  # MEXC uses 30s ping interval
    PING_TIMEOUT_SECONDS: Final[int] = 15   # Increased timeout for stability
    MAX_QUEUE_SIZE: Final[int] = 512        # WebSocket queue size
    MAX_MESSAGE_SIZE: Final[int] = 1024 * 1024  # 1MB max message size
    WRITE_LIMIT: Final[int] = 2 ** 20       # 1MB write buffer
    
    # MEXC-specific error handling
    ERROR_1005_RESET_DELAY_SECONDS: Final[float] = 1.0  # Reset delay for 1005 errors
    MAX_1005_ERRORS_PER_HOUR: Final[int] = 10          # 1005 error threshold
    
    # Protocol Buffer settings
    PROTOBUF_ENABLED: Final[bool] = True
    PROTOBUF_FALLBACK_TO_JSON: Final[bool] = True
    
    # Subscription management
    MAX_SYMBOLS_PER_SUBSCRIPTION: Final[int] = 100
    SUBSCRIPTION_CONFIRMATION_TIMEOUT_SECONDS: Final[int] = 5
        
    class GATEIO:
        """Gate.io-specific constants."""
        
        # Connection limits
        MAX_CONNECTIONS_PER_IP: Final[int] = 10
        MAX_SUBSCRIPTIONS_PER_CONNECTION: Final[int] = 100
        
        # Rate limiting
        SUBSCRIPTION_RATE_LIMIT_PER_SECOND: Final[int] = 20
        MESSAGE_RATE_LIMIT_PER_SECOND: Final[int] = 2000
        
        # Futures-specific
        MAX_LEVERAGE: Final[int] = 100
        POSITION_UPDATE_INTERVAL_MS: Final[int] = 100


class ValidationConstants:
    """Constants for input validation and error handling."""
    
    # Symbol validation
    MIN_SYMBOL_LENGTH: Final[int] = 3
    MAX_SYMBOL_LENGTH: Final[int] = 20
    VALID_SYMBOL_PATTERN: Final[str] = r'^[A-Z0-9_]{3,20}$'
    
    # Numeric validation
    MAX_DECIMAL_PLACES: Final[int] = 8
    MIN_PRICE_VALUE: Final[float] = 0.00000001
    MAX_PRICE_VALUE: Final[float] = 1000000000.0
    
    # List validation
    MAX_SYMBOLS_LIST_SIZE: Final[int] = 1000
    MAX_CHANNELS_LIST_SIZE: Final[int] = 100
    
    # Error handling
    MAX_ERROR_MESSAGE_LENGTH: Final[int] = 500
    ERROR_CONTEXT_FIELDS_LIMIT: Final[int] = 20


# Convenience groupings for easy import
class HFTConstants:
    """High-level grouping of HFT-critical constants."""
    
    Performance = PerformanceConstants
    Connection = ConnectionConstants
    Message = MessageConstants
    Domain = DomainConstants
    Logging = LoggingConstants
    Validation = ValidationConstants


# Environment-specific overrides
class EnvironmentConstants:
    """Environment-specific constant overrides."""
    
    class Development:
        """Development environment overrides."""
        RING_BUFFER_SIZE = PerformanceConstants.SMALL_RING_BUFFER_SIZE
        CONNECTION_TIMEOUT_SECONDS = 5
        METRICS_LOG_INTERVAL_SECONDS = 10
    
    class Testing:
        """Testing environment overrides."""
        RING_BUFFER_SIZE = 100
        CONNECTION_TIMEOUT_SECONDS = 2
        METRICS_LOG_INTERVAL_SECONDS = 1
    
    class Production:
        """Production environment overrides."""
        RING_BUFFER_SIZE = PerformanceConstants.LARGE_RING_BUFFER_SIZE
        CONNECTION_TIMEOUT_SECONDS = ConnectionConstants.CONNECTION_TIMEOUT_SECONDS
        METRICS_LOG_INTERVAL_SECONDS = LoggingConstants.METRICS_LOG_INTERVAL_SECONDS