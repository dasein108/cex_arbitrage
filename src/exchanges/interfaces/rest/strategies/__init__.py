"""
Shared REST Strategy Interfaces

Common strategy patterns extracted from exchange-specific implementations.
Provides base classes and interfaces for authentication, rate limiting, 
retry logic, request handling, and exception management.
"""

from .base_auth_strategy import BaseExchangeAuthStrategy
from .base_rate_limit_strategy import BaseExchangeRateLimitStrategy
from .base_request_strategy import BaseExchangeRequestStrategy
from .base_retry_strategy import BaseExchangeRetryStrategy
from .base_exception_handler import BaseExchangeExceptionHandler

__all__ = [
    'BaseExchangeAuthStrategy',
    'BaseExchangeRateLimitStrategy', 
    'BaseExchangeRequestStrategy',
    'BaseExchangeRetryStrategy',
    'BaseExchangeExceptionHandler',
]