"""
Exchange Mappings Factory

Factory pattern for creating exchange-specific mapping services using
the standardized BaseExchangeFactory infrastructure with enhanced auto-injection.

HFT COMPLIANCE: Fast service instantiation, cached instances, factory coordination.
"""

from typing import Dict, Type

from structs.common import ExchangeName
from core.cex.services.unified_mapper.exchange_mappings import ExchangeMappingsInterface
from core.cex.services.symbol_mapper.base_symbol_mapper import SymbolMapperInterface
from core.factories.base_exchange_factory import BaseExchangeFactory


class ExchangeMappingsFactory(BaseExchangeFactory[ExchangeMappingsInterface]):
    """
    Factory for creating exchange-specific mapping services.
    
    Inherits from BaseExchangeFactory to provide standardized factory patterns:
    - Registry management via base class (_implementations, _instances)
    - Enhanced auto-injection with symbol_mapper dependency resolution
    - Factory-to-factory coordination for seamless dependency management
    - Consistent error handling and validation patterns
    """
    
    @classmethod
    def register(
        cls, 
        exchange_name: str, 
        implementation_class: Type[ExchangeMappingsInterface],
        **kwargs
    ) -> None:
        """
        Register a mapping implementation for an exchange.
        Enhanced with base class infrastructure and automatic symbol_mapper injection.
        
        Args:
            exchange_name: Exchange identifier (e.g., 'MEXC', 'GATEIO')
            implementation_class: ExchangeMappingsInterface implementation
        """
        # Use base class validation
        cls._validate_implementation_class(implementation_class, ExchangeMappingsInterface)
        
        # Use base class normalization
        exchange_key = cls._normalize_exchange_key(exchange_name)
        
        # Register with base class registry
        cls._implementations[exchange_key] = implementation_class
        
        # Enhanced auto-injection with symbol_mapper dependency
        try:
            from core.cex.services.symbol_mapper.factory import ExchangeSymbolMapperFactory
            
            # Get or create symbol mapper for this exchange
            symbol_mapper = ExchangeSymbolMapperFactory.inject(exchange_key)
            
            # Create and cache the instance immediately using base class helper
            instance = cls._create_instance_with_auto_injection(
                exchange_name, implementation_class, symbol_mapper=symbol_mapper
            )
            cls._instances[exchange_key] = instance
            
            print(f"✅ Auto-registered {exchange_key} mappings with injected symbol_mapper")
            
        except Exception as e:
            # If symbol mapper not available, just register the class
            # Instance will be created later when symbol mapper is available
            print(f"⚠️  Registered {exchange_key} mappings class (symbol_mapper not yet available)")
            pass
    
    @classmethod
    def inject(cls, exchange_name: str, **kwargs) -> ExchangeMappingsInterface:
        """
        Get or create exchange mappings instance with auto-injection.
        
        Standardized factory method following BaseExchangeFactory patterns.
        
        Args:
            exchange_name: Exchange identifier
            
        Returns:
            ExchangeMappingsInterface implementation for the exchange
            
        Raises:
            ValueError: If exchange implementation not registered
        """
        # Use base class normalization
        exchange_key = cls._normalize_exchange_key(exchange_name)
        
        # Return cached instance if available
        if exchange_key in cls._instances:
            return cls._instances[exchange_key]
        
        # Create new instance with auto-injection
        if exchange_key not in cls._implementations:
            available = cls.get_registered_exchanges()
            raise ValueError(
                f"No mapping implementation registered for '{exchange_name}'. "
                f"Available: {available}"
            )
        
        implementation_class = cls._implementations[exchange_key]
        
        # Use base class auto-injection helper
        instance = cls._create_instance_with_auto_injection(exchange_name, implementation_class)
        
        # Cache for singleton pattern
        cls._instances[exchange_key] = instance
        
        return instance
    
    @classmethod
    def create(
        cls,
        exchange_name: ExchangeName,
        symbol_mapper: SymbolMapperInterface = None,
        use_singleton: bool = True
    ) -> ExchangeMappingsInterface:
        """
        Create mapping service for an exchange.
        
        Legacy method that now delegates to inject() for consistency.
        Can optionally override symbol_mapper dependency.

        Args:
            exchange_name: Exchange identifier
            symbol_mapper: Optional symbol mapper override (if None, uses auto-injection)
            use_singleton: Whether to reuse existing instance

        Returns:
            ExchangeMappingsInterface implementation for the exchange

        Raises:
            ValueError: If exchange implementation not registered
        """
        if symbol_mapper is None:
            # Use standardized inject() method with auto-injection
            return cls.inject(exchange_name)
        
        # Handle explicit symbol_mapper override
        exchange_key = cls._normalize_exchange_key(exchange_name)

        if exchange_key not in cls._implementations:
            available = cls.get_registered_exchanges()
            raise ValueError(
                f"No mapping implementation registered for '{exchange_name}'. "
                f"Available: {available}"
            )

        # Return cached instance if singleton requested and no override
        if use_singleton and exchange_key in cls._instances:
            return cls._instances[exchange_key]

        # Create new instance with explicit symbol_mapper
        implementation_class = cls._implementations[exchange_key]
        instance = implementation_class(symbol_mapper)

        # Cache if singleton
        if use_singleton:
            cls._instances[exchange_key] = instance

        return instance

    # Note: get_registered_exchanges(), clear_cache(), is_registered(), and reset_factory()
    # are inherited from BaseExchangeFactory and work with the base class registries