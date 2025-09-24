"""
MEXC WebSocket Factory Registration

Separate module to handle factory registration and avoid circular imports.
Uses delayed import pattern to prevent circular dependencies during module initialization.
"""

from infrastructure.data_structures.common import ExchangeEnum


def register_mexc_websocket_implementations():
    """
    Register MEXC WebSocket implementations with factories.
    
    Uses delayed import pattern to avoid circular dependencies.
    This function should be called after the factory modules are fully initialized.
    """
    # Delayed imports to avoid circular dependencies
    from infrastructure.factories.websocket import PublicWebSocketExchangeFactory, PrivateWebSocketExchangeFactory
    from .mexc_ws_public import MexcWebsocketExchangePublicWebsocket
    from .mexc_ws_private import MexcWebsocketPrivateSpot
    
    # Register MEXC WebSocket implementations
    PublicWebSocketExchangeFactory.register(ExchangeEnum.MEXC, MexcWebsocketExchangePublicWebsocket)
    PrivateWebSocketExchangeFactory.register(ExchangeEnum.MEXC, MexcWebsocketPrivateSpot)


# Auto-register when this module is imported (delayed execution)
try:
    register_mexc_websocket_implementations()
except ImportError:
    # If factories are not yet initialized, registration will be retried later
    pass