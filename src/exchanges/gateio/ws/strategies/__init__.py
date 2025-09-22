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

from .futures.connection import GateioFuturesConnectionStrategy
from .futures.subscription import GateioFuturesSubscriptionStrategy
from .futures.message_parser import GateioFuturesMessageParser

# Import factory for registration
from core.transport.websocket.strategies import WebSocketStrategyFactory
from structs.common import ExchangeEnum

# Register public strategies with factory
WebSocketStrategyFactory.register_strategies(
    ExchangeEnum.GATEIO, False,
    GateioPublicConnectionStrategy,
    GateioPublicSubscriptionStrategy,
    GateioPublicMessageParser
)

# Register private strategies with factory
WebSocketStrategyFactory.register_strategies(
    ExchangeEnum.GATEIO, True,
    GateioPrivateConnectionStrategy,
    GateioPrivateSubscriptionStrategy,
    GateioPrivateMessageParser
)

WebSocketStrategyFactory.register_strategies(
    ExchangeEnum.GATEIO_FUTURES, False,
    GateioFuturesConnectionStrategy,
    GateioFuturesSubscriptionStrategy,
    GateioFuturesMessageParser
)

__all__ = [
    # Public strategies
    'GateioPublicConnectionStrategy',
    'GateioPublicSubscriptionStrategy', 
    'GateioPublicMessageParser',
    
    # Private strategies
    'GateioPrivateConnectionStrategy',
    'GateioPrivateSubscriptionStrategy',
    'GateioPrivateMessageParser',

    # Futures strategies
    'GateioFuturesConnectionStrategy',
    'GateioFuturesSubscriptionStrategy',
    'GateioFuturesMessageParser'
]