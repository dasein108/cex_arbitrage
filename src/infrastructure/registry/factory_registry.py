"""
Factory Registry for dynamic factory loading.

This registry enables dynamic loading of factory implementations
based on configuration, supporting dependency injection and
plugin-style architecture.
"""

import importlib
import logging
from typing import Dict, Type, Optional, Any, Protocol
from dataclasses import dataclass

from interfaces.factories.exchange_factory_interface import ExchangeFactoryInterface
from interfaces.factories.transport_factory_interface import TransportFactoryInterface
from interfaces.factories.symbol_mapper_factory_interface import SymbolMapperFactoryInterface


class FactoryProtocol(Protocol):
    """Protocol for factory classes."""
    pass


@dataclass
class FactoryRegistration:
    """Registration information for a factory."""
    name: str
    factory_type: str  # "exchange", "transport", "symbol_mapper"
    module_path: str
    class_name: str
    description: str = ""
    is_default: bool = False
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class FactoryRegistry:
    """
    Registry for dynamically loading factory implementations.
    
    Provides a plugin-style architecture where factories can be registered
    and loaded dynamically, enabling dependency injection and easier testing.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._registrations: Dict[str, FactoryRegistration] = {}
        self._loaded_factories: Dict[str, Any] = {}
        self._register_built_in_factories()

    def _register_built_in_factories(self) -> None:
        """Register built-in factory implementations."""
        
        # Exchange Factory
        self.register_factory(FactoryRegistration(
            name="default_exchange_factory",
            factory_type="exchange",
            module_path="arbitrage.exchange_factory",
            class_name="ExchangeFactory",
            description="Default exchange factory implementation",
            is_default=True,
            metadata={"supports_hot_reload": False}
        ))

    def register_factory(self, registration: FactoryRegistration) -> None:
        """
        Register a factory implementation.
        
        Args:
            registration: Factory registration information
        """
        self._registrations[registration.name] = registration
        self.logger.info(f"Registered factory: {registration.name} ({registration.factory_type})")

    def unregister_factory(self, factory_name: str) -> None:
        """
        Unregister a factory implementation.
        
        Args:
            factory_name: Name of factory to unregister
        """
        if factory_name in self._registrations:
            del self._registrations[factory_name]
            # Also remove from loaded cache
            if factory_name in self._loaded_factories:
                del self._loaded_factories[factory_name]
            self.logger.info(f"Unregistered factory: {factory_name}")
        else:
            self.logger.warning(f"Factory not found for unregistration: {factory_name}")

    def is_factory_registered(self, factory_name: str) -> bool:
        """
        Check if a factory is registered.
        
        Args:
            factory_name: Factory name to check
            
        Returns:
            True if factory is registered, False otherwise
        """
        return factory_name in self._registrations

    def get_registered_factories(self, factory_type: Optional[str] = None) -> Dict[str, FactoryRegistration]:
        """
        Get registered factories, optionally filtered by type.
        
        Args:
            factory_type: Optional type filter ("exchange", "transport", etc.)
            
        Returns:
            Dictionary of factory name to registration info
        """
        if factory_type is None:
            return self._registrations.copy()
        
        return {
            name: reg for name, reg in self._registrations.items()
            if reg.factory_type == factory_type
        }

    def get_default_factory(self, factory_type: str) -> Optional[str]:
        """
        Get the default factory name for a given type.
        
        Args:
            factory_type: Type of factory to get default for
            
        Returns:
            Factory name or None if no default found
        """
        for name, registration in self._registrations.items():
            if registration.factory_type == factory_type and registration.is_default:
                return name
        return None

    def load_factory(self, factory_name: str) -> Any:
        """
        Dynamically load a factory instance.
        
        Args:
            factory_name: Name of factory to load
            
        Returns:
            Factory instance
            
        Raises:
            ImportError: If factory loading fails
        """
        # Check cache first
        if factory_name in self._loaded_factories:
            return self._loaded_factories[factory_name]
        
        # Get registration
        registration = self._registrations.get(factory_name)
        if not registration:
            raise ImportError(f"Factory not registered: {factory_name}")
        
        try:
            # Dynamically import module
            module = importlib.import_module(registration.module_path)
            
            # Get class from module
            factory_class = getattr(module, registration.class_name)
            
            # Create instance
            factory_instance = factory_class()
            
            # Validate interface based on type
            self._validate_factory_interface(factory_instance, registration.factory_type)
            
            # Cache the instance
            self._loaded_factories[factory_name] = factory_instance
            
            self.logger.info(f"Successfully loaded factory: {factory_name}")
            return factory_instance
            
        except ImportError as e:
            raise ImportError(f"Failed to import factory module {registration.module_path}: {e}")
        except AttributeError as e:
            raise ImportError(f"Factory class {registration.class_name} not found in module: {e}")
        except Exception as e:
            raise ImportError(f"Unexpected error loading factory {factory_name}: {e}")

    def _validate_factory_interface(self, factory_instance: Any, factory_type: str) -> None:
        """
        Validate that a factory implements the correct interface.
        
        Args:
            factory_instance: Factory instance to validate
            factory_type: Expected factory type
            
        Raises:
            TypeError: If factory doesn't implement expected interface
        """
        if factory_type == "exchange":
            if not isinstance(factory_instance, ExchangeFactoryInterface):
                raise TypeError(f"Exchange factory must implement ExchangeFactoryInterface")
        elif factory_type == "transport":
            if not isinstance(factory_instance, TransportFactoryInterface):
                raise TypeError(f"Transport factory must implement TransportFactoryInterface")
        elif factory_type == "symbol_mapper":
            if not isinstance(factory_instance, SymbolMapperFactoryInterface):
                raise TypeError(f"Symbol mapper factory must implement SymbolMapperFactoryInterface")

    def get_exchange_factory(self, factory_name: Optional[str] = None) -> ExchangeFactoryInterface:
        """
        Get an exchange factory instance.
        
        Args:
            factory_name: Optional specific factory name, uses default if None
            
        Returns:
            Exchange factory instance
        """
        if factory_name is None:
            factory_name = self.get_default_factory("exchange")
            if factory_name is None:
                raise ImportError("No default exchange factory registered")
        
        return self.load_factory(factory_name)

    def get_transport_factory(self, factory_name: Optional[str] = None) -> TransportFactoryInterface:
        """
        Get a transport factory instance.
        
        Args:
            factory_name: Optional specific factory name, uses default if None
            
        Returns:
            Transport factory instance
        """
        if factory_name is None:
            factory_name = self.get_default_factory("transport")
            if factory_name is None:
                raise ImportError("No default transport factory registered")
        
        return self.load_factory(factory_name)

    def get_symbol_mapper_factory(self, factory_name: Optional[str] = None) -> SymbolMapperFactoryInterface:
        """
        Get a symbol mapper factory instance.
        
        Args:
            factory_name: Optional specific factory name, uses default if None
            
        Returns:
            Symbol mapper factory instance
        """
        if factory_name is None:
            factory_name = self.get_default_factory("symbol_mapper")
            if factory_name is None:
                raise ImportError("No default symbol mapper factory registered")
        
        return self.load_factory(factory_name)

    def get_registry_stats(self) -> Dict[str, Any]:
        """
        Get registry statistics.
        
        Returns:
            Dictionary with registry statistics
        """
        factory_types = {}
        for registration in self._registrations.values():
            factory_type = registration.factory_type
            factory_types[factory_type] = factory_types.get(factory_type, 0) + 1
        
        return {
            "total_registered": len(self._registrations),
            "loaded_instances": len(self._loaded_factories),
            "factory_types": factory_types,
            "factories": list(self._registrations.keys())
        }

    def clear_cache(self) -> None:
        """Clear the loaded factories cache."""
        self._loaded_factories.clear()
        self.logger.info("Cleared factory cache")

    def reload_factory(self, factory_name: str) -> None:
        """
        Reload a factory (useful for development).
        
        Args:
            factory_name: Factory to reload
        """
        # Remove from cache
        if factory_name in self._loaded_factories:
            del self._loaded_factories[factory_name]
        
        # Reload the module
        registration = self._registrations.get(factory_name)
        if registration:
            try:
                module = importlib.import_module(registration.module_path)
                importlib.reload(module)
                self.logger.info(f"Reloaded factory: {factory_name}")
            except Exception as e:
                self.logger.error(f"Failed to reload factory {factory_name}: {e}")


# Global registry instance
_factory_registry = FactoryRegistry()

def get_factory_registry() -> FactoryRegistry:
    """Get the global factory registry instance."""
    return _factory_registry