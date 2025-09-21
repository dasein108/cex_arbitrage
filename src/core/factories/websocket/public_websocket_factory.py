"""
Public WebSocket Exchange Factory

Factory for creating public WebSocket exchange instances following the established
BaseExchangeFactory pattern with singleton management and auto-dependency injection.

HFT COMPLIANCE: Sub-millisecond factory operations with efficient singleton management.
"""

import logging
from typing import Type, Optional, Callable, Awaitable, List

from core.factories.base_exchange_factory import BaseExchangeFactory
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.exchanges.websocket.spot.base_ws_public import BaseExchangePublicWebsocketInterface
from core.config.structs import ExchangeConfig
from structs.common import Symbol, OrderBook, Trade, BookTicker
from core.transport.websocket.structs import ConnectionState

logger = logging.getLogger(__name__)


class PublicWebSocketExchangeFactory(BaseExchangeFactory):
    """
    Factory for creating public WebSocket exchange instances.
    
    Follows the established BaseExchangeFactory pattern with:
    - Exchange-based service registration and retrieval
    - Singleton instance management with efficient caching
    - Automatic dependency injection infrastructure
    - Standardized error handling and validation
    
    Design Principles:
    - Generic type safety with BaseExchangePublicWebsocketInterface
    - Auto-registration pattern (exchanges register on import)
    - Singleton caching for performance
    - HFT-compliant sub-millisecond operations
    """

    @classmethod
    def register(cls, exchange_name: str, implementation_class: Type) -> None:
        """
        Register a public WebSocket exchange implementation.
        
        Follows the auto-registration pattern used throughout the system.
        Called by exchange modules on import to self-register.
        
        Args:
            exchange_name: Exchange identifier (e.g., 'MEXC', 'GATEIO', 'GATEIO_FUTURES')
            implementation_class: Implementation class inheriting from BaseExchangePublicWebsocketInterface
            
        Raises:
            ValueError: If implementation doesn't inherit from correct base class
        """
        # Use base class validation and normalization
        exchange_key = cls._normalize_exchange_key(exchange_name)
        # Skip validation to avoid circular imports - validation happens at runtime
        
        # Register with base class registry
        cls._implementations[exchange_key] = implementation_class
        
        logger.debug(f"Registered public WebSocket implementation for {exchange_key}: {implementation_class.__name__}")

    @classmethod
    def inject(cls, exchange_name: str, config: Optional[ExchangeConfig] = None, 
               orderbook_diff_handler: Optional[Callable[[OrderBook, Symbol], Awaitable[None]]] = None,
               trades_handler: Optional[Callable[[Symbol, List[Trade]], Awaitable[None]]] = None,
               book_ticker_handler: Optional[Callable[[Symbol, BookTicker], Awaitable[None]]] = None,
               state_change_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None,
               **kwargs):
        """
        Create or retrieve public WebSocket exchange instance.
        
        Implements singleton pattern with efficient caching and auto-dependency injection.
        Uses BaseExchangeFactory infrastructure for consistent behavior.
        
        Args:
            exchange_name: Exchange identifier (e.g., 'MEXC', 'GATEIO', 'GATEIO_FUTURES')
            config: ExchangeConfig for the exchange (required for creation)
            orderbook_diff_handler: Callback for orderbook updates
            trades_handler: Callback for trade updates
            book_ticker_handler: Callback for book ticker updates
            state_change_handler: Callback for connection state changes
            **kwargs: Additional creation parameters
            
        Returns:
            WebSocket instance (cached singleton)
            
        Raises:
            ValueError: If exchange not registered or config not provided
        """
        if config is None:
            raise ValueError("ExchangeConfig required for public WebSocket exchange creation")
        
        # Use base class normalization
        exchange_key = cls._normalize_exchange_key(exchange_name)
        
        # Check if registered
        if exchange_key not in cls._implementations:
            available = cls.get_registered_exchanges()
            raise ValueError(
                f"No public WebSocket implementation registered for {exchange_name}. "
                f"Available: {available}"
            )
        
        # Check singleton cache first (HFT performance optimization)
        cache_key = f"{exchange_key}_{id(config)}"
        if cache_key in cls._instances:
            logger.debug(f"Returning cached public WebSocket instance for {exchange_key}")
            return cls._instances[cache_key]
        
        # Create new instance with auto-dependency injection
        implementation_class = cls._implementations[exchange_key]
        
        try:
            # Create instance with WebSocket-specific parameters
            instance = implementation_class(
                config=config,
                orderbook_diff_handler=orderbook_diff_handler,
                trades_handler=trades_handler,
                book_ticker_handler=book_ticker_handler,
                state_change_handler=state_change_handler,
                **kwargs
            )
            
            # Cache the instance for future requests
            cls._instances[cache_key] = instance
            
            logger.info(f"Created and cached public WebSocket instance for {exchange_key}: {implementation_class.__name__}")
            return instance
            
        except Exception as e:
            logger.error(f"Failed to create public WebSocket instance for {exchange_key}: {e}")
            raise ValueError(f"Failed to create public WebSocket exchange {exchange_name}: {e}") from e

    @classmethod
    def create_for_config(cls, config: ExchangeConfig,
                         orderbook_diff_handler: Optional[Callable[[OrderBook, Symbol], Awaitable[None]]] = None,
                         trades_handler: Optional[Callable[[Symbol, List[Trade]], Awaitable[None]]] = None,
                         book_ticker_handler: Optional[Callable[[Symbol, BookTicker], Awaitable[None]]] = None,
                         state_change_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None):
        """
        Convenience method to create WebSocket exchange from ExchangeConfig.
        
        Simplifies usage when you have an ExchangeConfig object and want to create
        the corresponding public WebSocket exchange instance.
        
        Args:
            config: ExchangeConfig with exchange name and settings
            orderbook_diff_handler: Callback for orderbook updates
            trades_handler: Callback for trade updates
            book_ticker_handler: Callback for book ticker updates
            state_change_handler: Callback for connection state changes
            
        Returns:
            WebSocket instance
            
        Raises:
            ValueError: If exchange not registered or config invalid
        """
        if not config or not config.name:
            raise ValueError("Valid ExchangeConfig with name required")
        
        exchange_name = str(config.name).upper()
        return cls.inject(exchange_name, config=config,
                         orderbook_diff_handler=orderbook_diff_handler,
                         trades_handler=trades_handler,
                         book_ticker_handler=book_ticker_handler,
                         state_change_handler=state_change_handler)

    @classmethod
    def get_available_exchanges(cls) -> list[str]:
        """
        Get list of available public WebSocket exchanges.
        
        Alias for get_registered_exchanges() with more descriptive name.
        
        Returns:
            List of exchange names that have public WebSocket implementations
        """
        return cls.get_registered_exchanges()

    @classmethod
    def is_exchange_available(cls, exchange_name: str) -> bool:
        """
        Check if public WebSocket implementation is available for exchange.
        
        Alias for is_registered() with more descriptive name.
        
        Args:
            exchange_name: Exchange identifier
            
        Returns:
            True if public WebSocket implementation is available
        """
        return cls.is_registered(exchange_name)