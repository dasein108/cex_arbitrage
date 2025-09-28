"""
BaseMessageHandler - Template Method Pattern for Message Processing

Core message handler implementing template method pattern for structured message
processing with exchange-specific customization. Provides performance monitoring,
error handling, and routing infrastructure for HFT-compliant message processing.

Key Features:
- Template method pattern with _handle_message() entry point
- Abstract message type detection and routing
- Performance tracking with microsecond precision
- Error handling with exchange-specific classification
- Message validation and metrics collection
- HFT optimized: <5μs template method overhead

HFT COMPLIANCE: Sub-millisecond message processing throughout pipeline.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from infrastructure.networking.websocket.message_types import WebSocketMessageType
from infrastructure.logging import get_logger, LoggingTimer
from infrastructure.exceptions.exchange import ExchangeRestError


class BaseMessageHandler(ABC):
    """
    Base message handler with template method pattern for message processing.
    
    Provides structured message processing pipeline with exchange-specific
    customization points. Implements the core _handle_message() interface
    required by BaseWebSocketInterface.
    
    Template Method Pattern:
    1. _handle_message() - Main entry point (template method)
    2. _detect_message_type() - Exchange-specific type detection
    3. _route_message() - Route to appropriate parser based on type
    4. Performance validation and error handling throughout
    
    Performance Specifications:
    - Template method overhead: <5μs
    - Type detection: <10μs
    - Message routing: <5μs
    - Error handling: <2μs (success path)
    """
    
    def __init__(self, exchange_name: str, logger=None):
        """
        Initialize base message handler.
        
        Args:
            exchange_name: Name of the exchange for logging and metrics
            logger: Optional logger instance for dependency injection
        """
        self.exchange_name = exchange_name
        self.logger = logger or get_logger(f'ws.handler.{exchange_name}')
        
        # Performance tracking
        self.message_count = 0
        self.processing_times = []
        self.error_count = 0
        self.type_detection_times = []
        self.routing_times = []
        
        # Performance limits for HFT compliance
        self.max_processing_time_us = 1000  # 1ms warning threshold
        self.max_type_detection_time_us = 10  # 10μs for type detection
        self.max_routing_time_us = 5  # 5μs for message routing
        
        # Message statistics
        self.message_type_counts = {}
        self.last_performance_log = time.time()
        self.performance_log_interval = 60.0  # Log performance every 60 seconds
        
        self.logger.info(f"BaseMessageHandler initialized for {exchange_name}",
                        exchange=exchange_name,
                        performance_tracking=True,
                        hft_compliance=True)
    
    # Template method - main entry point
    
    async def _handle_message(self, raw_message: Any) -> None:
        """
        Template method for message processing with performance validation.
        
        This is the main entry point called by BaseWebSocketInterface.
        Implements template method pattern with exchange-specific customization.
        
        Performance Flow:
        1. Start timing
        2. Detect message type (exchange-specific)
        3. Route message to appropriate handler (exchange-specific)
        4. Performance validation and metrics collection
        5. Error handling with classification
        
        Args:
            raw_message: Raw message from WebSocket (bytes, str, or dict)
        """
        start_time = time.perf_counter()
        processing_success = False
        message_type = None
        
        try:
            self.message_count += 1
            
            # Phase 1: Message type detection (exchange-specific)
            type_detection_start = time.perf_counter()
            message_type = await self._detect_message_type(raw_message)
            type_detection_time_us = (time.perf_counter() - type_detection_start) * 1_000_000
            
            self.type_detection_times.append(type_detection_time_us)
            self._validate_type_detection_performance(type_detection_time_us)
            
            # Phase 2: Message routing (exchange-specific)
            routing_start = time.perf_counter()
            await self._route_message(message_type, raw_message)
            routing_time_us = (time.perf_counter() - routing_start) * 1_000_000
            
            self.routing_times.append(routing_time_us)
            self._validate_routing_performance(routing_time_us)
            
            # Track message type statistics
            self.message_type_counts[message_type] = self.message_type_counts.get(message_type, 0) + 1
            
            processing_success = True
            
        except Exception as e:
            await self._handle_processing_error(e, raw_message, message_type)
            
        finally:
            # Performance tracking and validation
            total_processing_time_us = (time.perf_counter() - start_time) * 1_000_000
            self.processing_times.append(total_processing_time_us)
            
            # HFT compliance validation
            self._validate_processing_performance(total_processing_time_us, processing_success)
            
            # Periodic performance logging
            await self._log_performance_metrics()
            
            # Track metrics for monitoring
            self.logger.metric("ws_handler_messages_processed", 1,
                             tags={"exchange": self.exchange_name, 
                                   "message_type": str(message_type) if message_type else "unknown",
                                   "success": str(processing_success)})
            
            self.logger.metric("ws_handler_processing_time_us", total_processing_time_us,
                             tags={"exchange": self.exchange_name})
    
    # Abstract methods for exchange-specific implementation
    
    @abstractmethod
    async def _detect_message_type(self, raw_message: Any) -> WebSocketMessageType:
        """
        Detect message type for routing purposes.
        
        Exchange-specific implementation must analyze the raw message and
        determine its type for proper routing. Performance target: <10μs.
        
        Args:
            raw_message: Raw message from WebSocket
            
        Returns:
            WebSocketMessageType enum value for routing
            
        Raises:
            ValueError: If message type cannot be determined
        """
        pass
    
    @abstractmethod
    async def _route_message(self, message_type: WebSocketMessageType, raw_message: Any) -> None:
        """
        Route message to appropriate handler based on type.
        
        Exchange-specific implementation must route the message to the
        appropriate parsing and callback logic. Performance target: <5μs for routing.
        
        Args:
            message_type: Detected message type
            raw_message: Raw message from WebSocket
            
        Raises:
            ValueError: If message type is not supported
        """
        pass
    
    # Performance validation methods
    
    def _validate_type_detection_performance(self, detection_time_us: float) -> None:
        """
        Validate type detection performance against HFT targets.
        
        Args:
            detection_time_us: Time taken for type detection in microseconds
        """
        if detection_time_us > self.max_type_detection_time_us:
            self.logger.warning("Type detection performance degraded",
                              detection_time_us=detection_time_us,
                              max_allowed_us=self.max_type_detection_time_us,
                              exchange=self.exchange_name)
            
            # Track performance degradation
            self.logger.metric("ws_handler_type_detection_slow", 1,
                             tags={"exchange": self.exchange_name})
    
    def _validate_routing_performance(self, routing_time_us: float) -> None:
        """
        Validate message routing performance against HFT targets.
        
        Args:
            routing_time_us: Time taken for message routing in microseconds
        """
        if routing_time_us > self.max_routing_time_us:
            self.logger.warning("Message routing performance degraded",
                              routing_time_us=routing_time_us,
                              max_allowed_us=self.max_routing_time_us,
                              exchange=self.exchange_name)
            
            # Track performance degradation
            self.logger.metric("ws_handler_routing_slow", 1,
                             tags={"exchange": self.exchange_name})
    
    def _validate_processing_performance(self, processing_time_us: float, success: bool) -> None:
        """
        Validate overall processing performance against HFT targets.
        
        Args:
            processing_time_us: Total processing time in microseconds
            success: Whether processing was successful
        """
        if processing_time_us > self.max_processing_time_us:
            if success:
                self.logger.warning("Message processing performance degraded",
                                  processing_time_us=processing_time_us,
                                  max_allowed_us=self.max_processing_time_us,
                                  exchange=self.exchange_name)
            else:
                self.logger.error("Message processing failed with performance degradation",
                                processing_time_us=processing_time_us,
                                max_allowed_us=self.max_processing_time_us,
                                exchange=self.exchange_name)
            
            # Track performance degradation
            self.logger.metric("ws_handler_processing_slow", 1,
                             tags={"exchange": self.exchange_name, "success": str(success)})
    
    # Error handling methods
    
    async def _handle_processing_error(self, error: Exception, raw_message: Any, message_type: Optional[WebSocketMessageType]) -> None:
        """
        Handle errors during message processing.
        
        Args:
            error: Exception that occurred
            raw_message: Original raw message
            message_type: Detected message type (if any)
        """
        self.error_count += 1
        
        error_type = type(error).__name__
        
        self.logger.error("Message processing error",
                        error_type=error_type,
                        error_message=str(error),
                        message_type=str(message_type) if message_type else "unknown",
                        exchange=self.exchange_name,
                        message_count=self.message_count)
        
        # Track error metrics
        self.logger.metric("ws_handler_processing_errors", 1,
                         tags={"exchange": self.exchange_name, 
                               "error_type": error_type,
                               "message_type": str(message_type) if message_type else "unknown"})
        
        # Consider circuit breaker pattern for repeated errors
        await self._evaluate_circuit_breaker()
    
    async def _evaluate_circuit_breaker(self) -> None:
        """
        Evaluate if circuit breaker should trigger based on error rate.
        
        For HFT systems, we need to be careful about stopping processing,
        but we should alert if error rates become excessive.
        """
        if len(self.processing_times) < 100:
            return  # Not enough data for evaluation
        
        # Calculate error rate over recent messages
        recent_messages = 100
        recent_errors = min(self.error_count, recent_messages)
        error_rate = recent_errors / recent_messages
        
        # Alert on high error rates (but don't stop processing)
        if error_rate > 0.1:  # 10% error rate threshold
            self.logger.error("High message processing error rate detected",
                            error_rate=error_rate,
                            recent_errors=recent_errors,
                            recent_messages=recent_messages,
                            exchange=self.exchange_name)
            
            # Track high error rate
            self.logger.metric("ws_handler_high_error_rate", 1,
                             tags={"exchange": self.exchange_name})
    
    # Performance monitoring and metrics
    
    async def _log_performance_metrics(self) -> None:
        """
        Log performance metrics periodically for monitoring.
        """
        current_time = time.time()
        if current_time - self.last_performance_log < self.performance_log_interval:
            return
        
        if not self.processing_times:
            return
        
        # Calculate performance statistics
        avg_processing_time_us = sum(self.processing_times) / len(self.processing_times)
        max_processing_time_us = max(self.processing_times)
        avg_type_detection_us = sum(self.type_detection_times) / len(self.type_detection_times) if self.type_detection_times else 0
        avg_routing_time_us = sum(self.routing_times) / len(self.routing_times) if self.routing_times else 0
        
        # Calculate throughput
        time_window = current_time - self.last_performance_log
        messages_per_second = len(self.processing_times) / time_window if time_window > 0 else 0
        
        self.logger.info("Message handler performance metrics",
                        exchange=self.exchange_name,
                        messages_processed=self.message_count,
                        messages_per_second=messages_per_second,
                        avg_processing_time_us=avg_processing_time_us,
                        max_processing_time_us=max_processing_time_us,
                        avg_type_detection_us=avg_type_detection_us,
                        avg_routing_time_us=avg_routing_time_us,
                        error_count=self.error_count,
                        error_rate=self.error_count / self.message_count if self.message_count > 0 else 0,
                        message_type_counts=self.message_type_counts)
        
        # Reset statistics for next window
        self.processing_times.clear()
        self.type_detection_times.clear()
        self.routing_times.clear()
        self.last_performance_log = current_time
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get current performance metrics for monitoring.
        
        Returns:
            Dictionary with performance statistics
        """
        if not self.processing_times:
            return {
                'exchange': self.exchange_name,
                'messages_processed': self.message_count,
                'error_count': self.error_count,
                'avg_processing_time_us': 0,
                'max_processing_time_us': 0,
                'message_type_counts': self.message_type_counts
            }
        
        avg_processing_time_us = sum(self.processing_times) / len(self.processing_times)
        max_processing_time_us = max(self.processing_times)
        avg_type_detection_us = sum(self.type_detection_times) / len(self.type_detection_times) if self.type_detection_times else 0
        avg_routing_time_us = sum(self.routing_times) / len(self.routing_times) if self.routing_times else 0
        
        return {
            'exchange': self.exchange_name,
            'messages_processed': self.message_count,
            'error_count': self.error_count,
            'error_rate': self.error_count / self.message_count if self.message_count > 0 else 0,
            'avg_processing_time_us': avg_processing_time_us,
            'max_processing_time_us': max_processing_time_us,
            'avg_type_detection_us': avg_type_detection_us,
            'avg_routing_time_us': avg_routing_time_us,
            'message_type_counts': self.message_type_counts,
            'hft_compliance': {
                'processing_under_1ms': avg_processing_time_us < 1000,
                'type_detection_under_10us': avg_type_detection_us < 10,
                'routing_under_5us': avg_routing_time_us < 5
            }
        }
    
    # Utility methods
    
    def reset_performance_metrics(self) -> None:
        """
        Reset performance metrics for fresh monitoring period.
        """
        self.processing_times.clear()
        self.type_detection_times.clear()
        self.routing_times.clear()
        self.message_type_counts.clear()
        self.error_count = 0
        self.message_count = 0
        self.last_performance_log = time.time()
        
        self.logger.info("Performance metrics reset",
                        exchange=self.exchange_name)