"""
Gate.io WebSocket Factory Registration

Separate module to handle factory registration and avoid circular imports.
"""

from core.factories.websocket import PublicWebSocketExchangeFactory, PrivateWebSocketExchangeFactory
from exchanges.consts import ExchangeEnum
from .gateio_ws_public import GateioWebsocketPublic
from .gateio_ws_private import GateioWebsocketPrivate
from .gateio_ws_public_futures import GateioWebsocketPublicFutures

# Register Gate.io WebSocket implementations
PublicWebSocketExchangeFactory.register(ExchangeEnum.GATEIO.value, GateioWebsocketPublic)
PrivateWebSocketExchangeFactory.register(ExchangeEnum.GATEIO.value, GateioWebsocketPrivate)

# Register Gate.io futures as separate exchange
PublicWebSocketExchangeFactory.register(ExchangeEnum.GATEIO_FUTURES.value, GateioWebsocketPublicFutures)
# Note: Private futures WebSocket not yet implemented