from abc import ABC, abstractmethod
from typing import Optional, Callable, Awaitable, Any, Dict, List

from config.structs import ExchangeConfig
from infrastructure.networking.websocket import WebSocketManager

# HFT Logger Integration
from infrastructure.logging import get_exchange_logger, LoggingTimer, HFTLoggerInterface
from websockets.client import WebSocketClientProtocol
from websockets.protocol import State as WsState
from infrastructure.networking.websocket.structs import ConnectionState


class BaseWebsocketInterface(ABC):
    """
    Abstract composite for exchange WebSocket operations using dependency injection.
    
    Provides unified interface for both public and private exchange WebSocket operations
    with automatic strategy selection, authentication, and message handling.
    Similar pattern to BaseExchangeRestInterface for consistency.
    """

    @abstractmethod
    async def _create_websocket(self) -> WebSocketClientProtocol:
        """Create and return a new WebSocket connection."""
        pass

    async def _connect(self) -> WebSocketClientProtocol:
        self._websocket = await self._create_websocket()
        return self._websocket

    async def _auth(self) -> bool:
        return True  # Default to True for public connections

    def __init__(
            self,
            config: ExchangeConfig,
            is_private: bool = False,
            logger: HFTLoggerInterface = None
    ):
        self.config = config
        self.exchange_name = config.name

        self._websocket: Optional[WebSocketClientProtocol] = None

        self.is_private = is_private

        # Tag for logging consistency
        tag = 'private' if is_private else 'public'
        self.exchange_tag = f'{self.exchange_name}_{tag}'

        # Initialize HFT logger with optional injection or exchange-specific logger
        self.logger = logger or get_exchange_logger(self.exchange_name, f'ws.{tag}')

        # Mapper dependency removed - strategies use direct utility functions

        # Initialize WebSocket manager using factory pattern with logger injection
        self._ws_manager = WebSocketManager(config=config.websocket,
                                            connect_method=self._connect,
                                            auth_method=self._auth,
                                            message_handler=self._handle_message,
                                            connection_handler=self._connection_handler, logger=self.logger)

        self.logger.info("Initialized WebSocket manager",
                         exchange=self.exchange_name,
                         tag=tag,
                         is_private=is_private)

    @abstractmethod
    async def _handle_message(self, raw_message: Any) -> None:
        """Default message handler - should be overridden by subclasses."""
        pass

    @abstractmethod
    async def _resubscribe_all(self) -> None:
        pass

    async def _connection_handler(self, state: ConnectionState) -> None:
        if state == ConnectionState.CONNECTED:
            self.logger.info("WebSocket connected")
            # Resubscribe to all channels on reconnect
            await self._resubscribe_all()
            self.logger.info("Resubscribed to all channels after reconnect")
        elif state == ConnectionState.DISCONNECTED:
            self.logger.warning("WebSocket disconnected")
        elif state == ConnectionState.RECONNECTING:
            self.logger.info("WebSocket reconnecting...")
        elif state == ConnectionState.ERROR:
            self.logger.error("WebSocket connection failed")

    async def _send_message_if_connected(self, message: Any) -> None:
        """
        Send message if WebSocket is connected.
        Otherwise, just ignore, all subscriptions will be resent on reconnect.
        """
        if self.is_connected():
            await self._ws_manager.send_message(message)


    async def initialize(self) -> None:
        """Initialize WebSocket connection using mixin composition."""
        try:
            with LoggingTimer(self.logger, "ws_interface_initialization") as timer:
                await self._ws_manager.initialize()

            self.logger.info("WebSocket initialized",
                             exchange=self.exchange_name,
                             initialization_time_ms=timer.elapsed_ms)

            # Track initialization metrics
            self.logger.metric("ws_interface_initializations", 1,
                               tags={"exchange": self.exchange_name,
                                     "type": "private" if self.is_private else "public"})

        except Exception as e:
            self.logger.error("Failed to initialize WebSocket",
                              exchange=self.exchange_name,
                              error_type=type(e).__name__,
                              error_message=str(e))

            # Track initialization failure metrics
            self.logger.metric("ws_interface_initialization_failures", 1,
                               tags={"exchange": self.exchange_name,
                                     "type": "private" if self.is_private else "public"})

            raise

    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._ws_manager.is_connected()

    async def close(self) -> None:
        """Close WebSocket connection and clean up resources."""
        self.logger.info("Stopping WebSocket connection",
                         exchange_tag=self.exchange_tag)

        try:
            with LoggingTimer(self.logger, "ws_interface_close") as timer:
                await self._ws_manager.close()

            self.logger.info("WebSocket stopped",
                             exchange_tag=self.exchange_tag,
                             close_time_ms=timer.elapsed_ms)

            # Track close metrics
            self.logger.metric("ws_interface_closes", 1,
                               tags={"exchange": self.exchange_name,
                                     "type": "private" if self.is_private else "public"})

        except Exception as e:
            self.logger.error("Error stopping WebSocket connection",
                              exchange_tag=self.exchange_tag,
                              error_type=type(e).__name__,
                              error_message=str(e))

            # Track close error metrics
            self.logger.metric("ws_interface_close_errors", 1,
                               tags={"exchange": self.exchange_name,
                                     "type": "private" if self.is_private else "public"})

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
