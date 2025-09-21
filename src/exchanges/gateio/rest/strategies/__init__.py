"""
Gate.io REST Strategy Module

This module auto-registers Gate.io strategies with the RestStrategyFactory
when imported. This ensures exchange-agnostic factory operation.
"""

from .request import GateioRequestStrategy
from .rate_limit import GateioRateLimitStrategy
from .retry import GateioRetryStrategy
from .auth import GateioAuthStrategy
from .exception_handler import GateioExceptionHandlerStrategy
from exchanges.consts import ExchangeEnum
from core.transport.rest.strategies import RestStrategyFactory

# Register public API strategies
RestStrategyFactory.register_strategies(
    exchange=ExchangeEnum.GATEIO.value,
    is_private=False,
    request_strategy_cls=GateioRequestStrategy,
    rate_limit_strategy_cls=GateioRateLimitStrategy,
    retry_strategy_cls=GateioRetryStrategy,
    auth_strategy_cls=None,
    exception_handler_strategy_cls=GateioExceptionHandlerStrategy
)

# Register private API strategies
RestStrategyFactory.register_strategies(
    exchange=ExchangeEnum.GATEIO.value,
    is_private=True,
    request_strategy_cls=GateioRequestStrategy,
    rate_limit_strategy_cls=GateioRateLimitStrategy,
    retry_strategy_cls=GateioRetryStrategy,
    auth_strategy_cls=GateioAuthStrategy,
    exception_handler_strategy_cls=GateioExceptionHandlerStrategy
)

# Register GATEIO_FUTURES public API strategies (uses same strategies as spot)
RestStrategyFactory.register_strategies(
    exchange=ExchangeEnum.GATEIO_FUTURES.value,
    is_private=False,
    request_strategy_cls=GateioRequestStrategy,
    rate_limit_strategy_cls=GateioRateLimitStrategy,
    retry_strategy_cls=GateioRetryStrategy,
    auth_strategy_cls=None,
    exception_handler_strategy_cls=GateioExceptionHandlerStrategy
)

# Register GATEIO_FUTURES private API strategies (uses same strategies as spot)
RestStrategyFactory.register_strategies(
    exchange=ExchangeEnum.GATEIO_FUTURES.value,
    is_private=True,
    request_strategy_cls=GateioRequestStrategy,
    rate_limit_strategy_cls=GateioRateLimitStrategy,
    retry_strategy_cls=GateioRetryStrategy,
    auth_strategy_cls=GateioAuthStrategy,
    exception_handler_strategy_cls=GateioExceptionHandlerStrategy
)


__all__ = [
    'GateioRequestStrategy',
    'GateioRateLimitStrategy',
    'GateioRetryStrategy',
    'GateioAuthStrategy',
    'GateioExceptionHandlerStrategy',
]