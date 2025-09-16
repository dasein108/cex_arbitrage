from .structs import HTTPMethod
from .rest_client import RestClient, create_transport_manager, create_transport_from_config
from .strategies import (
    RequestStrategy, RateLimitStrategy, RetryStrategy, AuthStrategy,
    RestStrategySet, RestStrategyFactory,
    RequestContext, RateLimitContext, PerformanceTargets, RequestMetrics
)
from .transport_manager import RestTransportManager
# Exchange-specific strategies are now registered in their respective exchange modules
# This keeps the core transport module free of exchange-specific code

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
    "RestTransportManager"
    # Exchange-specific strategies are now exported from their respective exchange modules
]
