"""
Private WebSocket Exchange Factory

Factory for creating private WebSocket exchange instances following the established
BaseExchangeFactory pattern with singleton management and auto-dependency injection.

HFT COMPLIANCE: Sub-millisecond factory operations with efficient singleton management.
"""

import traceback
from typing import Type, Optional, Callable, Awaitable, Union, Dict

from infrastructure.factories.base_exchange_factory import BaseExchangeFactory
from exchanges.base.utils.exchange_utils import exchange_name_to_enum
from infrastructure.data_structures.common import ExchangeEnum

from infrastructure.config.structs import ExchangeConfig
from infrastructure.data_structures.common import Order, AssetBalance, AssetName, Trade
from infrastructure.factories.rest.private_rest_factory import PrivateRestExchangeFactory

# HFT Logger Integration
from infrastructure.logging import get_logger, get_exchange_logger, LoggingTimer

logger = get_logger('websocket.factory.private')


class PrivateWebSocketExchangeFactory(BaseExchangeFactory):
    """
    Factory for creating private WebSocket exchange instances.
    
    Follows the established BaseExchangeFactory pattern with:
    - Exchange-based service registration and retrieval
    - Singleton instance management with efficient caching
    - Automatic dependency injection infrastructure
    - Standardized error handling and validation
    
    Design Principles:
    - Generic type safety with BaseExchangePrivateWebsocketInterface
    - Auto-registration pattern (exchanges register on import)
    - Singleton caching for performance
    - HFT-compliant sub-millisecond operations
    """

    @classmethod
    def register(cls, exchange: Union[str, ExchangeEnum], implementation_class: Type) -> None:
        """
        Register a private WebSocket exchange implementation.
        
        ENTRY POINT: Accepts both string and ExchangeEnum for backward compatibility.
        Converts strings to ExchangeEnum immediately at entry point.
        
        Follows the auto-registration pattern used throughout the system.
        Called by exchange modules on import to self-register.
        
        Args:
            exchange: Exchange identifier (string or ExchangeEnum - converted to ExchangeEnum immediately)
            implementation_class: Implementation class inheriting from BaseExchangePrivateWebsocketInterface
            
        Raises:
            ValueError: If exchange not recognized
        """
        # Convert to ExchangeEnum at entry point
        exchange_enum = exchange_name_to_enum(exchange)
        
        # Skip validation to avoid circular imports - validation happens at runtime
        
        # Register with base class registry using ExchangeEnum as key
        cls._implementations[exchange_enum] = implementation_class
        
        logger.info("Registered private WebSocket implementation", 
                   exchange=exchange_enum.value,
                   implementation_class=implementation_class.__name__)
        
        # Track registration metrics
        logger.metric("websocket_implementations_registered", 1,
                     tags={"exchange": exchange_enum.value, "type": "private"})

    @classmethod
    def inject(cls, exchange: Union[str, ExchangeEnum], config: Optional[ExchangeConfig] = None,
               order_handler: Optional[Callable[[Order], Awaitable[None]]] = None,
               balance_handler: Optional[Callable[[Dict[AssetName, AssetBalance]], Awaitable[None]]] = None,
               trade_handler: Optional[Callable[[Trade], Awaitable[None]]] = None,
               state_change_handler: Optional[Callable] = None,
               **kwargs):
        """
        Create or retrieve private WebSocket exchange instance.
        
        Implements singleton pattern with efficient caching and auto-dependency injection.
        Uses BaseExchangeFactory infrastructure for consistent behavior.
        
        ENTRY POINT: Accepts both string and ExchangeEnum for backward compatibility.
        Converts strings to ExchangeEnum immediately at entry point.
        
        Args:
            exchange: Exchange identifier (string or ExchangeEnum - converted to ExchangeEnum immediately)
            config: ExchangeConfig for the exchange (required for creation)
            order_handler: Callback for individual order updates
            balance_handler: Callback for balance updates (dict of all balances)
            trade_handler: Callback for individual trade updates
            state_change_handler: Callback for connection state changes
            **kwargs: Additional creation parameters
            
        Returns:
            WebSocket instance (cached singleton)
            
        Raises:
            ValueError: If exchange not registered, not recognized, or config not provided
        """
        if config is None:
            raise ValueError("ExchangeConfig required for private WebSocket exchange creation")
        
        # Convert to ExchangeEnum at entry point
        exchange_enum = exchange_name_to_enum(exchange)
        
        # Check if registered
        if exchange_enum not in cls._implementations:
            available = cls.get_registered_exchanges()
            raise ValueError(
                f"No private WebSocket implementation registered for {exchange_enum.value}. "
                f"Available: {available}"
            )
        
        # Check singleton cache first (HFT performance optimization)
        cache_key = f"{exchange_enum.value}_{id(config)}"
        if cache_key in cls._instances:
            logger.debug("Returning cached private WebSocket instance", 
                        exchange=exchange_enum.value,
                        cache_key=cache_key)
            
            # Track cache hit metrics
            logger.metric("websocket_cache_hits", 1,
                         tags={"exchange": exchange_enum.value, "type": "private"})
            
            return cls._instances[cache_key]
        
        # Create exchange-specific logger for the instance
        exchange_logger = get_exchange_logger(exchange_enum.value, 'websocket.private')
        
        # Create new instance with auto-dependency injection and performance tracking
        implementation_class = cls._implementations[exchange_enum]
        
        try:
            logger.info("Creating new private WebSocket instance",
                       exchange=exchange_enum.value,
                       implementation_class=implementation_class.__name__)
            
            # Track creation performance
            with LoggingTimer(logger, "websocket_instance_creation") as timer:
                # Create private REST client dependency using factory
                with LoggingTimer(logger, "rest_client_creation") as rest_timer:
                    private_rest_client = PrivateRestExchangeFactory.inject(exchange_enum, config=config)
                
                logger.metric("rest_client_creation_time_ms", rest_timer.elapsed_ms,
                             tags={"exchange": exchange_enum.value, "type": "private"})
                
                # Try to create instance with logger injection first, fallback without logger
                try:
                    instance = implementation_class(
                        private_rest_client=private_rest_client,
                        config=config,
                        logger=exchange_logger,  # Try to inject HFT logger
                        order_handler=order_handler,
                        balance_handler=balance_handler,
                        trade_handler=trade_handler,
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
                            private_rest_client=private_rest_client,
                            config=config,
                            order_handler=order_handler,
                            balance_handler=balance_handler,
                            trade_handler=trade_handler,
                            state_change_handler=state_change_handler,
                            **kwargs
                        )
                    else:
                        raise
            
            # Cache the instance for future requests
            cls._instances[cache_key] = instance
            
            logger.info("Created and cached private WebSocket instance",
                       exchange=exchange_enum.value,
                       implementation_class=implementation_class.__name__,
                       creation_time_ms=timer.elapsed_ms)
            
            # Track creation metrics
            logger.metric("websocket_instances_created", 1,
                         tags={"exchange": exchange_enum.value, "type": "private"})
            
            logger.metric("websocket_creation_time_ms", timer.elapsed_ms,
                         tags={"exchange": exchange_enum.value, "type": "private"})
            
            return instance
            
        except Exception as e:
            logger.error("Failed to create private WebSocket instance",
                        exchange=exchange_enum.value,
                        error_type=type(e).__name__,
                        error_message=str(e))
            
            # Track creation failure metrics
            logger.metric("websocket_creation_failures", 1,
                         tags={"exchange": exchange_enum.value, "type": "private"})
            
            traceback.print_exc()
            raise ValueError(f"Failed to create private WebSocket exchange {exchange_enum.value}: {e}") from e
    @classmethod
    def create_for_config(cls, config: ExchangeConfig,
                         order_handler: Optional[Callable[[Order], Awaitable[None]]] = None,
                         balance_handler: Optional[Callable[[Dict[AssetName, AssetBalance]], Awaitable[None]]] = None,
                         trade_handler: Optional[Callable[[Trade], Awaitable[None]]] = None,
                         state_change_handler: Optional[Callable] = None):
        """
        Convenience method to create WebSocket exchange from ExchangeConfig.
        
        Simplifies usage when you have an ExchangeConfig object and want to create
        the corresponding private WebSocket exchange instance.
        
        Args:
            config: ExchangeConfig with exchange name and settings
            order_handler: Callback for individual order updates
            balance_handler: Callback for balance updates (dict of all balances)
            trade_handler: Callback for individual trade updates
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
                         order_handler=order_handler,
                         balance_handler=balance_handler,
                         trade_handler=trade_handler,
                         state_change_handler=state_change_handler)

    @classmethod
    def get_available_exchanges(cls) -> list[str]:
        """
        Get list of available private WebSocket exchanges.
        
        Alias for get_registered_exchanges() with more descriptive name.
        
        Returns:
            List of exchange names that have private WebSocket implementations
        """
        return cls.get_registered_exchanges()

    @classmethod
    def is_exchange_available(cls, exchange_name: str) -> bool:
        """
        Check if private WebSocket implementation is available for exchange.
        
        Alias for is_registered() with more descriptive name.
        
        Args:
            exchange_name: Exchange identifier
            
        Returns:
            True if private WebSocket implementation is available
        """
        return cls.is_registered(exchange_name)