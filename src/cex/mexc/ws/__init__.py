from cex.mexc.ws.public import (MexcWebsocketPublic,
                                      MexcPublicSubscriptionStrategy,
                                      MexcPublicConnectionStrategy, MexcPublicMessageParser)

from cex.mexc.ws.private import (MexcWebsocketPrivate, MexcPrivateConnectionStrategy,
                                       MexcPrivateSubscriptionStrategy,
                                       MexcPrivateMessageParser)

from core.cex.websocket.strategies import (
    WebSocketStrategyFactory
)

# Register strategies with factory
WebSocketStrategyFactory.register_strategies(
    'mexc', False,
    MexcPublicConnectionStrategy,
    MexcPublicSubscriptionStrategy,
    MexcPublicMessageParser
)

WebSocketStrategyFactory.register_strategies(
    'mexc', True,
    MexcPrivateConnectionStrategy,
    MexcPrivateSubscriptionStrategy,
    MexcPrivateMessageParser
)

__all__ = ["MexcWebsocketPublic", "MexcWebsocketPrivate"]
