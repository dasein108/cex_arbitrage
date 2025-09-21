"""
REST Transport Strategy Factory

Exchange-agnostic factory for creating REST strategy sets using the
standardized BaseExchangeFactory infrastructure with enhanced auto-injection.

HFT COMPLIANT: Fast strategy creation with pre-validated combinations and auto-dependency injection.
"""

import logging
from typing import List, Dict, Optional, Any

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
        exchange_name: str,
        strategy_config: Dict[str, type],
        **kwargs
    ) -> None:
        """
        Register strategy configuration for an exchange.
        
        Implements BaseCompositeFactory.register() for REST strategies.
        
        Args:
            exchange_name: Exchange identifier with API type (e.g., 'MEXC_public', 'MEXC_private')
            strategy_config: Dictionary containing strategy class mappings
            **kwargs: Additional registration parameters
        """
        # Use base class validation and normalization
        exchange_key = cls._normalize_exchange_key(exchange_name)
        
        # Validate strategy configuration using base class method
        required_strategies = ['request', 'rate_limit', 'retry']
        cls._validate_strategy_config(strategy_config, required_strategies)
        
        # Register with base class registry
        cls._implementations[exchange_key] = strategy_config
    
    @classmethod
    def inject(cls, exchange_name: str, config: ExchangeConfig = None, **kwargs) -> RestStrategySet:
        """
        Create or retrieve REST strategy set for an exchange.
        
        Implements BaseCompositeFactory.inject() with auto-dependency injection.
        
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
        
        # Get strategy configuration and delegate to assembly method
        strategy_config = cls._implementations[exchange_key]
        return cls._assemble_components(exchange_name, strategy_config, config=config, **kwargs)
    
    @classmethod
    def _assemble_components(cls, exchange_name: str, strategy_config: Dict[str, type], **kwargs) -> RestStrategySet:
        """
        Assemble REST strategy components into RestStrategySet.
        
        Implements BaseCompositeFactory._assemble_components() for REST strategies.
        
        Args:
            exchange_name: Exchange identifier
            strategy_config: Component configuration
            **kwargs: Assembly parameters including config
            
        Returns:
            Assembled RestStrategySet
        """
        config = kwargs.get('config')
        if not config:
            raise ValueError("ExchangeConfig required for REST strategy assembly")
        
        # Auto-resolve dependencies
        resolved_kwargs = cls._resolve_dependencies(exchange_name, **{k: v for k, v in kwargs.items() if k != 'config'})
        
        # Create strategies with ExchangeConfig - use fallback for constructor differences
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
        is_private = 'PRIVATE' in exchange_name.upper()
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
        elif 'GATEIO' in exchange_name.upper():
            # Fallback: Import Gate.io exception handler directly if registration failed
            try:
                from exchanges.gateio.rest.strategies.exception_handler import GateioExceptionHandlerStrategy
                exception_handler_strategy = GateioExceptionHandlerStrategy()
            except ImportError:
                pass  # Ignore if import fails
        elif 'MEXC' in exchange_name.upper():
            # Fallback: Import MEXC exception handler directly if registration failed
            try:
                from exchanges.mexc.rest.strategies.exception_handler import MexcExceptionHandlerStrategy
                exception_handler_strategy = MexcExceptionHandlerStrategy()
            except ImportError:
                pass  # Ignore if import fails
        
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
        exchange_name = str(exchange_config.name).upper()
        exchange_key = f"{exchange_name}_{'PRIVATE' if is_private else 'PUBLIC'}"
        
        # Delegate to standardized inject() method
        return cls.inject(exchange_key, config=exchange_config)

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