"""
Exchange Symbol Mapper Factory

Factory pattern implementation for creating and managing exchange-specific
symbol mappers. Replaces singleton pattern with controlled instance management.

Key Features:
- One instance per exchange type (not global singleton)
- Extensible registration system for new exchanges
- Unified caching strategy across all mappers
- Thread-safe mapper instance management
- Performance monitoring and cache statistics

HFT Performance:
- Mapper retrieval: O(1) lookup
- Instance reuse: Optimal memory usage
- Cache sharing: Cross-exchange optimization opportunities
"""

import logging
from typing import Dict, Type, Optional, Any
from .base_symbol_mapper import BaseSymbolMapper

logger = logging.getLogger(__name__)


class ExchangeSymbolMapperFactory:
    """
    Factory for creating and managing exchange-specific symbol mappers.
    
    Provides centralized instance management with one mapper per exchange type.
    Eliminates global singleton pattern while maintaining performance benefits.
    """
    
    # Class-level mapper type registry
    _mapper_classes: Dict[str, Type[BaseSymbolMapper]] = {}
    
    # Instance cache - one instance per exchange type
    _mapper_instances: Dict[str, BaseSymbolMapper] = {}
    
    @classmethod
    def register_mapper(cls, exchange_name: str, mapper_class: Type[BaseSymbolMapper]) -> None:
        """
        Register a symbol mapper class for an exchange.
        
        Args:
            exchange_name: Exchange identifier (e.g., 'MEXC', 'GATEIO')
            mapper_class: Symbol mapper class implementing BaseSymbolMapper
        """
        exchange_key = exchange_name.upper()
        
        if not issubclass(mapper_class, BaseSymbolMapper):
            raise ValueError(f"Mapper class must inherit from BaseSymbolMapper")
        
        cls._mapper_classes[exchange_key] = mapper_class
        logger.info(f"Registered symbol mapper for {exchange_key}: {mapper_class.__name__}")
    
    @classmethod
    def get_mapper(cls, exchange_name: str) -> BaseSymbolMapper:
        """
        Get or create symbol mapper for specified exchange.
        
        Args:
            exchange_name: Exchange identifier (case-insensitive)
            
        Returns:
            Symbol mapper instance for the exchange
            
        Raises:
            ValueError: If exchange is not registered
            
        Performance: O(1) lookup with instance reuse
        """
        exchange_key = exchange_name.upper()
        
        # Return existing instance if available
        if exchange_key in cls._mapper_instances:
            return cls._mapper_instances[exchange_key]
        
        # Create new instance
        if exchange_key not in cls._mapper_classes:
            available_exchanges = list(cls._mapper_classes.keys())
            raise ValueError(
                f"Unknown exchange: {exchange_name}. "
                f"Available exchanges: {available_exchanges}. "
                f"Use register_mapper() to add new exchanges."
            )
        
        mapper_class = cls._mapper_classes[exchange_key]
        mapper_instance = mapper_class()
        
        # Cache instance for reuse
        cls._mapper_instances[exchange_key] = mapper_instance
        
        logger.info(f"Created symbol mapper instance for {exchange_key}: {mapper_class.__name__}")
        return mapper_instance
    
    @classmethod
    def is_exchange_supported(cls, exchange_name: str) -> bool:
        """
        Check if exchange is supported by the factory.
        
        Args:
            exchange_name: Exchange identifier
            
        Returns:
            True if exchange is registered, False otherwise
        """
        return exchange_name.upper() in cls._mapper_classes
    
    @classmethod
    def get_supported_exchanges(cls) -> list[str]:
        """
        Get list of supported exchange names.
        
        Returns:
            List of registered exchange identifiers
        """
        return list(cls._mapper_classes.keys())
    
    @classmethod
    def get_all_mappers(cls) -> Dict[str, BaseSymbolMapper]:
        """
        Get all active mapper instances.
        
        Returns:
            Dictionary mapping exchange names to mapper instances
        """
        # Create instances for all registered exchanges
        for exchange_name in cls._mapper_classes:
            if exchange_name not in cls._mapper_instances:
                cls.get_mapper(exchange_name)  # Creates instance
        
        return cls._mapper_instances.copy()
    
    @classmethod
    def get_cache_statistics(cls) -> Dict[str, Any]:
        """
        Get comprehensive cache statistics across all mappers.
        
        Returns:
            Dictionary with cache statistics for each exchange
        """
        stats = {
            'factory_info': {
                'registered_exchanges': len(cls._mapper_classes),
                'active_instances': len(cls._mapper_instances),
                'supported_exchanges': cls.get_supported_exchanges()
            },
            'exchange_stats': {}
        }
        
        for exchange_name, mapper in cls._mapper_instances.items():
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
        
        Useful for testing or memory management.
        """
        cleared_count = 0
        for mapper in cls._mapper_instances.values():
            mapper.clear_cache()
            cleared_count += 1
        
        logger.info(f"Cleared caches for {cleared_count} mapper instances")
    
    @classmethod
    def reset_factory(cls) -> None:
        """
        Reset factory state - clear all instances and registrations.
        
        WARNING: This will break existing mapper references.
        Use only for testing or complete system reset.
        """
        cls._mapper_instances.clear()
        cls._mapper_classes.clear()
        logger.warning("Factory reset: All mapper instances and registrations cleared")
    
    @classmethod
    def validate_all_mappers(cls) -> Dict[str, bool]:
        """
        Validate all registered mapper classes can be instantiated.
        
        Returns:
            Dictionary mapping exchange names to validation results
        """
        validation_results = {}
        
        for exchange_name, mapper_class in cls._mapper_classes.items():
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


# Convenience function for common usage
def get_symbol_mapper(exchange_name: str) -> BaseSymbolMapper:
    """
    Convenience function to get symbol mapper for an exchange.
    
    Args:
        exchange_name: Exchange identifier
        
    Returns:
        Symbol mapper instance
    """
    return ExchangeSymbolMapperFactory.get_mapper(exchange_name)