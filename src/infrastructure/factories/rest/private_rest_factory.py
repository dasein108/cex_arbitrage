"""
Private REST Exchange Factory

Factory for creating private REST exchange instances following the established
BaseExchangeFactory pattern with singleton management and auto-dependency injection.

HFT COMPLIANCE: Sub-millisecond factory operations with efficient singleton management.
"""

from typing import Type, Optional, Union

from infrastructure.factories.base_exchange_factory import BaseExchangeFactory
from exchanges.interfaces.rest import PrivateTradingInterface
from config.structs import ExchangeConfig
from infrastructure.utils.exchange_utils import exchange_name_to_enum
from exchanges.structs import ExchangeEnum
# HFT Logger Integration
from infrastructure.logging import get_logger, get_exchange_logger, LoggingTimer

logger = get_logger('rest.factory.private')


class PrivateRestExchangeFactory(BaseExchangeFactory[PrivateTradingInterface]):
    """
    Factory for creating private REST exchange instances.
    
    Follows the established BaseExchangeFactory pattern with:
    - Exchange-based service registration and retrieval
    - Singleton instance management with efficient caching
    - Automatic dependency injection infrastructure
    - Standardized error handling and validation
    
    Design Principles:
    - Generic type safety with PrivateExchangeSpotRestInterface
    - Auto-registration pattern (exchanges register on import)
    - Singleton caching for performance
    - HFT-compliant sub-millisecond operations
    """

    @classmethod
    def register(cls, exchange: Union[str, ExchangeEnum], implementation_class: Type[PrivateTradingInterface]) -> None:
        """
        Register a private REST exchange implementation.
        
        ENTRY POINT: Accepts both string and ExchangeEnum for backward compatibility.
        Converts strings to ExchangeEnum immediately at entry point.
        
        Follows the auto-registration pattern used throughout the system.
        Called by exchange modules on import to self-register.
        
        Args:
            exchange: Exchange identifier (string or ExchangeEnum - converted to ExchangeEnum immediately)
            implementation_class: Implementation class inheriting from PrivateExchangeSpotRestInterface
            
        Raises:
            ValueError: If implementation doesn't inherit from correct composite class or exchange not recognized
        """
        # Convert to ExchangeEnum at entry point
        exchange_enum = exchange_name_to_enum(exchange)
        
        # Use composite class validation
        cls._validate_implementation_class(implementation_class, PrivateTradingInterface)
        
        # Register with composite class registry using ExchangeEnum as key
        cls._implementations[exchange_enum] = implementation_class
        
        logger.info("Registered private REST implementation", 
                   exchange=exchange_enum.value,
                   implementation_class=implementation_class.__name__)
        
        # Track registration metrics
        logger.metric("rest_implementations_registered", 1,
                     tags={"exchange": exchange_enum.value, "type": "private"})

    @classmethod
    def inject(cls, exchange: Union[str, ExchangeEnum], config: Optional[ExchangeConfig] = None, **kwargs) -> PrivateTradingInterface:
        """
        Create or retrieve private REST exchange instance.
        
        Implements singleton pattern with efficient caching and auto-dependency injection.
        Uses BaseExchangeFactory infrastructure for consistent behavior.
        
        ENTRY POINT: Accepts both string and ExchangeEnum for backward compatibility.
        Converts strings to ExchangeEnum immediately at entry point.
        
        Args:
            exchange: Exchange identifier (string or ExchangeEnum - converted to ExchangeEnum immediately)
            config: ExchangeConfig for the exchange (required for creation)
            **kwargs: Additional creation parameters
            
        Returns:
            PrivateExchangeSpotRestInterface instance (cached singleton)
            
        Raises:
            ValueError: If exchange not registered, not recognized, or config not provided
        """
        if config is None:
            raise ValueError("ExchangeConfig required for private REST exchange creation")
        
        # Convert to ExchangeEnum at entry point
        exchange_enum = exchange_name_to_enum(exchange)
        
        # Check if registered
        if exchange_enum not in cls._implementations:
            available = cls.get_registered_exchanges()
            raise ValueError(
                f"No private REST implementation registered for {exchange_enum.value}. "
                f"Available: {available}"
            )
        
        # Check singleton cache first (HFT performance optimization)
        cache_key = f"{exchange_enum.value}_{id(config)}"
        if cache_key in cls._instances:
            logger.debug("Returning cached private REST instance", 
                        exchange=exchange_enum.value,
                        cache_key=cache_key)
            
            # Track cache hit metrics
            logger.metric("rest_cache_hits", 1,
                         tags={"exchange": exchange_enum.value, "type": "private"})
            
            return cls._instances[cache_key]
        
        # Create exchange-specific logger for the instance
        exchange_logger = get_exchange_logger(exchange_enum.value, 'rest.private')
        
        # Create new instance with auto-dependency injection and performance tracking
        implementation_class = cls._implementations[exchange_enum]
        
        try:
            logger.info("Creating new private REST instance",
                       exchange=exchange_enum.value,
                       implementation_class=implementation_class.__name__)
            
            # Track creation performance
            with LoggingTimer(logger, "rest_instance_creation") as timer:
                # Explicitly inject exchange mapper (not handled by composite factory due to circular dependency)
                from exchanges.services.exchange_mapper.factory import ExchangeMapperFactory
                
                with LoggingTimer(logger, "mapper_creation") as mapper_timer:
                    mapper = ExchangeMapperFactory.inject(exchange_enum)
                
                logger.metric("mapper_creation_time_ms", mapper_timer.elapsed_ms,
                             tags={"exchange": exchange_enum.value, "type": "private"})
                
                # Create instance with injected logger and dependencies
                instance = implementation_class(
                    config=config, 
                    mapper=mapper,
                    logger=exchange_logger  # Inject HFT logger
                )
            
            # Cache the instance for future requests
            cls._instances[cache_key] = instance
            
            logger.info("Created and cached private REST instance",
                       exchange=exchange_enum.value,
                       implementation_class=implementation_class.__name__,
                       creation_time_ms=timer.elapsed_ms)
            
            # Track creation metrics
            logger.metric("rest_instances_created", 1,
                         tags={"exchange": exchange_enum.value, "type": "private"})
            
            logger.metric("rest_creation_time_ms", timer.elapsed_ms,
                         tags={"exchange": exchange_enum.value, "type": "private"})
            
            return instance
            
        except Exception as e:
            logger.error("Failed to create private REST instance",
                        exchange=exchange_enum.value,
                        error_type=type(e).__name__,
                        error_message=str(e))
            
            # Track creation failure metrics
            logger.metric("rest_creation_failures", 1,
                         tags={"exchange": exchange_enum.value, "type": "private"})
            
            raise ValueError(f"Failed to create private REST exchange {exchange_enum.value}: {e}") from e

    @classmethod
    def create_for_config(cls, config: ExchangeConfig) -> PrivateTradingInterface:
        """
        Convenience method to create exchange from ExchangeConfig.
        
        Simplifies usage when you have an ExchangeConfig object and want to create
        the corresponding private REST exchange instance.
        
        Args:
            config: ExchangeConfig with exchange name and settings
            
        Returns:
            PrivateExchangeSpotRestInterface instance
            
        Raises:
            ValueError: If exchange not registered or config invalid
        """
        if not config or not config.name:
            raise ValueError("Valid ExchangeConfig with name required")
        
        # Pass config.name directly to inject() - it will handle string-to-enum conversion
        return cls.inject(config.name, config=config)

    @classmethod
    def get_available_exchanges(cls) -> list[str]:
        """
        Get list of available private REST exchanges.
        
        Alias for get_registered_exchanges() with more descriptive name.
        
        Returns:
            List of exchange names that have private REST implementations
        """
        return cls.get_registered_exchanges()

    @classmethod
    def is_exchange_available(cls, exchange_name: str) -> bool:
        """
        Check if private REST implementation is available for exchange.
        
        Alias for is_registered() with more descriptive name.
        
        Args:
            exchange_name: Exchange identifier
            
        Returns:
            True if private REST implementation is available
        """
        return cls.is_registered(exchange_name)