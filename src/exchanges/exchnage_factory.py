from exchanges.integrations.mexc.rest import *
from exchanges.integrations.gateio.rest import *
from exchanges.integrations.mexc.ws import *
from exchanges.integrations.gateio.ws import *
from config.structs import ExchangeConfig
from exchanges.structs.enums import ExchangeEnum
from exchanges.interfaces.composite import *

EXCHANGE_REST_MAP = {
    (ExchangeEnum.MEXC, False): MexcPublicSpotRest,
    (ExchangeEnum.MEXC, True): MexcPrivateSpotRest,
    (ExchangeEnum.GATEIO, False): GateioPublicSpotRest,
    (ExchangeEnum.GATEIO, True): GateioPrivateSpotRest,
    (ExchangeEnum.GATEIO_FUTURES, False): GateioPublicFuturesRest,
    (ExchangeEnum.GATEIO_FUTURES, True): GateioPrivateFuturesRest,
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

    # TODO: return instance of composite class with rest and ws clients
