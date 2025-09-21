"""
Exchange Symbol Mapper Factory

Factory pattern implementation for creating and managing exchange-specific
symbol mappers using the standardized BaseExchangeFactory infrastructure.

Key Features:
- Inherits from BaseExchangeFactory for consistent patterns
- One instance per exchange type (singleton per exchange)
- Automatic dependency injection infrastructure
- Thread-safe mapper instance management
- Performance monitoring and cache statistics

HFT Performance:
- Mapper retrieval: O(1) lookup via base class
- Instance reuse: Optimal memory usage with singleton pattern
- Auto-injection: Sub-millisecond dependency resolution
"""

import logging
from typing import Dict, Type, Optional, Any
from .base_symbol_mapper import SymbolMapperInterface
from core.factories.base_exchange_factory import BaseExchangeFactory

logger = logging.getLogger(__name__)


class ExchangeSymbolMapperFactory(BaseExchangeFactory[SymbolMapperInterface]):
    """
    Factory for creating and managing exchange-specific symbol mappers.
    
    Inherits from BaseExchangeFactory to provide standardized factory patterns:
    - Registry management via base class (_implementations, _instances)
    - Exchange key normalization and validation
    - Consistent error handling and logging
    - Auto-dependency injection infrastructure
    """
    
    @classmethod
    def register(cls, exchange_name: str, mapper_class: Type[SymbolMapperInterface], **kwargs) -> None:
        """
        Register a symbol mapper class for an exchange.
        
        Uses base class infrastructure with validation and auto-instance creation.
        
        Args:
            exchange_name: Exchange identifier (e.g., 'MEXC', 'GATEIO')
            mapper_class: Symbol mapper class implementing SymbolMapperInterface
        """
        # Use base class validation
        cls._validate_implementation_class(mapper_class, SymbolMapperInterface)
        
        # Use base class normalization
        exchange_key = cls._normalize_exchange_key(exchange_name)
        
        # Register with base class registry
        cls._implementations[exchange_key] = mapper_class
        
        # Auto-create instance immediately for symbol mappers (they have no dependencies)
        try:
            mapper_instance = mapper_class()
            cls._instances[exchange_key] = mapper_instance
            logger.info(f"Registered and created symbol mapper for {exchange_key}: {mapper_class.__name__}")
        except Exception as e:
            # Log error but still register the class
            logger.warning(f"Failed to auto-create symbol mapper for {exchange_key}: {e}")
            logger.info(f"Registered symbol mapper class for {exchange_key}: {mapper_class.__name__}")
    
    @classmethod
    def inject(cls, exchange_name: str, **kwargs) -> SymbolMapperInterface:
        """
        Get or create symbol mapper for specified exchange.
        
        Uses base class infrastructure for consistent error handling and caching.
        
        Args:
            exchange_name: Exchange identifier (case-insensitive)
            
        Returns:
            Symbol mapper instance for the exchange
            
        Raises:
            ValueError: If exchange is not registered
            
        Performance: O(1) lookup with instance reuse via base class
        """
        # Use base class normalization
        exchange_key = cls._normalize_exchange_key(exchange_name)
        
        # Return existing instance if available (from base class registry)
        if exchange_key in cls._instances:
            return cls._instances[exchange_key]
        
        # Create new instance if registered
        if exchange_key not in cls._implementations:
            available_exchanges = cls.get_registered_exchanges()
            raise ValueError(
                f"Unknown exchange: {exchange_name}. "
                f"Available exchanges: {available_exchanges}. "
                f"Use register() to add new exchanges."
            )
        
        mapper_class = cls._implementations[exchange_key]
        mapper_instance = mapper_class()
        
        # Cache instance for reuse (in base class registry)
        cls._instances[exchange_key] = mapper_instance
        
        logger.info(f"Created symbol mapper instance for {exchange_key}: {mapper_class.__name__}")
        return mapper_instance
    
    # Legacy method aliases for backward compatibility
    @classmethod
    def is_exchange_supported(cls, exchange_name: str) -> bool:
        """
        Check if exchange is supported by the factory.
        
        Legacy alias for is_registered() from base class.
        
        Args:
            exchange_name: Exchange identifier
            
        Returns:
            True if exchange is registered, False otherwise
        """
        return cls.is_registered(exchange_name)
    
    @classmethod
    def get_supported_exchanges(cls) -> list[str]:
        """
        Get list of supported exchange names.
        
        Legacy alias for get_registered_exchanges() from base class.
        
        Returns:
            List of registered exchange identifiers
        """
        return cls.get_registered_exchanges()
    
    @classmethod
    def get_all_mappers(cls) -> Dict[str, SymbolMapperInterface]:
        """
        Get all active mapper instances.
        
        Uses base class registries for consistent state management.
        
        Returns:
            Dictionary mapping exchange names to mapper instances
        """
        # Create instances for all registered exchanges
        for exchange_name in cls._implementations:
            if exchange_name not in cls._instances:
                cls.inject(exchange_name)  # Creates instance
        
        return cls._instances.copy()
    
    @classmethod
    def get_cache_statistics(cls) -> Dict[str, Any]:
        """
        Get comprehensive cache statistics across all mappers.
        
        Enhanced with base class factory statistics.
        
        Returns:
            Dictionary with cache statistics for each exchange
        """
        # Start with base class statistics
        stats = cls.get_factory_statistics()
        
        # Add mapper-specific statistics
        stats['exchange_stats'] = {}
        
        for exchange_name, mapper in cls._instances.items():
            stats['exchange_stats'][exchange_name] = {
                'mapper_class': mapper.__class__.__name__,
                'cache_stats': mapper.get_cache_stats(),
                'quote_assets': mapper.quote_assets
            }
        
        return stats
    
    @classmethod
    def clear_all_caches(cls) -> None:
        """
        Clear all caches across all mapper instances.
        
        Also clears base class instance cache for consistency.
        
        Useful for testing or memory management.
        """
        cleared_count = 0
        for mapper in cls._instances.values():
            mapper.clear_cache()
            cleared_count += 1
        
        # Also clear base class cache
        cls.clear_cache()
        
        logger.info(f"Cleared caches for {cleared_count} mapper instances")
    
    @classmethod
    def validate_all_mappers(cls) -> Dict[str, bool]:
        """
        Validate all registered mapper classes can be instantiated.
        
        Uses base class registries for consistent validation.
        
        Returns:
            Dictionary mapping exchange names to validation results
        """
        validation_results = {}
        
        for exchange_name, mapper_class in cls._implementations.items():
            try:
                # Try to create instance
                test_instance = mapper_class()
                # Basic validation
                if hasattr(test_instance, 'quote_assets') and test_instance.quote_assets:
                    validation_results[exchange_name] = True
                else:
                    validation_results[exchange_name] = False
                    logger.warning(f"Mapper {exchange_name} missing quote_assets")
            except Exception as e:
                validation_results[exchange_name] = False
                logger.error(f"Mapper {exchange_name} validation failed: {e}")
        
        return validation_results