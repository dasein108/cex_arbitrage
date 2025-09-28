"""
Performance Tracking Utility for WebSocket Interfaces

Shared performance tracking functionality for HFT WebSocket operations.
Provides sub-millisecond latency tracking, message throughput monitoring,
and memory-efficient ring buffer implementation using collections.deque.

Architecture compliance:
- HFT performance requirements (sub-millisecond tracking)
- Memory efficient with configurable ring buffer size
- Type-safe with comprehensive annotations
- Zero-allocation measurement recording
- Thread-safe operations for concurrent access
"""

import time
from collections import deque
from typing import Dict, Union, Optional, Deque
from threading import Lock

from infrastructure.logging import HFTLoggerInterface


class WebSocketPerformanceTracker:
    """
    High-performance WebSocket performance tracking utility.
    
    Provides efficient performance metrics collection for HFT WebSocket operations
    with minimal memory overhead and sub-microsecond measurement recording.
    
    Features:
    - Ring buffer using collections.deque for O(1) operations
    - Thread-safe measurement recording
    - Memory-bounded storage with configurable limits
    - Zero-allocation fast path for measurement recording
    - Microsecond precision timing
    """
    
    # Configuration constants
    DEFAULT_RING_BUFFER_SIZE = 1000
    MICROSECOND_MULTIPLIER = 1_000_000
    
    def __init__(
        self,
        exchange_name: str,
        interface_type: str,
        logger: HFTLoggerInterface,
        ring_buffer_size: int = DEFAULT_RING_BUFFER_SIZE
    ) -> None:
        """
        Initialize performance tracker.
        
        Args:
            exchange_name: Exchange identifier for logging
            interface_type: Interface type (public_spot, private_spot, etc.)
            logger: HFT logger for performance monitoring
            ring_buffer_size: Maximum number of measurements to retain
        """
        self.exchange_name = exchange_name
        self.interface_type = interface_type
        self.logger = logger
        self.ring_buffer_size = ring_buffer_size
        
        # Performance metrics storage with thread safety
        self._processing_times: Deque[float] = deque(maxlen=ring_buffer_size)
        self._metrics_lock = Lock()
        
        # Connection and message tracking
        self._message_count = 0
        self._connection_start_time: Optional[float] = None
        self._last_message_time: Optional[float] = None
        
        # Domain-specific counters (will be set by inheriting classes)
        self._domain_counters: Dict[str, int] = {}
        
        self.logger.debug(
            "Performance tracker initialized",
            exchange=self.exchange_name,
            interface_type=self.interface_type,
            ring_buffer_size=ring_buffer_size
        )
    
    def start_connection_tracking(self) -> None:
        """Start tracking connection uptime."""
        self._connection_start_time = time.perf_counter()
        
        self.logger.debug(
            "Connection tracking started",
            exchange=self.exchange_name,
            interface_type=self.interface_type
        )
    
    def record_message_processing_time(self, processing_time: float) -> None:
        """
        Record message processing time with high performance.
        
        Args:
            processing_time: Processing time in seconds
            
        Note:
            This is optimized for the fast path - minimal allocations,
            thread-safe append to ring buffer, automatic eviction.
        """
        with self._metrics_lock:
            self._processing_times.append(processing_time)
            self._message_count += 1
            self._last_message_time = time.perf_counter()
    
    def increment_domain_counter(self, counter_name: str) -> None:
        """
        Increment domain-specific counter efficiently.
        
        Args:
            counter_name: Name of the counter to increment
        """
        self._domain_counters[counter_name] = self._domain_counters.get(counter_name, 0) + 1
    
    def get_performance_metrics(self, additional_metrics: Optional[Dict[str, Union[int, float, str]]] = None) -> Dict[str, Union[int, float, str]]:
        """
        Get comprehensive performance metrics.
        
        Args:
            additional_metrics: Additional metrics to include in the result
            
        Returns:
            Dictionary containing all performance metrics
        """
        with self._metrics_lock:
            # Calculate uptime
            uptime_seconds = 0.0
            if self._connection_start_time:
                uptime_seconds = time.perf_counter() - self._connection_start_time
            
            # Calculate average processing time in microseconds
            avg_processing_time_us = 0.0
            if self._processing_times:
                avg_processing_time_us = (
                    sum(self._processing_times) / len(self._processing_times) * self.MICROSECOND_MULTIPLIER
                )
            
            # Calculate messages per second
            messages_per_second = 0.0
            if uptime_seconds > 0:
                messages_per_second = self._message_count / uptime_seconds
            
            # Base metrics
            metrics = {
                "exchange": self.exchange_name,
                "interface_type": self.interface_type,
                "connection_uptime_seconds": uptime_seconds,
                "message_processing_latency_us": avg_processing_time_us,
                "messages_per_second": messages_per_second,
                "total_messages_processed": self._message_count,
                "ring_buffer_size": len(self._processing_times),
                "ring_buffer_capacity": self.ring_buffer_size
            }
            
            # Add domain-specific counters
            metrics.update(self._domain_counters)
            
            # Add any additional metrics
            if additional_metrics:
                metrics.update(additional_metrics)
            
            return metrics
    
    def reset_metrics(self) -> None:
        """Reset all performance metrics."""
        with self._metrics_lock:
            self._processing_times.clear()
            self._message_count = 0
            self._connection_start_time = None
            self._last_message_time = None
            self._domain_counters.clear()
        
        self.logger.info(
            "Performance metrics reset",
            exchange=self.exchange_name,
            interface_type=self.interface_type
        )
    
    def get_current_throughput(self, window_seconds: float = 60.0) -> float:
        """
        Calculate current message throughput over a time window.
        
        Args:
            window_seconds: Time window for throughput calculation
            
        Returns:
            Messages per second over the specified window
        """
        if not self._last_message_time or not self._connection_start_time:
            return 0.0
        
        current_time = time.perf_counter()
        time_since_last = current_time - self._last_message_time
        
        # If no recent messages, return 0
        if time_since_last > window_seconds:
            return 0.0
        
        # Calculate based on recent activity
        window_start = current_time - window_seconds
        effective_start = max(window_start, self._connection_start_time)
        window_duration = current_time - effective_start
        
        if window_duration <= 0:
            return 0.0
        
        return self._message_count / window_duration


class PublicWebSocketPerformanceTracker(WebSocketPerformanceTracker):
    """Performance tracker specialized for public market data WebSocket operations."""
    
    def __init__(
        self,
        exchange_name: str,
        logger: HFTLoggerInterface,
        ring_buffer_size: int = WebSocketPerformanceTracker.DEFAULT_RING_BUFFER_SIZE
    ) -> None:
        super().__init__(exchange_name, "public_market_data", logger, ring_buffer_size)
        
        # Public-specific counters
        self._domain_counters.update({
            "orderbook_updates_count": 0,
            "trade_updates_count": 0,
            "ticker_updates_count": 0,
            "book_ticker_updates_count": 0
        })
    
    def record_orderbook_update(self, processing_time: float) -> None:
        """Record orderbook update processing time."""
        self.record_message_processing_time(processing_time)
        self.increment_domain_counter("orderbook_updates_count")
    
    def record_trade_update(self, processing_time: float) -> None:
        """Record trade update processing time."""
        self.record_message_processing_time(processing_time)
        self.increment_domain_counter("trade_updates_count")
    
    def record_ticker_update(self, processing_time: float) -> None:
        """Record ticker update processing time."""
        self.record_message_processing_time(processing_time)
        self.increment_domain_counter("ticker_updates_count")
    
    def record_book_ticker_update(self, processing_time: float) -> None:
        """Record book ticker update processing time."""
        self.record_message_processing_time(processing_time)
        self.increment_domain_counter("book_ticker_updates_count")


class PrivateWebSocketPerformanceTracker(WebSocketPerformanceTracker):
    """Performance tracker specialized for private trading WebSocket operations."""
    
    def __init__(
        self,
        exchange_name: str,
        logger: HFTLoggerInterface,
        ring_buffer_size: int = WebSocketPerformanceTracker.DEFAULT_RING_BUFFER_SIZE
    ) -> None:
        super().__init__(exchange_name, "private_trading_operations", logger, ring_buffer_size)
        
        # Private-specific counters
        self._domain_counters.update({
            "order_updates_count": 0,
            "balance_updates_count": 0,
            "execution_updates_count": 0,
            "position_updates_count": 0
        })
    
    def record_order_update(self, processing_time: float) -> None:
        """Record order update processing time."""
        self.record_message_processing_time(processing_time)
        self.increment_domain_counter("order_updates_count")
    
    def record_balance_update(self, processing_time: float) -> None:
        """Record balance update processing time."""
        self.record_message_processing_time(processing_time)
        self.increment_domain_counter("balance_updates_count")
    
    def record_execution_update(self, processing_time: float) -> None:
        """Record execution update processing time."""
        self.record_message_processing_time(processing_time)
        self.increment_domain_counter("execution_updates_count")
    
    def record_position_update(self, processing_time: float) -> None:
        """Record position update processing time."""
        self.record_message_processing_time(processing_time)
        self.increment_domain_counter("position_updates_count")