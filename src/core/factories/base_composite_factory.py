"""
Base Composite Factory for Strategy Sets

Specialized factory for creating composite objects (strategy sets) from multiple
component strategies. Provides the same standardized API as BaseExchangeFactory
but optimized for assembly patterns rather than single component creation.

HFT COMPLIANCE: Sub-millisecond strategy set creation with efficient assembly.
"""

import logging
from typing import TypeVar, Generic, Dict, Type, Any, List
from abc import ABC, abstractmethod

from .factory_interface import ExchangeFactoryInterface

logger = logging.getLogger(__name__)

# Generic type for the composite product (e.g., RestStrategySet, WebSocketStrategySet)
T = TypeVar('T')


class BaseCompositeFactory(Generic[T], ExchangeFactoryInterface, ABC):
    """
    Abstract base factory for composite object creation from multiple components.
    
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
    # Stores component configurations: Dict[exchange_key, Dict[component_name, component_class]]
    _implementations: Dict[str, Dict[str, type]]
    _instances: Dict[str, T]
    
    def __init_subclass__(cls, **kwargs):
        """Initialize separate registries for each factory subclass."""
        super().__init_subclass__(**kwargs)
        cls._implementations = {}
        cls._instances = {}
    
    @classmethod
    @abstractmethod
    def register(cls, exchange_name: str, strategy_config: Dict[str, type], **kwargs) -> None:
        """
        Register component configuration for an exchange.
        
        Args:
            exchange_name: Exchange identifier (e.g., 'MEXC_PUBLIC', 'MEXC_PRIVATE')
            strategy_config: Dictionary mapping component names to implementation classes
            **kwargs: Additional registration parameters
        """
        pass
    
    @classmethod
    @abstractmethod
    def inject(cls, exchange_name: str, **kwargs) -> T:
        """
        Create composite object for an exchange.
        
        Must be implemented by subclass to handle component assembly.
        Should use _assemble_components() for consistent dependency injection.
        
        Args:
            exchange_name: Exchange identifier
            **kwargs: Creation parameters (config, dependencies, etc.)
            
        Returns:
            Assembled composite object
        """
        pass
    
    @classmethod
    @abstractmethod
    def _assemble_components(cls, exchange_name: str, strategy_config: Dict[str, type], **kwargs) -> T:
        """
        Assemble components into composite object.
        
        Must be implemented by subclass to define assembly logic.
        Base class provides dependency resolution infrastructure.
        
        Args:
            exchange_name: Exchange identifier
            strategy_config: Component configuration
            **kwargs: Assembly parameters
            
        Returns:
            Assembled composite object
        """
        pass
    
    # Standard utility methods - implemented in base class
    
    @classmethod
    def is_registered(cls, exchange_name: str) -> bool:
        """
        Check if exchange has registered component configuration.
        
        Args:
            exchange_name: Exchange identifier
            
        Returns:
            True if exchange is registered, False otherwise
        """
        exchange_key = cls._normalize_exchange_key(exchange_name)
        return exchange_key in cls._implementations
    
    @classmethod
    def get_registered_exchanges(cls) -> List[str]:
        """
        Get list of exchanges with registered configurations.
        
        Returns:
            List of registered exchange identifiers
        """
        return list(cls._implementations.keys())
    
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
            component_counts[exchange] = len(config)
            
        return {
            'factory_name': cls.__name__,
            'registered_exchanges_count': len(cls._implementations),
            'active_instances_count': len(cls._instances),
            'registered_exchanges': list(cls._implementations.keys()),
            'cached_instances': list(cls._instances.keys()),
            'component_counts_per_exchange': component_counts,
        }
    
    @staticmethod
    def _normalize_exchange_key(exchange_name: str) -> str:
        """
        Normalize exchange name to standard key format.
        
        Args:
            exchange_name: Exchange identifier in any case
            
        Returns:
            Normalized exchange key (uppercase)
        """
        return str(exchange_name).upper()
    
    @classmethod
    def _resolve_dependencies(cls, exchange_name: str, **context) -> Dict[str, Any]:
        """
        Generic dependency resolution infrastructure.
        
        Automatically resolves common dependencies used across factories:
        - symbol_mapper via ExchangeSymbolMapperFactory
        - exchange_mappings via ExchangeMappingsFactory
        
        Args:
            exchange_name: Exchange identifier for dependency resolution
            **context: Additional context for dependency resolution
            
        Returns:
            Dictionary with resolved dependencies for injection
        """
        resolved = {}
        # Strip API type suffixes for base exchange name
        base_exchange_name = exchange_name.replace('_PUBLIC', '').replace('_PRIVATE', '').replace('_public', '').replace('_private', '')
        exchange_key = cls._normalize_exchange_key(base_exchange_name)
        
        try:
            # Import factories lazily to avoid circular dependencies
            from core.cex.services.unified_mapper.factory import ExchangeMappingsFactory
            
            # Auto-resolve symbol mapper if available
            if 'symbol_mapper' not in context:
                from core.cex.services.symbol_mapper.factory import ExchangeSymbolMapperFactory

                try:
                    symbol_mapper = ExchangeSymbolMapperFactory.inject(exchange_key)
                    resolved['symbol_mapper'] = symbol_mapper
                except Exception:
                    # Graceful fallback - symbol mapper not available
                    pass
            # Auto-resolve exchange mappings if symbol mapper available
            if 'exchange_mappings' not in context:
                try:
                    exchange_mappings = ExchangeMappingsFactory.inject(exchange_key)
                    resolved['exchange_mappings'] = exchange_mappings
                except Exception:
                    # Graceful fallback - exchange mappings not available
                    pass
        except ImportError:
            # Graceful fallback - factories not available
            pass
        except Exception as e:
            # Log unexpected errors but don't fail
            logger.debug(f"Dependency resolution failed for {exchange_name}: {e}")
        
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