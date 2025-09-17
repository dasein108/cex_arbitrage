"""
REST Transport Strategy Factory

Exchange-agnostic factory for creating REST strategy sets using the
standardized BaseExchangeFactory infrastructure with enhanced auto-injection.

HFT COMPLIANT: Fast strategy creation with pre-validated combinations and auto-dependency injection.
"""

import logging
from typing import List, Dict, Optional, Any

from ....config.structs import ExchangeConfig, ExchangeName
from .request import RequestStrategy
from .rate_limit import RateLimitStrategy
from .retry import RetryStrategy
from .auth import AuthStrategy
from .exception_handler import ExceptionHandlerStrategy
from .strategy_set import RestStrategySet
from core.factories.base_exchange_factory import BaseExchangeFactory


class RestStrategyFactory(BaseExchangeFactory[RestStrategySet]):
    """
    Factory for creating REST strategy sets with exchange-specific configurations.
    
    Inherits from BaseExchangeFactory to provide standardized factory patterns:
    - Registry management via base class (_implementations stores strategy configurations)
    - Enhanced auto-injection with symbol_mapper and exchange_mappings
    - Standardized inject() method for consistent API
    - Factory-to-factory coordination for seamless dependency management
    
    Strategy sets are registered by exchange and API type (public/private).
    """
    
    @classmethod
    def register(
        cls,
        exchange_name: str,
        strategy_config: Dict[str, type],
        **kwargs
    ) -> None:
        """
        Register strategy configuration for an exchange.
        
        Implements BaseExchangeFactory.register() for REST strategies.
        
        Args:
            exchange_name: Exchange identifier with API type (e.g., 'MEXC_public', 'MEXC_private')
            strategy_config: Dictionary containing strategy class mappings
            **kwargs: Additional registration parameters
        """
        # Use base class validation and normalization
        exchange_key = cls._normalize_exchange_key(exchange_name)
        
        # Validate strategy configuration
        required_strategies = ['request', 'rate_limit', 'retry']
        for strategy_type in required_strategies:
            if strategy_type not in strategy_config:
                raise ValueError(f"Missing required strategy: {strategy_type}")
        
        # Register with base class registry (strategy_config is our "implementation")
        cls._implementations[exchange_key] = strategy_config
        
        # Note: We don't auto-create instances for strategy sets as they require ExchangeConfig
        # Instances will be created on-demand via inject()
    
    @classmethod
    def inject(cls, exchange_name: str, config: ExchangeConfig = None, **kwargs) -> RestStrategySet:
        """
        Create or retrieve REST strategy set for an exchange.
        
        Implements BaseExchangeFactory.inject() with auto-dependency injection.
        
        Args:
            exchange_name: Exchange identifier with API type (e.g., 'MEXC_public')
            config: ExchangeConfig required for strategy creation
            **kwargs: Additional creation parameters
            
        Returns:
            RestStrategySet with configured strategies and auto-injected dependencies
            
        Raises:
            ValueError: If exchange not registered or config not provided
        """
        if config is None:
            raise ValueError("ExchangeConfig required for REST strategy creation")
        
        # Use base class normalization
        exchange_key = cls._normalize_exchange_key(exchange_name)
        
        # Check if registered
        if exchange_key not in cls._implementations:
            available = cls.get_registered_exchanges()
            raise ValueError(
                f"No strategies registered for {exchange_name}. Available: {available}"
            )
        
        # For strategy sets, we don't use singleton pattern as they need fresh config
        # Get strategy configuration
        strategy_config = cls._implementations[exchange_key]
        
        # Auto-resolve dependencies
        resolved_kwargs = cls._resolve_dependencies(exchange_name, config=config, **kwargs)
        
        # Create strategies with ExchangeConfig and auto-injected dependencies
        request_strategy = strategy_config['request'](config, **resolved_kwargs)
        rate_limit_strategy = strategy_config['rate_limit'](config, **resolved_kwargs) 
        retry_strategy = strategy_config['retry'](config, **resolved_kwargs)
        
        # Auth strategy for private endpoints
        auth_strategy = None
        is_private = 'private' in exchange_name.lower()
        if is_private and strategy_config.get('auth'):
            auth_strategy = strategy_config['auth'](config, **resolved_kwargs)
        
        # Exception handler (optional)
        exception_handler_strategy = None
        if strategy_config.get('exception_handler'):
            try:
                exception_handler_strategy = strategy_config['exception_handler'](config, **resolved_kwargs)
            except TypeError:
                try:
                    exception_handler_strategy = strategy_config['exception_handler'](config)
                except TypeError:
                    exception_handler_strategy = strategy_config['exception_handler']()
        
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
        exchange: ExchangeName,
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
            exchange: Exchange name (e.g., 'mexc', 'gateio')
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
        
        # Use standardized register method
        exchange_key = f"{exchange}_{'private' if is_private else 'public'}"
        cls.register(exchange_key, strategy_config)
    
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
        exchange_name = str(exchange_config.name).lower()
        exchange_key = f"{exchange_name}_{'private' if is_private else 'public'}"
        
        # Delegate to standardized inject() method
        return cls.inject(exchange_key, config=exchange_config)

    # Note: _resolve_dependencies() is inherited from BaseExchangeFactory
    # It provides automatic symbol_mapper and exchange_mappings resolution

    @classmethod
    def list_available_strategies(cls) -> Dict[str, List[str]]:
        """
        List all registered strategy combinations.
        
        Uses base class registry for consistent state management.
        
        Returns:
            Dictionary mapping exchange names to available API types
        """
        result = {}
        for key in cls.get_registered_exchanges():
            if '_' in key:
                exchange, api_type = key.rsplit('_', 1)
                if exchange not in result:
                    result[exchange] = []
                result[exchange].append(api_type)
        return result