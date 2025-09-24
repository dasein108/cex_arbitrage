from abc import ABC, abstractmethod
from typing import Any, Optional
from dataclasses import dataclass
from websockets.client import WebSocketClientProtocol
from websockets.protocol import State as WsState
from infrastructure.config.structs import ExchangeConfig

from infrastructure.networking.websocket.structs import ConnectionContext


@dataclass
class ReconnectionPolicy:
    """Strategy-specific reconnection policy configuration."""
    max_attempts: int
    initial_delay: float
    backoff_factor: float
    max_delay: float
    reset_on_1005: bool = True  # Reset attempts on WebSocket 1005 errors
    

class ConnectionStrategy(ABC):
    """
    Strategy for WebSocket connection management.

    Handles connection establishment, authentication, and keep-alive.
    Each strategy owns its WebSocket instance and manages it internally.
    HFT COMPLIANT: <100ms connection establishment.
    """
    
    def __init__(self, config: ExchangeConfig):
        self._websocket: Optional[WebSocketClientProtocol] = None
        self.config = config

    @property
    def websocket(self) -> Optional[WebSocketClientProtocol]:
        """Get the current WebSocket instance."""
        return self._websocket

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        if self._websocket is None:
            return False
        try:
            return self._websocket.state == WsState.OPEN
        except AttributeError:
            # Handle case where ws object doesn't have 'closed' attribute
            import logging
            logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
            logger.error(f"WebSocket object {type(self._websocket)} has no 'closed' attribute")
            return False

    @abstractmethod
    async def connect(self) -> WebSocketClientProtocol:
        """
        Establish WebSocket connection and store it internally.
        
        This method encapsulates all exchange-specific connection logic
        including URL building, headers, authentication, and connection settings.
        The WebSocket instance is stored internally for use by other methods.
        
        Returns:
            Raw WebSocket ClientProtocol instance
            
        Raises:
            ConnectionError: If connection establishment fails
        """
        pass
    
    @abstractmethod
    def get_reconnection_policy(self) -> ReconnectionPolicy:
        """
        Get strategy-specific reconnection policy.
        
        Returns:
            ReconnectionPolicy with exchange-specific settings
        """
        pass
    
    @abstractmethod
    async def create_connection_context(self) -> ConnectionContext:
        """
        Create connection configuration.

        Returns:
            ConnectionContext with URL, headers, auth parameters
        """
        pass

    async def authenticate(self) -> bool:
        """
        Perform authentication if required using the internal WebSocket instance.

        Returns:
            True if authentication successful
            
        Raises:
            RuntimeError: If no WebSocket connection is available
        """
        if not self.is_connected:
            raise RuntimeError("No WebSocket connection available for authentication")
        return True

    @abstractmethod
    async def handle_heartbeat(self) -> None:
        """
        Handle exchange-specific heartbeat/ping operations using internal WebSocket.
        
        Some exchanges use built-in WebSocket ping/pong, others require custom messages.
        This method encapsulates the exchange-specific heartbeat logic.
        
        Raises:
            RuntimeError: If no WebSocket connection is available
        """
        pass

    @abstractmethod
    def should_reconnect(self, error: Exception) -> bool:
        """
        Determine if reconnection should be attempted based on error type.
        
        Exchange-specific error interpretation and reconnection logic.

        Args:
            error: Exception that caused disconnection

        Returns:
            True if reconnection should be attempted
        """
        pass
    
    def classify_error(self, error: Exception) -> str:
        """
        Classify error for logging and debugging purposes.
        
        Args:
            error: Exception to classify
            
        Returns:
            String classification of error type
        """
        error_str = str(error)
        if "1005" in error_str or "no status received" in error_str:
            return "abnormal_closure"
        elif "Connection refused" in error_str:
            return "connection_refused"
        elif "timeout" in error_str.lower():
            return "timeout"
        elif "authentication" in error_str.lower():
            return "authentication_failure"
        else:
            return "unknown"

    async def disconnect(self) -> None:
        """
        Disconnect and clean up the WebSocket connection.
        
        Properly closes the WebSocket connection and clears the internal reference.
        """
        if self._websocket:
            try:
                if self._websocket.state != WsState.CLOSED:
                    await self._websocket.close()
            except AttributeError:
                # Handle case where ws doesn't have 'closed' attribute
                try:
                    await self._websocket.close()
                except Exception:
                    pass  # Ignore errors during cleanup
        self._websocket = None
        await self.cleanup()

    async def cleanup(self) -> None:
        """
        Clean up resources when closing connection.

        Optional method for strategies to implement resource cleanup.
        Default implementation does nothing.
        """
        pass
