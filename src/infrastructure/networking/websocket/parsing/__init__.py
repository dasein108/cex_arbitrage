"""
WebSocket message parsing utilities.

Common utilities for parsing WebSocket messages across all exchanges,
providing standardized JSON decoding, error handling, and message creation 
patterns to eliminate code duplication.

Symbol extraction moved to exchange-specific utils for direct function calls.
"""

from .message_parsing_utils import MessageParsingUtils, ExchangeMessageHandler
from .error_handling import WebSocketErrorHandler, ParseErrorType
# Symbol extraction moved to exchange-specific utils - no more strategy pattern
# Universal transformer removed - exchanges use direct utility functions

__all__ = [
    'MessageParsingUtils',
    'ExchangeMessageHandler',
    'WebSocketErrorHandler',
    'ParseErrorType',
    # Symbol extraction exports removed - use exchange-specific utils instead
]