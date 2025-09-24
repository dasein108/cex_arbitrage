from .private import MexcPrivateConnectionStrategy, MexcPrivateSubscriptionStrategy, MexcPrivateMessageParser
from .public import MexcPublicConnectionStrategy, MexcPublicSubscriptionStrategy, MexcPublicMessageParser


from infrastructure.networking.websocket.strategies import (
    WebSocketStrategyFactory
)

from infrastructure.data_structures.common import ExchangeEnum

# Register strategies with factory
WebSocketStrategyFactory.register_strategies(
    ExchangeEnum.MEXC, False,
    MexcPublicConnectionStrategy,
    MexcPublicSubscriptionStrategy,
    MexcPublicMessageParser
)

WebSocketStrategyFactory.register_strategies(
    ExchangeEnum.MEXC, True,
    MexcPrivateConnectionStrategy,
    MexcPrivateSubscriptionStrategy,
    MexcPrivateMessageParser
)

__all__ = [
    "MexcPrivateConnectionStrategy",
    "MexcPrivateSubscriptionStrategy",
    "MexcPrivateMessageParser",
    "MexcPublicConnectionStrategy",
    "MexcPublicSubscriptionStrategy",
    "MexcPublicMessageParser",
]