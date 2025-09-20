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

# Import factory for registration
from core.transport.websocket.strategies import WebSocketStrategyFactory
from cex.consts import ExchangeEnum

# Register public strategies with factory
WebSocketStrategyFactory.register_strategies(
    ExchangeEnum.GATEIO.value, False,
    GateioPublicConnectionStrategy,
    GateioPublicSubscriptionStrategy,
    GateioPublicMessageParser
)

# Register private strategies with factory
WebSocketStrategyFactory.register_strategies(
    ExchangeEnum.GATEIO.value, True,
    GateioPrivateConnectionStrategy,
    GateioPrivateSubscriptionStrategy,
    GateioPrivateMessageParser
)

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