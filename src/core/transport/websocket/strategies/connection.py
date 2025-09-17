from abc import ABC, abstractmethod
from typing import Any

from core.transport.websocket.structs import ConnectionContext


class ConnectionStrategy(ABC):
    """
    Strategy for WebSocket connection management.

    Handles connection establishment, authentication, and keep-alive.
    HFT COMPLIANT: <100ms connection establishment.
    """

    @abstractmethod
    async def create_connection_context(self) -> ConnectionContext:
        """
        Create connection configuration.

        Returns:
            ConnectionContext with URL, headers, auth parameters
        """
        pass

    @abstractmethod
    async def authenticate(self, websocket: Any) -> bool:
        """
        Perform authentication if required.

        Args:
            websocket: WebSocket connection instance

        Returns:
            True if authentication successful
        """
        pass

    @abstractmethod
    async def handle_keep_alive(self, websocket: Any) -> None:
        """
        Handle keep-alive/ping operations.

        Args:
            websocket: WebSocket connection instance
        """
        pass

    @abstractmethod
    def should_reconnect(self, error: Exception) -> bool:
        """
        Determine if reconnection should be attempted.

        Args:
            error: Exception that caused disconnection

        Returns:
            True if reconnection should be attempted
        """
        pass

    async def cleanup(self) -> None:
        """
        Clean up resources when closing connection.

        Optional method for strategies to implement resource cleanup.
        Default implementation does nothing.
        """
        pass
