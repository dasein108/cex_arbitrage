"""
BasePrivateWebsocket Interface - Pure Trading Operations

Abstract base class for private WebSocket operations with complete domain separation.
Handles only trading operations (orders, balances, positions) with authentication required.
No symbols parameter - subscribes to account-wide streams automatically.

Architecture compliance:
- Complete domain separation from public operations  
- Authentication required for all operations
- No symbols parameter in initialize method (account streams)
- HFT performance tracking and sub-millisecond logging
- Clean interface following pragmatic SOLID principles
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, Callable, Awaitable, Union

from infrastructure.networking.websocket.structs import ConnectionState
from infrastructure.networking.websocket.handlers import PrivateWebsocketHandlers
from config.structs import ExchangeConfig
from infrastructure.logging import HFTLoggerInterface
from infrastructure.exceptions.unified import UnifiedConnectionError, UnifiedValidationError


class BasePrivateWebsocket(ABC):
    """
    Abstract base class for private trading WebSocket operations.
    
    Pure trading interface with authentication required.
    No symbols parameter - subscribes to account-wide streams automatically.
    
    Key Design Principles:
    - Domain Separation: No reference to public operations or symbols
    - Authentication: Required for all operations
    - Account Streams: Subscribes to account-wide data (orders, balances, positions)
    - Performance: Sub-millisecond message processing targets
    - Error Handling: Specialized exceptions for private WebSocket operations
    - Type Safety: Full type hints for compile-time validation
    """
    
    def __init__(
        self,
        config: ExchangeConfig,
        handlers: PrivateWebsocketHandlers,
        logger: HFTLoggerInterface,
        connection_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None
    ) -> None:
        """
        Initialize private WebSocket interface.
        
        Args:
            config: Exchange configuration with authentication credentials
            handlers: Private WebSocket message handlers for trading data
            logger: HFT logger for sub-millisecond performance tracking
            connection_handler: Optional callback for connection state changes
            
        Note:
            Authentication credentials from config are required for private operations.
        """
        self.config = config
        self.exchange_name = config.name
        self.handlers = handlers
        self.logger = logger
        self.connection_handler = connection_handler
        
        # Validate authentication credentials
        if not self._has_authentication_credentials():
            raise UnifiedValidationError(
                exchange=self.exchange_name,
                message="Authentication credentials required for private WebSocket"
            )
        
        # Authentication state tracking
        self._is_authenticated = False
        
        # Performance tracking
        self._message_count = 0
        self._connection_start_time: Optional[float] = None
        
        self.logger.info(
            "Initialized private WebSocket interface",
            exchange=self.exchange_name,
            interface_type="private_trading_operations"
        )
    
    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize private WebSocket connection.
        
        No symbols parameter - subscribes to account streams automatically.
        Handles authentication and establishes trading data streams.
        
        Raises:
            UnifiedConnectionError: If connection fails
            UnifiedValidationError: If authentication fails
            
        Note:
            No symbols parameter - private WebSocket subscribes to account-wide
            streams for orders, balances, and positions automatically.
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """
        Close WebSocket connection and clean up resources.
        
        Raises:
            ConnectionError: If close operation fails
        """
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """
        Check connection status.
        
        Returns:
            True if WebSocket is connected, False otherwise
        """
        pass
    
    @abstractmethod
    def is_authenticated(self) -> bool:
        """
        Check authentication status.
        
        Returns:
            True if WebSocket is authenticated for trading operations, False otherwise
        """
        pass
    
    @abstractmethod
    def get_performance_metrics(self) -> Dict[str, Union[int, float, str]]:
        """
        Get HFT performance metrics for monitoring.
        
        Returns:
            Dictionary containing performance metrics:
            - message_processing_latency_us: Average message processing time
            - messages_per_second: Current message throughput
            - connection_uptime_seconds: Time since connection established
            - authentication_status: Current authentication state
            - order_updates_count: Number of order update messages
            - balance_updates_count: Number of balance update messages
            - position_updates_count: Number of position update messages
            - reconnection_count: Number of reconnections
        """
        pass

    # Common utility methods for credential validation
    def _has_authentication_credentials(self) -> bool:
        """
        Validate that required authentication credentials are present.

        Returns:
            True if valid credentials are available, False otherwise
        """
        # Check for API key and secret at minimum
        return self.config.has_credentials()
    
    def _mark_authenticated(self) -> None:
        """Mark the connection as authenticated."""
        self._is_authenticated = True
        self.logger.info(
            "Private WebSocket authenticated successfully",
            exchange=self.exchange_name
        )
    
    def _mark_unauthenticated(self) -> None:
        """Mark the connection as unauthenticated."""
        self._is_authenticated = False
        self.logger.warning(
            "Private WebSocket authentication lost",
            exchange=self.exchange_name
        )
    
    # Context manager support for resource cleanup
    async def __aenter__(self) -> "BasePrivateWebsocket":
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit with cleanup."""
        await self.close()