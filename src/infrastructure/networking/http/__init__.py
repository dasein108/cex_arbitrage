from .structs import HTTPMethod
# from .rest_client_legacy import RestClient  # File missing - commented out to prevent import error
from .strategies import (
    RequestStrategy, RateLimitStrategy, RetryStrategy, AuthStrategy, ExceptionHandlerStrategy,
    RestStrategySet, RestStrategyFactory,
    RequestContext, RateLimitContext, PerformanceTargets, RequestMetrics, AuthenticationData
)
from .rest_transport_manager import RestTransportManager
# Exchange-specific strategies are now registered in their respective exchange modules
# This keeps the core transport module free of exchange-specific code

__all__ = [
    "HTTPMethod",
    # "RestClient",  # Commented out due to missing file
    # Strategy interfaces
    "RequestStrategy", "RateLimitStrategy", "RetryStrategy", "AuthStrategy", "ExceptionHandlerStrategy",
    "RestStrategySet", "RestStrategyFactory",
    # Data structures
    "RequestContext", "RateLimitContext", "PerformanceTargets", "RequestMetrics", "AuthenticationData",
    # Transport manager
    "RestTransportManager"
    # Exchange-specific strategies are now exported from their respective exchange modules
]
