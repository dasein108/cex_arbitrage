"""
Private REST Exchange Factory

Factory for creating private REST exchange instances following the established
BaseExchangeFactory pattern with singleton management and auto-dependency injection.

HFT COMPLIANCE: Sub-millisecond factory operations with efficient singleton management.
"""

import logging
from typing import Type, Optional, Union

from core.factories.base_exchange_factory import BaseExchangeFactory
from core.exchanges.rest.spot.base_rest_spot_private import PrivateExchangeSpotRestInterface
from core.config.structs import ExchangeConfig
from core.utils.exchange_utils import exchange_name_to_enum
from structs.common import ExchangeEnum

logger = logging.getLogger(__name__)


class PrivateRestExchangeFactory(BaseExchangeFactory[PrivateExchangeSpotRestInterface]):
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
    def register(cls, exchange: Union[str, ExchangeEnum], implementation_class: Type[PrivateExchangeSpotRestInterface]) -> None:
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
            ValueError: If implementation doesn't inherit from correct base class or exchange not recognized
        """
        # Convert to ExchangeEnum at entry point
        exchange_enum = exchange_name_to_enum(exchange)
        
        # Use base class validation 
        cls._validate_implementation_class(implementation_class, PrivateExchangeSpotRestInterface)
        
        # Register with base class registry using ExchangeEnum as key
        cls._implementations[exchange_enum] = implementation_class
        
        logger.debug(f"Registered private REST implementation for {exchange_enum.value}: {implementation_class.__name__}")

    @classmethod
    def inject(cls, exchange: Union[str, ExchangeEnum], config: Optional[ExchangeConfig] = None, **kwargs) -> PrivateExchangeSpotRestInterface:
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
            logger.debug(f"Returning cached private REST instance for {exchange_enum.value}")
            return cls._instances[cache_key]
        
        # Create new instance with auto-dependency injection
        implementation_class = cls._implementations[exchange_enum]
        
        try:
            # Use base class auto-injection for consistent dependency resolution
            instance = cls._create_instance_with_auto_injection(
                exchange=exchange_enum,
                implementation_class=implementation_class,
                config=config,
                **kwargs
            )
            
            # Cache the instance for future requests
            cls._instances[cache_key] = instance
            
            logger.info(f"Created and cached private REST instance for {exchange_enum.value}: {implementation_class.__name__}")
            return instance
            
        except Exception as e:
            logger.error(f"Failed to create private REST instance for {exchange_enum.value}: {e}")
            raise ValueError(f"Failed to create private REST exchange {exchange_enum.value}: {e}") from e

    @classmethod
    def create_for_config(cls, config: ExchangeConfig) -> PrivateExchangeSpotRestInterface:
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