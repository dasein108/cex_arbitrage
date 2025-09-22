"""
MEXC WebSocket Factory Registration

Separate module to handle factory registration and avoid circular imports.
"""

from core.factories.websocket import PublicWebSocketExchangeFactory, PrivateWebSocketExchangeFactory
from structs.common import ExchangeEnum
from .mexc_ws_public import MexcWebsocketPublic
from .mexc_ws_private import MexcWebsocketPrivate

# Register MEXC WebSocket implementations
PublicWebSocketExchangeFactory.register(ExchangeEnum.MEXC, MexcWebsocketPublic)
PrivateWebSocketExchangeFactory.register(ExchangeEnum.MEXC, MexcWebsocketPrivate)