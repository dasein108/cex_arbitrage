"""
REST Transport Strategy Factory

Exchange-agnostic factory for creating REST strategy sets using the
standardized BaseExchangeFactory infrastructure with enhanced auto-injection.

HFT COMPLIANT: Fast strategy creation with pre-validated combinations and auto-dependency injection.
"""

from typing import List, Dict, Optional, Any

# HFT Logger Integration
from infrastructure.logging import get_logger, get_strategy_logger, LoggingTimer

from exchanges.structs import ExchangeEnum
from config.structs import ExchangeConfig
from .strategy_set import RestStrategySet
from infrastructure.factories.base_composite_factory import BaseCompositeFactory


class RestStrategyFactory(BaseCompositeFactory[RestStrategySet]):
    """
    Factory for creating REST strategy sets with exchange-specific configurations.
    
    Inherits from BaseCompositeFactory to provide standardized factory patterns:
    - Component configuration management (stores strategy configurations)
    - Enhanced auto-injection with symbol_mapper and exchange_mappings
    - Standardized inject() method for consistent API
    - Factory-to-factory coordination for seamless dependency management
    - HFT logger injection with hierarchical tagging
    
    Strategy sets are registered by exchange and API type (public/private).
    """
    
    # Factory logger
    _factory_logger = get_logger('rest.strategy.factory')
    
    @classmethod
    def _create_component_with_logger(cls, component_class: type, exchange_name: str, 
                                     logger, config, resolved_kwargs: Dict[str, Any]) -> Any:
        """
        Create strategy component with logger injection using fallback patterns.
        
        Args:
            component_class: Strategy class to instantiate
            exchange_name: Exchange name for logging
            logger: HFT logger to inject
            config: ExchangeConfig
            resolved_kwargs: Resolved dependencies
            
        Returns:
            Instantiated strategy component with logger
        """
        try:
            # Try with logger injection first
            return component_class(
                exchange_config=config,
                logger=logger,
                **resolved_kwargs
            )
        except TypeError:
            try:
                # Fallback: try without resolved kwargs
                return component_class(
                    exchange_config=config,
                    logger=logger
                )
            except TypeError:
                # Fallback: try original pattern without logger (legacy compatibility)
                cls._factory_logger.warning("Strategy class does not support logger injection",
                                          component_class=component_class.__name__,
                                          exchange=exchange_name)
                return cls._create_component_with_fallback(
                    component_class, exchange_name,
                    {'exchange_config': config, **resolved_kwargs},
                    {'exchange_config': config}
                )
    
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
        
        # Validate strategy configuration using composite class method
        required_strategies = ['request', 'rate_limit', 'retry']
        cls._validate_strategy_config(strategy_config, required_strategies)
        
        # Register with tuple key
        cls._implementations[exchange] = strategy_config
        
        # Log registration with metrics
        api_type = 'private' if is_private else 'public'
        cls._factory_logger.info("Registered REST strategy configuration",
                                exchange=exchange.value,
                                api_type=api_type,
                                strategy_count=len(strategy_config))
        
        cls._factory_logger.metric("rest_strategies_registered", 1,
                                  tags={"exchange": exchange.value, "api_type": api_type})
    
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
        Assemble REST strategy components into RestStrategySet with HFT logger injection.
        
        Implements BaseCompositeFactory._assemble_components() for REST strategies.
        
        Args:
            exchange: Exchange identifier (ExchangeEnum only)
            strategy_config: Component configuration
            **kwargs: Assembly parameters including is_private, config, etc.
            
        Returns:
            Assembled RestStrategySet with injected loggers
        """
        config = kwargs.get('config')
        if not config:
            raise ValueError("ExchangeConfig required for REST strategy assembly")
        
        is_private = kwargs.get('is_private', False)
        api_type = 'private' if is_private else 'public'
        base_tags = [exchange.value, api_type, 'rest']
        
        cls._factory_logger.info("Assembling REST strategy set",
                               exchange=exchange.value,
                               api_type=api_type)
        
        try:
            with LoggingTimer(cls._factory_logger, "rest_strategy_assembly") as timer:
                # Auto-resolve dependencies
                resolved_kwargs = cls._resolve_dependencies(exchange, **{k: v for k, v in kwargs.items() if k != 'config'})
                
                # Create strategies with injected loggers
                exchange_name = exchange.value
                
                # Request strategy with logger injection
                request_logger = get_strategy_logger('rest.request', base_tags + ['request'])
                request_strategy = cls._create_component_with_logger(
                    strategy_config['request'], 
                    exchange_name,
                    logger=request_logger,
                    config=config,
                    resolved_kwargs=resolved_kwargs
                )
                
                # Rate limit strategy with logger injection
                rate_limit_logger = get_strategy_logger('rest.rate_limit', base_tags + ['rate_limit'])
                rate_limit_strategy = cls._create_component_with_logger(
                    strategy_config['rate_limit'],
                    exchange_name,
                    logger=rate_limit_logger,
                    config=config,
                    resolved_kwargs=resolved_kwargs
                )
                
                # Retry strategy with logger injection
                retry_logger = get_strategy_logger('rest.retry', base_tags + ['retry'])
                retry_strategy = cls._create_component_with_logger(
                    strategy_config['retry'],
                    exchange_name,
                    logger=retry_logger,
                    config=config,
                    resolved_kwargs=resolved_kwargs
                )
                
                # Auth strategy for private endpoints
                auth_strategy = None
                if is_private and strategy_config.get('auth'):
                    auth_logger = get_strategy_logger('rest.auth', base_tags + ['auth'])
                    auth_strategy = cls._create_component_with_logger(
                        strategy_config['auth'],
                        exchange_name,
                        logger=auth_logger,
                        config=config,
                        resolved_kwargs=resolved_kwargs
                    )
                
                # Exception handler with fallback constructor patterns
                exception_handler_strategy = None
                if strategy_config.get('exception_handler'):
                    exception_logger = get_strategy_logger('rest.exception_handler', base_tags + ['exception_handler'])
                    exception_handler_strategy = cls._create_component_with_logger(
                        strategy_config['exception_handler'],
                        exchange_name,
                        logger=exception_logger,
                        config=config,
                        resolved_kwargs=resolved_kwargs
                    )
                
                # Create strategy set with injected logger
                strategy_set_logger = get_strategy_logger('rest.strategy_set', base_tags)
                
                strategy_set = RestStrategySet(
                    request_strategy=request_strategy,
                    rate_limit_strategy=rate_limit_strategy,
                    retry_strategy=retry_strategy,
                    auth_strategy=auth_strategy,
                    exception_handler_strategy=exception_handler_strategy,
                    logger=strategy_set_logger
                )
            
            # Track assembly metrics
            cls._factory_logger.info("REST strategy set assembled successfully",
                                   exchange=exchange.value,
                                   api_type=api_type,
                                   assembly_time_ms=timer.elapsed_ms)
            
            cls._factory_logger.metric("rest_strategy_sets_assembled", 1,
                                     tags={"exchange": exchange.value, "api_type": api_type})
            
            cls._factory_logger.metric("rest_assembly_time_ms", timer.elapsed_ms,
                                     tags={"exchange": exchange.value, "api_type": api_type})
            
            return strategy_set
            
        except Exception as e:
            cls._factory_logger.error("Failed to assemble REST strategy set",
                                    exchange=exchange.value,
                                    api_type=api_type,
                                    error_type=type(e).__name__,
                                    error_message=str(e))
            
            cls._factory_logger.metric("rest_assembly_failures", 1,
                                     tags={"exchange": exchange.value, "api_type": api_type})
            
            raise
    
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
        from infrastructure.utils.exchange_utils import exchange_name_to_enum
        exchange_enum = exchange_name_to_enum(exchange_config.name)
        
        # Delegate to standardized inject() method
        return cls.inject(exchange_enum, is_private, config=exchange_config)

    @classmethod
    def list_available_strategies(cls) -> Dict[str, List[str]]:
        """
        List all registered strategy combinations.
        
        Uses composite class registry for consistent state management.
        
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