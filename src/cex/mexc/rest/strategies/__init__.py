"""
MEXC REST Strategy Module

This module auto-registers MEXC strategies with the RestStrategyFactory
when imported. This ensures exchange-agnostic factory operation.
"""

from .request import MexcRequestStrategy
from .rate_limit import MexcRateLimitStrategy
from .retry import MexcRetryStrategy
from .auth import MexcAuthStrategy
from .exception_handler import MexcExceptionHandlerStrategy
from cex.consts import ExchangeEnum
from core.transport.rest.strategies import RestStrategyFactory

# Register public API strategies
RestStrategyFactory.register_strategies(
    exchange=ExchangeEnum.MEXC.value,
    is_private=False,
    request_strategy_cls=MexcRequestStrategy,
    rate_limit_strategy_cls=MexcRateLimitStrategy,
    retry_strategy_cls=MexcRetryStrategy,
    auth_strategy_cls=None,
    exception_handler_strategy_cls=MexcExceptionHandlerStrategy
)

# Register private API strategies
RestStrategyFactory.register_strategies(
    exchange=ExchangeEnum.MEXC.value,
    is_private=True,
    request_strategy_cls=MexcRequestStrategy,
    rate_limit_strategy_cls=MexcRateLimitStrategy,
    retry_strategy_cls=MexcRetryStrategy,
    auth_strategy_cls=MexcAuthStrategy,
    exception_handler_strategy_cls=MexcExceptionHandlerStrategy
)


__all__ = [
    'MexcRequestStrategy',
    'MexcRateLimitStrategy', 
    'MexcRetryStrategy',
    'MexcAuthStrategy',
    'MexcExceptionHandlerStrategy',
]