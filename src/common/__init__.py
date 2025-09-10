"""
Common utilities and shared components for the CEX arbitrage system.

This module provides shared components used across the arbitrage trading system:
- Exception hierarchy for unified error handling
- High-performance REST client for exchange API interactions
- Utility functions for common operations
"""

from .exceptions import *
from .rest import *

__all__ = [
    # Exception classes
    'ExchangeAPIError', 'RateLimitError', 'InsufficientBalanceError',
    'OrderError', 'NetworkError', 'AuthenticationError', 'ValidationError',
    
    # REST client classes
    'HighPerformanceRestClient', 'RequestConfig', 'ConnectionConfig',
    'create_market_data_config', 'create_trading_config', 'HTTPMethod',
    'RateLimiter'
]