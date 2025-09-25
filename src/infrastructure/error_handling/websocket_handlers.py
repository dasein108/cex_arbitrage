"""
WebSocket-Specific Error Handlers

Specialized error handling for WebSocket connections, message parsing,
and real-time data streams in HFT trading systems.
"""

import json
import asyncio
from typing import Dict, Any, Optional, Callable, Awaitable
from websockets.exceptions import (
    ConnectionClosedError, 
    ConnectionClosedOK,
    InvalidStatusCode,
    InvalidHandshake,
    WebSocketException
)
from aiohttp import ClientError, ClientTimeout, ClientConnectorError

from infrastructure.logging.interfaces import HFTLoggerInterface
from .handlers import ComposableErrorHandler, ErrorContext, ErrorSeverity


class WebSocketErrorHandler(ComposableErrorHandler):
    """
    Specialized error handling for WebSocket connections.
    
    Handles connection management, message parsing, and reconnection logic
    with HFT-optimized performance characteristics.
    """
    
    def __init__(self, logger: HFTLoggerInterface, max_retries: int = 5, base_delay: float = 0.1):
        super().__init__(logger, max_retries, base_delay, "WebSocketErrorHandler")
        self._register_websocket_handlers()
        
        # Performance optimization: pre-compile reconnection delays
        self._reconnection_delays = {
            "connection_lost": 0.1,      # Fast reconnect for connection drops
            "timeout": 0.5,             # Medium delay for timeouts  
            "handshake_error": 2.0,     # Longer delay for handshake issues
            "rate_limit": 5.0           # Longest delay for rate limiting
        }
    
    def _register_websocket_handlers(self) -> None:
        """Register WebSocket-specific exception handlers."""
        # Connection-related errors
        self.register_handler(ConnectionClosedError, self._handle_connection_closed)
        self.register_handler(ConnectionClosedOK, self._handle_connection_closed_ok)
        self.register_handler(InvalidStatusCode, self._handle_invalid_status)
        self.register_handler(InvalidHandshake, self._handle_handshake_error)
        self.register_handler(WebSocketException, self._handle_websocket_error)
        
        # HTTP client errors
        self.register_handler(ClientTimeout, self._handle_timeout)
        self.register_handler(ClientError, self._handle_client_error)
        self.register_handler(ClientConnectorError, self._handle_connection_error)
        
        # Message parsing errors
        self.register_handler(json.JSONDecodeError, self._handle_json_error)
        self.register_handler(KeyError, self._handle_missing_field)
        self.register_handler(ValueError, self._handle_value_error)
    
    async def _handle_connection_closed(
        self, 
        exception: ConnectionClosedError, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle WebSocket connection closed unexpectedly."""
        close_code = getattr(exception, 'code', None)
        close_reason = getattr(exception, 'reason', 'Unknown')
        
        # Determine reconnection strategy based on close code
        should_reconnect = self._should_reconnect(close_code)
        reconnect_delay = self._get_reconnect_delay(close_code)
        
        self.logger.warning("WebSocket connection closed unexpectedly",
                          component=self.component_name,
                          operation=context.operation,
                          close_code=close_code,
                          close_reason=close_reason,
                          attempt=context.attempt,
                          should_reconnect=should_reconnect,
                          reconnect_delay=reconnect_delay)
        
        # Track connection failure metrics
        self.logger.metric("websocket_connection_closed", 1,
                         tags={
                             "component": self.component_name,
                             "close_code": str(close_code) if close_code else "unknown",
                             "should_reconnect": str(should_reconnect)
                         })
        
        # Trigger reconnection if appropriate and callback available
        if should_reconnect and context.reconnect_callback:
            try:
                await asyncio.sleep(reconnect_delay)
                await context.reconnect_callback()
                
                self.logger.info("WebSocket reconnection initiated",
                               component=self.component_name,
                               operation=context.operation,
                               delay_applied=reconnect_delay)
                
            except Exception as reconnect_error:
                self.logger.error("WebSocket reconnection failed",
                                component=self.component_name,
                                reconnection_error=str(reconnect_error),
                                reconnection_exception_type=type(reconnect_error).__name__)
    
    async def _handle_connection_closed_ok(
        self, 
        exception: ConnectionClosedOK, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle graceful WebSocket closure."""
        self.logger.info("WebSocket connection closed gracefully",
                        component=self.component_name,
                        operation=context.operation)
        
        # Track graceful closures for monitoring
        self.logger.metric("websocket_connection_closed_gracefully", 1,
                         tags={"component": self.component_name})
    
    async def _handle_invalid_status(
        self, 
        exception: InvalidStatusCode, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle invalid HTTP status codes during WebSocket handshake."""
        status_code = getattr(exception, 'status_code', None)
        
        self.logger.error("WebSocket handshake failed with invalid status",
                        component=self.component_name,
                        operation=context.operation,
                        status_code=status_code,
                        attempt=context.attempt)
        
        # Track handshake failures
        self.logger.metric("websocket_handshake_failure", 1,
                         tags={
                             "component": self.component_name,
                             "status_code": str(status_code) if status_code else "unknown"
                         })
    
    async def _handle_handshake_error(
        self, 
        exception: InvalidHandshake, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle WebSocket handshake errors with longer backoff."""
        self.logger.error("WebSocket handshake error",
                        component=self.component_name,
                        operation=context.operation,
                        handshake_error=str(exception),
                        attempt=context.attempt)
        
        # Apply longer delay for handshake errors
        await asyncio.sleep(self._reconnection_delays["handshake_error"])
    
    async def _handle_websocket_error(
        self, 
        exception: WebSocketException, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle general WebSocket exceptions."""
        self.logger.error("WebSocket protocol error",
                        component=self.component_name,
                        operation=context.operation,
                        websocket_error=str(exception),
                        exception_type=type(exception).__name__,
                        attempt=context.attempt)
    
    async def _handle_timeout(
        self, 
        exception: ClientTimeout, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle connection timeouts with appropriate backoff."""
        timeout_duration = getattr(exception, 'timeout', 'unknown')
        
        self.logger.warning("WebSocket connection timeout",
                          component=self.component_name,
                          operation=context.operation,
                          timeout_duration=timeout_duration,
                          attempt=context.attempt)
        
        # Track timeout patterns for monitoring
        self.logger.metric("websocket_timeout", 1,
                         tags={
                             "component": self.component_name,
                             "operation": context.operation
                         })
        
        # Apply timeout-specific backoff
        await asyncio.sleep(self._reconnection_delays["timeout"])
    
    async def _handle_client_error(
        self, 
        exception: ClientError, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle HTTP client errors."""
        self.logger.error("HTTP client error during WebSocket operation",
                        component=self.component_name,
                        operation=context.operation,
                        client_error=str(exception),
                        exception_type=type(exception).__name__,
                        attempt=context.attempt)
    
    async def _handle_connection_error(
        self, 
        exception: ClientConnectorError, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle connection establishment errors."""
        self.logger.error("Failed to establish WebSocket connection",
                        component=self.component_name,
                        operation=context.operation,
                        connection_error=str(exception),
                        attempt=context.attempt)
        
        # Track connection establishment failures
        self.logger.metric("websocket_connection_establishment_failure", 1,
                         tags={"component": self.component_name})
    
    async def _handle_json_error(
        self, 
        exception: json.JSONDecodeError, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle JSON parsing errors in WebSocket messages."""
        # Extract problematic message portion for debugging
        msg_preview = getattr(exception, 'doc', '')[:100] + '...' if hasattr(exception, 'doc') else 'unknown'
        
        self.logger.warning("WebSocket message JSON decode error",
                          component=self.component_name,
                          operation=context.operation,
                          json_error=str(exception),
                          message_preview=msg_preview,
                          attempt=context.attempt)
        
        # Track parsing errors for data quality monitoring
        self.logger.metric("websocket_json_parse_error", 1,
                         tags={
                             "component": self.component_name,
                             "operation": context.operation
                         })
    
    async def _handle_missing_field(
        self, 
        exception: KeyError, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle missing required fields in WebSocket messages."""
        missing_field = str(exception).strip("'\"")
        
        self.logger.warning("WebSocket message missing required field",
                          component=self.component_name,
                          operation=context.operation,
                          missing_field=missing_field,
                          attempt=context.attempt,
                          metadata=context.metadata)
        
        # Track field validation errors
        self.logger.metric("websocket_missing_field", 1,
                         tags={
                             "component": self.component_name,
                             "field": missing_field
                         })
    
    async def _handle_value_error(
        self, 
        exception: ValueError, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle value conversion errors in WebSocket data processing."""
        self.logger.warning("WebSocket data value conversion error",
                          component=self.component_name,
                          operation=context.operation,
                          value_error=str(exception),
                          attempt=context.attempt,
                          metadata=context.metadata)
        
        # Track data quality issues
        self.logger.metric("websocket_value_conversion_error", 1,
                         tags={"component": self.component_name})
    
    def _should_reconnect(self, close_code: Optional[int]) -> bool:
        """Determine if reconnection should be attempted based on close code."""
        if close_code is None:
            return True  # Unknown closure, attempt reconnect
        
        # WebSocket close codes that suggest reconnection might succeed
        reconnectable_codes = {
            1006,  # Abnormal closure
            1011,  # Server error
            1012,  # Service restart
            1013,  # Try again later
            1014   # Bad gateway
        }
        
        # Don't reconnect for client errors or permanent failures
        permanent_failure_codes = {
            1002,  # Protocol error
            1003,  # Unsupported data
            1007,  # Invalid data
            1008,  # Policy violation
            1009,  # Message too big
            1010   # Mandatory extension
        }
        
        if close_code in permanent_failure_codes:
            return False
            
        return close_code in reconnectable_codes or close_code >= 4000  # Custom codes
    
    def _get_reconnect_delay(self, close_code: Optional[int]) -> float:
        """Get appropriate reconnection delay based on close code."""
        if close_code is None or close_code == 1006:  # Abnormal closure
            return self._reconnection_delays["connection_lost"]
        elif close_code in {1011, 1012}:  # Server errors
            return self._reconnection_delays["timeout"]  
        elif close_code == 1013:  # Try again later
            return self._reconnection_delays["rate_limit"]
        else:
            return self._reconnection_delays["connection_lost"]  # Default