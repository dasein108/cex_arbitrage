"""
Unified Exchange Factory - Single Entry Point for All Exchange Components

This factory provides a single, clear interface for creating all exchange-related
components with explicit component type selection. Eliminates confusion between
multiple factory patterns and provides clear decision path.

HFT COMPLIANT: Minimal overhead component creation with unified caching and logging.
"""

from typing import Optional, Union, Dict, Any, Callable, Literal, Tuple, List
from exchanges.structs.enums import ExchangeEnum
from config.structs import ExchangeConfig
from infrastructure.logging import get_logger, get_exchange_logger, HFTLoggerInterface
from infrastructure.networking.websocket.handlers import PublicWebsocketHandlers, PrivateWebsocketHandlers

# Component type definitions
ComponentType = Literal['rest', 'websocket', 'composite']
logger = get_logger('exchange.unified_factory')

# Unified cache for all components
_unified_cache: Dict[str, Any] = {}

def create_exchange_component(
    exchange: ExchangeEnum,
    config: ExchangeConfig,
    component_type: ComponentType,
    is_private: bool = False,
    handlers: Optional[Union[PublicWebsocketHandlers, PrivateWebsocketHandlers]] = None,
    use_cache: bool = True,
    logger_override: Optional[HFTLoggerInterface] = None
) -> Any:
    """
    Unified factory for creating all exchange components.
    
    This is the MAIN FACTORY for all exchange component creation.
    Replaces transport_factory and composite_exchange_factory.
    
    Args:
        exchange: Exchange to create component for
        config: Exchange configuration
        component_type: Type of component to create
            - 'rest': REST client (public or private)
            - 'websocket': WebSocket client (public or private) 
            - 'composite': Full composite exchange (public or private)
        is_private: Whether to create private or public component
        handlers: Required for websocket component_type
        use_cache: Whether to use component caching
        logger_override: Custom logger injection
        
    Returns:
        Component instance based on component_type:
        - 'rest': REST client instance
        - 'websocket': WebSocket client instance
        - 'composite': Composite exchange instance

    Raises:
        ValueError: If exchange not supported, invalid config, or missing handlers
        
    Examples:
        # REST client for API calls
        rest_client = create_exchange_component(
            ExchangeEnum.MEXC, config, 'rest', is_private=False
        )
        
        # WebSocket client for streaming
        ws_client = create_exchange_component(
            ExchangeEnum.MEXC, config, 'websocket', 
            is_private=False, handlers=public_handlers
        )
        
        # Full composite exchange for trading
        exchange = create_exchange_component(
            ExchangeEnum.MEXC, config, 'composite', is_private=True
        )
        
        # Composite exchange with custom handlers
        public_handlers = create_public_handlers(
            orderbook_handler=my_orderbook_handler
        )
        exchange_with_handlers = create_exchange_component(
            ExchangeEnum.MEXC, config, 'composite', 
            is_private=False, handlers=public_handlers
        )

    """
    # Validate inputs
    _validate_component_request(exchange, config, component_type, is_private, handlers)
    
    # Build cache key
    private_suffix = "_private" if is_private else "_public"
    cache_key = f"{exchange.value}_{component_type}{private_suffix}"
    
    # Check cache first
    if use_cache and cache_key in _unified_cache:
        logger.debug(f"Using cached {component_type} component for {exchange.value}")
        return _unified_cache[cache_key]
    
    # Create logger if not provided
    if not logger_override:
        component_name = f'{component_type}_{private_suffix.strip("_")}'
        logger_override = get_exchange_logger(exchange.value, component_name)
    
    # Route to appropriate creation method
    if component_type == 'rest':
        instance = _create_rest_component(exchange, config, is_private, logger_override)
    elif component_type == 'websocket':
        instance = _create_websocket_component(exchange, config, is_private, handlers, logger_override)
    elif component_type == 'composite':
        instance = _create_composite_component(exchange, config, is_private, handlers, logger_override)
    else:
        raise ValueError(f"Unsupported component_type: {component_type}")
    
    # Cache and return instance
    if use_cache:
        _unified_cache[cache_key] = instance
        
    logger.info(f"Created {component_type} component: {exchange.value} ({'private' if is_private else 'public'})")
    return instance


def _validate_component_request(
    exchange: ExchangeEnum,
    config: ExchangeConfig, 
    component_type: ComponentType,
    is_private: bool,
    handlers: Optional[Union[PublicWebsocketHandlers, PrivateWebsocketHandlers]]
) -> None:
    """Validate component creation request."""
    # Check if exchange is supported
    if exchange not in get_supported_exchanges():
        raise ValueError(f"Exchange {exchange.value} not supported")
    
    # Check credentials for private components
    if is_private and not config.credentials.has_private_api:
        raise ValueError(f"Private component requires valid credentials for {exchange.value}")
    
    # Check handlers for websocket and composite components
    if component_type in ['websocket', 'composite'] and handlers is not None:
        # Validate handler type matches component privacy when handlers are provided
        if is_private and not isinstance(handlers, PrivateWebsocketHandlers):
            raise ValueError(f"Private {component_type} requires PrivateWebsocketHandlers, got {type(handlers).__name__}")
        elif not is_private and not isinstance(handlers, PublicWebsocketHandlers):
            raise ValueError(f"Public {component_type} requires PublicWebsocketHandlers, got {type(handlers).__name__}")
    
    # WebSocket components require handlers
    if component_type == 'websocket' and handlers is None:
        raise ValueError("WebSocket component requires handlers parameter")


def _create_rest_component(
    exchange: ExchangeEnum,
    config: ExchangeConfig,
    is_private: bool,
    logger: HFTLoggerInterface
) -> Any:
    """Create REST client component."""
    if exchange == ExchangeEnum.MEXC:
        if is_private:
            from exchanges.integrations.mexc.rest.mexc_rest_spot_private import MexcPrivateSpotRest
            return MexcPrivateSpotRest(config=config, logger=logger)
        else:
            from exchanges.integrations.mexc.rest.mexc_rest_spot_public import MexcPublicSpotRest
            return MexcPublicSpotRest(config=config, logger=logger)
            
    elif exchange == ExchangeEnum.GATEIO:
        if is_private:
            from exchanges.integrations.gateio.rest.gateio_rest_spot_private import GateioPrivateSpotRest
            return GateioPrivateSpotRest(config=config, logger=logger)
        else:
            from exchanges.integrations.gateio.rest.gateio_rest_spot_public import GateioPublicSpotRest
            return GateioPublicSpotRest(config=config, logger=logger)
            
    elif exchange == ExchangeEnum.GATEIO_FUTURES:
        if is_private:
            from exchanges.integrations.gateio.rest.gateio_rest_futures_private import GateioPrivateFuturesRest
            return GateioPrivateFuturesRest(config=config, logger=logger)
        else:
            from exchanges.integrations.gateio.rest.gateio_rest_futures_public import GateioPublicFuturesRest
            return GateioPublicFuturesRest(config=config, logger=logger)
    else:
        raise ValueError(f"REST component not implemented for {exchange.value}")


def _create_websocket_component(
    exchange: ExchangeEnum,
    config: ExchangeConfig,
    is_private: bool,
    handlers: Union[PublicWebsocketHandlers, PrivateWebsocketHandlers],
    logger: HFTLoggerInterface
) -> Any:
    """Create WebSocket client component."""
    if exchange == ExchangeEnum.MEXC:
        if is_private:
            from exchanges.integrations.mexc.ws import MexcPrivateSpotWebsocket
            return MexcPrivateSpotWebsocket(config=config, handlers=handlers, logger=logger)
        else:
            from exchanges.integrations.mexc.ws import MexcPublicSpotWebsocket
            return MexcPublicSpotWebsocket(config=config, handlers=handlers, logger=logger)

    elif exchange == ExchangeEnum.GATEIO:
        if is_private:
            from exchanges.integrations.gateio.ws import GateioPrivateSpotWebsocket
            return GateioPrivateSpotWebsocket(config=config, handlers=handlers, logger=logger)
        else:
            from exchanges.integrations.gateio.ws import GateioPublicSpotWebsocket
            return GateioPublicSpotWebsocket(config=config, handlers=handlers, logger=logger)
            
    elif exchange == ExchangeEnum.GATEIO_FUTURES:
        if is_private:
            from exchanges.integrations.gateio.ws import GateioPrivateFuturesWebsocket
            return GateioPrivateFuturesWebsocket(config=config, handlers=handlers, logger=logger)
        else:
            from exchanges.integrations.gateio.ws import GateioPublicFuturesWebsocket
            return GateioPublicFuturesWebsocket(config=config, handlers=handlers, logger=logger)
    else:
        raise ValueError(f"WebSocket component not implemented for {exchange.value}")


def _create_composite_component(
    exchange: ExchangeEnum,
    config: ExchangeConfig,
    is_private: bool,
    handlers: Optional[Union[PublicWebsocketHandlers, PrivateWebsocketHandlers]],
    logger: HFTLoggerInterface
) -> Any:
    """Create composite exchange component."""
    if exchange == ExchangeEnum.MEXC:
        if is_private:
            from exchanges.integrations.mexc.mexc_composite_private import MexcCompositePrivateSpotExchange
            return MexcCompositePrivateSpotExchange(config=config, logger=logger, handlers=handlers)
        else:
            from exchanges.integrations.mexc.mexc_composite_public import MexcCompositePublicSpotExchange
            return MexcCompositePublicSpotExchange(config=config, logger=logger, handlers=handlers)
            
    elif exchange == ExchangeEnum.GATEIO:
        if is_private:
            from exchanges.integrations.gateio.gateio_composite_private import GateioCompositePrivateSpotExchange
            return GateioCompositePrivateSpotExchange(config=config, logger=logger, handlers=handlers)
        else:
            from exchanges.integrations.gateio.gateio_composite_public import GateioCompositePublicSpotExchange
            return GateioCompositePublicSpotExchange(config=config, logger=logger, handlers=handlers)
            
    elif exchange == ExchangeEnum.GATEIO_FUTURES:
        if is_private:
            from exchanges.integrations.gateio.gateio_futures_composite_private import GateioFuturesCompositePrivateExchange
            return GateioFuturesCompositePrivateExchange(config=config, logger=logger, handlers=handlers)
        else:
            from exchanges.integrations.gateio.gateio_futures_composite_public import GateioFuturesCompositePublicSpotExchange
            return GateioFuturesCompositePublicSpotExchange(config=config, logger=logger, handlers=handlers)
    else:
        raise ValueError(f"Composite component not implemented for {exchange.value}")


# Convenience functions for backward compatibility and ease of use

def create_rest_client(
    exchange: ExchangeEnum,
    config: ExchangeConfig,
    is_private: bool = False,
    use_cache: bool = True,
    logger_override: Optional[HFTLoggerInterface] = None
) -> Any:
    """
    Convenience function for creating REST clients.
    
    Equivalent to: create_exchange_component(..., component_type='rest')
    """
    return create_exchange_component(
        exchange=exchange,
        config=config,
        component_type='rest',
        is_private=is_private,
        use_cache=use_cache,
        logger_override=logger_override
    )


def create_websocket_client(
    exchange: ExchangeEnum,
    config: ExchangeConfig,
    handlers: Union[PublicWebsocketHandlers, PrivateWebsocketHandlers],
    is_private: bool = False,
    use_cache: bool = True,
    logger_override: Optional[HFTLoggerInterface] = None
) -> Any:
    """
    Convenience function for creating WebSocket clients.
    
    Equivalent to: create_exchange_component(..., component_type='websocket')
    """
    return create_exchange_component(
        exchange=exchange,
        config=config,
        component_type='websocket',
        is_private=is_private,
        handlers=handlers,
        use_cache=use_cache,
        logger_override=logger_override
    )


def create_composite_exchange(
    exchange: ExchangeEnum,
    config: ExchangeConfig,
    is_private: bool = False,
    handlers: Optional[Union[PublicWebsocketHandlers, PrivateWebsocketHandlers]] = None,
    use_cache: bool = True,
    logger_override: Optional[HFTLoggerInterface] = None
) -> Any:
    """
    Convenience function for creating composite exchanges.
    
    Args:
        exchange: Exchange to create composite for
        config: Exchange configuration
        is_private: Whether to create private or public composite
        handlers: Optional WebSocket handlers for custom event handling
        use_cache: Whether to use component caching
        logger_override: Custom logger injection
    
    Returns:
        Composite exchange instance with optional custom handlers
    
    Equivalent to: create_exchange_component(..., component_type='composite')
    """
    return create_exchange_component(
        exchange=exchange,
        config=config,
        component_type='composite',
        is_private=is_private,
        handlers=handlers,
        use_cache=use_cache,
        logger_override=logger_override
    )


# Handler creation convenience functions

def create_public_handlers(
    orderbook_handler: Optional[Callable] = None,
    trades_handler: Optional[Callable] = None,
    book_ticker_handler: Optional[Callable] = None,
    ticker_handler: Optional[Callable] = None
) -> PublicWebsocketHandlers:
    """Create PublicWebsocketHandlers object."""
    return PublicWebsocketHandlers(
        orderbook_handler=orderbook_handler,
        trade_handler=trades_handler,
        book_ticker_handler=book_ticker_handler,
        ticker_handler=ticker_handler
    )


def create_private_handlers(
    order_handler: Optional[Callable] = None,
    balance_handler: Optional[Callable] = None,
    execution_handler: Optional[Callable] = None
) -> PrivateWebsocketHandlers:
    """Create PrivateWebsocketHandlers object."""
    return PrivateWebsocketHandlers(
        order_handler=order_handler,
        balance_handler=balance_handler,
        execution_handler=execution_handler
    )


# Utility functions

def get_supported_exchanges() -> List[ExchangeEnum]:
    """Get list of exchanges supported by this factory."""
    return [
        ExchangeEnum.MEXC,
        ExchangeEnum.GATEIO,
        ExchangeEnum.GATEIO_FUTURES
    ]


def is_exchange_supported(exchange: ExchangeEnum) -> bool:
    """Check if exchange is supported by this factory."""
    return exchange in get_supported_exchanges()


def get_supported_component_types() -> List[ComponentType]:
    """Get list of supported component types."""
    return ['rest', 'websocket', 'composite']


def clear_cache() -> None:
    """Clear all cached components."""
    global _unified_cache
    _unified_cache.clear()
    logger.info("Cleared unified exchange factory cache")


def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics."""
    return {
        "cached_components": len(_unified_cache),
        "cache_keys": list(_unified_cache.keys()),
        "memory_usage_estimate": len(str(_unified_cache))
    }


# Component type validation

def validate_component_request(
    exchange: ExchangeEnum,
    component_type: ComponentType,
    is_private: bool = False
) -> Dict[str, bool]:
    """
    Validate if a component request is supported.
    
    Returns:
        Dict with validation results:
        {
            "exchange_supported": bool,
            "component_supported": bool, 
            "requires_credentials": bool,
            "is_valid": bool
        }
    """
    exchange_supported = is_exchange_supported(exchange)
    component_supported = component_type in get_supported_component_types()
    requires_credentials = is_private
    
    return {
        "exchange_supported": exchange_supported,
        "component_supported": component_supported,
        "requires_credentials": requires_credentials,
        "is_valid": exchange_supported and component_supported
    }


# Decision matrix helper

def get_component_decision_matrix() -> Dict[str, Dict[str, str]]:
    """
    Get decision matrix for component selection.
    
    Returns:
        Dict mapping use cases to recommended component types
    """
    return {
        "custom_rest_integration": {
            "component_type": "rest",
            "description": "Direct REST API calls with custom logic",
            "use_case": "Custom data pipelines, specific API endpoints"
        },
        "custom_websocket_streaming": {
            "component_type": "websocket", 
            "description": "Custom WebSocket message handling",
            "use_case": "Custom message processing, specialized streaming"
        },
        "standard_trading": {
            "component_type": "composite",
            "description": "Full exchange interface for trading operations",
            "use_case": "Arbitrage trading, portfolio management"
        },
        "market_data_analysis": {
            "component_type": "composite",
            "description": "Full market data interface",
            "use_case": "Market analysis, price monitoring"
        },
        "custom_event_handling": {
            "component_type": "composite",
            "description": "Composite exchange with custom WebSocket handlers",
            "use_case": "Custom orderbook processing, specialized event handling"
        },
        "separated_domain_trading": {
            "component_type": "pair",
            "description": "Both public and private exchanges separately",
            "use_case": "HFT systems with separated market data and trading"
        }
    }