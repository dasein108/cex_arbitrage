"""
Exchange Registry for dynamic exchange loading.

This registry enables dynamic loading of exchange implementations
based on configuration, eliminating hardcoded imports and enabling
plugin-style architecture.
"""

import importlib
import logging
from typing import Dict, List, Type, Optional, Any
from dataclasses import dataclass

from infrastructure.data_structures.common import ExchangeName
from interfaces.exchanges.base import BasePrivateExchangeInterface
from infrastructure.exceptions.exchange import BaseExchangeError


@dataclass
class ExchangeRegistration:
    """Registration information for an exchange."""
    name: ExchangeName
    module_path: str
    class_name: str
    public_class_name: Optional[str] = None
    supports_futures: bool = False
    supports_margin: bool = False
    min_trade_amount: float = 0.001
    supported_order_types: List[str] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.supported_order_types is None:
            self.supported_order_types = ["limit", "market"]
        if self.metadata is None:
            self.metadata = {}


class ExchangeRegistry:
    """
    Registry for dynamically loading exchange implementations.
    
    Provides a plugin-style architecture where exchanges can be registered
    and loaded dynamically based on configuration, eliminating hardcoded
    imports and enabling easier testing and development.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._registrations: Dict[str, ExchangeRegistration] = {}
        self._loaded_classes: Dict[str, Type[BasePrivateExchangeInterface]] = {}
        self._register_built_in_exchanges()

    def _register_built_in_exchanges(self) -> None:
        """Register built-in exchange implementations."""
        
        # MEXC Exchange
        self.register_exchange(ExchangeRegistration(
            name=ExchangeName("mexc"),
            module_path="exchanges.mexc.private_exchange",
            class_name="MexcPrivateExchange",
            public_class_name="MexcPublicExchange",
            supports_futures=False,
            supports_margin=False,
            min_trade_amount=0.001,
            supported_order_types=["limit", "market", "stop_limit"],
            metadata={
                "api_version": "v3",
                "rate_limit_requests_per_minute": 1200,
                "websocket_channels": ["orderbook", "trades", "orders", "balances"],
                "base_url": "https://api.mexc.com",
                "websocket_url": "wss://wbs.mexc.com/ws"
            }
        ))
        
        # Gate.io Exchange
        self.register_exchange(ExchangeRegistration(
            name=ExchangeName("gateio"),
            module_path="exchanges.gateio.private_exchange",
            class_name="GateioPrivateExchange",
            public_class_name="GateioPublicExchange",
            supports_futures=False,
            supports_margin=True,
            min_trade_amount=0.0001,
            supported_order_types=["limit", "market", "stop"],
            metadata={
                "api_version": "v4",
                "rate_limit_requests_per_second": 10,
                "websocket_channels": ["orderbook", "trades", "orders", "balances"],
                "base_url": "https://api.gateio.ws",
                "websocket_url": "wss://api.gateio.ws/ws/v4/"
            }
        ))

    def register_exchange(self, registration: ExchangeRegistration) -> None:
        """
        Register an exchange implementation.
        
        Args:
            registration: Exchange registration information
        """
        exchange_name = str(registration.name)
        self._registrations[exchange_name] = registration
        self.logger.info(f"Registered exchange: {exchange_name}")

    def unregister_exchange(self, exchange_name: ExchangeName) -> None:
        """
        Unregister an exchange implementation.
        
        Args:
            exchange_name: Name of exchange to unregister
        """
        exchange_name_str = str(exchange_name)
        if exchange_name_str in self._registrations:
            del self._registrations[exchange_name_str]
            # Also remove from loaded classes cache
            if exchange_name_str in self._loaded_classes:
                del self._loaded_classes[exchange_name_str]
            self.logger.info(f"Unregistered exchange: {exchange_name_str}")
        else:
            self.logger.warning(f"Exchange not found for unregistration: {exchange_name_str}")

    def is_exchange_registered(self, exchange_name: ExchangeName) -> bool:
        """
        Check if an exchange is registered.
        
        Args:
            exchange_name: Exchange name to check
            
        Returns:
            True if exchange is registered, False otherwise
        """
        return str(exchange_name) in self._registrations

    def get_registered_exchanges(self) -> List[ExchangeName]:
        """
        Get list of all registered exchange names.
        
        Returns:
            List of registered exchange names
        """
        return [ExchangeName(name) for name in self._registrations.keys()]

    def get_exchange_info(self, exchange_name: ExchangeName) -> Optional[ExchangeRegistration]:
        """
        Get registration information for an exchange.
        
        Args:
            exchange_name: Exchange name to get info for
            
        Returns:
            Exchange registration info or None if not found
        """
        return self._registrations.get(str(exchange_name))

    def load_exchange_class(self, exchange_name: ExchangeName) -> Type[BasePrivateExchangeInterface]:
        """
        Dynamically load an exchange class.
        
        Args:
            exchange_name: Name of exchange to load
            
        Returns:
            Exchange class type
            
        Raises:
            BaseExchangeError: If exchange is not registered or loading fails
        """
        exchange_name_str = str(exchange_name)
        
        # Check cache first
        if exchange_name_str in self._loaded_classes:
            return self._loaded_classes[exchange_name_str]
        
        # Get registration
        registration = self._registrations.get(exchange_name_str)
        if not registration:
            raise BaseExchangeError(f"Exchange not registered: {exchange_name_str}")
        
        try:
            # Dynamically import module
            module = importlib.import_module(registration.module_path)
            
            # Get class from module
            exchange_class = getattr(module, registration.class_name)
            
            # Validate that it implements the correct interface
            if not issubclass(exchange_class, BasePrivateExchangeInterface):
                raise BaseExchangeError(
                    f"Exchange class {registration.class_name} does not implement BasePrivateExchangeInterface"
                )
            
            # Cache the loaded class
            self._loaded_classes[exchange_name_str] = exchange_class
            
            self.logger.info(f"Successfully loaded exchange class: {exchange_name_str}")
            return exchange_class
            
        except ImportError as e:
            raise BaseExchangeError(f"Failed to import exchange module {registration.module_path}: {e}")
        except AttributeError as e:
            raise BaseExchangeError(f"Exchange class {registration.class_name} not found in module: {e}")
        except Exception as e:
            raise BaseExchangeError(f"Unexpected error loading exchange {exchange_name_str}: {e}")

    def create_exchange_instance(
        self, 
        exchange_name: ExchangeName,
        config: Any,
        **kwargs
    ) -> BasePrivateExchangeInterface:
        """
        Create an instance of an exchange.
        
        Args:
            exchange_name: Name of exchange to create
            config: Exchange configuration
            **kwargs: Additional arguments for exchange constructor
            
        Returns:
            Exchange instance
            
        Raises:
            BaseExchangeError: If exchange creation fails
        """
        exchange_class = self.load_exchange_class(exchange_name)
        
        try:
            # Create instance with config and kwargs
            instance = exchange_class(config, **kwargs)
            self.logger.info(f"Created exchange instance: {exchange_name}")
            return instance
            
        except Exception as e:
            raise BaseExchangeError(f"Failed to create exchange instance {exchange_name}: {e}")

    def get_exchanges_with_capability(self, capability: str) -> List[ExchangeName]:
        """
        Get exchanges that support a specific capability.
        
        Args:
            capability: Capability to check for ('futures', 'margin', etc.)
            
        Returns:
            List of exchange names that support the capability
        """
        result = []
        for name, registration in self._registrations.items():
            if capability == "futures" and registration.supports_futures:
                result.append(ExchangeName(name))
            elif capability == "margin" and registration.supports_margin:
                result.append(ExchangeName(name))
            elif capability in registration.supported_order_types:
                result.append(ExchangeName(name))
        
        return result

    def get_registry_stats(self) -> Dict[str, Any]:
        """
        Get registry statistics.
        
        Returns:
            Dictionary with registry statistics
        """
        return {
            "total_registered": len(self._registrations),
            "loaded_classes": len(self._loaded_classes),
            "exchanges": list(self._registrations.keys()),
            "futures_support": len(self.get_exchanges_with_capability("futures")),
            "margin_support": len(self.get_exchanges_with_capability("margin"))
        }

    def clear_cache(self) -> None:
        """Clear the loaded classes cache."""
        self._loaded_classes.clear()
        self.logger.info("Cleared exchange class cache")

    def reload_exchange(self, exchange_name: ExchangeName) -> None:
        """
        Reload an exchange class (useful for development).
        
        Args:
            exchange_name: Exchange to reload
        """
        exchange_name_str = str(exchange_name)
        
        # Remove from cache
        if exchange_name_str in self._loaded_classes:
            del self._loaded_classes[exchange_name_str]
        
        # Reload the module
        registration = self._registrations.get(exchange_name_str)
        if registration:
            try:
                module = importlib.import_module(registration.module_path)
                importlib.reload(module)
                self.logger.info(f"Reloaded exchange: {exchange_name_str}")
            except Exception as e:
                self.logger.error(f"Failed to reload exchange {exchange_name_str}: {e}")


# Global registry instance
_exchange_registry = ExchangeRegistry()

def get_exchange_registry() -> ExchangeRegistry:
    """Get the global exchange registry instance."""
    return _exchange_registry