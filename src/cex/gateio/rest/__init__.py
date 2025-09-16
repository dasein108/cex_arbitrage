"""Gate.io REST API Implementations"""

from .gateio_public import GateioPublicExchangeSpotRest
from .gateio_private import GateioPrivateExchangeSpot
from .strategies_gateio_rest import (
    GateioRequestStrategy, GateioRateLimitStrategy, GateioRetryStrategy, GateioAuthStrategy
)

# Register Gate.io strategies with the factory
from core.transport.rest.strategies import RestStrategyFactory

# Register exchange strategies
RestStrategyFactory.register_strategies(
    exchange="gateio",
    is_private=False,
    request_strategy_cls=GateioRequestStrategy,
    rate_limit_strategy_cls=GateioRateLimitStrategy,
    retry_strategy_cls=GateioRetryStrategy,
    auth_strategy_cls=None
)

RestStrategyFactory.register_strategies(
    exchange="gateio",
    is_private=True,
    request_strategy_cls=GateioRequestStrategy,
    rate_limit_strategy_cls=GateioRateLimitStrategy,
    retry_strategy_cls=GateioRetryStrategy,
    auth_strategy_cls=GateioAuthStrategy
)

__all__ = [
    'GateioPublicExchangeSpotRest', 
    'GateioPrivateExchangeSpot',
    'GateioRequestStrategy', 
    'GateioRateLimitStrategy', 
    'GateioRetryStrategy', 
    'GateioAuthStrategy'
]