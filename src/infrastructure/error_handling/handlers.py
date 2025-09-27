"""
Composable Error Handler Implementation

High-performance error handling with composition patterns designed for HFT systems.
Eliminates nested try/catch complexity while maintaining sub-millisecond performance.
"""

from typing import TypeVar, Generic, Callable, Awaitable, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import random
from contextlib import asynccontextmanager

from infrastructure.logging.interfaces import HFTLoggerInterface
from infrastructure.logging import LoggingTimer
from infrastructure.exceptions.exchange import ExchangeRestError

T = TypeVar('T')
R = TypeVar('R')


class ErrorSeverity(Enum):
    """Error severity levels for routing and handling decisions."""
    CRITICAL = "critical"      # System shutdown required
    HIGH = "high"             # Component restart required  
    MEDIUM = "medium"         # Retry with backoff
    LOW = "low"               # Log and continue


@dataclass
class ErrorContext:
    """Context information for error handling operations."""
    operation: str
    component: str
    attempt: int = 1
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)
    
    # Callback hooks for specialized handling
    reconnect_callback: Optional[Callable[[], Awaitable[None]]] = None
    balance_refresh_callback: Optional[Callable[[], Awaitable[None]]] = None
    cleanup_callback: Optional[Callable[[], Awaitable[None]]] = None


class ComposableErrorHandler:
    """
    High-performance error handler with composition pattern.
    
    Designed for HFT systems with <0.5ms latency requirements.
    Uses pre-compiled mappings and cached handlers for optimal performance.
    """
    
    def __init__(self, logger: HFTLoggerInterface, max_retries: int = 3, base_delay: float = 1.0, component_name: str = None):
        self.logger = logger
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.component_name = component_name or self.__class__.__name__
        self._handlers: Dict[type, Callable] = {}
        self._fallback_handler = self._default_fallback
        
        # Performance optimization: pre-compile backoff values
        self._backoff_cache = {
            i: min(self.base_delay * (2 ** (i - 1)), self.base_delay * 10) for i in range(1, self.max_retries + 1)
        }
    
    def register_handler(self, exception_type: type, handler: Callable) -> None:
        """Register specific exception handlers for composition."""
        self._handlers[exception_type] = handler
    
    async def handle_with_retry(
        self, 
        operation: Callable[[], Awaitable[T]], 
        context: ErrorContext,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM
    ) -> Optional[T]:
        """
        Execute operation with automatic retry and error handling.
        
        Optimized for HFT performance with minimal object allocation.
        """
        with LoggingTimer(self.logger, f"{context.operation}_error_handling") as timer:
            for attempt in range(1, self.max_retries + 1):
                try:
                    context.attempt = attempt
                    result = await operation()
                    
                    # Log recovery if this was a retry
                    if attempt > 1:
                        self.logger.info("Operation recovered after retry",
                                       component=self.component_name,
                                       operation=context.operation,
                                       attempts=attempt,
                                       recovery_time_ms=timer.elapsed_ms)
                        
                        # Performance metric for recovery tracking
                        self.logger.metric("error_recovery_success", 1,
                                         tags={
                                             "component": self.component_name,
                                             "operation": context.operation,
                                             "attempts": str(attempt)
                                         })
                    
                    return result
                    
                except Exception as e:
                    # Auto-classify error severity if not explicitly provided
                    if severity == ErrorSeverity.MEDIUM:  # Default value
                        actual_severity = self._classify_error(e)
                    else:
                        actual_severity = severity
                    
                    await self._handle_exception(e, context, actual_severity, attempt)
                    
                    # Critical errors propagate immediately - no retries
                    if actual_severity == ErrorSeverity.CRITICAL:
                        # Track critical error metrics
                        self.logger.metric("critical_error_immediate_failure", 1,
                                         tags={
                                             "component": self.component_name,
                                             "operation": context.operation,
                                             "exception_type": type(e).__name__
                                         })
                        raise
                    
                    # Other errors return None after all retries exhausted
                    if attempt == self.max_retries:
                        # Non-critical errors return None after exhausting retries
                        self.logger.metric("error_handling_final_failure", 1,
                                         tags={
                                             "component": self.component_name,
                                             "severity": actual_severity.value,
                                             "exception_type": type(e).__name__
                                         })
                        return None
                        
                    # Apply backoff before retry
                    if attempt < self.max_retries:
                        backoff_time = self._calculate_backoff(attempt)
                        await asyncio.sleep(backoff_time)
            
            return None
    
    async def handle_single(
        self,
        operation: Callable[[], Awaitable[T]], 
        context: ErrorContext,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM
    ) -> Optional[T]:
        """
        Execute operation with single-attempt error handling (no retry).
        
        Optimized for high-frequency operations where retry is not appropriate.
        """
        try:
            context.attempt = 1
            return await operation()
            
        except Exception as e:
            # Auto-classify error severity
            actual_severity = self._classify_error(e) if severity == ErrorSeverity.MEDIUM else severity
            await self._handle_exception(e, context, actual_severity, 1)
            
            if actual_severity == ErrorSeverity.CRITICAL:
                raise
            
            return None
    
    async def _handle_exception(
        self, 
        exception: Exception, 
        context: ErrorContext,
        severity: ErrorSeverity,
        attempt: int
    ) -> None:
        """Route exception to appropriate handler with performance tracking."""
        exception_type = type(exception)
        
        # Track error occurrence metrics
        self.logger.metric("error_handled", 1,
                         tags={
                             "component": self.component_name,
                             "exception_type": exception_type.__name__,
                             "severity": severity.value,
                             "attempt": str(attempt)
                         })
        
        # Execute error context callbacks before handling
        await self._execute_error_context_callbacks(context, exception, attempt)
        
        # Route to specific handler if registered
        if exception_type in self._handlers:
            try:
                await self._handlers[exception_type](exception, context, severity)
            except Exception as handler_error:
                # Handler errors fall back to default handling
                await self._fallback_handler(handler_error, context, severity, attempt)
        else:
            await self._fallback_handler(exception, context, severity, attempt)
    
    async def _execute_error_context_callbacks(
        self, 
        context: ErrorContext, 
        exception: Exception, 
        attempt: int
    ) -> None:
        """Execute error context callbacks with error handling."""
        callbacks_to_execute = []
        
        # Determine which callbacks to execute based on error type
        error_type_name = type(exception).__name__.lower()
        
        if context.reconnect_callback and ("connection" in error_type_name or "websocket" in error_type_name):
            callbacks_to_execute.append(("reconnect", context.reconnect_callback))
            
        if context.balance_refresh_callback and ("insufficient" in error_type_name or "balance" in error_type_name):
            callbacks_to_execute.append(("balance_refresh", context.balance_refresh_callback))
            
        if context.cleanup_callback and attempt >= self.max_retries:
            callbacks_to_execute.append(("cleanup", context.cleanup_callback))
        
        # Execute callbacks with error handling
        for callback_name, callback in callbacks_to_execute:
            try:
                await callback()
                self.logger.debug(f"Executed {callback_name} callback successfully",
                                component=self.component_name,
                                operation=context.operation,
                                callback_type=callback_name)
            except Exception as callback_error:
                self.logger.error(f"Error executing {callback_name} callback",
                                component=self.component_name,
                                operation=context.operation,
                                callback_error=str(callback_error),
                                original_error=str(exception))

    def _classify_error(self, exception: Exception) -> ErrorSeverity:
        """Classify exception severity for retry logic."""
        exception_type = type(exception)
        error_message = str(exception).lower()
        
        # Critical errors - don't retry
        if isinstance(exception, (ValueError, TypeError)):
            return ErrorSeverity.CRITICAL
            
        if isinstance(exception, ExchangeRestError):
            # Check status codes for criticality
            if hasattr(exception, 'status_code'):
                if exception.status_code in [400, 401, 403, 404]:
                    return ErrorSeverity.CRITICAL
                elif exception.status_code in [429, 500, 502, 503]:
                    return ErrorSeverity.HIGH
            
            # Check error message content
            if any(term in error_message for term in ['invalid api key', 'insufficient', 'not found']):
                return ErrorSeverity.CRITICAL
        
        # High severity - retry with longer delays
        if "rate limit" in error_message or "too many requests" in error_message:
            return ErrorSeverity.HIGH
            
        # Medium severity - standard retry
        if isinstance(exception, (ConnectionError, TimeoutError)):
            return ErrorSeverity.MEDIUM
            
        # Default to medium for unknown errors
        return ErrorSeverity.MEDIUM

    def _calculate_backoff(self, attempt: int) -> float:
        """
        Calculate exponential backoff with jitter.
        
        Uses pre-computed cache for performance in hot paths.
        """
        base_delay = self._backoff_cache.get(attempt, 5.0)
        jitter = random.uniform(0.8, 1.2)
        return base_delay * jitter
    
    async def _default_fallback(
        self, 
        exception: Exception, 
        context: ErrorContext,
        severity: ErrorSeverity,
        attempt: int
    ) -> None:
        """Default error handling logic with structured logging."""
        error_data = {
            "component": self.component_name,
            "operation": context.operation,
            "exception_type": type(exception).__name__,
            "exception_message": str(exception),
            "attempt": attempt,
            "max_retries": self.max_retries,
            "severity": severity.value
        }
        
        # Include context metadata
        if context.metadata:
            error_data.update(context.metadata)
        
        # Log with appropriate level based on severity
        if severity == ErrorSeverity.CRITICAL:
            self.logger.error(f"CRITICAL: Operation failed: {context.operation}", **error_data)
        elif severity == ErrorSeverity.HIGH:
            self.logger.error(f"HIGH: Operation failed: {context.operation}", **error_data)
        elif severity == ErrorSeverity.MEDIUM:
            self.logger.warning(f"MEDIUM: Operation failed: {context.operation}", **error_data)
        else:  # LOW
            self.logger.debug(f"LOW: Operation failed: {context.operation}", **error_data)


# Context manager for guaranteed resource cleanup
@asynccontextmanager
async def managed_resource(
    resource_factory: Callable[[], Awaitable[T]],
    cleanup_func: Callable[[T], Awaitable[None]],
    logger: HFTLoggerInterface,
    component_name: str,
    operation_name: str = "resource_management"
):
    """
    Guaranteed resource cleanup with error handling.
    
    Ensures resources are properly cleaned up even in exception scenarios,
    preventing resource leaks in long-running HFT systems.
    """
    resource = None
    
    with LoggingTimer(logger, f"{operation_name}_resource_lifecycle") as timer:
        try:
            # Create resource
            resource = await resource_factory()
            
            logger.debug("Resource created successfully",
                        component=component_name,
                        operation=operation_name,
                        resource_type=type(resource).__name__)
            
            yield resource
            
        except Exception as e:
            logger.error("Resource operation failed",
                        component=component_name,
                        operation=operation_name,
                        exception_type=type(e).__name__,
                        exception_message=str(e),
                        resource_created=resource is not None)
            raise
            
        finally:
            # Guaranteed cleanup
            if resource:
                try:
                    await cleanup_func(resource)
                    
                    logger.debug("Resource cleaned up successfully",
                               component=component_name,
                               operation=operation_name,
                               total_time_ms=timer.elapsed_ms)
                    
                except Exception as cleanup_error:
                    # Cleanup errors are logged but don't propagate
                    logger.warning("Resource cleanup failed",
                                 component=component_name,
                                 operation=operation_name,
                                 cleanup_error=str(cleanup_error),
                                 cleanup_exception_type=type(cleanup_error).__name__)
                    
                    # Track cleanup failures for monitoring
                    logger.metric("resource_cleanup_failure", 1,
                                tags={
                                    "component": component_name,
                                    "operation": operation_name,
                                    "resource_type": type(resource).__name__
                                })