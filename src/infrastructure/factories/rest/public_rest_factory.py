"""
Public REST Exchange Factory

Factory for creating public REST exchange instances following the established
BaseExchangeFactory pattern with singleton management and auto-dependency injection.

HFT COMPLIANCE: Sub-millisecond factory operations with efficient singleton management.
"""

from typing import Type, Optional, Union

from infrastructure.factories.base_exchange_factory import BaseExchangeFactory
from exchanges.base.rest.spot.base_rest_spot_public import PublicExchangeSpotRestInterface
from infrastructure.config.structs import ExchangeConfig
from exchanges.base.utils.exchange_utils import exchange_name_to_enum
from infrastructure.data_structures.common import ExchangeEnum

# HFT Logger Integration
from infrastructure.logging import get_logger, get_exchange_logger, LoggingTimer

logger = get_logger('rest.factory.public')


class PublicRestExchangeFactory(BaseExchangeFactory[PublicExchangeSpotRestInterface]):
    """
    Factory for creating public REST exchange instances.
    
    Follows the established BaseExchangeFactory pattern with:
    - Exchange-based service registration and retrieval
    - Singleton instance management with efficient caching
    - Automatic dependency injection infrastructure
    - Standardized error handling and validation
    
    Design Principles:
    - Generic type safety with PublicExchangeSpotRestInterface
    - Auto-registration pattern (exchanges register on import)
    - Singleton caching for performance
    - HFT-compliant sub-millisecond operations
    """

    @classmethod
    def register(cls, exchange: ExchangeEnum, implementation_class: Type[PublicExchangeSpotRestInterface]) -> None:
        """
        Register a public REST exchange implementation.
        
        ENTRY POINT: Accepts both string and ExchangeEnum for backward compatibility.
        Converts strings to ExchangeEnum immediately at entry point.
        
        Follows the auto-registration pattern used throughout the system.
        Called by exchange modules on import to self-register.
        
        Args:
            exchange: Exchange identifier (string or ExchangeEnum - converted to ExchangeEnum immediately)
            implementation_class: Implementation class inheriting from PublicExchangeSpotRestInterface
            
        Raises:
            ValueError: If implementation doesn't inherit from correct base class or exchange not recognized
        """
        # Convert to ExchangeEnum at entry point
        exchange_enum = exchange_name_to_enum(exchange)
        
        # Use base class validation 
        cls._validate_implementation_class(implementation_class, PublicExchangeSpotRestInterface)
        
        # Register with base class registry using ExchangeEnum as key
        cls._implementations[exchange_enum] = implementation_class
        
        logger.info("Registered public REST implementation", 
                   exchange=exchange_enum.value,
                   implementation_class=implementation_class.__name__)
        
        # Track registration metrics
        logger.metric("rest_implementations_registered", 1,
                     tags={"exchange": exchange_enum.value, "type": "public"})

    @classmethod
    def inject(cls, exchange: Union[str, ExchangeEnum], config: Optional[ExchangeConfig] = None, **kwargs) -> PublicExchangeSpotRestInterface:
        """
        Create or retrieve public REST exchange instance.
        
        ENTRY POINT: Accepts both string and ExchangeEnum for backward compatibility.
        Converts strings to ExchangeEnum immediately at entry point.
        
        Implements singleton pattern with efficient caching and auto-dependency injection.
        Uses BaseExchangeFactory infrastructure for consistent behavior.
        
        Args:
            exchange: Exchange identifier (string or ExchangeEnum - converted to ExchangeEnum immediately)
            config: ExchangeConfig for the exchange (required for creation)
            **kwargs: Additional creation parameters
            
        Returns:
            PublicExchangeSpotRestInterface instance (cached singleton)
            
        Raises:
            ValueError: If exchange not registered, not recognized, or config not provided
        """
        if config is None:
            raise ValueError("ExchangeConfig required for public REST exchange creation")
        
        # Convert to ExchangeEnum at entry point
        exchange_enum = exchange_name_to_enum(exchange)
        
        # Check if registered
        if exchange_enum not in cls._implementations:
            available = cls.get_registered_exchanges()
            raise ValueError(
                f"No public REST implementation registered for {exchange_enum.value}. "
                f"Available: {available}"
            )
        
        # Check singleton cache first (HFT performance optimization)
        cache_key = f"{exchange_enum.value}_{id(config)}"
        if cache_key in cls._instances:
            logger.debug("Returning cached public REST instance",
                        exchange=exchange_enum.value,
                        cache_key=cache_key)
            
            # Track cache hit metrics
            logger.metric("rest_cache_hits", 1,
                         tags={"exchange": exchange_enum.value, "type": "public"})
            
            return cls._instances[cache_key]
        
        # Create exchange-specific logger for the instance
        exchange_logger = get_exchange_logger(exchange_enum.value, 'rest.public')
        
        # Create new instance with auto-dependency injection and performance tracking
        implementation_class = cls._implementations[exchange_enum]
        
        try:
            logger.info("Creating new public REST instance",
                       exchange=exchange_enum.value,
                       implementation_class=implementation_class.__name__)
            
            # Track creation performance
            with LoggingTimer(logger, "rest_instance_creation") as timer:
                # Explicitly inject exchange mapper (not handled by base factory due to circular dependency)
                from exchanges.services.exchange_mapper.factory import ExchangeMapperFactory
                
                with LoggingTimer(logger, "mapper_creation") as mapper_timer:
                    mapper = ExchangeMapperFactory.inject(exchange_enum)
                
                logger.metric("mapper_creation_time_ms", mapper_timer.elapsed_ms,
                             tags={"exchange": exchange_enum.value, "type": "public"})
                
                # Create instance with injected logger and dependencies
                instance = implementation_class(
                    config=config, 
                    mapper=mapper,
                    logger=exchange_logger  # Inject HFT logger
                )
            
            # Cache the instance for future requests
            cls._instances[cache_key] = instance
            
            logger.info("Created and cached public REST instance",
                       exchange=exchange_enum.value,
                       implementation_class=implementation_class.__name__,
                       creation_time_ms=timer.elapsed_ms)
            
            # Track creation metrics
            logger.metric("rest_instances_created", 1,
                         tags={"exchange": exchange_enum.value, "type": "public"})
            
            logger.metric("rest_creation_time_ms", timer.elapsed_ms,
                         tags={"exchange": exchange_enum.value, "type": "public"})
            
            return instance
            
        except Exception as e:
            logger.error("Failed to create public REST instance",
                        exchange=exchange_enum.value,
                        error_type=type(e).__name__,
                        error_message=str(e))
            
            # Track creation failure metrics
            logger.metric("rest_creation_failures", 1,
                         tags={"exchange": exchange_enum.value, "type": "public"})
            
            raise ValueError(f"Failed to create public REST exchange {exchange_enum.value}: {e}") from e

    @classmethod
    def create_for_config(cls, config: ExchangeConfig) -> PublicExchangeSpotRestInterface:
        """
        Convenience method to create exchange from ExchangeConfig.
        
        Simplifies usage when you have an ExchangeConfig object and want to create
        the corresponding public REST exchange instance.
        
        Args:
            config: ExchangeConfig with exchange name and settings
            
        Returns:
            PublicExchangeSpotRestInterface instance
            
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
        Get list of available public REST exchanges.
        
        Alias for get_registered_exchanges() with more descriptive name.
        
        Returns:
            List of exchange names that have public REST implementations
        """
        return cls.get_registered_exchanges()

    @classmethod
    def is_exchange_available(cls, exchange_name: str) -> bool:
        """
        Check if public REST implementation is available for exchange.
        
        Alias for is_registered() with more descriptive name.
        
        Args:
            exchange_name: Exchange identifier
            
        Returns:
            True if public REST implementation is available
        """
        return cls.is_registered(exchange_name)