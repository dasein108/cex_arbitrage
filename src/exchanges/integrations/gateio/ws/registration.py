"""
Gate.io WebSocket Factory Registration

Separate module to handle factory registration and avoid circular imports.
"""

from infrastructure.factories.websocket import PublicWebSocketExchangeFactory, PrivateWebSocketExchangeFactory
from infrastructure.data_structures.common import ExchangeEnum
from .gateio_ws_public import GateioWebsocketPublic
from .gateio_ws_private import GateioWebsocketPrivate
from .gateio_ws_public_futures import GateioWebsocketPublicFutures
from .gateio_ws_private_futures import GateioWebsocketPrivateFutures

# Register Gate.io WebSocket implementations
PublicWebSocketExchangeFactory.register(ExchangeEnum.GATEIO, GateioWebsocketPublic)
PrivateWebSocketExchangeFactory.register(ExchangeEnum.GATEIO, GateioWebsocketPrivate)

# Register Gate.io futures as separate exchange
PublicWebSocketExchangeFactory.register(ExchangeEnum.GATEIO_FUTURES, GateioWebsocketPublicFutures)
PrivateWebSocketExchangeFactory.register(ExchangeEnum.GATEIO_FUTURES, GateioWebsocketPrivateFutures)