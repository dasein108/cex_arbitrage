import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Set, Optional, Callable, Awaitable
from enum import Enum

from structs.exchange import ExchangeName, Symbol, OrderBook, SymbolsInfo
from core.config.structs import ExchangeConfig
from core.transport.websocket.structs import ConnectionState


class BaseExchangeInterface(ABC):
    """
    Base exchange interface with common orderbook management logic.
    
    Handles:
    - Initial orderbook loading from REST API
    - Reconnection and state recovery
    - Orderbook state management
    - Update broadcasting to arbitrage layer
    """

    def __init__(self, tag:str, config: ExchangeConfig):
        self._config = config
        self._initialized = False
        self.logger = logging.getLogger(f"{__name__}.{config.name}")
        

        self._symbols_info: Optional[SymbolsInfo] = None
        self._connection_healthy = False
        self._last_update_time = 0.0
        self._tag = tag

    @abstractmethod
    async def close(self):
        """Close exchange connections and cleanup."""
        pass

    async def initialize(self, **kwargs) -> None:
        """Initialize exchange with symbols."""
        if self._initialized:
            self.logger.warning(f"{self._tag} already initialized")
            return

    async def _handle_connection_state_change(self, state: ConnectionState) -> None:
        """
        React to WebSocket connection state changes.
        
        Called by WebSocket client via connection_handler callback.
        Delegates to specific handlers for each state.
        """
        try:
            if state == ConnectionState.CONNECTED:
                await self._on_websocket_connected()
            elif state == ConnectionState.DISCONNECTED:
                await self._on_websocket_disconnected()
            elif state == ConnectionState.RECONNECTING:
                await self._on_websocket_reconnecting()
            elif state == ConnectionState.ERROR:
                await self._on_websocket_error()
                
        except Exception as e:
            self.logger.error(f"Error handling connection state change to {state}: {e}")
    
    async def _on_websocket_connected(self) -> None:
        """
        Handle WebSocket connection established.
        
        This is called after successful connection/reconnection.
        Refresh exchange data and notify arbitrage layer.
        """
        self._connection_healthy = True
        await self._refresh_exchange_data()
        self.logger.info(f"{self._tag} WebSocket connected and data refreshed")
    
    async def _on_websocket_disconnected(self) -> None:
        """Handle WebSocket disconnection."""
        self._connection_healthy = False
        self.logger.warning(f"{self._tag} WebSocket disconnected")
    
    async def _on_websocket_reconnecting(self) -> None:
        """Handle WebSocket reconnection in progress."""
        self._connection_healthy = False
        self.logger.info(f"{self._tag} WebSocket reconnecting...")
    
    async def _on_websocket_error(self) -> None:
        """Handle WebSocket error state."""
        self._connection_healthy = False
        self.logger.error(f"{self._tag} WebSocket error state")
    
    @abstractmethod
    async def _refresh_exchange_data(self) -> None:
        """
        Refresh all exchange data after reconnection.
        
        Public exchanges: refresh orderbooks, symbols
        Private exchanges: refresh orderbooks, symbols, balances, orders, positions
        
        Implementation should notify arbitrage layer of refreshed data.
        """
        pass

    @property
    def is_connected(self) -> bool:
        """Check if exchange is connected and healthy."""
        # Delegate to WebSocket client if available, otherwise use internal state
        if hasattr(self, '_websocket_client') and self._websocket_client:
            return self._websocket_client.is_connected
        return self._connection_healthy
    
    @property
    def connection_state(self) -> ConnectionState:
        """Get current WebSocket connection state."""
        if hasattr(self, '_websocket_client') and self._websocket_client:
            return self._websocket_client.state
        return ConnectionState.DISCONNECTED if not self._connection_healthy else ConnectionState.CONNECTED


