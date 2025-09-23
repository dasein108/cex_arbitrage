"""
Enhanced Base Message Parser with Common Functionality

Consolidates common parsing patterns from exchange implementations to eliminate
code duplication while maintaining HFT performance requirements.

HFT COMPLIANT: Zero-allocation patterns, <1ms parsing latency.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, AsyncIterator

from core.transport.websocket.structs import ParsedMessage, MessageType
from core.transport.websocket.error_handling import BaseMessageErrorHandler
from core.structs.common import Symbol, OrderBookEntry
from core.exchanges.services import BaseExchangeMapper

# HFT Logger Integration
from core.logging import get_strategy_logger, HFTLoggerInterface, LoggingTimer


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
    
    def __init__(self, mapper: BaseExchangeMapper, exchange_name: str = "unknown", logger: Optional[HFTLoggerInterface] = None):
        """
        Initialize enhanced parser with unified components.
        
        Args:
            mapper: Exchange mappings interface for symbol conversion (mandatory)
            exchange_name: Name of exchange for error tracking
            logger: Optional injected HFT logger
        """
        self.mapper = mapper
        self.exchange_name = exchange_name
        
        # Use injected logger or create strategy-specific logger
        if logger is None:
            # Create hierarchical tags for enhanced message parser
            tags = [exchange_name.lower(), 'public', 'ws', 'message_parser']
            logger = get_strategy_logger('ws.message_parser.enhanced', tags)
        
        self.logger = logger
        
        # Initialize unified error handler with HFT logger
        self.error_handler = BaseMessageErrorHandler(exchange_name, self.logger)
        
        # Log initialization with structured data
        self.logger.info("EnhancedBaseMessageParser initialized",
                        exchange=exchange_name,
                        has_mapper=mapper is not None)
        
        # Track component initialization metrics
        self.logger.metric("ws_enhanced_parsers_initialized", 1,
                          tags={"exchange": exchange_name})
    
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
        batch_size = len(raw_messages)
        
        # Track batch parsing performance
        with LoggingTimer(self.logger, "ws_batch_message_parsing") as timer:
            self.logger.debug("Starting batch message parsing",
                            exchange=self.exchange_name,
                            batch_size=batch_size)
            
            parsed_count = 0
            error_count = 0
            
            for raw_message in raw_messages:
                try:
                    parsed = await self.parse_message(raw_message)
                    if parsed:
                        parsed_count += 1
                        yield parsed
                except Exception as e:
                    error_count += 1
                    # Use unified error handler for batch parsing errors
                    error_msg = self.error_handler.handle_parsing_exception(
                        exception=e,
                        context="batch message parsing",
                        raw_data={"message": raw_message}
                    )
                    yield error_msg
            
            # Log batch processing metrics
            self.logger.info("Batch message parsing completed",
                           exchange=self.exchange_name,
                           batch_size=batch_size,
                           parsed_count=parsed_count,
                           error_count=error_count,
                           processing_time_ms=timer.elapsed_ms)
            
            # Track batch processing metrics
            self.logger.metric("ws_batch_messages_processed", batch_size,
                              tags={"exchange": self.exchange_name})
            
            self.logger.metric("ws_batch_messages_parsed", parsed_count,
                              tags={"exchange": self.exchange_name, "status": "success"})
            
            if error_count > 0:
                self.logger.metric("ws_batch_messages_parsed", error_count,
                                  tags={"exchange": self.exchange_name, "status": "error"})
            
            self.logger.metric("ws_batch_parsing_duration_ms", timer.elapsed_ms,
                              tags={"exchange": self.exchange_name})
    
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
                    self.logger.debug("Symbol extracted from channel",
                                    exchange=self.exchange_name,
                                    channel=channel,
                                    extracted_symbol=potential_symbol)
                    return potential_symbol
        except Exception as e:
            self.logger.debug("Failed to extract symbol from channel",
                            exchange=self.exchange_name,
                            channel=channel,
                            error_message=str(e))
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