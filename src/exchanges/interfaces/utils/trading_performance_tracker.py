"""
Trading Performance Tracker

Centralizes performance metrics and timing utilities for trading operations.
Eliminates code duplication across exchange implementations while providing
consistent performance tracking and error handling patterns.

HFT COMPLIANCE: Sub-millisecond overhead, efficient metrics collection.
"""

from typing import Dict, Any, Optional, Callable, TypeVar, Awaitable, List
import time
from functools import wraps
import asyncio
from collections import deque, defaultdict

from infrastructure.logging import HFTLoggerInterface
from infrastructure.exceptions.exchange import ExchangeRestError

T = TypeVar('T')


class TradingPerformanceTracker:
    """
    Tracks performance metrics and provides timing utilities for trading operations.
    
    Handles operation counting, timing, error tracking, and metric logging
    in a consistent manner across all exchange implementations.
    
    Features:
    - Sub-millisecond performance tracking
    - Operation success/failure metrics
    - Automatic error handling and logging
    - Performance statistics aggregation
    - HFT-compliant minimal overhead
    """
    
    def __init__(self, logger: HFTLoggerInterface, exchange_name: str):
        """
        Initialize performance tracker for specific exchange.
        
        Args:
            logger: HFT logger instance for metrics and logging
            exchange_name: Name of exchange for tagging metrics
        """
        self.logger = logger
        self.exchange_name = exchange_name
        
        # Operation counters
        self._trading_operations = 0
        self._successful_operations = 0
        self._failed_operations = 0
        
        # Performance metrics storage (using deque for O(1) operations)
        self._operation_times: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=self._max_stored_times)
        )
        self._error_counts: Dict[str, int] = defaultdict(int)
        
        # Configuration
        self._max_stored_times = 1000  # Keep recent measurements for averaging
        
        self.logger.debug("TradingPerformanceTracker initialized",
                         exchange=exchange_name)
    
    async def track_operation(self, 
                            operation_name: str, 
                            operation_func: Callable[[], Awaitable[T]],
                            log_success: bool = True,
                            log_errors: bool = True,
                            raise_on_error: bool = True) -> T:
        """
        Track timing and performance for a trading operation.
        
        Args:
            operation_name: Name of the operation for logging/metrics
            operation_func: Async function to execute and track
            log_success: Whether to log successful operations
            log_errors: Whether to log failed operations  
            raise_on_error: Whether to re-raise exceptions
            
        Returns:
            Result from operation_func
            
        Raises:
            BaseExchangeError: If operation fails and raise_on_error=True
        """
        start_time = time.perf_counter()
        self._trading_operations += 1
        
        try:
            # Execute the operation
            result = await operation_func()
            
            # Calculate execution time
            execution_time_ms = (time.perf_counter() - start_time) * 1000
            
            # Track success
            self._successful_operations += 1
            self._record_operation_time(operation_name, execution_time_ms)
            
            # Log success if enabled
            if log_success:
                self.logger.debug(f"{operation_name} completed successfully",
                                exchange=self.exchange_name,
                                operation=operation_name,
                                execution_time_ms=round(execution_time_ms, 2))
            
            # Record performance metrics
            self.logger.metric("trading_operation_duration_ms", execution_time_ms,
                             tags={
                                 "exchange": self.exchange_name,
                                 "operation": operation_name,
                                 "status": "success"
                             })
            
            return result
            
        except Exception as e:
            # Calculate execution time for failed operation
            execution_time_ms = (time.perf_counter() - start_time) * 1000
            
            # Track failure
            self._failed_operations += 1
            self._record_operation_error(operation_name)
            
            # Log error if enabled
            if log_errors:
                self.logger.error(f"{operation_name} failed",
                                exchange=self.exchange_name,
                                operation=operation_name,
                                execution_time_ms=round(execution_time_ms, 2),
                                error=str(e),
                                error_type=type(e).__name__)
            
            # Record error metrics
            self.logger.metric("trading_operation_duration_ms", execution_time_ms,
                             tags={
                                 "exchange": self.exchange_name,
                                 "operation": operation_name,
                                 "status": "error"
                             })
            
            self.logger.metric("trading_operation_errors", 1,
                             tags={
                                 "exchange": self.exchange_name,
                                 "operation": operation_name,
                                 "error_type": type(e).__name__
                             })
            
            # Re-raise as BaseExchangeError if requested, otherwise re-raise original
            if raise_on_error:
                raise ExchangeRestError(f"{operation_name} failed: {e}") from e
            else:
                raise
    
    def _record_operation_time(self, operation_name: str, execution_time_ms: float) -> None:
        """Record execution time for operation (O(1) with deque)."""
        # deque with maxlen automatically handles size management
        self._operation_times[operation_name].append(execution_time_ms)
    
    def _record_operation_error(self, operation_name: str) -> None:
        """Record error count for operation."""
        self._error_counts[operation_name] += 1
    
    def get_operation_stats(self, operation_name: str) -> Dict[str, Any]:
        """Get performance statistics for specific operation."""
        times = list(self._operation_times.get(operation_name, deque()))  # Convert deque to list for calculations
        error_count = self._error_counts.get(operation_name, 0)
        
        if not times:
            return {
                "operation": operation_name,
                "total_executions": error_count,
                "successful_executions": 0,
                "error_count": error_count,
                "error_rate": 1.0 if error_count > 0 else 0.0,
                "avg_execution_time_ms": None,
                "min_execution_time_ms": None,
                "max_execution_time_ms": None
            }
        
        successful_executions = len(times)
        total_executions = successful_executions + error_count
        
        return {
            "operation": operation_name,
            "total_executions": total_executions,
            "successful_executions": successful_executions,
            "error_count": error_count,
            "error_rate": error_count / total_executions if total_executions > 0 else 0.0,
            "avg_execution_time_ms": sum(times) / len(times),
            "min_execution_time_ms": min(times),
            "max_execution_time_ms": max(times),
            "p95_execution_time_ms": sorted(times)[int(len(times) * 0.95)] if len(times) >= 20 else None
        }
    
    def get_overall_stats(self) -> Dict[str, Any]:
        """Get overall performance statistics."""
        return {
            "exchange": self.exchange_name,
            "total_operations": self._trading_operations,
            "successful_operations": self._successful_operations,
            "failed_operations": self._failed_operations,
            "overall_success_rate": (
                self._successful_operations / self._trading_operations 
                if self._trading_operations > 0 else 0.0
            ),
            "operations_tracked": list(self._operation_times.keys()),
            "operations_with_errors": list(self._error_counts.keys())
        }
    
    @property
    def trading_operations_count(self) -> int:
        """Get total trading operations count."""
        return self._trading_operations