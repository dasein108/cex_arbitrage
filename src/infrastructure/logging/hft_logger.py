"""
High-Performance HFT Logger Implementation

Main logger with async dispatch, ring buffer, and zero-blocking operations.
Designed for sub-100μs call latency in HFT trading systems.

HFT COMPLIANT: No blocking operations, minimal allocation overhead.
"""

import asyncio
import logging
import os
import time
from typing import Dict, List, Optional, Any, Union
import weakref

from common.ring_buffer import RingBuffer
from .interfaces import (
    HFTLoggerInterface, LogBackend, LogRouter, LogRecord, 
    LogLevel, LogType, PerformanceMonitor
)
from .structs import PerformanceConfig


class HFTLogger(HFTLoggerInterface):
    """
    High-performance logger with async dispatch and multiple backends.
    
    Key features:
    - Zero blocking on log calls
    - Ring buffer for message queuing  
    - Async dispatch to backends
    - Context management
    - Performance monitoring
    - Python logging compatibility
    """
    
    # Class-level registry for cleanup
    _instances = weakref.WeakSet()
    _global_shutdown = False
    
    def __init__(self, name: str, backends: List[LogBackend], router: LogRouter, config: PerformanceConfig):
        """
        Initialize HFT logger with struct configuration.
        
        Args:
            name: Logger name
            backends: List of backend instances
            router: Router for message routing
            config: PerformanceConfig struct (required)
        """
        if not isinstance(config, PerformanceConfig):
            raise TypeError(f"Expected PerformanceConfig, got {type(config)}")
        
        self.name = name
        self.backends = backends
        self.router = router
        self.perf_config = config
        
        # Configuration from struct
        self.batch_size = config.batch_size
        buffer_size = config.buffer_size
        self.dispatch_interval = config.dispatch_interval
        self.max_queue_size = config.max_queue_size
        self.enable_sampling = config.enable_sampling
        self.sampling_rate = config.sampling_rate
        
        # Persistent context for all log messages
        self.context = {}
        
        # Ring buffer for async dispatch
        self._buffer = RingBuffer[LogRecord](buffer_size)
        
        # Performance monitoring
        self._perf_monitor = PerformanceMonitor()
        
        # Async dispatch task (will be created when needed)
        self._dispatch_task: Optional[asyncio.Task] = None
        self._shutdown_event: Optional[asyncio.Event] = None
        self._task_started = False
        
        # Python logging compatibility
        self._py_logger = logging.getLogger(name)
        
        # Set propagate=True by default in DEV environment for easier debugging
        environment = os.getenv('ENVIRONMENT', 'dev').lower()
        if environment in ('dev', 'development', 'local', 'test'):
            self._py_logger.propagate = True
        
        # Register for cleanup
        HFTLogger._instances.add(self)
    
    def _convert_level_to_python(self, level: LogLevel) -> int:
        """Convert HFT LogLevel to Python logging level."""
        mapping = {
            LogLevel.DEBUG: logging.DEBUG,
            LogLevel.INFO: logging.INFO,
            LogLevel.WARNING: logging.WARNING,
            LogLevel.ERROR: logging.ERROR,
            LogLevel.CRITICAL: logging.CRITICAL
        }
        return mapping.get(level, logging.INFO)
    
    @property
    def propagate(self) -> bool:
        """Get propagation setting from underlying Python logger."""
        return self._py_logger.propagate

    @propagate.setter  
    def propagate(self, value: bool) -> None:
        """Set propagation on underlying Python logger."""
        self._py_logger.propagate = value
    
    def _start_dispatch_task(self) -> None:
        """Start the async dispatch task if event loop is available."""
        if self._task_started:
            return
            
        try:
            # Only start if there's a running event loop
            loop = asyncio.get_running_loop()
            if self._shutdown_event is None:
                self._shutdown_event = asyncio.Event()
            if self._dispatch_task is None or self._dispatch_task.done():
                self._dispatch_task = loop.create_task(self._dispatch_loop())
                self._task_started = True
        except RuntimeError:
            # No event loop running - task will be started on first log
            pass
    
    async def _dispatch_loop(self) -> None:
        """
        Background task to dispatch log messages to backends.
        
        Runs continuously, processing batches of messages.
        """
        try:
            while self._shutdown_event is None or not self._shutdown_event.is_set():
                # Get batch of messages
                batch = self._buffer.get_batch(self.batch_size)
                
                if batch:
                    # Process batch
                    await self._process_batch(batch)
                else:
                    # No messages, wait briefly
                    await asyncio.sleep(0.001)  # 1ms
                    
        except asyncio.CancelledError:
            # Clean shutdown
            pass
        except Exception as e:
            # Log error and continue (logging must not fail)
            print(f"HFTLogger dispatch error: {e}")
            await asyncio.sleep(0.1)  # Prevent tight error loop
    
    async def _process_batch(self, batch: List[LogRecord]) -> None:
        """Process a batch of log records."""
        # Group records by backend to minimize context switching
        backend_batches: Dict[LogBackend, List[LogRecord]] = {}
        
        for record in batch:
            # Get matching backends for this record
            matching_backends = self.router.get_backends(record)
            
            for backend in matching_backends:
                if backend.enabled and backend.should_handle(record):
                    if backend not in backend_batches:
                        backend_batches[backend] = []
                    backend_batches[backend].append(record)
        
        # Dispatch to backends concurrently
        if backend_batches:
            tasks = []
            for backend, records in backend_batches.items():
                for record in records:
                    tasks.append(self._safe_write_to_backend(backend, record))
            
            # Wait for all writes to complete
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _safe_write_to_backend(self, backend: LogBackend, record: LogRecord) -> None:
        """Safely write to backend with error handling."""
        try:
            await backend.write(record)
        except Exception as e:
            # Backend error - handle gracefully
            backend._handle_error(e)
    
    def _sync_dispatch_immediate(self, record: LogRecord) -> None:
        """
        Synchronous dispatch for environments without event loop.
        Used for simple scripts and testing.
        """
        # Route the message
        backends = self.router.get_backends(record)
        
        # Write to each backend synchronously  
        for backend in backends:
            if backend.should_handle(record):
                try:
                    # Convert async write to sync using backend's sync method if available
                    # or just skip if backend requires async
                    import inspect
                    if hasattr(backend, 'write_sync'):
                        backend.write_sync(record)

                except Exception as e:
                    # Silently ignore backend errors in sync mode
                    pass
    
    def _log(self, level: LogLevel, msg: str, log_type: LogType = LogType.TEXT, **context) -> None:
        """
        Core logging method with performance monitoring.
        
        Zero blocking - just creates record and adds to buffer.
        """
        start_time = time.perf_counter()
        
        try:
            # Merge persistent context with call context
            full_context = {**self.context, **context}
            
            # Extract correlation info from context
            correlation_id = full_context.pop('correlation_id', None)
            exchange = full_context.pop('exchange', None) 
            symbol = full_context.pop('symbol', None)
            
            # Create log record using factory method (includes stack trace for ERROR+)
            if log_type == LogType.TEXT:
                record = LogRecord.create_text(level, self.name, msg, **full_context)
                # Update correlation fields
                record.correlation_id = correlation_id
                record.exchange = exchange
                record.symbol = symbol
            else:
                # For non-text records (metrics, audit), use direct constructor
                record = LogRecord(
                    timestamp=time.time(),
                    level=level,
                    log_type=log_type,
                    logger_name=self.name,
                    message=msg,
                    context=full_context,
                    correlation_id=correlation_id,
                    exchange=exchange,
                    symbol=symbol
                )
            
            # Immediate propagation for errors/critical (real-time requirement)
            immediate_propagated = False
            if level.value >= LogLevel.WARNING.value and self._py_logger.propagate:
                py_level = self._convert_level_to_python(level)
                extra = f"\r\n{str(full_context)}" if full_context else ""
                self._py_logger.log(py_level, str(msg) + extra)
                immediate_propagated = True
            
            # Add to buffer only if not immediately propagated to avoid double logging
            if not immediate_propagated:
                if not self._buffer.put_nowait(record):
                    # Buffer full - this is a problem but don't block
                    print(f"HFTLogger buffer full, dropped message: {msg[:50]}")
            
            # Ensure dispatch task is running (async) or dispatch synchronously
            if not immediate_propagated and (not self._task_started or self._dispatch_task is None or self._dispatch_task.done()):
                self._start_dispatch_task()
                
                # If no async task started, dispatch synchronously for simple scripts
                if not self._task_started:
                    self._sync_dispatch_immediate(record)
            
        finally:
            # Record performance
            latency_us = (time.perf_counter() - start_time) * 1_000_000
            self._perf_monitor.record_call(latency_us)
    
    # Standard logging methods
    def debug(self, msg: str, **context) -> None:
        """Log debug message."""
        self._log(LogLevel.DEBUG, msg, **context)
    
    def info(self, msg: str, **context) -> None:
        """Log info message."""
        self._log(LogLevel.INFO, msg, **context)
    
    def warning(self, msg: str, **context) -> None:
        """Log warning message."""
        self._log(LogLevel.WARNING, msg, **context)
    
    def error(self, msg: str, **context) -> None:
        """Log error message."""
        self._log(LogLevel.ERROR, msg, **context)
    
    def critical(self, msg: str, **context) -> None:
        """Log critical message."""
        self._log(LogLevel.CRITICAL, msg, **context)
    
    # HFT-specific methods
    def metric(self, name: str, value: float, **tags) -> None:
        """Log metric value."""
        start_time = time.perf_counter()
        
        try:
            # Merge persistent context with tags
            full_tags = {**self.context, **tags}
            
            # Extract correlation info
            correlation_id = full_tags.pop('correlation_id', None)
            exchange = full_tags.pop('exchange', None)
            symbol = full_tags.pop('symbol', None)
            
            # Create metric record
            record = LogRecord(
                timestamp=time.time(),
                level=LogLevel.INFO,
                log_type=LogType.METRIC,
                logger_name=self.name,
                message="",
                metric_name=name,
                metric_value=value,
                metric_tags=full_tags,
                correlation_id=correlation_id,
                exchange=exchange,
                symbol=symbol
            )
            
            # Add to buffer
            if not self._buffer.put_nowait(record):
                print(f"HFTLogger buffer full, dropped metric: {name}={value}")
            
            # Ensure dispatch task is running
            if self._dispatch_task is None or self._dispatch_task.done():
                self._start_dispatch_task()
                
        finally:
            # Record performance
            latency_us = (time.perf_counter() - start_time) * 1_000_000
            self._perf_monitor.record_call(latency_us)
    
    def latency(self, operation: str, duration_ms: float, **tags) -> None:
        """Log latency metric."""
        self.metric(f"{operation}_latency_ms", duration_ms, **tags)
    
    def counter(self, name: str, value: int = 1, **tags) -> None:
        """Log counter metric."""
        self.metric(f"{name}_count", float(value), **tags)
    
    def audit(self, event: str, **context) -> None:
        """Log audit event."""
        self._log(LogLevel.INFO, event, LogType.AUDIT, **context)
    
    def set_context(self, **context) -> None:
        """Set persistent context for all logs."""
        self.context.update(context)
    
    async def flush(self) -> None:
        """Flush all backends."""
        # Process any remaining messages
        remaining = self._buffer.get_batch(self._buffer.size())
        if remaining:
            await self._process_batch(remaining)
        
        # Flush all backends
        for backend in self.backends:
            try:
                await backend.flush()
            except Exception as e:
                print(f"Backend {backend.name} flush error: {e}")
    
    # Python logging compatibility
    def isEnabledFor(self, level: int) -> bool:
        """Check if logging is enabled for level."""
        # Convert Python logging level to our LogLevel
        our_level = self._convert_py_level(level)
        # For simplicity, assume all levels are enabled
        # Filtering happens in backends
        return True
    
    def log(self, level: int, msg: str, *args, **kwargs) -> None:
        """Generic log method for Python logging compatibility."""
        # Convert Python logging level
        our_level = self._convert_py_level(level)
        
        # Format message if args provided
        if args:
            try:
                msg = msg % args
            except (TypeError, ValueError):
                # Formatting failed, use original message
                pass
        
        # Extract context from kwargs
        context = kwargs.copy()
        
        # Log with our system
        self._log(our_level, msg, **context)
    
    def _convert_py_level(self, py_level: int) -> LogLevel:
        """Convert Python logging level to our LogLevel."""
        if py_level >= logging.CRITICAL:
            return LogLevel.CRITICAL
        elif py_level >= logging.ERROR:
            return LogLevel.ERROR
        elif py_level >= logging.WARNING:
            return LogLevel.WARNING
        elif py_level >= logging.INFO:
            return LogLevel.INFO
        else:
            return LogLevel.DEBUG
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics."""
        stats = self._perf_monitor.get_stats()
        stats.update({
            "buffer_size": self._buffer.size(),
            "buffer_dropped": self._buffer.dropped_count(),
            "buffer_capacity": self._buffer.maxsize,
            "dispatch_task_running": self._dispatch_task is not None and not self._dispatch_task.done(),
            "backends_enabled": sum(1 for b in self.backends if b.enabled),
            "backends_total": len(self.backends)
        })
        return stats
    
    async def shutdown(self) -> None:
        """Graceful shutdown."""
        # Signal shutdown
        if self._shutdown_event:
            self._shutdown_event.set()
        
        # Wait for dispatch task to finish
        if self._dispatch_task and not self._dispatch_task.done():
            try:
                await asyncio.wait_for(self._dispatch_task, timeout=5.0)
            except asyncio.TimeoutError:
                self._dispatch_task.cancel()
        
        # Flush remaining messages
        await self.flush()
    
    @classmethod
    async def shutdown_all(cls) -> None:
        """Shutdown all logger instances."""
        cls._global_shutdown = True
        
        # Shutdown all instances
        shutdown_tasks = []
        for logger in list(cls._instances):
            shutdown_tasks.append(logger.shutdown())
        
        if shutdown_tasks:
            await asyncio.gather(*shutdown_tasks, return_exceptions=True)


# Context manager for timing operations
class LoggingTimer:
    """Context manager for timing operations with automatic logging."""
    
    def __init__(self, logger: HFTLoggerInterface, operation: str, **tags):
        self.logger = logger
        self.operation = operation
        self.tags = tags
        self.start_time = None
        self.end_time = None
    
    def __enter__(self):
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time is not None:
            self.end_time = time.perf_counter()
            duration_ms = (self.end_time - self.start_time) * 1000
            self.logger.latency(self.operation, duration_ms, **self.tags)
        
        # Log error if exception occurred
        if exc_type is not None:
            self.logger.error(f"{self.operation} failed", 
                            error_type=exc_type.__name__,
                            **self.tags)
    
    @property
    def elapsed_ms(self) -> float:
        """Get elapsed time in milliseconds."""
        if self.start_time is None:
            return 0.0
        end_time = self.end_time or time.perf_counter()
        return (end_time - self.start_time) * 1000


def log_performance(operation: str, **tags):
    """Decorator for logging function performance."""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            # Find logger in args/kwargs or use default
            logger = None
            if args and hasattr(args[0], 'logger'):
                logger = args[0].logger
            
            if logger:
                with LoggingTimer(logger, f"{func.__name__}_{operation}", **tags):
                    return await func(*args, **kwargs)
            else:
                return await func(*args, **kwargs)
        
        def sync_wrapper(*args, **kwargs):
            # Find logger in args/kwargs or use default
            logger = None
            if args and hasattr(args[0], 'logger'):
                logger = args[0].logger
            
            if logger:
                with LoggingTimer(logger, f"{func.__name__}_{operation}", **tags):
                    return func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator