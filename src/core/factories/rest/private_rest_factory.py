"""
Private REST Exchange Factory

Factory for creating private REST exchange instances following the established
BaseExchangeFactory pattern with singleton management and auto-dependency injection.

HFT COMPLIANCE: Sub-millisecond factory operations with efficient singleton management.
"""

import logging
from typing import Type, Optional

from core.factories.base_exchange_factory import BaseExchangeFactory
from core.exchanges.rest.spot.base_rest_spot_private import PrivateExchangeSpotRestInterface
from core.config.structs import ExchangeConfig

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
    def register(cls, exchange_name: str, implementation_class: Type[PrivateExchangeSpotRestInterface]) -> None:
        """
        Register a private REST exchange implementation.
        
        Follows the auto-registration pattern used throughout the system.
        Called by exchange modules on import to self-register.
        
        Args:
            exchange_name: Exchange identifier (e.g., 'MEXC', 'GATEIO')
            implementation_class: Implementation class inheriting from PrivateExchangeSpotRestInterface
            
        Raises:
            ValueError: If implementation doesn't inherit from correct base class
        """
        # Use base class validation and normalization
        exchange_key = cls._normalize_exchange_key(exchange_name)
        cls._validate_implementation_class(implementation_class, PrivateExchangeSpotRestInterface)
        
        # Register with base class registry
        cls._implementations[exchange_key] = implementation_class
        
        logger.debug(f"Registered private REST implementation for {exchange_key}: {implementation_class.__name__}")

    @classmethod
    def inject(cls, exchange_name: str, config: Optional[ExchangeConfig] = None, **kwargs) -> PrivateExchangeSpotRestInterface:
        """
        Create or retrieve private REST exchange instance.
        
        Implements singleton pattern with efficient caching and auto-dependency injection.
        Uses BaseExchangeFactory infrastructure for consistent behavior.
        
        Args:
            exchange_name: Exchange identifier (e.g., 'MEXC', 'GATEIO')
            config: ExchangeConfig for the exchange (required for creation)
            **kwargs: Additional creation parameters
            
        Returns:
            PrivateExchangeSpotRestInterface instance (cached singleton)
            
        Raises:
            ValueError: If exchange not registered or config not provided
        """
        if config is None:
            raise ValueError("ExchangeConfig required for private REST exchange creation")
        
        # Use base class normalization
        exchange_key = cls._normalize_exchange_key(exchange_name)
        
        # Check if registered
        if exchange_key not in cls._implementations:
            available = cls.get_registered_exchanges()
            raise ValueError(
                f"No private REST implementation registered for {exchange_name}. "
                f"Available: {available}"
            )
        
        # Check singleton cache first (HFT performance optimization)
        cache_key = f"{exchange_key}_{id(config)}"
        if cache_key in cls._instances:
            logger.debug(f"Returning cached private REST instance for {exchange_key}")
            return cls._instances[cache_key]
        
        # Create new instance with auto-dependency injection
        implementation_class = cls._implementations[exchange_key]
        
        try:
            # Use base class auto-injection for consistent dependency resolution
            instance = cls._create_instance_with_auto_injection(
                exchange_name=exchange_name,
                implementation_class=implementation_class,
                config=config,
                **kwargs
            )
            
            # Cache the instance for future requests
            cls._instances[cache_key] = instance
            
            logger.info(f"Created and cached private REST instance for {exchange_key}: {implementation_class.__name__}")
            return instance
            
        except Exception as e:
            logger.error(f"Failed to create private REST instance for {exchange_key}: {e}")
            raise ValueError(f"Failed to create private REST exchange {exchange_name}: {e}") from e

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
        
        exchange_name = str(config.name).upper()
        return cls.inject(exchange_name, config=config)

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