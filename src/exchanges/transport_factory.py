"""
Unified Transport Factory

Direct client creation with switch-based routing and handler objects.
Eliminates registry pattern and auto-registration complexity.

Supports:
- Public/Private REST clients
- Public/Private WebSocket clients with handler objects
- Direct instantiation without registries
- Simple caching for performance
- Logger injection
- Type-safe handler validation

WebSocket Usage:
    # Create handler objects
    handlers = create_public_handlers(trades_handler=my_trade_handler)
    
    # Create WebSocket client with handlers
    client = create_websocket_client(ExchangeEnum.MEXC, config, handlers)

HFT COMPLIANT: Minimal overhead transport client creation with type safety.
"""

from typing import Optional, Union, Dict, Any, Callable
from msgspec import Struct
from exchanges.structs import ExchangeEnum
from config.structs import ExchangeConfig
from infrastructure.logging import get_logger, get_exchange_logger
from infrastructure.networking.websocket.handlers import PublicWebsocketHandlers, PrivateWebsocketHandlers

logger = get_logger('transport.factory')

# Simple caches
_client_cache: Dict[str, Any] = {}


def create_rest_client(
    exchange: ExchangeEnum,
    config: ExchangeConfig,
    is_private: bool = False,
    use_cache: bool = True,
    logger_override: Optional[Any] = None
) -> Any:
    """
    Create REST client for exchange with direct instantiation.
    
    Args:
        exchange: Exchange to create client for
        config: Exchange configuration (required)
        is_private: Whether to create private or public client
        use_cache: Whether to use caching
        logger_override: Custom logger to inject
        
    Returns:
        REST client instance
        
    Raises:
        ValueError: If exchange not supported or invalid config
    """
    client_type = "private" if is_private else "public"
    cache_key = f"{exchange.value}_{client_type}_rest"
    
    # Check cache first
    if use_cache and cache_key in _client_cache:
        logger.debug(f"Using cached {client_type} REST client for {exchange.value}")
        return _client_cache[cache_key]
    
    # Validate config for private clients
    if is_private and not config.credentials.has_private_api:
        raise ValueError(f"Private REST client requires valid credentials for {exchange.value}")
    
    # Create logger
    if not logger_override:
        logger_override = get_exchange_logger(exchange.value, f'rest_{client_type}')
    
    # Direct instantiation based on exchange
    if exchange == ExchangeEnum.MEXC:
        if is_private:
            from exchanges.integrations.mexc.rest.mexc_rest_private import MexcPrivateSpotRest
            instance = MexcPrivateSpotRest(config=config, logger=logger_override)
        else:
            from exchanges.integrations.mexc.rest.mexc_rest_public import MexcPublicSpotRest
            instance = MexcPublicSpotRest(config=config, logger=logger_override)
            
    elif exchange == ExchangeEnum.GATEIO:
        if is_private:
            from exchanges.integrations.gateio.rest.gateio_rest_private import GateioPrivateSpotRest
            instance = GateioPrivateSpotRest(config=config, logger=logger_override)
        else:
            from exchanges.integrations.gateio.rest.gateio_rest_public import GateioPublicSpotRest
            instance = GateioPublicSpotRest(config=config, logger=logger_override)
            
    elif exchange == ExchangeEnum.GATEIO_FUTURES:
        if is_private:
            from exchanges.integrations.gateio.rest.gateio_futures_private import GateioPrivateFuturesRest
            instance = GateioPrivateFuturesRest(config=config, logger=logger_override)
        else:
            from exchanges.integrations.gateio.rest.gateio_futures_public import GateioPublicFuturesRest
            instance = GateioPublicFuturesRest(config=config, logger=logger_override)
            
    else:
        raise ValueError(f"Exchange {exchange.value} REST client not implemented")
    
    logger.info(f"Created {client_type} REST client: {exchange.value}")
    
    # Cache instance
    if use_cache:
        _client_cache[cache_key] = instance
    
    return instance


def create_websocket_client(
    exchange: ExchangeEnum,
    config: ExchangeConfig,
    handlers: Union[PublicWebsocketHandlers, PrivateWebsocketHandlers],
    is_private: bool = False,
    use_cache: bool = True,
    logger_override: Optional[Any] = None
) -> Any:
    """
    Create WebSocket client for exchange with direct instantiation.
    
    Args:
        exchange: Exchange to create client for
        config: Exchange configuration (required)
        handlers: PublicWebsocketHandlers or PrivateWebsocketHandlers object
        is_private: Whether to create private or public client
        use_cache: Whether to use caching
        logger_override: Custom logger to inject
        
    Returns:
        WebSocket client instance
        
    Raises:
        ValueError: If exchange not supported or invalid config
    """
    client_type = "private" if is_private else "public"
    cache_key = f"{exchange.value}_{client_type}_ws"
    
    # Check cache first
    if use_cache and cache_key in _client_cache:
        logger.debug(f"Using cached {client_type} WebSocket client for {exchange.value}")
        return _client_cache[cache_key]
    
    # Validate config for private clients
    if is_private and not config.credentials.has_private_api:
        raise ValueError(f"Private WebSocket client requires valid credentials for {exchange.value}")
    
    # Validate handler type matches client type
    if is_private and not isinstance(handlers, PrivateWebsocketHandlers):
        raise ValueError(f"Private WebSocket client requires PrivateWebsocketHandlers, got {type(handlers).__name__}")
    elif not is_private and not isinstance(handlers, PublicWebsocketHandlers):
        raise ValueError(f"Public WebSocket client requires PublicWebsocketHandlers, got {type(handlers).__name__}")
    
    # Create logger
    if not logger_override:
        logger_override = get_exchange_logger(exchange.value, f'ws_{client_type}')
    
    # Direct instantiation based on exchange
    if exchange == ExchangeEnum.MEXC:
        if is_private:
            from exchanges.integrations.mexc.ws import MexcPrivateSpotWebsocket
            instance = MexcPrivateSpotWebsocket(config=config, handlers=handlers, logger=logger_override)
        else:
            from exchanges.integrations.mexc.ws import MexcPublicSpotWebsocket
            instance = MexcPublicSpotWebsocket(config=config, handlers=handlers, logger=logger_override)
            
    elif exchange == ExchangeEnum.GATEIO:
        if is_private:
            from exchanges.integrations.gateio.ws import GateioPrivateSpotWebsocket
            instance = GateioPrivateSpotWebsocket(config=config, handlers=handlers, logger=logger_override)
        else:
            from exchanges.integrations.gateio.ws import GateioPublicSpotWebsocket
            instance = GateioPublicSpotWebsocket(config=config, handlers=handlers, logger=logger_override)
            
    elif exchange == ExchangeEnum.GATEIO_FUTURES:
        if is_private:
            from exchanges.integrations.gateio.ws import GateioPrivateFuturesWebsocket
            instance = GateioPrivateFuturesWebsocket(config=config, handlers=handlers, logger=logger_override)
        else:
            from exchanges.integrations.gateio.ws import GateioPublicFuturesWebsocket
            instance = GateioPublicFuturesWebsocket(config=config, handlers=handlers, logger=logger_override)
            
    else:
        raise ValueError(f"Exchange {exchange.value} WebSocket client not implemented")
    
    logger.info(f"Created {client_type} WebSocket client: {exchange.value}")
    
    # Cache instance
    if use_cache:
        _client_cache[cache_key] = instance
    
    return instance


def create_public_handlers(
    orderbook_diff_handler: Optional[Callable] = None,
    trades_handler: Optional[Callable] = None,
    book_ticker_handler: Optional[Callable] = None
) -> PublicWebsocketHandlers:
    """
    Convenience function to create PublicWebsocketHandlers.
    
    Args:
        orderbook_diff_handler: Handler for orderbook difference updates
        trades_handler: Handler for trade data
        book_ticker_handler: Handler for book ticker updates
        
    Returns:
        PublicWebsocketHandlers object
    """
    return PublicWebsocketHandlers(
        orderbook_handler=orderbook_diff_handler,
        trades_handler=trades_handler,
        book_ticker_handler=book_ticker_handler
    )


def create_private_handlers(
    order_handler: Optional[Callable] = None,
    balance_handler: Optional[Callable] = None,
    trade_handler: Optional[Callable] = None
) -> PrivateWebsocketHandlers:
    """
    Convenience function to create PrivateWebsocketHandlers.
    
    Args:
        order_handler: Handler for order updates
        balance_handler: Handler for balance changes  
        trade_handler: Handler for private trade executions
        
    Returns:
        PrivateWebsocketHandlers object
    """
    return PrivateWebsocketHandlers(
        order_handler=order_handler,
        balance_handler=balance_handler,
        execution_handler=trade_handler
    )


def clear_caches() -> None:
    """Clear all client caches."""
    _client_cache.clear()
    logger.info("Cleared all transport client caches")