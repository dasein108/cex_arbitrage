from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, AsyncIterator

from core.cex.websocket.structs import ParsedMessage, MessageType
from structs.exchange import OrderBook


class MessageParser(ABC):
    """
    Strategy for WebSocket message parsing.

    Handles message parsing, type detection, and data conversion.
    HFT COMPLIANT: <1ms message processing, zero-copy where possible.
    """

    @abstractmethod
    async def parse_message(self, raw_message: str) -> Optional[ParsedMessage]:
        """
        Parse raw WebSocket message.

        Args:
            raw_message: Raw message string from WebSocket

        Returns:
            ParsedMessage with extracted data, None if unparseable
        """
        pass

    @abstractmethod
    def get_message_type(self, message: Dict[str, Any]) -> MessageType:
        """
        Fast message type detection for routing.

        Args:
            message: Parsed message dictionary

        Returns:
            MessageType for routing decisions
        """
        pass

    @abstractmethod
    async def parse_orderbook_message(
        self,
        message: Dict[str, Any]
    ) -> Optional[OrderBook]:
        """
        Parse orderbook-specific message.

        Args:
            message: Parsed message dictionary

        Returns:
            OrderBook instance if valid, None otherwise
        """
        pass

    @abstractmethod
    def supports_batch_parsing(self) -> bool:
        """
        Check if parser supports batch message processing.

        Returns:
            True if batch parsing supported
        """
        pass

    async def parse_batch_messages(
        self,
        raw_messages: List[str]
    ) -> AsyncIterator[ParsedMessage]:
        """
        Parse multiple messages efficiently.

        Args:
            raw_messages: List of raw message strings

        Yields:
            ParsedMessage instances
        """
        # Default implementation - override for batch optimizations
        for raw_message in raw_messages:
            parsed = await self.parse_message(raw_message)
            if parsed:
                yield parsed
