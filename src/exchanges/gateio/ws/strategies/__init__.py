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

# Futures strategies
from .futures.connection import GateioFuturesConnectionStrategy
from .futures.subscription import GateioFuturesSubscriptionStrategy
from .futures.message_parser import GateioFuturesMessageParser

# Private futures strategies
from .private_futures.connection import GateioPrivateFuturesConnectionStrategy
from .private_futures.subscription import GateioPrivateFuturesSubscriptionStrategy
from .private_futures.message_parser import GateioPrivateFuturesMessageParser

# Import factory for registration
from infrastructure.networking.websocket.strategies import WebSocketStrategyFactory
from infrastructure.data_structures.common import ExchangeEnum

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

# Register public futures strategies with factory
WebSocketStrategyFactory.register_strategies(
    ExchangeEnum.GATEIO_FUTURES, False,
    GateioFuturesConnectionStrategy,
    GateioFuturesSubscriptionStrategy,
    GateioFuturesMessageParser
)

# Register private futures strategies with factory
WebSocketStrategyFactory.register_strategies(
    ExchangeEnum.GATEIO_FUTURES, True,
    GateioPrivateFuturesConnectionStrategy,
    GateioPrivateFuturesSubscriptionStrategy,
    GateioPrivateFuturesMessageParser
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
    'GateioFuturesMessageParser',

    # Private futures strategies
    'GateioPrivateFuturesConnectionStrategy',
    'GateioPrivateFuturesSubscriptionStrategy',
    'GateioPrivateFuturesMessageParser'
]