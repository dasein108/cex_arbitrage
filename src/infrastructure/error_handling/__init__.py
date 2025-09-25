"""
Infrastructure Error Handling Module

Provides composition-based error handling patterns that eliminate deep nesting
and reduce complexity while maintaining HFT performance requirements.
"""

from .handlers import (
    ComposableErrorHandler,
    ErrorSeverity,
    ErrorContext,
    managed_resource
)
from .websocket_handlers import WebSocketErrorHandler
from .trading_handlers import TradingErrorHandler
from .rest_handlers import RestApiErrorHandler

__all__ = [
    'ComposableErrorHandler',
    'ErrorSeverity', 
    'ErrorContext',
    'managed_resource',
    'WebSocketErrorHandler',
    'TradingErrorHandler', 
    'RestApiErrorHandler'
]