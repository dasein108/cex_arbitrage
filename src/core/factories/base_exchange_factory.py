"""
Generic Exchange Factory Base Class

Provides standardized factory patterns for all exchange-based services,
eliminating code duplication and ensuring consistency across the system.

HFT COMPLIANCE: Sub-millisecond factory operations with efficient singleton management.
"""

import logging
from typing import TypeVar, Generic, Dict, Type, Any, Optional, List, Union, TYPE_CHECKING
from abc import ABC, abstractmethod

from .factory_interface import ExchangeFactoryInterface
from core.utils.exchange_utils import exchange_name_to_enum, exchange_to_key

if TYPE_CHECKING:
    from structs.common import ExchangeEnum
else:
    from structs.common import ExchangeEnum

logger = logging.getLogger(__name__)

# Generic type for the service/strategy being managed
T = TypeVar('T')


class BaseExchangeFactory(Generic[T], ExchangeFactoryInterface, ABC):
    """
    Abstract base factory for exchange-specific service management.
    
    Provides standardized patterns for all exchange-based factories:
    - Exchange-based service registration and retrieval
    - Singleton instance management with efficient caching
    - Automatic dependency injection infrastructure
    - Factory-to-factory coordination
    - Consistent error handling and validation
    
    Design Principles:
    - Generic type safety with TypeVar
    - Standardized API across all factory types
    - Auto-injection of common dependencies
    - Registry isolation per factory subclass
    - HFT-compliant performance characteristics
    """
    
    # NOTE: Each subclass gets its own registry by explicit initialization
    # This ensures complete isolation between factory types
    _implementations: Dict[ExchangeEnum, Type[T]]
    _instances: Dict[str, T]  # Keep string keys for instances (cache includes config hash)
    
    def __init_subclass__(cls, **kwargs):
        """Initialize separate registries for each factory subclass."""
        super().__init_subclass__(**kwargs)
        cls._implementations = {}
        cls._instances = {}
    
    @classmethod
    @abstractmethod
    def register(cls, exchange: ExchangeEnum, implementation_class: Type[T], **kwargs) -> None:
        """
        Register implementation for an exchange.
        
        Must be implemented by subclass to handle factory-specific registration logic.
        Should use base class infrastructure for consistency.
        
        Args:
            exchange: Exchange identifier (ExchangeEnum only)
            implementation_class: Implementation class for the exchange
            **kwargs: Additional registration parameters
        """
        pass
    
    @classmethod
    @abstractmethod  
    def inject(cls, exchange: ExchangeEnum, **kwargs) -> T:
        """
        Create or retrieve instance for an exchange.
        
        Must be implemented by subclass to handle factory-specific creation logic.
        Should use base class infrastructure and auto-injection patterns.
        
        Args:
            exchange: Exchange identifier (ExchangeEnum only)
            **kwargs: Additional creation parameters
            
        Returns:
            Instance of the registered type for the exchange
            
        Raises:
            ValueError: If exchange not registered
        """
        pass
    
    # Standard utility methods - implemented in base class
    
    @classmethod
    def is_registered(cls, exchange: Union[str, ExchangeEnum]) -> bool:
        """
        Check if exchange has registered implementation.
        
        ENTRY POINT: Accepts both string and ExchangeEnum for backward compatibility.
        Converts strings to ExchangeEnum immediately at entry point.
        
        Args:
            exchange: Exchange identifier (string or ExchangeEnum - converted to ExchangeEnum immediately)
            
        Returns:
            True if exchange is registered, False otherwise
        """
        exchange_enum = exchange_name_to_enum(exchange)
        return exchange_enum in cls._implementations
    
    @classmethod
    def get_registered_exchanges(cls) -> List[str]:
        """
        Get list of exchanges with registered implementations.
        
        Returns:
            List of registered exchange identifiers (as string values)
        """
        return [exchange.value for exchange in cls._implementations.keys()]
    
    @classmethod
    def clear_cache(cls) -> None:
        """
        Clear cached singleton instances.
        
        Useful for testing or memory management. Does not affect registrations.
        """
        cls._instances.clear()
        logger.debug(f"Cleared cache for {cls.__name__}")
    
    @classmethod
    def reset_factory(cls) -> None:
        """
        Reset factory state - clear instances and registrations.
        
        WARNING: This will break existing references to instances.
        Use only for testing or complete system reset.
        """
        cls._instances.clear()
        cls._implementations.clear()
        logger.warning(f"Factory reset: {cls.__name__} - all instances and registrations cleared")
    
    @classmethod
    def get_factory_statistics(cls) -> Dict[str, Any]:
        """
        Get comprehensive factory statistics.
        
        Returns:
            Dictionary with factory state and performance metrics
        """
        return {
            'factory_name': cls.__name__,
            'registered_exchanges_count': len(cls._implementations),
            'active_instances_count': len(cls._instances),
            'registered_exchanges': [exchange.value for exchange in cls._implementations.keys()],
            'cached_instances': list(cls._instances.keys()),
        }
    
    # REMOVED: _normalize_exchange_key method
    # Use normalize_exchange_input() and exchange_to_key() from exchange_utils instead
    
    @classmethod
    def _resolve_dependencies(cls, exchange: ExchangeEnum, **context) -> Dict[str, Any]:
        """
        Generic dependency resolution infrastructure.
        
        Automatically resolves mandatory dependencies used across factories:
        - symbol_mapper via ExchangeSymbolMapperFactory (required)
        - mapper via ExchangeMapperFactory (required)
        
        Args:
            exchange: Exchange identifier for dependency resolution (ExchangeEnum only)
            **context: Additional context for dependency resolution
            
        Returns:
            Dictionary with resolved dependencies for injection
            
        Raises:
            Exception: If required dependencies (symbol_mapper, mapper) cannot be resolved
            
        Performance: Sub-millisecond resolution via factory caching
        """
        resolved = {}
        
        # Import symbol mapper factory only (exchange mapper is handled by specific factories)
        from core.exchanges.services.symbol_mapper.factory import ExchangeSymbolMapperFactory
        
        # Auto-resolve symbol mapper (mandatory for most factories)
        if 'symbol_mapper' not in context:
            symbol_mapper = ExchangeSymbolMapperFactory.inject(exchange)
            resolved['symbol_mapper'] = symbol_mapper
        
        # Note: Exchange mapper injection removed to prevent circular dependency
        # Factories that need exchange mapper should inject it explicitly
        
        return resolved
    
    @classmethod
    def _create_instance_with_auto_injection(
        cls, 
        exchange: ExchangeEnum, 
        implementation_class: Type[T], 
        **kwargs
    ) -> T:
        """
        Create instance with automatic dependency injection.
        
        Helper method for subclasses to create instances with auto-resolved dependencies.
        
        Args:
            exchange: Exchange identifier (ExchangeEnum only)
            implementation_class: Class to instantiate
            **kwargs: Additional constructor arguments
            
        Returns:
            Instance with auto-injected dependencies
        """
        # Resolve dependencies automatically
        auto_deps = cls._resolve_dependencies(exchange, **kwargs)
        
        # Merge with provided kwargs (provided kwargs take precedence)
        merged_kwargs = {**auto_deps, **kwargs}
        
        # Create instance with all dependencies (no fallback)
        return implementation_class(**merged_kwargs)
    
    @classmethod
    def _validate_implementation_class(cls, implementation_class: Type[T], expected_base: Type) -> None:
        """
        Validate that implementation class inherits from expected base class.
        
        Args:
            implementation_class: Class to validate
            expected_base: Expected base class
            
        Raises:
            ValueError: If implementation doesn't inherit from expected base
        """
        if not issubclass(implementation_class, expected_base):
            raise ValueError(
                f"Implementation class {implementation_class.__name__} must inherit from {expected_base.__name__}"
            )