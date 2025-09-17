"""
Gate.io WebSocket Strategies

WebSocket strategy implementations for Gate.io following the unified pattern.
Provides connection, subscription, and message parsing strategies for both
public and private WebSocket channels.
"""

# Public strategies
from .public.connection import GateioPublicConnectionStrategy
from .public.subscription import GateioPublicSubscriptionStrategy  
from .public.message_parser import GateioPublicMessageParser

# Private strategies
from .private.connection import GateioPrivateConnectionStrategy
from .private.subscription import GateioPrivateSubscriptionStrategy
from .private.message_parser import GateioPrivateMessageParser

__all__ = [
    # Public strategies
    'GateioPublicConnectionStrategy',
    'GateioPublicSubscriptionStrategy', 
    'GateioPublicMessageParser',
    
    # Private strategies
    'GateioPrivateConnectionStrategy',
    'GateioPrivateSubscriptionStrategy',
    'GateioPrivateMessageParser'
]