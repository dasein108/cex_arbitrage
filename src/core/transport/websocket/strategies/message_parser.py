from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, AsyncIterator, TYPE_CHECKING

from core.transport.websocket.structs import ParsedMessage, MessageType
from structs.common import OrderBook
from core.exchanges.services import BaseExchangeMapper


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

    def __init__(self, mapper: Optional[BaseExchangeMapper] = None):
        """Initialize with optional mapper injection.
        
        Args:
            mapper: Exchange mappings interface containing symbol_mapper functionality
        """
        self.mapper = mapper
        # Maintain backward compatibility with symbol_mapper property
        self.symbol_mapper = mapper._symbol_mapper if mapper else None
