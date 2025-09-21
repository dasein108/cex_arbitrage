"""Gate.io WebSocket Implementations"""

from .gateio_ws_public import GateioWebsocketPublic
from .gateio_ws_private import GateioWebsocketPrivate
from .strategies import (
    GateioPublicConnectionStrategy,
    GateioPublicSubscriptionStrategy,
    GateioPublicMessageParser,
    GateioPrivateConnectionStrategy,
    GateioPrivateSubscriptionStrategy,
    GateioPrivateMessageParser
)
from core.transport.websocket.strategies import (
    WebSocketStrategyFactory
)

from exchanges.consts import ExchangeEnum

# Register strategies with factory
WebSocketStrategyFactory.register_strategies(
    ExchangeEnum.GATEIO.value, False,
    GateioPublicConnectionStrategy,
    GateioPublicSubscriptionStrategy,
    GateioPublicMessageParser,
)

WebSocketStrategyFactory.register_strategies(
    ExchangeEnum.GATEIO.value, True,
    GateioPrivateConnectionStrategy,
    GateioPrivateSubscriptionStrategy,
    GateioPrivateMessageParser
)

__all__ = ['GateioWebsocketPublic', 'GateioWebsocketPrivate']