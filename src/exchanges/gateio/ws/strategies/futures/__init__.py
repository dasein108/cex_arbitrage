"""
Gate.io Futures WebSocket Strategies

Strategy implementations for Gate.io futures WebSocket connections.
Extends spot strategies with futures-specific endpoints and message handling.
"""

from .connection import GateioFuturesConnectionStrategy
from .message_parser import GateioFuturesMessageParser
from .subscription import GateioFuturesSubscriptionStrategy

__all__ = [
    "GateioFuturesConnectionStrategy",
    "GateioFuturesMessageParser", 
    "GateioFuturesSubscriptionStrategy"
]