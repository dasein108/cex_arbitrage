"""
Gate.io Private WebSocket Strategies

Private WebSocket strategies for Gate.io authenticated channels.
Requires API credentials for trading data and account updates.
"""

from .connection import GateioPrivateConnectionStrategy
from .subscription import GateioPrivateSubscriptionStrategy
from .message_parser import GateioPrivateMessageParser

__all__ = [
    'GateioPrivateConnectionStrategy',
    'GateioPrivateSubscriptionStrategy',
    'GateioPrivateMessageParser'
]