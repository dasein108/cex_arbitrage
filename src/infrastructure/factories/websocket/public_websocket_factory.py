"""
Public WebSocket Exchange Factory

Factory for creating public WebSocket exchange instances following the established
BaseExchangeFactory pattern with singleton management and auto-dependency injection.

HFT COMPLIANCE: Sub-millisecond factory operations with efficient singleton management.
"""

from typing import Type, Optional, Callable, Awaitable, List, Union

from infrastructure.factories.base_exchange_factory import BaseExchangeFactory
from exchanges.base.utils.exchange_utils import exchange_name_to_enum
from infrastructure.data_structures.common import ExchangeEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass
from infrastructure.config.structs import ExchangeConfig
from infrastructure.data_structures.common import Symbol, OrderBook, Trade, BookTicker
from infrastructure.networking.websocket.structs import ConnectionState

# HFT Logger Integration
from infrastructure.logging import get_logger, get_exchange_logger, LoggingTimer

logger = get_logger('websocket.factory.public')


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
    def register(cls, exchange: Union[str, ExchangeEnum], implementation_class: Type) -> None:
        """
        Register a public WebSocket exchange implementation.
        
        ENTRY POINT: Accepts both string and ExchangeEnum for backward compatibility.
        Converts strings to ExchangeEnum immediately at entry point.
        
        Follows the auto-registration pattern used throughout the system.
        Called by exchange modules on import to self-register.
        
        Args:
            exchange: Exchange identifier (string or ExchangeEnum - converted to ExchangeEnum immediately)
            implementation_class: Implementation class inheriting from BaseExchangePublicWebsocketInterface
            
        Raises:
            ValueError: If exchange not recognized
        """
        # Convert to ExchangeEnum at entry point
        exchange_enum = exchange_name_to_enum(exchange)
        
        # Skip validation to avoid circular imports - validation happens at runtime
        
        # Register with base class registry using ExchangeEnum as key
        cls._implementations[exchange_enum] = implementation_class
        
        logger.info("Registered public WebSocket implementation", 
                   exchange=exchange_enum.value,
                   implementation_class=implementation_class.__name__)
        
        # Track registration metrics
        logger.metric("websocket_implementations_registered", 1,
                     tags={"exchange": exchange_enum.value, "type": "public"})

    @classmethod
    def inject(cls, exchange: Union[str, ExchangeEnum], config: Optional[ExchangeConfig] = None, 
               orderbook_diff_handler: Optional[Callable[[OrderBook, Symbol], Awaitable[None]]] = None,
               trades_handler: Optional[Callable[[Symbol, List[Trade]], Awaitable[None]]] = None,
               book_ticker_handler: Optional[Callable[[Symbol, BookTicker], Awaitable[None]]] = None,
               state_change_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None,
               **kwargs):
        """
        Create or retrieve public WebSocket exchange instance.
        
        Implements singleton pattern with efficient caching and auto-dependency injection.
        Uses BaseExchangeFactory infrastructure for consistent behavior.
        
        ENTRY POINT: Accepts both string and ExchangeEnum for backward compatibility.
        Converts strings to ExchangeEnum immediately at entry point.
        
        Args:
            exchange: Exchange identifier (string or ExchangeEnum - converted to ExchangeEnum immediately)
            config: ExchangeConfig for the exchange (required for creation)
            orderbook_diff_handler: Callback for orderbook updates
            trades_handler: Callback for trade updates
            book_ticker_handler: Callback for book ticker updates
            state_change_handler: Callback for connection state changes
            **kwargs: Additional creation parameters
            
        Returns:
            WebSocket instance (cached singleton)
            
        Raises:
            ValueError: If exchange not registered, not recognized, or config not provided
        """
        if config is None:
            raise ValueError("ExchangeConfig required for public WebSocket exchange creation")
        
        # Convert to ExchangeEnum at entry point
        exchange_enum = exchange_name_to_enum(exchange)
        
        # Check if registered
        if exchange_enum not in cls._implementations:
            available = cls.get_registered_exchanges()
            raise ValueError(
                f"No public WebSocket implementation registered for {exchange_enum.value}. "
                f"Available: {available}"
            )
        
        # Check singleton cache first (HFT performance optimization)
        cache_key = f"{exchange_enum.value}_{id(config)}"
        if cache_key in cls._instances:
            logger.debug("Returning cached public WebSocket instance", 
                        exchange=exchange_enum.value,
                        cache_key=cache_key)
            
            # Track cache hit metrics
            logger.metric("websocket_cache_hits", 1,
                         tags={"exchange": exchange_enum.value, "type": "public"})
            
            return cls._instances[cache_key]
        
        # Create exchange-specific logger for the instance
        exchange_logger = get_exchange_logger(exchange_enum.value, 'websocket.public')
        
        # Create new instance with auto-dependency injection and performance tracking
        implementation_class = cls._implementations[exchange_enum]
        
        try:
            logger.info("Creating new public WebSocket instance",
                       exchange=exchange_enum.value,
                       implementation_class=implementation_class.__name__)
            
            # Track creation performance
            with LoggingTimer(logger, "websocket_instance_creation") as timer:
                # Try to create instance with logger injection first, fallback without logger
                try:
                    instance = implementation_class(
                        config=config,
                        logger=exchange_logger,  # Try to inject HFT logger
                        orderbook_diff_handler=orderbook_diff_handler,
                        trades_handler=trades_handler,
                        book_ticker_handler=book_ticker_handler,
                        state_change_handler=state_change_handler,
                        **kwargs
                    )
                except TypeError as e:
                    if "unexpected keyword argument 'logger'" in str(e):
                        # Fallback: create without logger injection
                        logger.debug("Constructor doesn't support logger injection, creating without it",
                                   exchange=exchange_enum.value,
                                   implementation=implementation_class.__name__)
                        instance = implementation_class(
                            config=config,
                            orderbook_diff_handler=orderbook_diff_handler,
                            trades_handler=trades_handler,
                            book_ticker_handler=book_ticker_handler,
                            state_change_handler=state_change_handler,
                            **kwargs
                        )
                    else:
                        raise
            
            # Cache the instance for future requests
            cls._instances[cache_key] = instance
            
            logger.info("Created and cached public WebSocket instance",
                       exchange=exchange_enum.value,
                       implementation_class=implementation_class.__name__,
                       creation_time_ms=timer.elapsed_ms)
            
            # Track creation metrics
            logger.metric("websocket_instances_created", 1,
                         tags={"exchange": exchange_enum.value, "type": "public"})
            
            logger.metric("websocket_creation_time_ms", timer.elapsed_ms,
                         tags={"exchange": exchange_enum.value, "type": "public"})
            
            return instance
            
        except Exception as e:
            logger.error("Failed to create public WebSocket instance",
                        exchange=exchange_enum.value,
                        error_type=type(e).__name__,
                        error_message=str(e))
            
            # Track creation failure metrics
            logger.metric("websocket_creation_failures", 1,
                         tags={"exchange": exchange_enum.value, "type": "public"})
            
            raise ValueError(f"Failed to create public WebSocket exchange {exchange_enum.value}: {e}") from e

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
        
        # Pass config.name directly to inject() - it will handle string-to-enum conversion
        return cls.inject(config.name, config=config,
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