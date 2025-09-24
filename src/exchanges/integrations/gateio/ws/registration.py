"""
Gate.io WebSocket Factory Registration

Separate module to handle factory registration and avoid circular imports.
Uses delayed import pattern to prevent circular dependencies during module initialization.
"""

from exchanges.structs import ExchangeEnum

def register_gateio_websocket_implementations():
    """
    Register Gate.io WebSocket implementations with factories.
    
    Uses delayed import pattern to avoid circular dependencies.
    This function should be called after the factory modules are fully initialized.
    """
    # Delayed imports to avoid circular dependencies
    from infrastructure.factories.websocket import PublicWebSocketExchangeFactory, PrivateWebSocketExchangeFactory
    from .gateio_ws_public import GateioWebsocketPublic
    from .gateio_ws_private import GateioWebsocketPrivateSpot
    from .gateio_ws_public_futures import GateioWebsocketExchangePublicFuturesWebsocket
    from .gateio_ws_private_futures import GateioWebsocketPrivateSpotFutures
    
    # Register Gate.io WebSocket implementations
    PublicWebSocketExchangeFactory.register(ExchangeEnum.GATEIO, GateioWebsocketPublic)
    PrivateWebSocketExchangeFactory.register(ExchangeEnum.GATEIO, GateioWebsocketPrivateSpot)
    
    # Register Gate.io futures as separate exchange
    PublicWebSocketExchangeFactory.register(ExchangeEnum.GATEIO_FUTURES, GateioWebsocketExchangePublicFuturesWebsocket)
    PrivateWebSocketExchangeFactory.register(ExchangeEnum.GATEIO_FUTURES, GateioWebsocketPrivateSpotFutures)


# Auto-register when this module is imported (delayed execution)
try:
    register_gateio_websocket_implementations()
except ImportError:
    # If factories are not yet initialized, registration will be retried later
    pass