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
from infrastructure.data_structures.common import ExchangeEnum
from infrastructure.networking.http.strategies import RestStrategyFactory

# Register Gate.io spot public API strategies
RestStrategyFactory.register_strategies(
    exchange=ExchangeEnum.GATEIO,
    is_private=False,
    request_strategy_cls=GateioRequestStrategy,
    rate_limit_strategy_cls=GateioRateLimitStrategy,
    retry_strategy_cls=GateioRetryStrategy,
    auth_strategy_cls=None,
    exception_handler_strategy_cls=GateioExceptionHandlerStrategy
)

# Register Gate.io spot private API strategies
RestStrategyFactory.register_strategies(
    exchange=ExchangeEnum.GATEIO,
    is_private=True,
    request_strategy_cls=GateioRequestStrategy,
    rate_limit_strategy_cls=GateioRateLimitStrategy,
    retry_strategy_cls=GateioRetryStrategy,
    auth_strategy_cls=GateioAuthStrategy,
    exception_handler_strategy_cls=GateioExceptionHandlerStrategy
)

# Register Gate.io futures public API strategies
RestStrategyFactory.register_strategies(
    exchange=ExchangeEnum.GATEIO_FUTURES,
    is_private=False,
    request_strategy_cls=GateioRequestStrategy,
    rate_limit_strategy_cls=GateioRateLimitStrategy,
    retry_strategy_cls=GateioRetryStrategy,
    auth_strategy_cls=None,
    exception_handler_strategy_cls=GateioExceptionHandlerStrategy
)

# Register Gate.io futures private API strategies
RestStrategyFactory.register_strategies(
    exchange=ExchangeEnum.GATEIO_FUTURES,
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