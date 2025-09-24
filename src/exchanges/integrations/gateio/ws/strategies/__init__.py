"""
Gate.io WebSocket Strategies

WebSocket strategy implementations for Gate.io following the unified pattern.
Provides connection, subscription, and message parsing strategies for both
public and private WebSocket channels.
"""

# Public strategies
from exchanges.integrations.gateio.ws.strategies.spot.public import GateioPublicConnectionStrategy
from exchanges.integrations.gateio.ws.strategies.spot.public.subscription import GateioPublicSubscriptionStrategy
from exchanges.integrations.gateio.ws.strategies.spot.public import GateioPublicMessageParser

# Private strategies
from exchanges.integrations.gateio.ws.strategies.spot.private import GateioPrivateConnectionStrategy
from exchanges.integrations.gateio.ws.strategies.spot.private.subscription import GateioPrivateSubscriptionStrategy
from exchanges.integrations.gateio.ws.strategies.spot.private.message_parser import GateioPrivateMessageParser

# Futures strategies
from exchanges.integrations.gateio.ws.strategies.futures.public.connection import GateioPublicFuturesConnectionStrategy
from exchanges.integrations.gateio.ws.strategies.futures.public.subscription import GateioPublicFuturesSubscriptionStrategy
from exchanges.integrations.gateio.ws.strategies.futures.public.message_parser import GateioPublicFuturesMessageParser

# Private futures strategies
from exchanges.integrations.gateio.ws.strategies.futures.private.connection import GateioPrivateFuturesConnectionStrategy
from exchanges.integrations.gateio.ws.strategies.futures.private import GateioPrivateFuturesSubscriptionStrategy
from exchanges.integrations.gateio.ws.strategies.futures.private import GateioPrivateFuturesMessageParser

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
    GateioPublicFuturesConnectionStrategy,
    GateioPublicFuturesSubscriptionStrategy,
    GateioPublicFuturesMessageParser
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
    'GateioPublicFuturesConnectionStrategy',
    'GateioPublicFuturesSubscriptionStrategy',
    'GateioPublicFuturesMessageParser',

    # Private futures strategies
    'GateioPrivateFuturesConnectionStrategy',
    'GateioPrivateFuturesSubscriptionStrategy',
    'GateioPrivateFuturesMessageParser'
]