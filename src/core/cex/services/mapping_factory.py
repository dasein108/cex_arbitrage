"""
Exchange Mappings Factory

Factory pattern for creating exchange-specific mapping services.
Provides centralized service creation with proper dependency injection.

HFT COMPLIANCE: Fast service instantiation, cached instances.
"""

from typing import Dict, Type, TYPE_CHECKING
from core.cex.services.exchange_mappings import ExchangeMappingsInterface
from core.cex.services.symbol_mapper.base_symbol_mapper import SymbolMapperInterface


class ExchangeMappingsFactory:
    """
    Factory for creating exchange-specific mapping services.
    
    Manages registration and creation of mapping implementations for different
    exchanges. Enables dependency injection and service lifecycle management.
    """
    
    _implementations: Dict[str, Type[ExchangeMappingsInterface]] = {}
    _instances: Dict[str, ExchangeMappingsInterface] = {}
    
    @classmethod
    def register_implementation(
        cls, 
        exchange_name: str, 
        implementation_class: Type[ExchangeMappingsInterface]
    ) -> None:
        """
        Register a mapping implementation for an exchange.
        
        Args:
            exchange_name: Exchange identifier (e.g., 'MEXC', 'GATEIO')
            implementation_class: ExchangeMappingsInterface implementation
        """
        cls._implementations[exchange_name.upper()] = implementation_class
    
    @classmethod
    def create_mappings(
        cls, 
        exchange_name: str, 
        symbol_mapper: SymbolMapperInterface,
        use_singleton: bool = True
    ) -> ExchangeMappingsInterface:
        """
        Create mapping service for an exchange.
        
        Args:
            exchange_name: Exchange identifier
            symbol_mapper: Symbol mapper for the exchange
            use_singleton: Whether to reuse existing instance
            
        Returns:
            ExchangeMappingsInterface implementation for the exchange
            
        Raises:
            ValueError: If exchange implementation not registered
        """
        exchange_key = exchange_name.upper()
        
        if exchange_key not in cls._implementations:
            available = list(cls._implementations.keys())
            raise ValueError(
                f"No mapping implementation registered for '{exchange_name}'. "
                f"Available: {available}"
            )
        
        # Return cached instance if singleton requested
        if use_singleton and exchange_key in cls._instances:
            return cls._instances[exchange_key]
        
        # Create new instance
        implementation_class = cls._implementations[exchange_key]
        instance = implementation_class(symbol_mapper)
        
        # Cache if singleton
        if use_singleton:
            cls._instances[exchange_key] = instance
        
        return instance
    
    @classmethod
    def get_registered_exchanges(cls) -> list[str]:
        """Get list of exchanges with registered implementations."""
        return list(cls._implementations.keys())
    
    @classmethod
    def clear_cache(cls) -> None:
        """Clear cached singleton instances."""
        cls._instances.clear()
    
    @classmethod
    def is_registered(cls, exchange_name: str) -> bool:
        """Check if exchange has registered implementation."""
        return exchange_name.upper() in cls._implementations