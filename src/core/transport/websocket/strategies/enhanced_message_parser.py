"""
Enhanced Base Message Parser with Common Functionality

Consolidates common parsing patterns from exchange implementations to eliminate
code duplication while maintaining HFT performance requirements.

HFT COMPLIANT: Zero-allocation patterns, <1ms parsing latency.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, AsyncIterator, TYPE_CHECKING

from core.transport.websocket.structs import ParsedMessage, MessageType
from core.transport.websocket.error_handling import BaseMessageErrorHandler
from structs.common import OrderBook, Trade, BookTicker, Symbol, OrderBookEntry
from core.exchanges.services import BaseExchangeMapper


class EnhancedBaseMessageParser(ABC):
    """
    Enhanced base message parser with common functionality.
    
    Provides:
    - Unified error handling with correlation tracking
    - Common batch parsing implementation
    - Standard message type detection patterns
    - Shared parsing utilities
    - HFT-optimized data conversion helpers
    """
    
    def __init__(self, mapper: BaseExchangeMapper, exchange_name: str = "unknown"):
        """
        Initialize enhanced parser with unified components.
        
        Args:
            mapper: Exchange mappings interface for symbol conversion (mandatory)
            exchange_name: Name of exchange for error tracking
        """
        self.mapper = mapper
        self.exchange_name = exchange_name
        
        # Initialize logger with exchange-specific name
        self.logger = logging.getLogger(f"{self.__class__.__module__}.{self.__class__.__name__}")
        
        # Initialize unified error handler
        self.error_handler = BaseMessageErrorHandler(exchange_name, self.logger)
    
    @abstractmethod
    async def parse_message(self, raw_message: Any) -> Optional[ParsedMessage]:
        """
        Parse raw WebSocket message.
        
        Must be implemented by exchange-specific parsers.
        
        Args:
            raw_message: Raw message (string or bytes) from WebSocket
            
        Returns:
            ParsedMessage with extracted data, None if unparseable
        """
        pass
    
    async def parse_batch_messages(
        self,
        raw_messages: List[Any]
    ) -> AsyncIterator[ParsedMessage]:
        """
        Parse multiple messages efficiently with unified implementation.
        
        Args:
            raw_messages: List of raw messages
            
        Yields:
            ParsedMessage instances
        """
        for raw_message in raw_messages:
            try:
                parsed = await self.parse_message(raw_message)
                if parsed:
                    yield parsed
            except Exception as e:
                # Use unified error handler for batch parsing errors
                error_msg = self.error_handler.handle_parsing_exception(
                    exception=e,
                    context="batch message parsing",
                    raw_data={"message": raw_message}
                )
                yield error_msg
    
    def create_parsed_message(
        self,
        message_type: MessageType,
        symbol: Optional[Symbol] = None,
        channel: Optional[str] = None,
        data: Optional[Any] = None,
        raw_data: Optional[Dict[str, Any]] = None
    ) -> ParsedMessage:
        """
        Create standardized ParsedMessage with consistent structure.
        
        Args:
            message_type: Type of message
            symbol: Trading symbol (optional)
            channel: WebSocket channel (optional)
            data: Parsed data payload
            raw_data: Original raw message
            
        Returns:
            ParsedMessage with standardized format
        """
        return ParsedMessage(
            message_type=message_type,
            symbol=symbol,
            channel=channel,
            data=data,
            raw_data=raw_data or {}
        )
    
    def create_heartbeat_response(self, raw_data: Dict[str, Any]) -> ParsedMessage:
        """
        Create standardized heartbeat response.
        
        Args:
            raw_data: Original heartbeat message
            
        Returns:
            ParsedMessage with HEARTBEAT type
        """
        return self.create_parsed_message(
            message_type=MessageType.HEARTBEAT,
            raw_data=raw_data
        )
    
    def create_subscription_response(
        self,
        channel: str,
        status: str,
        raw_data: Dict[str, Any]
    ) -> ParsedMessage:
        """
        Create standardized subscription response.
        
        Args:
            channel: Subscription channel
            status: Subscription status (success/fail)
            raw_data: Original subscription message
            
        Returns:
            ParsedMessage with SUBSCRIPTION_CONFIRM type
        """
        return self.create_parsed_message(
            message_type=MessageType.SUBSCRIPTION_CONFIRM,
            channel=channel,
            data={"action": "subscribe", "status": status},
            raw_data=raw_data
        )
    
    def extract_symbol_from_channel(self, channel: str, separator: str = ".") -> Optional[str]:
        """
        Extract symbol from channel name using common patterns.
        
        Args:
            channel: Channel string (e.g., "spot.trades.BTCUSDT")
            separator: Channel separator character
            
        Returns:
            Symbol string if found, None otherwise
        """
        try:
            parts = channel.split(separator)
            if len(parts) > 0:
                # Usually symbol is the last part
                potential_symbol = parts[-1]
                # Check if it looks like a symbol (contains no special chars except underscore)
                if potential_symbol and (potential_symbol.replace('_', '').replace('-', '').isalnum()):
                    return potential_symbol
        except Exception:
            pass
        return None

    @abstractmethod
    def get_message_type(self, message: Dict[str, Any]) -> MessageType:
        """
        Detect message type from parsed JSON.
        
        Must be implemented by exchange-specific parsers as each
        exchange has different message type indicators.
        
        Args:
            message: Parsed JSON message
            
        Returns:
            Detected MessageType
        """
        pass
    
    def parse_price_size_array(
        self,
        data: List[List[Any]],
        create_entry_func=None
    ) -> List[OrderBookEntry]:
        """
        Parse array of [price, size] pairs with HFT optimization.
        
        Args:
            data: Array of price/size pairs
            create_entry_func: Optional function to create entries (for pooling)
            
        Returns:
            List of OrderBookEntry objects
        """
        entries = []
        for item in data:
            if isinstance(item, list) and len(item) >= 2:
                try:
                    price = float(item[0])
                    size = float(item[1])
                    
                    if create_entry_func:
                        entry = create_entry_func(price=price, size=size)
                    else:
                        entry = OrderBookEntry(price=price, size=size)
                    
                    entries.append(entry)
                except (ValueError, TypeError, IndexError):
                    continue
        return entries
    
    def safe_get_nested(
        self,
        data: Dict[str, Any],
        *keys: str,
        default: Any = None
    ) -> Any:
        """
        Safely get nested dictionary value with fallback.
        
        Args:
            data: Dictionary to search
            *keys: Sequence of keys to traverse
            default: Default value if not found
            
        Returns:
            Value if found, default otherwise
        """
        try:
            current = data
            for key in keys:
                if isinstance(current, dict):
                    current = current.get(key)
                    if current is None:
                        return default
                else:
                    return default
            return current
        except (KeyError, TypeError, AttributeError):
            return default
    
    def detect_format(self, raw_message: Any) -> str:
        """
        Detect message format (JSON, protobuf, etc.).
        
        Args:
            raw_message: Raw message to analyze
            
        Returns:
            Format type string ('json', 'protobuf', 'unknown')
        """
        # String that looks like JSON
        if isinstance(raw_message, str):
            if raw_message.strip().startswith(('{', '[')):
                return 'json'
            return 'unknown'
        
        # Bytes that might be protobuf
        elif isinstance(raw_message, bytes):
            # Common protobuf indicators
            if raw_message and raw_message[0] in (0x0a, 0x12, 0x1a):
                return 'protobuf'
            # Check if it's actually JSON in bytes
            try:
                decoded = raw_message.decode('utf-8')
                if decoded.strip().startswith(('{', '[')):
                    return 'json'
            except:
                pass
            return 'protobuf'
        
        # Already parsed dict
        elif isinstance(raw_message, dict):
            return 'json'
        
        return 'unknown'