# Core configuration and enums
from typing import Union
from config.structs import ExchangeConfig
from exchanges.structs.enums import ExchangeEnum

# Composite interfaces
from exchanges.interfaces.composite import (
    CompositePublicSpotExchange,
    CompositePrivateSpotExchange,
    CompositePublicFuturesExchange,
    CompositePrivateFuturesExchange
)

# MEXC REST interfaces
from exchanges.integrations.mexc.rest import MexcPublicSpotRestInterface, MexcPrivateSpotRestInterface

# MEXC WebSocket interfaces
from exchanges.integrations.mexc.ws import MexcPublicSpotWebsocket, MexcPrivateSpotWebsocket

# MEXC services
from exchanges.integrations.mexc.services.symbol_mapper import MexcSymbolMapper

# Gate.io REST interfaces
from exchanges.integrations.gateio.rest import (
    GateioPublicSpotRestInterface,
    GateioPrivateSpotRestInterface,
    GateioPublicFuturesRestInterface,
    GateioPrivateFuturesRestInterface
)

# Gate.io WebSocket interfaces
from exchanges.integrations.gateio.ws import (
    GateioPublicSpotWebsocket,
    GateioPrivateSpotWebsocket,
    GateioPublicFuturesWebsocket,
    GateioPrivateFuturesWebsocket
)

# Gate.io services
from exchanges.integrations.gateio.services.futures_symbol_mapper import GateioFuturesSymbolMapper
from exchanges.integrations.gateio.services.spot_symbol_mapper import GateioSymbolMapper

EXCHANGE_REST_MAP = {
    (ExchangeEnum.MEXC, False): MexcPublicSpotRestInterface,
    (ExchangeEnum.MEXC, True): MexcPrivateSpotRestInterface,
    (ExchangeEnum.GATEIO, False): GateioPublicSpotRestInterface,
    (ExchangeEnum.GATEIO, True): GateioPrivateSpotRestInterface,
    (ExchangeEnum.GATEIO_FUTURES, False): GateioPublicFuturesRestInterface,
    (ExchangeEnum.GATEIO_FUTURES, True): GateioPrivateFuturesRestInterface,
}

EXCHANGE_WS_MAP = {
    (ExchangeEnum.MEXC, False): MexcPublicSpotWebsocket,
    (ExchangeEnum.MEXC, True): MexcPrivateSpotWebsocket,
    (ExchangeEnum.GATEIO, False): GateioPublicSpotWebsocket,
    (ExchangeEnum.GATEIO, True):  GateioPrivateSpotWebsocket,
    (ExchangeEnum.GATEIO_FUTURES, False): GateioPublicFuturesWebsocket,
    (ExchangeEnum.GATEIO_FUTURES, True): GateioPrivateFuturesWebsocket,
}

# (is_futures, is_private) -> Composite Class
COMPOSITE_AGNOSTIC_MAP = {
    (False, False): CompositePublicSpotExchange,
    (False, True): CompositePrivateSpotExchange,
    (True, False): CompositePublicFuturesExchange,
    (True, True): CompositePrivateFuturesExchange,
}

SYMBOL_MAPPER_MAP = {
    ExchangeEnum.MEXC: MexcSymbolMapper,
    ExchangeEnum.GATEIO: GateioSymbolMapper,
    ExchangeEnum.GATEIO_FUTURES: GateioFuturesSymbolMapper,
}

def get_rest_implementation(exchange_config: ExchangeConfig, is_private: bool) -> Union[
    MexcPublicSpotRestInterface, MexcPrivateSpotRestInterface,
    GateioPublicSpotRestInterface, GateioPrivateSpotRestInterface,
    GateioPublicFuturesRestInterface, GateioPrivateFuturesRestInterface
]:
    """
    Get REST client implementation for specified exchange and access type.
    
    Args:
        exchange_config: Exchange configuration containing credentials and settings
        is_private: Whether to return private (authenticated) or public REST client
        
    Returns:
        Configured REST client instance for the specified exchange
        
    Raises:
        ValueError: If no implementation exists for the exchange/access type combination
    """
    key = (exchange_config.exchange_enum, is_private)
    impl_class = EXCHANGE_REST_MAP.get(key, None)
    if not impl_class:
        raise ValueError(f"No REST implementation found for exchange {exchange_config.name} "
                         f"with is_private={is_private}")

    return impl_class(exchange_config)

def get_ws_implementation(exchange_config: ExchangeConfig, is_private: bool) -> Union[
    MexcPublicSpotWebsocket, MexcPrivateSpotWebsocket,
    GateioPublicSpotWebsocket, GateioPrivateSpotWebsocket,
    GateioPublicFuturesWebsocket, GateioPrivateFuturesWebsocket
]:
    """
    Get WebSocket client implementation for specified exchange and access type.
    
    Args:
        exchange_config: Exchange configuration containing credentials and settings
        is_private: Whether to return private (authenticated) or public WebSocket client
        
    Returns:
        Configured WebSocket client instance for the specified exchange
        
    Raises:
        ValueError: If no implementation exists for the exchange/access type combination
    """
    key = (exchange_config.exchange_enum, is_private)
    impl_class = EXCHANGE_WS_MAP.get(key, None)
    if not impl_class:
        raise ValueError(f"No WebSocket implementation found for exchange {exchange_config.name} "
                         f"with is_private={is_private}")
    return impl_class(exchange_config)


def get_composite_implementation(exchange_config: ExchangeConfig, is_private: bool) -> Union[
    CompositePublicSpotExchange, CompositePrivateSpotExchange,
    CompositePublicFuturesExchange, CompositePrivateFuturesExchange
]:
    """
    Get composite exchange implementation with injected REST and WebSocket clients.
    
    Args:
        exchange_config: Exchange configuration containing credentials and settings
        is_private: Whether to return private (authenticated) or public composite exchange
        
    Returns:
        Configured composite exchange instance with injected REST and WebSocket clients
        
    Raises:
        ValueError: If no composite implementation exists for the exchange/access type combination
    """
    ws_client = get_ws_implementation(exchange_config, is_private)
    rest_client = get_rest_implementation(exchange_config, is_private)
    is_futures = exchange_config.is_futures

    composite_class = COMPOSITE_AGNOSTIC_MAP.get((is_futures, is_private), None)
    if not composite_class:
        raise ValueError(f"No Composite implementation found for exchange {exchange_config.name} "
                         f"with is_private={is_private} and is_futures={is_futures}")

    return composite_class(exchange_config, rest_client, ws_client)

def create_rest_client(exchange: ExchangeEnum, config: ExchangeConfig, is_private: bool = False, **kwargs) -> Union[
    MexcPublicSpotRestInterface, MexcPrivateSpotRestInterface,
    GateioPublicSpotRestInterface, GateioPrivateSpotRestInterface,
    GateioPublicFuturesRestInterface, GateioPrivateFuturesRestInterface
]:
    """
    Compatibility wrapper for legacy create_rest_client interface.
    
    Args:
        exchange: Exchange enum (ignored - uses config.exchange_enum)
        config: Exchange configuration containing credentials and settings
        is_private: Whether to return private (authenticated) or public REST client
        **kwargs: Additional arguments (ignored for compatibility)
        
    Returns:
        Configured REST client instance for the specified exchange
    """
    return get_rest_implementation(config, is_private)


def create_websocket_client(exchange: ExchangeEnum, config: ExchangeConfig, is_private: bool = False, **kwargs) -> Union[
    MexcPublicSpotWebsocket, MexcPrivateSpotWebsocket,
    GateioPublicSpotWebsocket, GateioPrivateSpotWebsocket,
    GateioPublicFuturesWebsocket, GateioPrivateFuturesWebsocket
]:
    """
    Compatibility wrapper for legacy create_websocket_client interface.
    
    Args:
        exchange: Exchange enum (ignored - uses config.exchange_enum)
        config: Exchange configuration containing credentials and settings
        is_private: Whether to return private (authenticated) or public WebSocket client
        **kwargs: Additional arguments (ignored for compatibility)
        
    Returns:
        Configured WebSocket client instance for the specified exchange
    """
    return get_ws_implementation(config, is_private)

def get_symbol_mapper(exchange: ExchangeEnum) -> Union[MexcSymbolMapper, GateioSymbolMapper, GateioFuturesSymbolMapper]:
    """
    Get symbol mapper instance for specified exchange.
    
    Args:
        exchange: Exchange enum identifying which symbol mapper to create
        
    Returns:
        Initialized symbol mapper instance for the specified exchange
        
    Raises:
        ValueError: If no symbol mapper exists for the specified exchange
    """
    symbol_mapper_class = SYMBOL_MAPPER_MAP.get(exchange, None)
    if not symbol_mapper_class:
        raise ValueError(f"No SymbolMapper found for exchange {exchange}")
    return symbol_mapper_class()

