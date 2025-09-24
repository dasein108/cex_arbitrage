"""
Unified WebSocket Message Parser

Consolidates all message parsing functionality with enhanced features
for HFT trading system requirements.

HFT COMPLIANT: Zero-allocation patterns, <1ms parsing latency.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, AsyncIterator

from infrastructure.networking.websocket.structs import ParsedMessage, MessageType
from infrastructure.data_structures.common import Symbol, OrderBookEntry
from exchanges.services import BaseExchangeMapper

# HFT Logger Integration
from infrastructure.logging import get_strategy_logger, HFTLoggerInterface, LoggingTimer


class MessageParser(ABC):
    """
    Unified WebSocket message parser with common functionality.
    
    Provides:
    - Unified error handling with correlation tracking
    - Common batch parsing implementation
    - Standard message type detection patterns
    - Shared parsing utilities
    - HFT-optimized data conversion helpers
    - Logger injection pattern for structured logging
    
    HFT COMPLIANT: <1ms message processing, zero-copy where possible.
    """
    
    def __init__(self, mapper: BaseExchangeMapper, logger: HFTLoggerInterface):
        """
        Initialize unified parser with all necessary components.
        
        Args:
            mapper: Exchange mappings interface for symbol conversion (mandatory)
            logger: HFT logger instance (mandatory)
        """
        if mapper is None:
            raise ValueError("mapper is required for MessageParser initialization")
        if logger is None:
            raise ValueError("logger is required for MessageParser initialization")
            
        self.mapper = mapper
        self.logger = logger
        
        # Log initialization with structured data
        self.logger.info("MessageParser initialized", has_mapper=mapper is not None)

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
            self.logger.debug("Starting batch message parsing", batch_size=batch_size)
            
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
                    self.logger.error("Message parsing error", error=str(e))
            
            # Log batch processing metrics
            self.logger.info("Batch message parsing completed",
                           batch_size=batch_size,
                           parsed_count=parsed_count,
                           error_count=error_count,
                           processing_time_ms=timer.elapsed_ms)
            
            # Track batch processing metrics
            self.logger.metric("ws_batch_messages_processed", batch_size)
            
            self.logger.metric("ws_batch_messages_parsed", parsed_count)
            
            if error_count > 0:
                self.logger.metric("ws_batch_parsing_errors", error_count)
            
            self.logger.metric("ws_batch_parsing_duration_ms", timer.elapsed_ms)
    
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
    
