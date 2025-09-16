from .structs import HTTPMethod
from .rest_client import RestClient, create_transport_manager, create_transport_from_config
from .strategies import (
    RequestStrategy, RateLimitStrategy, RetryStrategy, AuthStrategy,
    RestStrategySet, RestStrategyFactory,
    RequestContext, RateLimitContext, PerformanceTargets, RequestMetrics
)
from .transport_manager import RestTransportManager
from .strategies_mexc import (
    MexcRequestStrategy, MexcRateLimitStrategy, MexcRetryStrategy, MexcAuthStrategy
)
from .strategies_gateio import (
    GateioRequestStrategy, GateioRateLimitStrategy, GateioRetryStrategy, GateioAuthStrategy
)

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
    "HTTPMethod",
    "RestClient",
    "create_transport_manager",  # Factory function for new transport system
    "create_transport_from_config",  # Factory function using ExchangeConfig
    # Strategy interfaces
    "RequestStrategy", "RateLimitStrategy", "RetryStrategy", "AuthStrategy",
    "RestStrategySet", "RestStrategyFactory",
    # Data structures
    "RequestContext", "RateLimitContext", "PerformanceTargets", "RequestMetrics",
    # Transport manager
    "RestTransportManager",
    # MEXC strategies
    "MexcRequestStrategy", "MexcRateLimitStrategy", "MexcRetryStrategy", "MexcAuthStrategy",
    # Gate.io strategies
    "GateioRequestStrategy", "GateioRateLimitStrategy", "GateioRetryStrategy", "GateioAuthStrategy"
]
