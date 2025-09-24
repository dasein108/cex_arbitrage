"""
Unified WebSocket Error Handling

Provides standardized error processing for WebSocket message parsing,
subscription management, and exception handling across all exchanges.

HFT COMPLIANT: Minimal allocation error processing with correlation tracking.
"""

import logging
import time
from typing import Dict, Any, Optional, Union
from abc import ABC

from infrastructure.networking.websocket.structs import ParsedMessage, MessageType
from infrastructure.exceptions.unified import (
    UnifiedParsingError, 
    UnifiedSubscriptionError, 
    ErrorType
)


class BaseMessageErrorHandler(ABC):
    """
    Unified error handler for WebSocket message processing.
    
    Provides standardized error response creation, logging, and correlation
    tracking across all exchange implementations. Eliminates code duplication
    in error handling patterns.
    """
    
    def __init__(self, exchange_name: str, logger: Optional[logging.Logger] = None):
        """
        Initialize error handler.
        
        Args:
            exchange_name: Name of the exchange (e.g., 'mexc', 'gateio')
            logger: Optional logger instance (creates one if not provided)
        """
        self.exchange_name = exchange_name
        self.logger = logger or logging.getLogger(f"{__name__}.{exchange_name}")
    
    def create_error_response(
        self, 
        error_type: str, 
        message: str, 
        channel: Optional[str] = None, 
        symbol: Optional[str] = None,
        data: Optional[Any] = None,
        raw_data: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None
    ) -> ParsedMessage:
        """
        Create standardized error response message.
        
        Args:
            error_type: Type of error (parsing, subscription, etc.)
            message: Error message
            channel: WebSocket channel where error occurred
            symbol: Trading symbol related to error
            data: Error data payload
            raw_data: Original raw message data
            correlation_id: Optional correlation ID for tracking
            
        Returns:
            ParsedMessage with error information
        """
        # Create structured error data
        error_data = {
            "error_type": error_type,
            "error_message": message,
            "exchange": self.exchange_name,
            "correlation_id": correlation_id or self._generate_correlation_id(),
            "timestamp": time.time()
        }
        
        # Add additional data if provided
        if data:
            error_data.update(data if isinstance(data, dict) else {"data": data})
            
        return ParsedMessage(
            message_type=MessageType.ERROR,
            channel=channel,
            symbol=None,  # Symbol parsing failed, so don't include it
            data=error_data,
            raw_data=raw_data or {}
        )
    
    def handle_subscription_error(
        self, 
        message: Dict[str, Any], 
        channel: Optional[str] = None
    ) -> ParsedMessage:
        """
        Handle subscription error responses with unified processing.
        
        Args:
            message: Raw subscription response message
            channel: WebSocket channel
            
        Returns:
            ParsedMessage with standardized error information
        """
        # Extract error information using common patterns
        error_info = self._extract_error_info(message)
        
        # Create unified error
        error = UnifiedSubscriptionError(
            exchange=self.exchange_name,
            message=f"Subscription failed: {error_info['message']}",
            channel=channel,
            raw_data=message,
            error_code=error_info.get('code'),
            status=error_info.get('status')
        )
        
        # Log with correlation tracking
        self.log_structured_error(error)
        
        # Create error response
        return self.create_error_response(
            error_type="subscription",
            message=error.message,
            channel=channel,
            data={
                "error_code": error_info.get('code', 'unknown'),
                "status": error_info.get('status', 'failed')
            },
            raw_data=message,
            correlation_id=error.correlation_id
        )
    
    def handle_parsing_exception(
        self, 
        exception: Exception, 
        context: str,
        channel: Optional[str] = None,
        raw_data: Optional[Dict[str, Any]] = None
    ) -> ParsedMessage:
        """
        Handle parsing exceptions with unified processing.
        
        Args:
            exception: Exception that occurred during parsing
            context: Context where the error occurred (e.g., 'orderbook parsing')
            channel: WebSocket channel
            raw_data: Original raw message data
            
        Returns:
            ParsedMessage with standardized error information
        """
        # Create unified parsing error
        error = UnifiedParsingError(
            exchange=self.exchange_name,
            message=f"Failed to parse {context}: {str(exception)}",
            channel=channel,
            raw_data=raw_data,
            exception_type=type(exception).__name__,
            context=context
        )
        
        # Log with correlation tracking
        self.log_structured_error(error)
        
        # Create error response
        return self.create_error_response(
            error_type="parsing",
            message=error.message,
            channel=channel,
            data={
                "exception_type": type(exception).__name__,
                "context": context
            },
            raw_data=raw_data,
            correlation_id=error.correlation_id
        )
    
    def log_structured_error(self, error: Union[Exception, Dict[str, Any]]) -> None:
        """
        Log error with structured information and correlation tracking.
        
        Args:
            error: Error object or dictionary to log
        """
        if hasattr(error, 'to_dict'):
            # Unified error object
            error_dict = error.to_dict()
            self.logger.error(
                f"[{error_dict['correlation_id']}] {self.exchange_name} {error_dict['error_type']}: {error_dict['message']}",
                extra={"error_details": error_dict}
            )
        elif isinstance(error, dict):
            # Dictionary error info
            correlation_id = error.get('correlation_id', 'unknown')
            self.logger.error(
                f"[{correlation_id}] {self.exchange_name}: {error.get('message', 'Unknown error')}",
                extra={"error_details": error}
            )
        else:
            # Fallback for other error types
            self.logger.error(f"{self.exchange_name}: {str(error)}")
    
    def _extract_error_info(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract error information from message using common patterns.
        
        Handles different error response formats across exchanges.
        
        Args:
            message: Raw message dictionary
            
        Returns:
            Dictionary with extracted error information
        """
        error_info = {}
        
        # Pattern 1: Direct error field (Gate.io style)
        if "error" in message:
            error = message["error"]
            if isinstance(error, dict):
                error_info["code"] = error.get("code", "unknown")
                error_info["message"] = error.get("message", "unknown error")
            else:
                error_info["message"] = str(error)
        
        # Pattern 2: Result status field (Gate.io style)
        elif "result" in message:
            result = message["result"]
            if isinstance(result, dict):
                status = result.get("status", "unknown")
                if status == "fail":
                    error_info["status"] = "failed"
                    error_info["message"] = result.get("message", "subscription failed")
                else:
                    error_info["status"] = status
                    error_info["message"] = f"unexpected status: {status}"
        
        # Pattern 3: Code field (MEXC style)
        elif "code" in message:
            code = message["code"]
            if code != 200:  # Success code
                error_info["code"] = code
                error_info["message"] = message.get("msg", f"error code {code}")
        
        # Pattern 4: Direct message field
        elif "msg" in message:
            error_info["message"] = message["msg"]
        
        # Fallback
        else:
            error_info["message"] = "unknown error format"
            error_info["raw_message"] = message
            
        return error_info
    
    def _generate_correlation_id(self) -> str:
        """Generate correlation ID for error tracking."""
        import uuid
        return f"{self.exchange_name}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"