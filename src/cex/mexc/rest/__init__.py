from .rest_public import MexcPublicSpotRest
from .rest_private import MexcPrivateSpotRest
from .strategies.request import MexcRequestStrategy
from .strategies.rate_limit import MexcRateLimitStrategy
from .strategies.retry import MexcRetryStrategy
from cex.mexc.rest.strategies.auth import MexcAuthStrategy
from cex.mexc.rest.strategies.exception_handler import MexcExceptionHandlerStrategy

# Register MEXC strategies with the factory
from core.transport.rest.strategies import RestStrategyFactory

# Register exchange strategies
RestStrategyFactory.register_strategies(
    exchange="mexc",
    is_private=False,
    request_strategy_cls=MexcRequestStrategy,
    rate_limit_strategy_cls=MexcRateLimitStrategy,
    retry_strategy_cls=MexcRetryStrategy,
    auth_strategy_cls=None,
    exception_handler_strategy_cls=MexcExceptionHandlerStrategy
)

RestStrategyFactory.register_strategies(
    exchange="mexc",
    is_private=True,
    request_strategy_cls=MexcRequestStrategy,
    rate_limit_strategy_cls=MexcRateLimitStrategy,
    retry_strategy_cls=MexcRetryStrategy,
    auth_strategy_cls=MexcAuthStrategy,
    exception_handler_strategy_cls=MexcExceptionHandlerStrategy
)

__all__ = [
    "MexcPublicSpotRest", 
    "MexcPrivateSpotRest"
]