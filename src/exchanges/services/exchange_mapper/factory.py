"""
Exchange Mappings Factory

Factory pattern for creating exchange-specific mapping services using
the standardized BaseExchangeFactory infrastructure with enhanced auto-injection.

HFT COMPLIANCE: Fast service instantiation, cached instances, factory coordination.
"""

from typing import Type, Union

from infrastructure.data_structures.common import ExchangeName, ExchangeEnum
from exchanges.services.exchange_mapper.base_exchange_mapper import BaseExchangeMapper
from exchanges.services.symbol_mapper.base_symbol_mapper import SymbolMapperInterface
from core.factories.base_exchange_factory import BaseExchangeFactory


class ExchangeMapperFactory(BaseExchangeFactory[BaseExchangeMapper]):
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
        exchange: ExchangeEnum, 
        implementation_class: Type[BaseExchangeMapper],
        **kwargs
    ) -> None:
        """
        Register a mapping implementation for an exchange.
        
        Enhanced with base class infrastructure and automatic symbol_mapper injection.
        
        Args:
            exchange: Exchange identifier (ExchangeEnum only)
            implementation_class: ExchangeMappingsInterface implementation
            
        Raises:
            ValueError: If implementation class invalid
        """
        
        # Use base class validation
        cls._validate_implementation_class(implementation_class, BaseExchangeMapper)
        
        # Register with base class registry using ExchangeEnum as key
        cls._implementations[exchange] = implementation_class
        
        # Enhanced auto-injection with symbol_mapper dependency
        try:
            from exchanges.services.symbol_mapper.factory import ExchangeSymbolMapperFactory
            
            # Get or create symbol mapper for this exchange
            symbol_mapper = ExchangeSymbolMapperFactory.inject(exchange)
            
            # Create and cache the instance immediately using base class helper
            instance = cls._create_instance_with_auto_injection(
                exchange, implementation_class, symbol_mapper=symbol_mapper
            )
            cache_key = exchange.value  # Use string for instance cache
            cls._instances[cache_key] = instance
            
            print(f"✅ Auto-registered {exchange.value} mappings with injected symbol_mapper")
            
        except Exception as e:
            # If symbol mapper not available, just register the class
            # Instance will be created later when symbol mapper is available
            print(f"⚠️  Registered {exchange.value} mappings class (symbol_mapper not yet available)")
            pass
    
    @classmethod
    def inject(cls, exchange: ExchangeEnum, **kwargs) -> BaseExchangeMapper:
        """
        Get or create exchange mappings instance with direct symbol_mapper injection.
        
        Handles symbol_mapper dependency directly to avoid circular dependency with BaseExchangeFactory.
        
        Args:
            exchange: Exchange identifier (ExchangeEnum only)
            
        Returns:
            BaseExchangeMapper implementation for the exchange
            
        Raises:
            ValueError: If exchange implementation not registered
        """
        cache_key = exchange.value  # Use string for instance cache
        
        # Return cached instance if available
        if cache_key in cls._instances:
            return cls._instances[cache_key]
        
        # Create new instance with direct symbol_mapper injection
        if exchange not in cls._implementations:
            available = cls.get_registered_exchanges()
            raise ValueError(
                f"No mapping implementation registered for '{exchange.value}'. "
                f"Available: {available}"
            )
        
        implementation_class = cls._implementations[exchange]
        
        # Inject symbol_mapper dependency directly
        from exchanges.services.symbol_mapper.factory import ExchangeSymbolMapperFactory
        symbol_mapper = ExchangeSymbolMapperFactory.inject(exchange)
        
        # Create instance with injected symbol_mapper
        instance = implementation_class(symbol_mapper)
        
        # Cache for singleton pattern
        cls._instances[cache_key] = instance
        
        return instance
    
    @classmethod
    def create(
        cls,
        exchange_name: Union[str, ExchangeName],
        symbol_mapper: SymbolMapperInterface = None,
        use_singleton: bool = True
    ) -> BaseExchangeMapper:
        """
        Create mapping service for an exchange.
        
        Legacy method that now delegates to inject() for consistency.
        Can optionally override symbol_mapper dependency.

        Args:
            exchange_name: Exchange identifier (string or ExchangeName)
            symbol_mapper: Optional symbol mapper override (if None, uses auto-injection)
            use_singleton: Whether to reuse existing instance

        Returns:
            BaseExchangeMapper implementation for the exchange

        Raises:
            ValueError: If exchange implementation not registered
        """
        # Convert to ExchangeEnum
        from core.utils.exchange_utils import exchange_name_to_enum
        exchange_enum = exchange_name_to_enum(exchange_name)
        
        if symbol_mapper is None:
            # Use standardized inject() method with auto-injection
            return cls.inject(exchange_enum)
        
        # Handle explicit symbol_mapper override
        cache_key = exchange_enum.value  # Use string for instance cache

        if exchange_enum not in cls._implementations:
            available = cls.get_registered_exchanges()
            raise ValueError(
                f"No mapping implementation registered for '{exchange_enum.value}'. "
                f"Available: {available}"
            )

        # Return cached instance if singleton requested and no override
        if use_singleton and cache_key in cls._instances:
            return cls._instances[cache_key]

        # Create new instance with explicit symbol_mapper
        implementation_class = cls._implementations[exchange_enum]
        instance = implementation_class(symbol_mapper)

        # Cache if singleton
        if use_singleton:
            cls._instances[cache_key] = instance

        return instance

    # Note: get_registered_exchanges(), clear_cache(), is_registered(), and reset_factory()
    # are inherited from BaseExchangeFactory and work with the base class registries