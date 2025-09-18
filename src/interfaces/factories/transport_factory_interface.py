"""
Abstract interface for transport factory implementations.

This interface enables dependency injection of transport layer components,
allowing different REST and WebSocket client implementations to be
plugged in based on performance requirements or testing needs.
"""

from abc import ABC, abstractmethod
from typing import Optional
from core.config.structs import ExchangeConfig
from core.transport.rest.rest_transport_manager import RestTransportManager
from core.transport.websocket.ws_manager import WebSocketManager


class TransportFactoryInterface(ABC):
    """
    Abstract interface for transport factory implementations.
    
    Provides dependency injection capability for transport layer components,
    enabling different transport implementations to be used based on
    configuration, performance requirements, or testing scenarios.
    """

    @abstractmethod
    def create_rest_transport(
        self,
        config: ExchangeConfig,
        is_private: bool = False
    ) -> RestTransportManager:
        """
        Create a REST transport manager.
        
        Args:
            config: Exchange configuration
            is_private: Whether to create private (authenticated) transport
            
        Returns:
            Configured REST transport manager
        """
        pass

    @abstractmethod
    def create_websocket_manager(
        self,
        config: ExchangeConfig,
        is_private: bool = False
    ) -> WebSocketManager:
        """
        Create a WebSocket manager.
        
        Args:
            config: Exchange configuration  
            is_private: Whether to create private (authenticated) WebSocket
            
        Returns:
            Configured WebSocket manager
        """
        pass

    @abstractmethod
    async def cleanup_transports(self) -> None:
        """
        Clean up all managed transport instances.
        
        Should be called during shutdown to ensure proper cleanup
        of connections and resources.
        """
        pass

    @abstractmethod
    def get_transport_stats(self) -> dict:
        """
        Get statistics from managed transports.
        
        Returns:
            Dictionary with transport performance statistics
        """
        pass