"""
Common utilities for WebSocket message parsing across all exchanges.

Provides standardized JSON decoding, logging, context tracking,
and error handling patterns to eliminate duplication in message parsers.
"""

from typing import Dict, Any, Optional, List, Callable
import msgspec
import time
from abc import ABC, abstractmethod

from infrastructure.logging.interfaces import HFTLoggerInterface
from infrastructure.networking.websocket.structs import ParsedMessage, MessageType
from exchanges.structs.common import Symbol


class MessageParsingUtils:
    """
    Common utilities for WebSocket message parsing across all exchanges.
    
    Provides standardized JSON decoding, logging, context tracking,
    and error handling patterns to eliminate duplication in message parsers.
    """
    
    @staticmethod
    def safe_json_decode(raw_message: str, 
                        logger: Optional[HFTLoggerInterface] = None,
                        exchange: str = "unknown") -> Optional[Dict[str, Any]]:
        """
        Safely decode JSON message with standardized error handling.
        
        Args:
            raw_message: Raw JSON string to decode
            logger: Logger instance for error reporting
            exchange: Exchange name for context in logs
            
        Returns:
            Decoded message dict or None if parsing fails
        """
        try:
            return msgspec.json.decode(raw_message)
            
        except msgspec.DecodeError as e:
            if logger:
                logger.error(f"msgspec decode failed: {e}",
                           exchange=exchange,
                           error_type="msgspec_decode_error",
                           message_length=len(raw_message))
                # Log truncated message for debugging
                logger.debug(f"Failed message: {raw_message[:200]}...",
                           exchange=exchange)
            return None
            
        except ValueError as e:
            if logger:
                logger.error(f"JSON decode failed: {e}",
                           exchange=exchange,
                           error_type="json_decode_error",
                           message_length=len(raw_message))
                logger.debug(f"Failed message: {raw_message[:200]}...",
                           exchange=exchange)
            return None
            
        except Exception as e:
            if logger:
                logger.error(f"Unexpected parsing error: {e}",
                           exchange=exchange,
                           error_type=type(e).__name__,
                           message_length=len(raw_message))
            return None
    
    @staticmethod
    def create_error_response(error_msg: str, 
                            channel: str = "", 
                            data: Any = None,
                            error_type: str = "parse_error") -> ParsedMessage:
        """
        Create standardized error response message.
        
        Args:
            error_msg: Human-readable error description
            channel: WebSocket channel where error occurred
            data: Original data that caused the error
            error_type: Classification of error type
            
        Returns:
            ParsedMessage with ERROR type and structured error data
        """
        error_data = {
            "error_message": error_msg,
            "error_type": error_type,
            "original_data": data
        }
        
        return ParsedMessage(
            message_type=MessageType.ERROR,
            channel=channel,
            raw_data=error_data
        )
    
    @staticmethod
    def create_subscription_response(channel: str,
                                   status: str,
                                   raw_data: Dict[str, Any],
                                   symbol: Optional[Symbol] = None) -> ParsedMessage:
        """Create standardized subscription confirmation response."""
        return ParsedMessage(
            message_type=MessageType.SUBSCRIPTION_CONFIRM,
            channel=channel,
            symbol=symbol,
            data={"action": "subscribe", "status": status},
            raw_data=raw_data
        )
    
    @staticmethod
    def create_heartbeat_response(raw_data: Dict[str, Any]) -> ParsedMessage:
        """Create standardized heartbeat response."""
        return ParsedMessage(
            message_type=MessageType.HEARTBEAT,
            raw_data=raw_data
        )
    
    @staticmethod
    def log_parsing_context(logger: Optional[HFTLoggerInterface],
                          exchange: str,
                          message_type: str,
                          raw_message: str,
                          max_length: int = 200) -> None:
        """
        Log parsing context for debugging with length limits.
        
        Args:
            logger: Logger instance
            exchange: Exchange name
            message_type: Type of message being parsed
            raw_message: Original message content
            max_length: Maximum length to log
        """
        if not logger:
            return
        
        # Truncate long messages
        message_preview = raw_message
        if len(message_preview) > max_length:
            message_preview = message_preview[:max_length] + "..."
        
        logger.debug(f"Parsing {exchange} {message_type}",
                    exchange=exchange,
                    message_type=message_type,
                    message_length=len(raw_message),
                    message_preview=message_preview)
    
    @staticmethod
    def validate_required_fields(data: Dict[str, Any],
                                required_fields: List[str],
                                context: str = "") -> Optional[str]:
        """
        Validate that required fields are present in message data.
        
        Args:
            data: Message data to validate
            required_fields: List of required field names
            context: Context description for error messages
            
        Returns:
            Error message if validation fails, None if successful
        """
        missing_fields = []
        
        for field in required_fields:
            if field not in data or data[field] is None:
                missing_fields.append(field)
        
        if missing_fields:
            context_str = f" in {context}" if context else ""
            return f"Missing required fields{context_str}: {', '.join(missing_fields)}"
        
        return None
    
    @staticmethod
    def extract_timestamp(data: Dict[str, Any],
                         timestamp_fields: List[str] = None,
                         default_scale: str = "ms") -> int:
        """
        Extract timestamp from message data with multiple fallback strategies.
        
        Args:
            data: Message data
            timestamp_fields: Field names to check (in priority order)
            default_scale: Default time scale ('s', 'ms', 'us')
            
        Returns:
            Timestamp in milliseconds
        """
        if timestamp_fields is None:
            timestamp_fields = ['t', 'timestamp', 'time', 'create_time_ms', 'create_time']
        
        for field in timestamp_fields:
            if field in data and data[field] is not None:
                timestamp = data[field]
                
                # Handle different timestamp formats
                if isinstance(timestamp, (int, float)):
                    # Detect scale based on magnitude
                    if timestamp > 1e12:  # Microseconds
                        return int(timestamp / 1000)
                    elif timestamp > 1e10:  # Milliseconds
                        return int(timestamp)
                    else:  # Seconds
                        return int(timestamp * 1000)
                
                # Handle string timestamps
                elif isinstance(timestamp, str):
                    try:
                        timestamp_num = float(timestamp)
                        return MessageParsingUtils.extract_timestamp(
                            {field: timestamp_num}, [field], default_scale
                        )
                    except (ValueError, TypeError):
                        continue
        
        # Return current time if no timestamp found
        return int(time.time() * 1000)


class ExchangeMessageHandler(ABC):
    """
    Abstract base class for exchange-specific message handling.
    
    Provides common patterns while allowing exchange-specific customization
    of symbol conversion, channel parsing, and data transformation.
    """
    
    def __init__(self, 
                 exchange_name: str,
                 logger: Optional[HFTLoggerInterface] = None):
        """Initialize exchange message handler."""
        self.exchange_name = exchange_name
        self.logger = logger
        self.parsing_utils = MessageParsingUtils()
    
    @abstractmethod
    def convert_symbol(self, symbol_str: str) -> Optional[Symbol]:
        """Convert exchange-specific symbol string to unified Symbol."""
        pass
    
    @abstractmethod
    def get_channel_symbol_fields(self, channel: str) -> List[str]:
        """Get symbol field names for specific channel type."""
        pass
    
    @abstractmethod
    def extract_symbol_from_channel(self, channel: str) -> Optional[str]:
        """Extract symbol string from channel name."""
        pass
    
    def safe_extract_symbol(self, 
                          data: Dict[str, Any],
                          channel: str = "",
                          symbol_fields: Optional[List[str]] = None) -> Optional[Symbol]:
        """
        Safely extract symbol using exchange-specific logic and common patterns.
        
        Template method that uses exchange-specific symbol conversion
        but follows common extraction patterns.
        """
        # Use exchange-specific symbol fields if not provided
        if symbol_fields is None:
            symbol_fields = self.get_channel_symbol_fields(channel)
        
        # Try each symbol field
        for field in symbol_fields:
            symbol_str = data.get(field)
            if symbol_str:
                try:
                    symbol = self.convert_symbol(symbol_str)
                    if symbol:
                        return symbol
                except Exception as e:
                    if self.logger:
                        self.logger.debug(f"Symbol conversion failed for field '{field}': {e}",
                                        exchange=self.exchange_name,
                                        field=field,
                                        symbol_str=symbol_str)
                    continue
        
        # Fallback: extract from channel
        if channel:
            channel_symbol_str = self.extract_symbol_from_channel(channel)
            if channel_symbol_str:
                try:
                    return self.convert_symbol(channel_symbol_str)
                except Exception as e:
                    if self.logger:
                        self.logger.debug(f"Channel symbol conversion failed: {e}",
                                        exchange=self.exchange_name,
                                        channel=channel,
                                        symbol_str=channel_symbol_str)
        
        return None
    
    def create_parse_error(self, 
                         error_msg: str,
                         channel: str = "",
                         data: Any = None) -> ParsedMessage:
        """Create exchange-specific parse error with consistent format."""
        return self.parsing_utils.create_error_response(
            error_msg=f"{self.exchange_name}: {error_msg}",
            channel=channel,
            data=data,
            error_type=f"{self.exchange_name}_parse_error"
        )