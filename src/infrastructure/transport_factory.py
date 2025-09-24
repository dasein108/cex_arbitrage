"""
Unified Transport Factory

Simplified factory for creating both REST and WebSocket exchange clients.
Replaces 4 separate factories (994 lines) with single unified factory (~100 lines).

Supports:
- Public/Private REST clients
- Public/Private WebSocket clients  
- Direct instantiation without complex inheritance
- Singleton caching for performance
- Logger injection

HFT COMPLIANT: Minimal overhead transport client creation.
"""

from typing import Type, Optional, Union, Dict, Any, Callable
from msgspec import Struct
from exchanges.structs import ExchangeEnum
from config.structs import ExchangeConfig
from infrastructure.logging import get_logger, get_exchange_logger

logger = get_logger('transport.factory')


class PublicWebsocketHandlers(Struct):
    """Handler collection for public WebSocket clients."""
    orderbook_diff_handler: Optional[Callable] = None
    trades_handler: Optional[Callable] = None
    book_ticker_handler: Optional[Callable] = None
    state_change_handler: Optional[Callable] = None

    def has_any_handler(self) -> bool:
        """Check if any handler is configured."""
        return any([
            self.orderbook_diff_handler,
            self.trades_handler,
            self.book_ticker_handler,
            self.state_change_handler
        ])

    def to_kwargs(self) -> Dict[str, Any]:
        """Convert to kwargs dict for WebSocket client construction."""
        kwargs = {}
        if self.orderbook_diff_handler:
            kwargs['orderbook_diff_handler'] = self.orderbook_diff_handler
        if self.trades_handler:
            kwargs['trades_handler'] = self.trades_handler
        if self.book_ticker_handler:
            kwargs['book_ticker_handler'] = self.book_ticker_handler
        if self.state_change_handler:
            kwargs['state_change_handler'] = self.state_change_handler
        return kwargs


class PrivateWebsocketHandlers(Struct):
    """Handler collection for private WebSocket clients."""
    order_handler: Optional[Callable] = None
    balance_handler: Optional[Callable] = None
    trade_handler: Optional[Callable] = None  # Note: private uses 'trade_handler' not 'trades_handler'
    state_change_handler: Optional[Callable] = None

    def has_any_handler(self) -> bool:
        """Check if any handler is configured."""
        return any([
            self.order_handler,
            self.balance_handler,
            self.trade_handler,
            self.state_change_handler
        ])

    def to_kwargs(self) -> Dict[str, Any]:
        """Convert to kwargs dict for WebSocket client construction."""
        kwargs = {}
        if self.order_handler:
            kwargs['order_handler'] = self.order_handler
        if self.balance_handler:
            kwargs['balance_handler'] = self.balance_handler
        if self.trade_handler:
            kwargs['trade_handler'] = self.trade_handler
        if self.state_change_handler:
            kwargs['state_change_handler'] = self.state_change_handler
        return kwargs

# Transport type registries
_rest_public_registry: Dict[ExchangeEnum, Type] = {}
_rest_private_registry: Dict[ExchangeEnum, Type] = {}
_ws_public_registry: Dict[ExchangeEnum, Type] = {}
_ws_private_registry: Dict[ExchangeEnum, Type] = {}

# Singleton caches
_rest_public_cache: Dict[ExchangeEnum, Any] = {}
_rest_private_cache: Dict[ExchangeEnum, Any] = {}
_ws_public_cache: Dict[ExchangeEnum, Any] = {}  # Changed to str for handler-based cache keys
_ws_private_cache: Dict[ExchangeEnum, Any] = {}  # Changed to str for handler-based cache keys


def register_rest_public(exchange: ExchangeEnum, implementation_class: Type) -> None:
    """Register public REST implementation for exchange."""
    _rest_public_registry[exchange] = implementation_class
    logger.debug(f"Registered public REST: {exchange.value} -> {implementation_class.__name__}")


def register_rest_private(exchange: ExchangeEnum, implementation_class: Type) -> None:
    """Register private REST implementation for exchange."""
    _rest_private_registry[exchange] = implementation_class
    logger.debug(f"Registered private REST: {exchange.value} -> {implementation_class.__name__}")


def register_ws_public(exchange: ExchangeEnum, implementation_class: Type) -> None:
    """Register public WebSocket implementation for exchange."""
    _ws_public_registry[exchange] = implementation_class
    logger.debug(f"Registered public WebSocket: {exchange.value} -> {implementation_class.__name__}")


def register_ws_private(exchange: ExchangeEnum, implementation_class: Type) -> None:
    """Register private WebSocket implementation for exchange."""
    _ws_private_registry[exchange] = implementation_class
    logger.debug(f"Registered private WebSocket: {exchange.value} -> {implementation_class.__name__}")


def create_rest_client(
    exchange: ExchangeEnum,
    config: Optional[ExchangeConfig] = None,
    is_private: bool = False,
    use_cache: bool = True,
    logger_override: Optional[Any] = None,
    mapper: Optional[Any] = None
) -> Any:
    """
    Create REST client for exchange.
    
    Args:
        exchange: Exchange to create client for
        config: Exchange configuration (required for private clients)
        is_private: Whether to create private or public client
        use_cache: Whether to use singleton caching
        logger_override: Custom logger to inject
        mapper: BaseExchangeMapper for data transformations
        
    Returns:
        REST client instance
        
    Raises:
        ValueError: If exchange not registered or config missing for private client
    """
    registry = _rest_private_registry if is_private else _rest_public_registry
    cache = _rest_private_cache if is_private else _rest_public_cache
    client_type = "private" if is_private else "public"
    
    # Check if implementation is registered
    if exchange not in registry:
        available = list(registry.keys())
        raise ValueError(f"No {client_type} REST implementation for {exchange.value}. Available: {available}")
    
    # Check cache first
    if use_cache and exchange in cache:
        logger.debug(f"Using cached {client_type} REST client for {exchange.value}")
        return cache[exchange]
    
    # Validate config for private clients
    if is_private and (not config or not config.credentials.has_private_api):
        raise ValueError(f"Private REST client requires valid credentials for {exchange.value}")
    
    # Create logger
    if not logger_override:
        logger_override = get_exchange_logger(exchange.value, f'rest_{client_type}')
    
    # Create mapper if not provided
    if not mapper:
        from exchanges.services.exchange_mapper.factory import ExchangeMapperFactory
        mapper = ExchangeMapperFactory.inject(exchange)
    
    # Create instance
    implementation_class = registry[exchange]
    logger.info(f"Creating {client_type} REST client: {exchange.value} -> {implementation_class.__name__}")
    
    # All REST implementations require config, mapper, and logger
    if not config:
        raise ValueError(f"ExchangeConfig required for {exchange.value} REST client")
    
    instance = implementation_class(config=config, mapper=mapper, logger=logger_override)
    
    # Cache instance
    if use_cache:
        cache[exchange] = instance
    
    return instance


def create_websocket_client(
    exchange: ExchangeEnum,
    config: Optional[ExchangeConfig] = None,
    is_private: bool = False,
    use_cache: bool = True,
    logger_override: Optional[Any] = None,
    handlers: Optional[Union[PublicWebsocketHandlers, PrivateWebsocketHandlers]] = None,
    **kwargs
) -> Any:
    """
    Create WebSocket client for exchange.
    
    Args:
        exchange: Exchange to create client for
        config: Exchange configuration (required for private clients)
        is_private: Whether to create private or public client
        use_cache: Whether to use singleton caching
        logger_override: Custom logger to inject
        handlers: WebSocket handlers (PublicWebsocketHandlers for public, PrivateWebsocketHandlers for private)
        **kwargs: Additional arguments for WebSocket client
        
    Returns:
        WebSocket client instance
        
    Raises:
        ValueError: If exchange not registered, config missing for private client, or handler type mismatch
    """
    registry = _ws_private_registry if is_private else _ws_public_registry
    cache = _ws_private_cache if is_private else _ws_public_cache
    client_type = "private" if is_private else "public"
    
    # Check if implementation is registered
    if exchange not in registry:
        available = list(registry.keys())
        raise ValueError(f"No {client_type} WebSocket implementation for {exchange.value}. Available: {available}")
    
    # Validate handler type matches client type
    if handlers:
        if is_private and not isinstance(handlers, PrivateWebsocketHandlers):
            raise ValueError(f"Private WebSocket client requires PrivateWebsocketHandlers, got {type(handlers).__name__}")
        elif not is_private and not isinstance(handlers, PublicWebsocketHandlers):
            raise ValueError(f"Public WebSocket client requires PublicWebsocketHandlers, got {type(handlers).__name__}")
    
    # Create cache key including handler configuration


    if use_cache and exchange in cache:
        logger.debug(f"Using cached {client_type} WebSocket client for {exchange.value}")
        return cache[exchange]
    
    # Validate config for private clients
    if is_private and (not config or not config.credentials.has_private_api):
        raise ValueError(f"Private WebSocket client requires valid credentials for {exchange.value}")
    
    # Create logger
    if not logger_override:
        logger_override = get_exchange_logger(exchange.value, f'ws_{client_type}')
    
    # Create instance with appropriate parameters
    implementation_class = registry[exchange]
    logger.info(f"Creating {client_type} WebSocket client: {exchange.value} -> {implementation_class.__name__}")
    
    # Build kwargs from handlers struct
    client_kwargs = {}
    if handlers:
        client_kwargs.update(handlers.to_kwargs())
        logger.debug(f"Applied {len(client_kwargs)} handlers for {client_type} WebSocket client")
    
    # Add any additional kwargs
    client_kwargs.update(kwargs)
    
    # Create instance with proper parameters
    if is_private:
        # Private WebSocket requires config and logger
        instance = implementation_class(config=config, logger=logger_override, **client_kwargs)
    else:
        # Public WebSocket also requires config and logger
        if not config:
            # Create minimal config for public WebSocket with required URLs
            raise KeyError(f"ExchangeConfig with websocket_url required for {exchange.value}")

        instance = implementation_class(config=config, logger=logger_override, **client_kwargs)
    
    # Cache instance
    if use_cache:
        cache[exchange] = instance
    
    return instance


def list_registered_transports() -> Dict[str, Dict[str, list]]:
    """
    List all registered transport implementations.
    
    Returns:
        Dictionary with transport types and their registered exchanges
    """
    return {
        "rest_public": [ex.value for ex in _rest_public_registry.keys()],
        "rest_private": [ex.value for ex in _rest_private_registry.keys()],
        "ws_public": [ex.value for ex in _ws_public_registry.keys()],
        "ws_private": [ex.value for ex in _ws_private_registry.keys()],
    }


def clear_caches() -> None:
    """Clear all singleton caches."""
    _rest_public_cache.clear()
    _rest_private_cache.clear()
    _ws_public_cache.clear()
    _ws_private_cache.clear()
    logger.info("Cleared all transport client caches")