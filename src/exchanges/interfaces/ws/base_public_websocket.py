"""
BasePublicWebsocket Interface - Pure Market Data Operations

Abstract base class for public WebSocket operations with complete domain separation.
Handles only market data (orderbooks, trades, tickers) with no authentication required.
Symbols are mandatory for all operations as per HFT requirements.

Architecture compliance:
- Complete domain separation from private operations
- No authentication logic or private operation references
- Symbols parameter mandatory in initialize method
- HFT performance tracking and sub-millisecond logging
- Clean interface following pragmatic SOLID principles
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Callable, Awaitable, Set, Union
from msgspec import Struct

from exchanges.structs.common import Symbol
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, ConnectionState
from infrastructure.networking.websocket.handlers import PublicWebsocketHandlers
from config.structs import ExchangeConfig
from infrastructure.logging import HFTLoggerInterface
from infrastructure.exceptions.unified import UnifiedConnectionError, UnifiedSubscriptionError


class BasePublicWebsocket(ABC):
    """
    Abstract base class for public market data WebSocket operations.
    
    Pure market data interface with complete domain separation from private operations.
    No authentication required, symbols mandatory for all operations.
    
    Key Design Principles:
    - Domain Separation: No reference to private operations
    - Symbol Management: Symbols required in initialize, tracked throughout lifecycle
    - Performance: Sub-millisecond message processing targets
    - Error Handling: Specialized exceptions for public WebSocket operations
    - Type Safety: Full type hints for compile-time validation
    """
    
    def __init__(
        self,
        config: ExchangeConfig,
        handlers: PublicWebsocketHandlers,
        logger: HFTLoggerInterface,
        connection_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None
    ) -> None:
        """
        Initialize public WebSocket interface.
        
        Args:
            config: Exchange configuration with connection settings
            handlers: Public WebSocket message handlers for market data
            logger: HFT logger for sub-millisecond performance tracking
            connection_handler: Optional callback for connection state changes
            
        Note:
            No authentication credentials are used - this is pure market data interface.
        """
        self.config = config
        self.exchange_name = config.name
        self.handlers = handlers
        self.logger = logger
        self.connection_handler = connection_handler
        
        # Track active symbols for subscription management
        self._active_symbols: Set[Symbol] = set()
        
        # Performance tracking
        self._message_count = 0
        self._connection_start_time: Optional[float] = None
        
        self.logger.info(
            "Initialized public WebSocket interface",
            exchange=self.exchange_name,
            interface_type="public_market_data"
        )
    
    @abstractmethod
    async def initialize(
        self,
        symbols: List[Symbol],
        channels: List[PublicWebsocketChannelType]
    ) -> None:
        """
        Initialize WebSocket connection with required symbols.
        
        Args:
            symbols: List of symbols to subscribe to (REQUIRED - no default)
            channels: WebSocket channels to subscribe to (orderbook, trades, etc.)
            
        Raises:
            UnifiedConnectionError: If connection fails
            UnifiedSubscriptionError: If symbol subscription fails
            ValueError: If symbols list is empty
            
        Note:
            Symbols parameter is mandatory - public WebSocket requires symbols
            to determine which market data streams to subscribe to.
        """
        if not symbols:
            raise ValueError("Symbols are required for public WebSocket initialization")
    
    @abstractmethod
    async def subscribe(self, symbols: List[Symbol]) -> None:
        """
        Add symbols to existing subscription.
        
        Args:
            symbols: Additional symbols to subscribe to
            
        Raises:
            UnifiedSubscriptionError: If subscription fails
            ValueError: If symbols list is empty
        """
        if not symbols:
            raise ValueError("Symbols list cannot be empty for subscription")
    
    @abstractmethod
    async def unsubscribe(self, symbols: List[Symbol]) -> None:
        """
        Remove symbols from current subscription.
        
        Args:
            symbols: Symbols to remove from subscription
            
        Raises:
            UnifiedSubscriptionError: If unsubscription fails
            ValueError: If symbols list is empty
        """
        if not symbols:
            raise ValueError("Symbols list cannot be empty for unsubscription")
    
    @abstractmethod
    def get_active_symbols(self) -> Set[Symbol]:
        """
        Get currently subscribed symbols.
        
        Returns:
            Set of symbols currently subscribed to
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
    def get_performance_metrics(self) -> Dict[str, Union[int, float, str]]:
        """
        Get HFT performance metrics for monitoring.
        
        Returns:
            Dictionary containing performance metrics:
            - message_processing_latency_us: Average message processing time
            - messages_per_second: Current message throughput
            - connection_uptime_seconds: Time since connection established
            - active_symbols_count: Number of subscribed symbols
            - reconnection_count: Number of reconnections
        """
        pass
    
    # Common utility methods for symbol management
    def _add_symbols_to_active(self, symbols: List[Symbol]) -> None:
        """Add symbols to active set with validation."""
        for symbol in symbols:
            if not isinstance(symbol, Symbol):
                raise TypeError(f"Expected Symbol, got {type(symbol)}")
            self._active_symbols.add(symbol)
    
    def _remove_symbols_from_active(self, symbols: List[Symbol]) -> None:
        """Remove symbols from active set."""
        for symbol in symbols:
            self._active_symbols.discard(symbol)
    
    def _validate_symbols_list(self, symbols: List[Symbol], operation: str) -> None:
        """Validate symbols list for operations."""
        if not symbols:
            raise ValueError(f"Symbols list cannot be empty for {operation}")
        
        if not isinstance(symbols, list):
            raise TypeError(f"Expected list of symbols for {operation}, got {type(symbols)}")
        
        for symbol in symbols:
            if not isinstance(symbol, Symbol):
                raise TypeError(f"Expected Symbol objects in list, got {type(symbol)}")
    
    # Context manager support for resource cleanup
    async def __aenter__(self) -> "BasePublicWebsocket":
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit with cleanup."""
        await self.close()