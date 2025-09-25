"""
Base Composite Factory for Strategy Sets

Specialized factory for creating composite objects (strategy sets) from multiple
component strategies. Provides the same standardized API as BaseExchangeFactory
but optimized for assembly patterns rather than single component creation.

HFT COMPLIANCE: Sub-millisecond strategy set creation with efficient assembly.
"""

import logging
from typing import TypeVar, Generic, Dict, Any, List
from abc import ABC, abstractmethod

from .factory_interface import ExchangeFactoryInterface
from exchanges.structs import ExchangeEnum
logger = logging.getLogger(__name__)

# Generic type for the composite product (e.g., RestStrategySet, WebSocketStrategySet)
T = TypeVar('T')


class BaseCompositeFactory(Generic[T], ExchangeFactoryInterface, ABC):
    """
    Abstract composite factory for composite object creation from multiple components.
    
    Designed for factories that need to:
    - Store component configurations (Dict[str, type])
    - Assemble multiple strategies into composite objects
    - Handle different constructor patterns for different components
    - Maintain type safety with proper generics
    
    Examples: RestStrategyFactory, WebSocketStrategyFactory
    
    Design Principles:
    - Same API as BaseExchangeFactory (unified interface)
    - Component configuration storage instead of single types
    - Abstract assembly method for flexible composite creation
    - Auto-dependency injection for each component
    - Registry isolation per factory subclass
    """
    
    # NOTE: Each subclass gets its own registry by explicit initialization
    # Stores component configurations: Dict[ExchangeEnum, Dict[component_name, component_class]]
    _implementations: Dict[ExchangeEnum, Dict[str, type]]
    _instances: Dict[str, T]  # Keep string keys for instances (cache includes config hash)
    
    def __init_subclass__(cls, **kwargs):
        """Initialize separate registries for each factory subclass."""
        super().__init_subclass__(**kwargs)
        cls._implementations = {}
        cls._instances = {}
    
    @classmethod
    @abstractmethod
    def register(cls, exchange: ExchangeEnum, strategy_config: Dict[str, type], **kwargs) -> None:
        """
        Register component configuration for an exchange.
        
        Args:
            exchange: Exchange identifier (ExchangeEnum only)
            strategy_config: Dictionary mapping component names to implementation classes
            **kwargs: Additional registration parameters
        """
        pass
    
    @classmethod
    @abstractmethod
    def inject(cls, exchange: ExchangeEnum, **kwargs) -> T:
        """
        Create composite object for an exchange.
        
        Must be implemented by subclass to handle component assembly.
        Should use _assemble_components() for consistent dependency injection.
        
        Args:
            exchange: Exchange identifier (ExchangeEnum only)
            **kwargs: Creation parameters (config, dependencies, etc.)
            
        Returns:
            Assembled composite object
        """
        pass
    
    @classmethod
    @abstractmethod
    def _assemble_components(cls, exchange: ExchangeEnum, strategy_config: Dict[str, type], **kwargs) -> T:
        """
        Assemble components into composite object.
        
        Must be implemented by subclass to define assembly logic.
        Base class provides dependency resolution infrastructure.
        
        Args:
            exchange: Exchange identifier (ExchangeEnum only)
            strategy_config: Component configuration
            **kwargs: Assembly parameters (may include is_private, config, etc.)
            
        Returns:
            Assembled composite object
            
        Note:
            Subclasses should check for 'is_private' in kwargs when determining
            whether to create auth strategies or other private-specific components.
        """
        pass
    
    # Standard utility methods - implemented in composite class
    
    @classmethod
    def is_registered(cls, exchange: ExchangeEnum) -> bool:
        """
        Check if exchange has registered component configuration.
        
        Args:
            exchange: Exchange identifier (ExchangeEnum only)
            
        Returns:
            True if exchange is registered, False otherwise
        """
        return exchange in cls._implementations
    
    @classmethod
    def get_registered_exchanges(cls) -> List[str]:
        """
        Get list of exchanges with registered configurations.
        
        Returns:
            List of registered exchange identifiers (as string values)
        """
        return [exchange.value for exchange in cls._implementations.keys()]
    
    @classmethod
    def clear_cache(cls) -> None:
        """
        Clear cached composite instances.
        
        Note: Composite objects are typically not cached as they often need fresh
        configurations, but this method maintains API consistency.
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
            Dictionary with factory state and component metrics
        """
        component_counts = {}
        for exchange, config in cls._implementations.items():
            component_counts[exchange.value] = len(config)
            
        return {
            'factory_name': cls.__name__,
            'registered_exchanges_count': len(cls._implementations),
            'active_instances_count': len(cls._instances),
            'registered_exchanges': [exchange.value for exchange in cls._implementations.keys()],
            'cached_instances': list(cls._instances.keys()),
            'component_counts_per_exchange': component_counts,
        }
    

    @classmethod
    def _resolve_dependencies(cls, exchange: ExchangeEnum, **context) -> Dict[str, Any]:
        """
        Generic dependency resolution infrastructure.
        
        Note: Symbol mapper factory has been removed - exchanges now use direct utility functions.
        Only exchange mappings are resolved via factory injection.
        
        Args:
            exchange: Exchange identifier for dependency resolution (ExchangeEnum only)
            **context: Additional context for dependency resolution
            
        Returns:
            Dictionary with resolved dependencies for injection
        """
        resolved = {}
        exchange_key = exchange.value
        
        try:
            # ExchangeMapperFactory removed - exchanges use direct utility functions now
            # Symbol mapper factory removed - exchanges use direct utility functions now
            pass
        except ImportError:
            # Graceful fallback - factories not available
            pass
        except Exception as e:
            # Log unexpected errors but don't fail
            logger.debug(f"Dependency resolution failed for {exchange.value}: {e}")
        
        return resolved
    
    @classmethod
    def _create_component_with_fallback(
        cls,
        component_class: type,
        exchange_name: str,
        primary_kwargs: Dict[str, Any],
        fallback_kwargs: Dict[str, Any]
    ) -> Any:
        """
        Create component with intelligent constructor parameter handling.
        
        Tries primary kwargs first, falls back to simpler kwargs if constructor
        doesn't accept all parameters. Useful for components with different
        constructor signatures (e.g., public vs private strategies).
        
        Args:
            component_class: Class to instantiate
            exchange_name: Exchange identifier (for logging)
            primary_kwargs: Primary constructor arguments (with all dependencies)
            fallback_kwargs: Fallback constructor arguments (minimal set)
            
        Returns:
            Instantiated component
        """
        try:
            # Try with all dependencies first
            return component_class(**primary_kwargs)
        except TypeError as e:
            logger.debug(f"Primary constructor failed for {component_class.__name__}: {e}")
            try:
                # Fall back to minimal arguments
                return component_class(**fallback_kwargs)
            except TypeError as e2:
                logger.debug(f"Fallback constructor failed for {component_class.__name__}: {e2}")
                # Last resort: try with no arguments
                return component_class()
    
    @classmethod
    def _validate_strategy_config(cls, strategy_config: Dict[str, type], required_components: List[str]) -> None:
        """
        Validate that strategy configuration contains all required components.
        
        Args:
            strategy_config: Component configuration to validate
            required_components: List of required component names
            
        Raises:
            ValueError: If required components are missing
        """
        missing_components = []
        for component in required_components:
            if component not in strategy_config:
                missing_components.append(component)
        
        if missing_components:
            raise ValueError(f"Missing required components: {missing_components}")