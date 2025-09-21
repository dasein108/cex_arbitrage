"""Gate.io REST API Implementations"""

from .gateio_rest_public import GateioPublicSpotRest
from .gateio_rest_private import GateioPrivateSpotRest
from .strategies import (
    GateioRequestStrategy, GateioRateLimitStrategy, GateioRetryStrategy, GateioAuthStrategy
)

# Register REST implementations with factories (auto-registration pattern)
from core.factories.rest.public_rest_factory import PublicRestExchangeFactory
from core.factories.rest.private_rest_factory import PrivateRestExchangeFactory

# Register Gate.io strategies with the factory
from core.transport.rest.strategies import RestStrategyFactory
from exchanges.consts import ExchangeEnum

# Register exchange strategies
RestStrategyFactory.register_strategies(
    exchange=ExchangeEnum.GATEIO.value,
    is_private=False,
    request_strategy_cls=GateioRequestStrategy,
    rate_limit_strategy_cls=GateioRateLimitStrategy,
    retry_strategy_cls=GateioRetryStrategy,
    auth_strategy_cls=None
)

RestStrategyFactory.register_strategies(
    exchange=ExchangeEnum.GATEIO.value,
    is_private=True,
    request_strategy_cls=GateioRequestStrategy,
    rate_limit_strategy_cls=GateioRateLimitStrategy,
    retry_strategy_cls=GateioRetryStrategy,
    auth_strategy_cls=GateioAuthStrategy
)

PublicRestExchangeFactory.register(ExchangeEnum.GATEIO.value, GateioPublicSpotRest)
PrivateRestExchangeFactory.register(ExchangeEnum.GATEIO.value, GateioPrivateSpotRest)

__all__ = [
    'GateioPublicSpotRest', 
    'GateioPrivateSpotRest',
    'GateioRequestStrategy', 
    'GateioRateLimitStrategy', 
    'GateioRetryStrategy', 
    'GateioAuthStrategy'
]