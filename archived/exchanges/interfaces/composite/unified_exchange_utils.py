"""
Utility functions extracted from UnifiedCompositeExchange for code reuse.

This module contains safe-to-extract utility functions that don't affect HFT performance
but reduce code duplication across exchange implementations.
"""

import time
from typing import Dict, Any, Optional
from infrastructure.logging import HFTLoggerInterface


# Performance tracking configuration constants
class HFTPerformanceConfig:
    """Configuration constants for HFT performance tracking."""
    
    # Performance logging intervals
    OPERATION_LOGGING_INTERVAL = 1000  # Log every N operations to avoid spam
    
    # HFT compliance thresholds
    MIN_OPERATIONS_PER_SECOND = 20.0   # Minimum ops/sec for HFT compliance
    MAX_ERROR_RATE = 0.01              # Maximum error rate for HFT compliance
    
    # Performance limits
    COUNTER_RESET_THRESHOLD = 1_000_000  # Reset counters to prevent overflow


class ExchangePerformanceTracker:
    """
    Extracted performance tracking utilities from UnifiedCompositeExchange.
    
    Provides consistent performance monitoring across all exchange implementations
    without affecting critical trading paths.
    """
    
    def __init__(self, logger: HFTLoggerInterface):
        self.logger = logger
        self._operation_count = 0
        self._last_operation_time = 0.0
        self._start_time = time.perf_counter()
    
    def track_operation(self, operation_name: str) -> None:
        """Track operation for performance monitoring."""
        self._operation_count += 1
        self._last_operation_time = time.perf_counter()
        
        # Reset counter to prevent overflow after extended operation
        if self._operation_count >= HFTPerformanceConfig.COUNTER_RESET_THRESHOLD:
            self.logger.info("Performance counter reset", 
                           previous_count=self._operation_count,
                           operation=operation_name)
            self._operation_count = 0
            self._start_time = self._last_operation_time
        
        # Log every N operations to avoid spam
        if self._operation_count % HFTPerformanceConfig.OPERATION_LOGGING_INTERVAL == 0:
            self.logger.debug("Performance checkpoint",
                            operation=operation_name,
                            total_operations=self._operation_count,
                            uptime_seconds=self._last_operation_time - self._start_time)
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary for monitoring."""
        uptime = self._last_operation_time - self._start_time if self._last_operation_time > 0 else 0
        
        return {
            "total_operations": self._operation_count,
            "operations_per_second": self._operation_count / uptime if uptime > 0 else 0,
            "uptime_seconds": uptime,
            "last_operation_time": self._last_operation_time
        }


class ExchangeConnectionValidator:
    """
    Extracted connection validation utilities from UnifiedCompositeExchange.
    
    Provides consistent connection validation logic across all exchange implementations.
    """
    
    @staticmethod
    def validate_public_connections(public_rest_connected: bool, 
                                   public_ws_connected: bool,
                                   require_websocket: bool = True) -> bool:
        """Validate public connections."""
        if require_websocket:
            return public_rest_connected and public_ws_connected
        return public_rest_connected
    
    @staticmethod
    def validate_private_connections(private_rest_connected: bool,
                                    private_ws_connected: bool,
                                    has_credentials: bool,
                                    require_websocket: bool = True) -> bool:
        """Validate private connections."""
        if not has_credentials:
            return True  # Private connections not required
            
        if require_websocket:
            return private_rest_connected and private_ws_connected
        return private_rest_connected
    
    @staticmethod 
    def validate_all_connections(public_rest: bool, public_ws: bool,
                                private_rest: bool, private_ws: bool,
                                has_credentials: bool,
                                require_websocket: bool = True) -> bool:
        """Validate all connections based on requirements."""
        public_valid = ExchangeConnectionValidator.validate_public_connections(
            public_rest, public_ws, require_websocket)
        
        private_valid = ExchangeConnectionValidator.validate_private_connections(
            private_rest, private_ws, has_credentials, require_websocket)
        
        return public_valid and private_valid


class ExchangeErrorHandler:
    """
    Extracted error handling patterns from UnifiedCompositeExchange.
    
    Provides consistent error handling, logging, and recovery strategies 
    across all exchange implementations.
    """
    
    # Recoverable error types that can trigger automatic recovery
    RECOVERABLE_CONNECTION_ERRORS = {
        'ConnectionError', 'TimeoutError', 'OSError', 
        'ConnectionResetError', 'ConnectionAbortedError'
    }
    
    RECOVERABLE_API_ERRORS = {
        'HTTPError', 'RequestException', 'ReadTimeoutError'
    }
    
    def __init__(self, logger: HFTLoggerInterface, exchange_name: str):
        self.logger = logger
        self.exchange_name = exchange_name
        self._error_count = 0
        self._last_error_time = 0.0
    
    def handle_connection_error(self, error: Exception, connection_type: str) -> bool:
        """
        Handle connection errors with consistent logging and recovery classification.
        
        Returns:
            True if error is recoverable and reconnection should be attempted
        """
        self._track_error()
        error_type = type(error).__name__
        is_recoverable = error_type in self.RECOVERABLE_CONNECTION_ERRORS
        
        self.logger.error("Connection error occurred",
                         exchange=self.exchange_name,
                         connection_type=connection_type,
                         error_type=error_type,
                         error_message=str(error),
                         is_recoverable=is_recoverable)
        
        return is_recoverable
    
    def handle_initialization_error(self, error: Exception, context: str) -> bool:
        """
        Handle initialization errors with consistent logging and recovery classification.
        
        Returns:
            True if error is recoverable and initialization should be retried
        """
        self._track_error()
        error_type = type(error).__name__
        is_recoverable = (error_type in self.RECOVERABLE_CONNECTION_ERRORS or 
                         error_type in self.RECOVERABLE_API_ERRORS)
        
        self.logger.error("Initialization error occurred",
                         exchange=self.exchange_name,
                         context=context,
                         error_type=error_type,
                         error_message=str(error),
                         is_recoverable=is_recoverable)
        
        return is_recoverable
    
    def handle_operation_error(self, error: Exception, operation: str, **kwargs) -> bool:
        """
        Handle operation errors with consistent logging and recovery classification.
        
        Returns:
            True if error is recoverable and operation should be retried
        """
        self._track_error()
        error_type = type(error).__name__
        is_recoverable = error_type in self.RECOVERABLE_API_ERRORS
        
        self.logger.error("Operation error occurred",
                         exchange=self.exchange_name,
                         operation=operation,
                         error_type=error_type,
                         error_message=str(error),
                         is_recoverable=is_recoverable,
                         **kwargs)
        
        return is_recoverable
    
    def handle_websocket_error(self, error: Exception, ws_type: str, **kwargs) -> bool:
        """
        Handle WebSocket errors with consistent logging and recovery classification.
        
        Returns:
            True if error is recoverable and WebSocket should be reconnected
        """
        self._track_error()
        error_type = type(error).__name__
        is_recoverable = error_type in self.RECOVERABLE_CONNECTION_ERRORS
        
        self.logger.error("WebSocket error occurred",
                         exchange=self.exchange_name,
                         websocket_type=ws_type,
                         error_type=error_type,
                         error_message=str(error),
                         is_recoverable=is_recoverable,
                         **kwargs)
        
        return is_recoverable
    
    def _track_error(self) -> None:
        """Track error occurrence for monitoring."""
        self._error_count += 1
        self._last_error_time = time.perf_counter()
    
    def get_error_summary(self) -> Dict[str, Any]:
        """Get error statistics for monitoring."""
        return {
            "total_errors": self._error_count,
            "last_error_time": self._last_error_time,
            "exchange": self.exchange_name
        }


def create_health_status_base(exchange_name: str, 
                             is_connected: bool,
                             is_initialized: bool) -> Dict[str, Any]:
    """
    Create base health status dictionary.
    
    Extracted common health status creation logic to reduce duplication.
    """
    return {
        "exchange": exchange_name,
        "timestamp": time.time(),
        "overall_status": "healthy" if (is_connected and is_initialized) else "unhealthy",
        "connected": is_connected,
        "initialized": is_initialized,
        "components": {}
    }


def calculate_connection_uptime(start_time: float, 
                               current_connected: bool) -> Optional[float]:
    """
    Calculate connection uptime in seconds.
    
    Args:
        start_time: When the connection was established
        current_connected: Whether currently connected
        
    Returns:
        Uptime in seconds or None if not connected
    """
    if not current_connected or start_time <= 0:
        return None
    
    return time.perf_counter() - start_time


def format_performance_metrics(total_operations: int,
                              uptime_seconds: float,
                              error_count: int = 0) -> Dict[str, Any]:
    """
    Format performance metrics consistently.
    
    Args:
        total_operations: Total operations performed
        uptime_seconds: System uptime in seconds  
        error_count: Number of errors encountered
        
    Returns:
        Formatted performance metrics
    """
    ops_per_second = total_operations / uptime_seconds if uptime_seconds > 0 else 0
    error_rate = error_count / total_operations if total_operations > 0 else 0
    
    return {
        "total_operations": total_operations,
        "operations_per_second": round(ops_per_second, 2),
        "uptime_seconds": round(uptime_seconds, 2),
        "error_count": error_count,
        "error_rate": round(error_rate, 4),
        "hft_compliant": (ops_per_second > HFTPerformanceConfig.MIN_OPERATIONS_PER_SECOND and 
                         error_rate < HFTPerformanceConfig.MAX_ERROR_RATE)
    }


class InitializationHelper:
    """
    Extracted initialization utilities to reduce code duplication.
    
    Provides safe initialization patterns that don't affect HFT performance.
    """
    
    def __init__(self, logger: HFTLoggerInterface, exchange_name: str):
        self.logger = logger
        self.exchange_name = exchange_name
    
    async def safe_initialize_client(self, client_type: str, factory_method, *args, **kwargs):
        """
        Safely initialize a client with consistent error handling.
        
        Args:
            client_type: Type of client being initialized (for logging)
            factory_method: Method to call for client creation
            *args, **kwargs: Arguments for factory method
            
        Returns:
            Initialized client or None on failure
        """
        try:
            self.logger.debug(f"Creating {client_type} client", exchange=self.exchange_name)
            client = await factory_method(*args, **kwargs)
            
            if client:
                self.logger.info(f"{client_type} client created successfully", 
                               exchange=self.exchange_name)
                return client
            else:
                self.logger.warning(f"{client_type} client creation returned None",
                                  exchange=self.exchange_name)
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to create {client_type} client",
                            exchange=self.exchange_name,
                            error_type=type(e).__name__,
                            error_message=str(e))
            return None
    
    async def safe_initialize_data(self, data_type: str, load_method, *args, **kwargs):
        """
        Safely initialize data with consistent error handling.
        
        Args:
            data_type: Type of data being loaded (for logging)
            load_method: Method to call for data loading
            *args, **kwargs: Arguments for load method
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.logger.debug(f"Loading {data_type}", exchange=self.exchange_name)
            await load_method(*args, **kwargs)
            self.logger.info(f"{data_type} loaded successfully", 
                           exchange=self.exchange_name)
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load {data_type}",
                            exchange=self.exchange_name,
                            error_type=type(e).__name__,
                            error_message=str(e))
            return False