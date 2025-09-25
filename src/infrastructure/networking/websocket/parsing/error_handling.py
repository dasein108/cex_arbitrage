"""
Centralized error handling for WebSocket message parsing.

Provides consistent error classification, logging, metrics collection,
and error response creation across all exchange implementations.
"""

from typing import Dict, Any, Optional, List, Callable
from enum import Enum
import traceback
import time

from infrastructure.logging.interfaces import HFTLoggerInterface
from infrastructure.networking.websocket.structs import ParsedMessage, MessageType


class ParseErrorType(Enum):
    """Classification of parsing error types."""
    JSON_DECODE_ERROR = "json_decode_error"
    MISSING_REQUIRED_FIELDS = "missing_required_fields"
    INVALID_DATA_FORMAT = "invalid_data_format"
    SYMBOL_CONVERSION_ERROR = "symbol_conversion_error"
    CHANNEL_PARSING_ERROR = "channel_parsing_error"
    EXCHANGE_API_ERROR = "exchange_api_error"
    UNKNOWN_MESSAGE_TYPE = "unknown_message_type"
    TRANSFORMATION_ERROR = "transformation_error"


class WebSocketErrorHandler:
    """
    Centralized error handling for WebSocket message parsing.
    
    Provides consistent error classification, logging, metrics collection,
    and error response creation across all exchange implementations.
    """
    
    def __init__(self, 
                 exchange_name: str,
                 logger: Optional[HFTLoggerInterface] = None):
        """Initialize error handler for specific exchange."""
        self.exchange_name = exchange_name
        self.logger = logger
        
        # Error tracking
        self._error_counts: Dict[ParseErrorType, int] = {}
        self._recent_errors: List[Dict[str, Any]] = []
        self._max_recent_errors = 50
        
        # Error callbacks for custom handling
        self._error_callbacks: Dict[ParseErrorType, List[Callable]] = {}
    
    def handle_json_decode_error(self, 
                               raw_message: str, 
                               error: Exception,
                               context: str = "") -> ParsedMessage:
        """Handle JSON decoding errors with proper classification."""
        error_type = ParseErrorType.JSON_DECODE_ERROR
        
        error_msg = f"Failed to decode JSON message: {str(error)}"
        if context:
            error_msg = f"{error_msg} (context: {context})"
        
        self._log_and_track_error(
            error_type=error_type,
            error_msg=error_msg,
            raw_data=raw_message[:500],  # Truncate long messages
            exception=error
        )
        
        return self._create_error_response(
            error_type=error_type,
            error_msg=error_msg,
            raw_data={"raw_message": raw_message[:200], "error_details": str(error)}
        )
    
    def handle_missing_fields_error(self, 
                                  missing_fields: List[str],
                                  data: Dict[str, Any],
                                  context: str = "") -> ParsedMessage:
        """Handle missing required fields errors."""
        error_type = ParseErrorType.MISSING_REQUIRED_FIELDS
        
        error_msg = f"Missing required fields: {', '.join(missing_fields)}"
        if context:
            error_msg = f"{error_msg} (context: {context})"
        
        self._log_and_track_error(
            error_type=error_type,
            error_msg=error_msg,
            raw_data=data,
            additional_data={"missing_fields": missing_fields, "context": context}
        )
        
        return self._create_error_response(
            error_type=error_type,
            error_msg=error_msg,
            raw_data={"data": data, "missing_fields": missing_fields}
        )
    
    def handle_symbol_conversion_error(self, 
                                     symbol_str: str,
                                     error: Exception,
                                     context: str = "") -> ParsedMessage:
        """Handle symbol conversion errors."""
        error_type = ParseErrorType.SYMBOL_CONVERSION_ERROR
        
        error_msg = f"Failed to convert symbol '{symbol_str}': {str(error)}"
        if context:
            error_msg = f"{error_msg} (context: {context})"
        
        self._log_and_track_error(
            error_type=error_type,
            error_msg=error_msg,
            raw_data=symbol_str,
            exception=error,
            additional_data={"symbol_str": symbol_str, "context": context}
        )
        
        return self._create_error_response(
            error_type=error_type,
            error_msg=error_msg,
            raw_data={"symbol_str": symbol_str, "error_details": str(error)}
        )
    
    def handle_subscription_error(self, 
                                message: Dict[str, Any],
                                channel: str,
                                error_details: Optional[Dict[str, Any]] = None) -> ParsedMessage:
        """Handle WebSocket subscription errors."""
        error_type = ParseErrorType.EXCHANGE_API_ERROR
        
        # Extract error information from message
        error_info = message.get('error', {})
        error_code = error_info.get('code', 'unknown')
        error_message = error_info.get('message', 'Subscription failed')
        
        error_msg = f"Subscription error for channel '{channel}': {error_message} (code: {error_code})"
        
        self._log_and_track_error(
            error_type=error_type,
            error_msg=error_msg,
            raw_data=message,
            additional_data={
                "channel": channel,
                "error_code": error_code,
                "error_message": error_message,
                "error_details": error_details
            }
        )
        
        return self._create_error_response(
            error_type=error_type,
            error_msg=error_msg,
            channel=channel,
            raw_data=message
        )
    
    def handle_transformation_error(self, 
                                  data: Dict[str, Any],
                                  error: Exception,
                                  transformation_type: str,
                                  context: str = "") -> ParsedMessage:
        """Handle data transformation errors."""
        error_type = ParseErrorType.TRANSFORMATION_ERROR
        
        error_msg = f"Failed to transform {transformation_type}: {str(error)}"
        if context:
            error_msg = f"{error_msg} (context: {context})"
        
        self._log_and_track_error(
            error_type=error_type,
            error_msg=error_msg,
            raw_data=data,
            exception=error,
            additional_data={
                "transformation_type": transformation_type,
                "context": context
            }
        )
        
        return self._create_error_response(
            error_type=error_type,
            error_msg=error_msg,
            raw_data={"data": data, "transformation_type": transformation_type}
        )
    
    def handle_unknown_message_type(self, 
                                  message: Dict[str, Any],
                                  context: str = "") -> ParsedMessage:
        """Handle unknown message types."""
        error_type = ParseErrorType.UNKNOWN_MESSAGE_TYPE
        
        message_event = message.get('event', 'unknown')
        message_channel = message.get('channel', 'unknown')
        
        error_msg = f"Unknown message type - event: {message_event}, channel: {message_channel}"
        if context:
            error_msg = f"{error_msg} (context: {context})"
        
        self._log_and_track_error(
            error_type=error_type,
            error_msg=error_msg,
            raw_data=message,
            additional_data={
                "event": message_event,
                "channel": message_channel,
                "context": context
            }
        )
        
        return self._create_error_response(
            error_type=error_type,
            error_msg=error_msg,
            raw_data=message
        )
    
    def _log_and_track_error(self, 
                           error_type: ParseErrorType,
                           error_msg: str,
                           raw_data: Any,
                           exception: Optional[Exception] = None,
                           additional_data: Optional[Dict[str, Any]] = None) -> None:
        """Log error and update tracking metrics."""
        # Update error counts
        if error_type not in self._error_counts:
            self._error_counts[error_type] = 0
        self._error_counts[error_type] += 1
        
        # Create error record
        error_record = {
            "timestamp": time.time(),
            "exchange": self.exchange_name,
            "error_type": error_type.value,
            "error_message": error_msg,
            "exception_type": type(exception).__name__ if exception else None,
            "exception_message": str(exception) if exception else None,
            "additional_data": additional_data or {}
        }
        
        # Store recent error
        self._recent_errors.append(error_record)
        if len(self._recent_errors) > self._max_recent_errors:
            self._recent_errors.pop(0)
        
        # Log error
        if self.logger:
            log_data = {
                "exchange": self.exchange_name,
                "error_type": error_type.value,
                "error_message": error_msg
            }
            
            if additional_data:
                log_data.update(additional_data)
            
            if exception:
                log_data["exception_type"] = type(exception).__name__
                log_data["exception_message"] = str(exception)
                
                # Log full traceback for debugging
                self.logger.debug(f"Full traceback for {error_type.value}",
                                exchange=self.exchange_name,
                                traceback=traceback.format_exc())
            
            self.logger.error(f"WebSocket parsing error: {error_msg}", **log_data)
            
            # Log metrics
            self.logger.metric("websocket_parse_errors", 1,
                             tags={
                                 "exchange": self.exchange_name,
                                 "error_type": error_type.value
                             })
        
        # Call registered callbacks
        if error_type in self._error_callbacks:
            for callback in self._error_callbacks[error_type]:
                try:
                    callback(error_record)
                except Exception as callback_error:
                    if self.logger:
                        self.logger.error(f"Error callback failed: {callback_error}",
                                        exchange=self.exchange_name,
                                        callback_error=str(callback_error))
    
    def _create_error_response(self, 
                             error_type: ParseErrorType,
                             error_msg: str,
                             channel: str = "",
                             raw_data: Any = None) -> ParsedMessage:
        """Create standardized error response."""
        error_data = {
            "exchange": self.exchange_name,
            "error_type": error_type.value,
            "error_message": error_msg,
            "timestamp": time.time()
        }
        
        if raw_data is not None:
            error_data["original_data"] = raw_data
        
        return ParsedMessage(
            message_type=MessageType.ERROR,
            channel=channel,
            raw_data=error_data
        )
    
    def register_error_callback(self, 
                              error_type: ParseErrorType,
                              callback: Callable[[Dict[str, Any]], None]) -> None:
        """Register callback for specific error type."""
        if error_type not in self._error_callbacks:
            self._error_callbacks[error_type] = []
        self._error_callbacks[error_type].append(callback)
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """Get error statistics and recent error information."""
        total_errors = sum(self._error_counts.values())
        
        return {
            "exchange": self.exchange_name,
            "total_errors": total_errors,
            "error_counts_by_type": {
                error_type.value: count 
                for error_type, count in self._error_counts.items()
            },
            "error_rates_by_type": {
                error_type.value: (count / total_errors if total_errors > 0 else 0)
                for error_type, count in self._error_counts.items()
            },
            "recent_errors_count": len(self._recent_errors),
            "most_recent_errors": self._recent_errors[-5:] if self._recent_errors else []
        }
    
    def reset_statistics(self) -> None:
        """Reset error tracking statistics."""
        self._error_counts.clear()
        self._recent_errors.clear()