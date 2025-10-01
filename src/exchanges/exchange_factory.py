from exchanges.integrations.gateio.services.futures_symbol_mapper import GateioFuturesSymbolMapper
from exchanges.integrations.gateio.services.spot_symbol_mapper import GateioSymbolMapper
from exchanges.integrations.mexc.rest import *
from exchanges.integrations.gateio.rest import *
from exchanges.integrations.mexc.services.symbol_mapper import MexcSymbolMapper
from exchanges.integrations.mexc.ws import *
from exchanges.integrations.gateio.ws import *
from config.structs import ExchangeConfig
from exchanges.structs.enums import ExchangeEnum
from exchanges.interfaces.composite import *

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

def get_rest_implementation(exchange_config: ExchangeConfig, is_private: bool):
    key = (exchange_config.exchange_enum, is_private)
    impl_class = EXCHANGE_REST_MAP.get(key, None)
    if not impl_class:
        raise ValueError(f"No REST implementation found for exchange {exchange_config.name} "
                         f"with is_private={is_private}")

    return impl_class(exchange_config)

def get_ws_implementation(exchange_config: ExchangeConfig, is_private: bool):
    key = (exchange_config.exchange_enum, is_private)
    impl_class = EXCHANGE_WS_MAP.get(key, None)
    if not impl_class:
        raise ValueError(f"No REST implementation found for exchange {exchange_config.name} "
                         f"with is_private={is_private}")
    return impl_class(exchange_config)


def get_composite_implementation(exchange_config: ExchangeConfig, is_private: bool):
    ws_client = get_ws_implementation(exchange_config, is_private)
    rest_client = get_rest_implementation(exchange_config, is_private)
    is_futures = exchange_config.is_futures

    composite_class = COMPOSITE_AGNOSTIC_MAP.get((is_futures, is_private), None)
    if not composite_class:
        raise ValueError(f"No Composite implementation found for exchange {exchange_config.name} "
                         f"with is_private={is_private} and is_futures={is_futures}")

    return composite_class(exchange_config, rest_client, ws_client)


# Compatibility functions for old factory interface
def create_rest_client(exchange: ExchangeEnum, config: ExchangeConfig, is_private: bool = False, **kwargs):
    """Compatibility wrapper for create_rest_client."""
    return get_rest_implementation(config, is_private)


def create_websocket_client(exchange: ExchangeEnum, config: ExchangeConfig, is_private: bool = False, **kwargs):
    """Compatibility wrapper for create_websocket_client."""
    return get_ws_implementation(config, is_private)


def create_exchange_component(exchange: ExchangeEnum, config: ExchangeConfig, component_type: str, is_private: bool = False, **kwargs):
    """Compatibility wrapper for create_exchange_component."""
    if component_type == 'rest':
        return get_rest_implementation(config, is_private)
    elif component_type == 'websocket':
        return get_ws_implementation(config, is_private)
    elif component_type == 'composite':
        return get_composite_implementation(config, is_private)
    else:
        raise ValueError(f"Unsupported component_type: {component_type}")


# Symbol mapper (if needed)
def get_symbol_mapper(exchange: ExchangeEnum):
    """Get symbol mapper for exchange."""
    symbol_mapper_class = SYMBOL_MAPPER_MAP.get(exchange, None)
    if not symbol_mapper_class:
        raise ValueError(f"No SymbolMapper found for exchange {exchange}")
    return symbol_mapper_class()
