"""
REST Transport Strategy Module

This module provides strategy interfaces and data structures for REST transport.
All strategies follow the HFT-compliant design with sub-millisecond execution times.
"""

from .structs import (
    RequestContext,
    RateLimitContext,
    AuthenticationData,
    PerformanceTargets,
    RequestMetrics
)

from .request import RequestStrategy
from .rate_limit import RateLimitStrategy
from .retry import RetryStrategy
from .auth import AuthStrategy
from .exception_handler import ExceptionHandlerStrategy
from .strategy_set import RestStrategySet

from .factory import RestStrategyFactory

__all__ = [
    # Data structures
    'RequestContext',
    'RateLimitContext',
    'AuthenticationData',
    'PerformanceTargets',
    'RequestMetrics',
    
    # Strategy interfaces
    'RequestStrategy',
    'RateLimitStrategy',
    'RetryStrategy',
    'AuthStrategy',
    'ExceptionHandlerStrategy',
    
    # Strategy container
    'RestStrategySet',
    
    # Factory
    'RestStrategyFactory',
]