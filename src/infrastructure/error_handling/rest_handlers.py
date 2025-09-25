"""
REST API-Specific Error Handlers

Specialized error handling for HTTP REST API operations, authentication,
rate limiting, and API-specific error responses in HFT trading systems.
"""

import asyncio
import json
from typing import Dict, Any, Optional
from aiohttp import (
    ClientError, 
    ClientTimeout, 
    ClientResponseError,
    ClientConnectorError,
    ClientSession
)

from infrastructure.logging.interfaces import HFTLoggerInterface
from .handlers import ComposableErrorHandler, ErrorContext, ErrorSeverity


class RestApiErrorHandler(ComposableErrorHandler):
    """
    Specialized error handling for REST API operations.
    
    Handles HTTP status codes, authentication, rate limiting,
    and API response errors with HFT performance requirements.
    """
    
    def __init__(self, logger: HFTLoggerInterface, max_retries: int = 3, base_delay: float = 1.0):
        super().__init__(logger, max_retries, base_delay, "RestApiErrorHandler")
        self._register_rest_handlers()
        
        # Performance optimization: pre-compile status code handling
        self._status_code_handlers = {
            400: self._handle_bad_request,
            401: self._handle_unauthorized,
            403: self._handle_forbidden,
            404: self._handle_not_found,
            429: self._handle_rate_limited,
            500: self._handle_server_error,
            502: self._handle_bad_gateway,
            503: self._handle_service_unavailable,
            504: self._handle_gateway_timeout
        }
        
        # Rate limit backoff strategies by status/endpoint type
        self._rate_limit_backoffs = {
            "order_placement": 2.0,
            "market_data": 0.5, 
            "account_info": 1.0,
            "generic": 1.0
        }
    
    def _register_rest_handlers(self) -> None:
        """Register REST API-specific exception handlers."""
        # HTTP client errors
        self.register_handler(ClientTimeout, self._handle_timeout)
        self.register_handler(ClientResponseError, self._handle_response_error)
        self.register_handler(ClientError, self._handle_client_error)
        self.register_handler(ClientConnectorError, self._handle_connector_error)
        
        # JSON and data parsing errors  
        self.register_handler(json.JSONDecodeError, self._handle_json_error)
        self.register_handler(KeyError, self._handle_missing_field)
        self.register_handler(ValueError, self._handle_value_error)
    
    async def _handle_timeout(
        self, 
        exception: ClientTimeout, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle HTTP request timeouts with adaptive backoff."""
        timeout_type = getattr(exception, 'timeout_type', 'unknown')
        
        self.logger.warning("REST API request timeout",
                          component=self.component_name,
                          operation=context.operation,
                          timeout_type=timeout_type,
                          attempt=context.attempt,
                          endpoint=context.metadata.get('endpoint') if context.metadata else None)
        
        # Track timeout patterns for optimization
        self.logger.metric("rest_api_timeout", 1,
                         tags={
                             "component": self.component_name,
                             "timeout_type": timeout_type,
                             "operation": context.operation
                         })
        
        # Apply adaptive backoff based on timeout type
        if timeout_type == "connect":
            delay = 0.5  # Connection timeouts get shorter delay
        else:
            delay = 1.0  # Read/total timeouts get longer delay
            
        await asyncio.sleep(delay)
    
    async def _handle_response_error(
        self, 
        exception: ClientResponseError, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle HTTP response errors with status code specific logic."""
        status = exception.status
        url = str(exception.request_info.url) if exception.request_info else 'unknown'
        
        # Extract response body for error analysis
        response_text = getattr(exception, 'message', '') or str(exception)
        
        self.logger.error("REST API response error",
                        component=self.component_name,
                        operation=context.operation,
                        status_code=status,
                        url=url,
                        response_text=response_text[:500],  # Limit response size
                        attempt=context.attempt)
        
        # Track status code patterns
        self.logger.metric("rest_api_status_error", 1,
                         tags={
                             "component": self.component_name,
                             "status_code": str(status),
                             "operation": context.operation
                         })
        
        # Route to specific status code handler if available
        if status in self._status_code_handlers:
            await self._status_code_handlers[status](exception, context, severity)
    
    async def _handle_client_error(
        self, 
        exception: ClientError, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle general HTTP client errors."""
        self.logger.error("REST API client error",
                        component=self.component_name,
                        operation=context.operation,
                        client_error=str(exception),
                        exception_type=type(exception).__name__,
                        attempt=context.attempt)
        
        # Track general client errors
        self.logger.metric("rest_api_client_error", 1,
                         tags={
                             "component": self.component_name,
                             "exception_type": type(exception).__name__
                         })
    
    async def _handle_connector_error(
        self, 
        exception: ClientConnectorError, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle connection establishment errors."""
        host = getattr(exception, 'host', 'unknown')
        port = getattr(exception, 'port', 'unknown')
        
        self.logger.error("REST API connection error",
                        component=self.component_name,
                        operation=context.operation,
                        host=host,
                        port=port,
                        connection_error=str(exception),
                        attempt=context.attempt)
        
        # Track connection issues for infrastructure monitoring
        self.logger.metric("rest_api_connection_error", 1,
                         tags={
                             "component": self.component_name,
                             "host": str(host),
                             "port": str(port)
                         })
        
        # Apply longer backoff for connection issues
        await asyncio.sleep(2.0)
    
    async def _handle_json_error(
        self, 
        exception: json.JSONDecodeError, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle JSON parsing errors in API responses."""
        doc_preview = getattr(exception, 'doc', '')[:100] + '...' if hasattr(exception, 'doc') else 'unknown'
        
        self.logger.warning("REST API JSON decode error",
                          component=self.component_name,
                          operation=context.operation,
                          json_error=str(exception),
                          response_preview=doc_preview,
                          attempt=context.attempt)
        
        # Track API response quality issues
        self.logger.metric("rest_api_json_error", 1,
                         tags={"component": self.component_name})
    
    async def _handle_missing_field(
        self, 
        exception: KeyError, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle missing required fields in API responses."""
        missing_field = str(exception).strip("'\"")
        
        self.logger.warning("REST API response missing required field",
                          component=self.component_name,
                          operation=context.operation,
                          missing_field=missing_field,
                          attempt=context.attempt)
        
        # Track API schema compliance issues
        self.logger.metric("rest_api_missing_field", 1,
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
        """Handle value conversion errors in API response processing."""
        self.logger.warning("REST API value conversion error",
                          component=self.component_name,
                          operation=context.operation,
                          value_error=str(exception),
                          attempt=context.attempt)
        
        # Track data quality issues
        self.logger.metric("rest_api_value_error", 1,
                         tags={"component": self.component_name})
    
    # Status code specific handlers
    
    async def _handle_bad_request(
        self, 
        exception: ClientResponseError, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle 400 Bad Request errors."""
        self.logger.error("REST API bad request",
                        component=self.component_name,
                        operation=context.operation,
                        request_data=context.metadata,
                        attempt=context.attempt)
        
        # Bad requests typically don't benefit from retry
        # Set max retries to 1 to avoid unnecessary attempts
        context.max_retries = 1
    
    async def _handle_unauthorized(
        self, 
        exception: ClientResponseError, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle 401 Unauthorized errors with auth refresh."""
        self.logger.error("REST API unauthorized",
                        component=self.component_name,
                        operation=context.operation,
                        attempt=context.attempt)
        
        # Track authentication issues
        self.logger.metric("rest_api_unauthorized", 1,
                         tags={"component": self.component_name})
        
        # Trigger auth refresh if callback available
        if hasattr(context, 'auth_refresh_callback') and context.auth_refresh_callback:
            try:
                await context.auth_refresh_callback()
                self.logger.info("Authentication refresh triggered",
                               component=self.component_name)
            except Exception as auth_error:
                self.logger.error("Authentication refresh failed",
                                component=self.component_name,
                                auth_error=str(auth_error))
    
    async def _handle_forbidden(
        self, 
        exception: ClientResponseError, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle 403 Forbidden errors."""
        self.logger.error("REST API forbidden",
                        component=self.component_name,
                        operation=context.operation,
                        attempt=context.attempt)
        
        # Forbidden typically means permanent denial - don't retry
        context.max_retries = 1
    
    async def _handle_not_found(
        self, 
        exception: ClientResponseError, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle 404 Not Found errors."""
        self.logger.warning("REST API not found",
                          component=self.component_name,
                          operation=context.operation,
                          endpoint=context.metadata.get('endpoint') if context.metadata else None,
                          attempt=context.attempt)
        
        # Not found typically doesn't benefit from retry
        context.max_retries = 1
    
    async def _handle_rate_limited(
        self, 
        exception: ClientResponseError, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle 429 Rate Limited errors with intelligent backoff."""
        # Try to extract retry-after header
        retry_after = None
        if hasattr(exception, 'headers') and exception.headers:
            retry_after = exception.headers.get('Retry-After')
        
        operation_type = context.metadata.get('operation_type', 'generic') if context.metadata else 'generic'
        
        if retry_after:
            delay = float(retry_after)
        else:
            delay = self._rate_limit_backoffs.get(operation_type, 1.0)
        
        self.logger.warning("REST API rate limited",
                          component=self.component_name,
                          operation=context.operation,
                          operation_type=operation_type,
                          retry_after=delay,
                          attempt=context.attempt)
        
        # Track rate limiting patterns
        self.logger.metric("rest_api_rate_limited", 1,
                         tags={
                             "component": self.component_name,
                             "operation_type": operation_type
                         })
        
        # Apply backoff
        await asyncio.sleep(delay)
    
    async def _handle_server_error(
        self, 
        exception: ClientResponseError, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle 500 Internal Server Error."""
        self.logger.error("REST API server error",
                        component=self.component_name,
                        operation=context.operation,
                        attempt=context.attempt)
        
        # Track server stability issues
        self.logger.metric("rest_api_server_error", 1,
                         tags={"component": self.component_name})
        
        # Server errors may be transient - apply backoff
        await asyncio.sleep(1.0)
    
    async def _handle_bad_gateway(
        self, 
        exception: ClientResponseError, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle 502 Bad Gateway errors."""
        self.logger.error("REST API bad gateway",
                        component=self.component_name,
                        operation=context.operation,
                        attempt=context.attempt)
        
        # Bad gateway may indicate proxy/load balancer issues
        await asyncio.sleep(2.0)
    
    async def _handle_service_unavailable(
        self, 
        exception: ClientResponseError, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle 503 Service Unavailable errors."""
        self.logger.error("REST API service unavailable",
                        component=self.component_name,
                        operation=context.operation,
                        attempt=context.attempt)
        
        # Service unavailable may indicate maintenance
        await asyncio.sleep(5.0)
    
    async def _handle_gateway_timeout(
        self, 
        exception: ClientResponseError, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle 504 Gateway Timeout errors."""
        self.logger.error("REST API gateway timeout",
                        component=self.component_name,
                        operation=context.operation,
                        attempt=context.attempt)
        
        # Gateway timeouts may indicate overload
        await asyncio.sleep(3.0)