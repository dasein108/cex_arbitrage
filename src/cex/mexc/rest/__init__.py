from .rest_public import MexcPublicSpotRest
from .rest_private import MexcPrivateSpotRest
from .strategies_mexc import (
    MexcRequestStrategy, MexcRateLimitStrategy, MexcRetryStrategy, MexcAuthStrategy
)

# Register MEXC strategies with the factory
from core.transport.rest.strategies import RestStrategyFactory

# Register exchange strategies
RestStrategyFactory.register_strategies(
    exchange="mexc",
    is_private=False,
    request_strategy_cls=MexcRequestStrategy,
    rate_limit_strategy_cls=MexcRateLimitStrategy,
    retry_strategy_cls=MexcRetryStrategy,
    auth_strategy_cls=None
)

RestStrategyFactory.register_strategies(
    exchange="mexc",
    is_private=True,
    request_strategy_cls=MexcRequestStrategy,
    rate_limit_strategy_cls=MexcRateLimitStrategy,
    retry_strategy_cls=MexcRetryStrategy,
    auth_strategy_cls=MexcAuthStrategy
)

__all__ = [
    "MexcPublicSpotRest", 
    "MexcPrivateSpotRest",
    "MexcRequestStrategy", 
    "MexcRateLimitStrategy", 
    "MexcRetryStrategy", 
    "MexcAuthStrategy"
]