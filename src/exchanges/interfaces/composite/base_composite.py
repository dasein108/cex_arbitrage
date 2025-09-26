"""
Base exchange interface providing core functionality for all exchange implementations.

This interface establishes the foundation for both public and private exchange operations,
handling connection management, initialization, and state tracking.
"""

from abc import ABC, abstractmethod
from typing import Optional, Union

from exchanges.structs.common import SymbolsInfo
from config.structs import ExchangeConfig
from infrastructure.networking.websocket.handlers import PrivateWebsocketHandlers,PublicWebsocketHandlers
from infrastructure.networking.websocket.structs import ConnectionState

# HFT Logger Integration
from infrastructure.logging import get_exchange_logger, LoggingTimer, HFTLoggerInterface


class BaseCompositeExchange(ABC):
    """
    Base exchange interface with common connection and state management logic.
    
    Handles:
    - Exchange initialization and configuration
    - Connection state management 
    - WebSocket connection event handling
    - Exchange data refresh on reconnection
    - Resource cleanup and shutdown
    
    This class provides the foundation for both public and private exchange interfaces,
    establishing common patterns for connection management and state tracking.
    """

    def __init__(self, config: ExchangeConfig, is_private: bool, logger: Optional[HFTLoggerInterface] = None):
        """
        Initialize composite exchange interface.
        
        Args:
            tag: Unique identifier for this exchange instance
            config: Exchange configuration containing credentials and settings
            logger: Optional injected HFT logger (auto-created if not provided)
        """
        self._is_private = is_private
        self._exchange_name = config.name
        self._tag = f"{config.name}_{'private' if is_private else 'public'}"
        self._config = config
        self._initialized = False
        self._connection_state = ConnectionState.DISCONNECTED
        
        # Use injected logger or create exchange-specific logger
        self.logger = logger or get_exchange_logger(config.name, self._tag)
        
        # Connection and state management
        self._symbols_info: Optional[SymbolsInfo] = None
        self._last_update_time = 0.0

        # Log interface initialization
        self.logger.info("BaseExchangeInterface initialized", exchange=config.name)

    @abstractmethod
    async def close(self):
        """
        Close exchange connections and cleanup resources.
        
        Implementations must:
        - Close all WebSocket connections
        - Cancel pending tasks
        - Clean up resources
        - Set internal state appropriately
        """
        pass

    async def initialize(self, **kwargs) -> None:
        """
        Initialize exchange with configuration and optional parameters.
        
        Base implementation provides initialization safety checks.
        Subclasses should call super().initialize() and then perform
        their specific initialization logic.
        
        Args:
            **kwargs: Exchange-specific initialization parameters
        """
        if self._initialized:
            self.logger.warning("Exchange already initialized", 
                               tag=self._tag,
                               exchange=self._config.name)
            return
        
        self.logger.info("Starting exchange initialization",
                        tag=self._tag,
                        exchange=self._config.name)
        
        # Track initialization performance
        with LoggingTimer(self.logger, "exchange_initialization"):
            self._initialized = True

    @property
    def is_connected(self) -> bool:
        """
        Check if exchange is connected and healthy.
        
        Returns:
            True if exchange has healthy connection, False otherwise
        """
        return self._connection_state == ConnectionState.CONNECTED

    
    @property
    def connection_state(self) -> ConnectionState:
        """
        Get current WebSocket connection state.
        
        Returns:
            Current connection state enum value
        """
        return self._connection_state

    @property
    def config(self) -> ExchangeConfig:
        """Get exchange configuration."""
        return self._config

    @property 
    def tag(self) -> str:
        """Get exchange tag identifier."""
        return self._tag

    @property
    def symbols_info(self) -> Optional[SymbolsInfo]:
        """Get symbol information."""
        return self._symbols_info

    @abstractmethod
    def _get_websocket_handlers(self) -> Union[PrivateWebsocketHandlers, PublicWebsocketHandlers]:
        """
        Get WebSocket event handlers for this exchange.

        Returns:
            Instance of PrivateWebsocketHandlers or PublicWebsocketHandlers
        """
        pass

    async def _handle_connection_state(self, state: ConnectionState) -> None:
        """
        React to WebSocket connection state changes.
        
        Called by WebSocket client via connection_handler callback.
        Delegates to specific handlers for each state.
        
        Args:
            state: New connection state
        """
        try:
            self._connection_state = state
            self.logger.debug("Connection state change",
                             tag=self._tag,
                             exchange=self._config.name,
                             old_state=self.connection_state.name,
                             new_state=state.name)
            
            # Track state change metrics
            self.logger.metric("connection_state_changes", 1,
                              tags={"exchange": self._config.name, 
                                   "from_state": self.connection_state.name,
                                   "to_state": state.name})
            
            if state == ConnectionState.CONNECTED:
                await self._on_websocket_connected()
            elif state == ConnectionState.DISCONNECTED:
                await self._on_websocket_disconnected()
            elif state == ConnectionState.RECONNECTING:
                await self._on_websocket_reconnecting()
            elif state == ConnectionState.ERROR:
                await self._on_websocket_error()
                
        except Exception as e:
            self.logger.error("Error handling connection state change",
                             tag=self._tag,
                             exchange=self._config.name,
                             target_state=state.name,
                             error_type=type(e).__name__,
                             error_message=str(e))
    
    async def _on_websocket_connected(self) -> None:
        """
        Handle WebSocket connection established.
        
        This is called after successful connection/reconnection.
        Refresh exchange data and notify arbitrage layer.
        """

        # Track connection performance
        with LoggingTimer(self.logger, "exchange_data_refresh") as timer:
            await self._refresh_exchange_data()
        
        self.logger.info("WebSocket connected and data refreshed",
                        tag=self._tag,
                        exchange=self._config.name,
                        refresh_time_ms=timer.elapsed_ms)
        
        # Track successful connections
        self.logger.metric("websocket_connections", 1,
                          tags={"exchange": self._config.name, "status": "connected"})
    
    async def _on_websocket_disconnected(self) -> None:
        """Handle WebSocket disconnection."""

        self.logger.warning("WebSocket disconnected",
                           tag=self._tag,
                           exchange=self._config.name)
        
        # Track disconnections
        self.logger.metric("websocket_disconnections", 1,
                          tags={"exchange": self._config.name})
    
    async def _on_websocket_reconnecting(self) -> None:
        """Handle WebSocket reconnection in progress."""

        self.logger.info("WebSocket reconnecting",
                        tag=self._tag,
                        exchange=self._config.name)
        
        # Track reconnection attempts
        self.logger.metric("websocket_reconnections", 1,
                          tags={"exchange": self._config.name})

    async def _on_websocket_error(self) -> None:
        """Handle WebSocket error state."""

        self.logger.error("WebSocket error state",
                         tag=self._tag,
                         exchange=self._config.name)

        # Track errors
        self.logger.metric("websocket_errors", 1,
                          tags={"exchange": self._config.name})

    @abstractmethod
    async def _refresh_exchange_data(self) -> None:
        """
        Refresh all exchange data after reconnection.
        
        Public exchanges: refresh orderbooks, symbols
        Private exchanges: refresh orderbooks, symbols, balances, orders, positions
        
        Implementation should notify arbitrage layer of refreshed data.
        """
        pass