"""
Core trading interface for both spot and futures exchanges.

This interface provides common trading operations that are available
for both spot and futures exchanges.
"""

from abc import abstractmethod, ABC
from typing import Dict, List, Optional
from exchanges.interfaces.rest.rest_base import BaseRestInterface
# BaseExchangeMapper dependency removed - using direct utility functions
from exchanges.structs.common import (
    Symbol,
    Order,
    AssetBalance
)
from exchanges.structs.types import AssetName, OrderId
from exchanges.structs.enums import TimeInForce
from exchanges.structs import OrderType, Side

from config.structs import ExchangeConfig

# HFT Logger Integration
from infrastructure.logging import HFTLoggerInterface


class ListenKeyInterface(ABC):
    """Abstract interface for exchange listen key operations (both spot and futures)"""


    @abstractmethod
    async def create_listen_key(self) -> str:
        """
        Create a new listen key for user data stream.
        
        Returns:
            Listen key string for WebSocket user data stream
        """
        pass
    
    @abstractmethod
    async def get_all_listen_keys(self) -> Dict:
        """
        Get all active listen keys.
        
        Returns:
            Dictionary containing active listen keys and their metadata
        """
        pass
    
    @abstractmethod
    async def keep_alive_listen_key(self, listen_key: str) -> None:
        """
        Keep a listen key alive to prevent expiration.
        
        Args:
            listen_key: The listen key to keep alive
        """
        pass
    
    @abstractmethod
    async def delete_listen_key(self, listen_key: str) -> None:
        """
        Delete/close a listen key.

        Args:
            listen_key: The listen key to delete
        """
        pass