"""Gate.io REST API Implementations"""

from .gateio_rest_public import GateioPublicSpotRest
from .gateio_rest_private import GateioPrivateSpotRest
from .gateio_futures_public import GateioPublicFuturesRest
from .gateio_futures_private import GateioPrivateFuturesRest
from .strategies import (
    GateioRequestStrategy, GateioRateLimitStrategy, GateioRetryStrategy, GateioAuthStrategy
)

# Register REST implementations with factories (auto-registration pattern)
from core.factories.rest.public_rest_factory import PublicRestExchangeFactory
from core.factories.rest.private_rest_factory import PrivateRestExchangeFactory

# Register Gate.io strategies with the factory
from infrastructure.networking.http.strategies import RestStrategyFactory
from infrastructure.data_structures.common import ExchangeEnum

# Register exchange strategies
RestStrategyFactory.register_strategies(
    exchange=ExchangeEnum.GATEIO,
    is_private=False,
    request_strategy_cls=GateioRequestStrategy,
    rate_limit_strategy_cls=GateioRateLimitStrategy,
    retry_strategy_cls=GateioRetryStrategy,
    auth_strategy_cls=None
)

RestStrategyFactory.register_strategies(
    exchange=ExchangeEnum.GATEIO,
    is_private=True,
    request_strategy_cls=GateioRequestStrategy,
    rate_limit_strategy_cls=GateioRateLimitStrategy,
    retry_strategy_cls=GateioRetryStrategy,
    auth_strategy_cls=GateioAuthStrategy
)

# Register Gate.io Futures strategies  
RestStrategyFactory.register_strategies(
    exchange=ExchangeEnum.GATEIO_FUTURES,
    is_private=False,
    request_strategy_cls=GateioRequestStrategy,
    rate_limit_strategy_cls=GateioRateLimitStrategy,
    retry_strategy_cls=GateioRetryStrategy,
    auth_strategy_cls=None
)

RestStrategyFactory.register_strategies(
    exchange=ExchangeEnum.GATEIO_FUTURES,
    is_private=True,
    request_strategy_cls=GateioRequestStrategy,
    rate_limit_strategy_cls=GateioRateLimitStrategy,
    retry_strategy_cls=GateioRetryStrategy,
    auth_strategy_cls=GateioAuthStrategy
)

PublicRestExchangeFactory.register(ExchangeEnum.GATEIO, GateioPublicSpotRest)
PrivateRestExchangeFactory.register(ExchangeEnum.GATEIO, GateioPrivateSpotRest)
PublicRestExchangeFactory.register(ExchangeEnum.GATEIO_FUTURES, GateioPublicFuturesRest)
PrivateRestExchangeFactory.register(ExchangeEnum.GATEIO_FUTURES, GateioPrivateFuturesRest)

__all__ = [
    'GateioPublicSpotRest', 
    'GateioPrivateSpotRest',
    'GateioPublicFuturesRest',
    'GateioPrivateFuturesRest',
    'GateioRequestStrategy', 
    'GateioRateLimitStrategy', 
    'GateioRetryStrategy', 
    'GateioAuthStrategy'
]