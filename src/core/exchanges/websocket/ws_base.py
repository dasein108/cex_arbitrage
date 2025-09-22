from abc import ABC
import logging
from typing import Optional, Callable, Awaitable, Any, Dict

from core.config.structs import ExchangeConfig
from core.exchanges.services import ExchangeMapperFactory
from core.transport.websocket.utils import create_websocket_manager


class BaseExchangeWebsocketInterface(ABC):
    """
    Abstract base for exchange WebSocket operations using dependency injection.
    
    Provides unified interface for both public and private exchange WebSocket operations
    with automatic strategy selection, authentication, and message handling.
    Similar pattern to BaseExchangeRestInterface for consistency.
    """

    def __init__(
        self, 
        config: ExchangeConfig, 
        is_private: bool = False,
        message_handler: Optional[Callable[[Any], Awaitable[None]]] = None,
        state_change_handler: Optional[Callable] = None
    ):
        self.config = config
        self.exchange_name = config.name
        self.is_private = is_private
        
        # Tag for logging consistency
        tag = 'private' if is_private else 'public'
        self.exchange_tag = f'{self.exchange_name}_{tag}'
        self.logger = logging.getLogger(f"{__name__}.{self.exchange_tag}")
        
        # Factory-based dependency injection (similar to REST pattern)
        self._mapper = ExchangeMapperFactory.create(config.name)
        
        # Initialize WebSocket manager using factory pattern
        self._ws_manager = create_websocket_manager(
            exchange_config=config,
            is_private=is_private,
            message_handler=message_handler or self._handle_parsed_message,
            state_change_handler=state_change_handler
        )
        
        self.logger.info(f"Initialized WebSocket manager for {self.exchange_name} ({tag})")

    async def _handle_parsed_message(self, parsed_message) -> None:
        """Default message handler - should be overridden by subclasses."""
        self.logger.debug(f"Received message: {parsed_message.message_type}")

    async def initialize(self, symbols=None) -> None:
        """Initialize WebSocket connection using strategy pattern."""
        try:
            await self._ws_manager.initialize(symbols or [])
            self.logger.info(f"WebSocket initialized for {self.exchange_name}")
        except Exception as e:
            self.logger.error(f"Failed to initialize WebSocket: {e}")
            raise

    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._ws_manager.is_connected()
        
    def get_performance_metrics(self) -> Dict:
        """Get HFT performance metrics."""
        return self._ws_manager.get_performance_metrics()

    async def close(self) -> None:
        """Close WebSocket connection and clean up resources."""
        self.logger.info(f"Stopping {self.exchange_tag} WebSocket connection")
        await self._ws_manager.close()
        self.logger.info(f"{self.exchange_tag} WebSocket stopped")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
