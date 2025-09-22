"""
REST Transport Strategy Factory

Exchange-agnostic factory for creating REST strategy sets using the
standardized BaseExchangeFactory infrastructure with enhanced auto-injection.

HFT COMPLIANT: Fast strategy creation with pre-validated combinations and auto-dependency injection.
"""

import logging
from typing import List, Dict, Optional, Any, Union, TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    from structs.common import ExchangeEnum
else:
    from structs.common import ExchangeEnum
from ....config.structs import ExchangeConfig, ExchangeName
from .strategy_set import RestStrategySet
from core.factories.base_composite_factory import BaseCompositeFactory


class RestStrategyFactory(BaseCompositeFactory[RestStrategySet]):
    """
    Factory for creating REST strategy sets with exchange-specific configurations.
    
    Inherits from BaseCompositeFactory to provide standardized factory patterns:
    - Component configuration management (stores strategy configurations)
    - Enhanced auto-injection with symbol_mapper and exchange_mappings
    - Standardized inject() method for consistent API
    - Factory-to-factory coordination for seamless dependency management
    
    Strategy sets are registered by exchange and API type (public/private).
    """
    
    @classmethod
    def register(
        cls,
        exchange: ExchangeEnum,
        is_private: bool,
        strategy_config: Dict[str, type],
        **kwargs
    ) -> None:
        """
        Register strategy configuration for an exchange with API type.
        
        Args:
            exchange: Exchange enum (clean, no suffixes)
            is_private: True for private API, False for public API
            strategy_config: Dictionary containing strategy class mappings
            **kwargs: Additional registration parameters
            
        Raises:
            ValueError: If strategy config invalid
        """
        # Use tuple key for clean separation
        key = (exchange, is_private)
        
        # Validate strategy configuration using base class method
        required_strategies = ['request', 'rate_limit', 'retry']
        cls._validate_strategy_config(strategy_config, required_strategies)
        
        # Register with tuple key
        cls._implementations[key] = strategy_config
    
    @classmethod
    def inject(cls, exchange: ExchangeEnum, is_private: bool, config: ExchangeConfig = None, **kwargs) -> RestStrategySet:
        """
        Create or retrieve REST strategy set for an exchange.
        
        Args:
            exchange: Exchange enum (clean, no suffixes)
            is_private: True for private API, False for public API
            config: ExchangeConfig required for strategy creation
            **kwargs: Additional creation parameters
            
        Returns:
            RestStrategySet with configured strategies and auto-injected dependencies
            
        Raises:
            ValueError: If exchange not registered or config not provided
        """
        if config is None:
            raise ValueError("ExchangeConfig required for REST strategy creation")
        
        # Use tuple key for lookup
        key = (exchange, is_private)
        
        # Check if registered
        if key not in cls._implementations:
            available = list(cls._implementations.keys())
            raise ValueError(
                f"No strategies registered for {exchange.value} (private={is_private}). Available: {available}"
            )
        
        # Get strategy configuration and delegate to assembly method
        strategy_config = cls._implementations[key]
        return cls._assemble_components(exchange, strategy_config, is_private=is_private, config=config, **kwargs)
    
    @classmethod
    def _assemble_components(cls, exchange: ExchangeEnum, strategy_config: Dict[str, type], **kwargs) -> RestStrategySet:
        """
        Assemble REST strategy components into RestStrategySet.
        
        Implements BaseCompositeFactory._assemble_components() for REST strategies.
        
        Args:
            exchange: Exchange identifier (ExchangeEnum only)
            strategy_config: Component configuration
            **kwargs: Assembly parameters including is_private, config, etc.
            
        Returns:
            Assembled RestStrategySet
        """
        config = kwargs.get('config')
        if not config:
            raise ValueError("ExchangeConfig required for REST strategy assembly")
        
        is_private = kwargs.get('is_private', False)
        
        # Auto-resolve dependencies
        resolved_kwargs = cls._resolve_dependencies(exchange, **{k: v for k, v in kwargs.items() if k != 'config'})
        
        # Create strategies with ExchangeConfig - use fallback for constructor differences
        exchange_name = exchange.value
        request_strategy = cls._create_component_with_fallback(
            strategy_config['request'], exchange_name, 
            {'exchange_config': config, **resolved_kwargs}, {'exchange_config': config}
        )
        rate_limit_strategy = cls._create_component_with_fallback(
            strategy_config['rate_limit'], exchange_name,
            {'exchange_config': config, **resolved_kwargs}, {'exchange_config': config}
        )
        retry_strategy = cls._create_component_with_fallback(
            strategy_config['retry'], exchange_name,
            {'exchange_config': config, **resolved_kwargs}, {'exchange_config': config}
        )
        
        # Auth strategy for private endpoints
        auth_strategy = None
        if is_private and strategy_config.get('auth'):
            auth_strategy = cls._create_component_with_fallback(
                strategy_config['auth'], exchange_name,
                {'exchange_config': config, **resolved_kwargs}, {'exchange_config': config}
            )
        
        # Exception handler with fallback constructor patterns
        exception_handler_strategy = None
        if strategy_config.get('exception_handler'):
            exception_handler_strategy = cls._create_component_with_fallback(
                strategy_config['exception_handler'],
                exchange_name,
                {'config': config, **resolved_kwargs},  # Primary: with all dependencies
                {'config': config},  # Fallback: just config
            )

        return RestStrategySet(
            request_strategy=request_strategy,
            rate_limit_strategy=rate_limit_strategy,
            retry_strategy=retry_strategy,
            auth_strategy=auth_strategy,
            exception_handler_strategy=exception_handler_strategy
        )
    
    @classmethod
    def register_strategies(
        cls,
        exchange: ExchangeEnum,
        is_private: bool,
        request_strategy_cls: type,
        rate_limit_strategy_cls: type,
        retry_strategy_cls: type,
        auth_strategy_cls: Optional[type] = None,
        exception_handler_strategy_cls: Optional[type] = None
    ) -> None:
        """
        Register strategy implementations for an exchange.
        
        Legacy method that delegates to the standardized register() method.
        Used by exchange modules for backward compatibility.
        
        Args:
            exchange: Exchange identifier (ExchangeEnum only)
            is_private: True for private API, False for public
            request_strategy_cls: RequestStrategy implementation
            rate_limit_strategy_cls: RateLimitStrategy implementation
            retry_strategy_cls: RetryStrategy implementation
            auth_strategy_cls: AuthStrategy implementation (required for private)
            exception_handler_strategy_cls: ExceptionHandlerStrategy implementation (optional)
        """
        if is_private and auth_strategy_cls is None:
            raise ValueError("AuthStrategy required for private API")
        
        # Create strategy configuration
        strategy_config = {
            'request': request_strategy_cls,
            'rate_limit': rate_limit_strategy_cls,
            'retry': retry_strategy_cls,
            'auth': auth_strategy_cls,
            'exception_handler': exception_handler_strategy_cls
        }
        
        # Use standardized register method with tuple key
        cls.register(exchange, is_private, strategy_config)
    
    @classmethod
    def create_strategies(
        cls,
        exchange_config: ExchangeConfig,
        is_private: bool
    ) -> RestStrategySet:
        """
        Create strategy set from ExchangeConfig with enhanced auto-injection.
        
        Legacy method that delegates to the standardized inject() method.
        
        Args:
            exchange_config: ExchangeConfig with all necessary settings
            is_private: True for private API requiring authentication
            
        Returns:
            RestStrategySet with configured strategies and auto-injected dependencies
            
        Raises:
            ValueError: If no strategies registered for the exchange
        """
        # Convert exchange config name to ExchangeEnum
        from core.utils.exchange_utils import exchange_name_to_enum
        exchange_enum = exchange_name_to_enum(exchange_config.name)
        
        # Delegate to standardized inject() method
        return cls.inject(exchange_enum, is_private, config=exchange_config)

    @classmethod
    def list_available_strategies(cls) -> Dict[str, List[str]]:
        """
        List all registered strategy combinations.
        
        Uses base class registry for consistent state management.
        
        Returns:
            Dictionary mapping exchange names to available API types
        """
        result = {}
        for key in cls._implementations.keys():
            if isinstance(key, tuple) and len(key) == 2:
                exchange_enum, is_private = key
                exchange_name = exchange_enum.value
                api_type = 'private' if is_private else 'public'
                
                if exchange_name not in result:
                    result[exchange_name] = []
                result[exchange_name].append(api_type)
        return result