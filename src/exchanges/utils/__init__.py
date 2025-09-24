"""
Exchange Base Utils

Core utilities for exchange composite classes:
- kline_utils: Candlestick data processing utilities
- exchange_utils: Exchange enumeration and conversion utilities

Note: Symbol mapper interfaces are available directly from exchanges.services
to avoid circular dependencies.
"""

from .kline_utils import get_interval_seconds

__all__ = [
    'get_interval_seconds',
]