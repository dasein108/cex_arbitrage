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

__all__ = [
    'GateioRequestStrategy',
    'GateioRateLimitStrategy',
    'GateioRetryStrategy',
    'GateioAuthStrategy',
    'GateioExceptionHandlerStrategy',
]