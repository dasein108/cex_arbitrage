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
    from infrastructure.transport_factory import register_ws_public, register_ws_private
    from .gateio_ws_public import GateioPublicSpotWebsocket
    from .gateio_ws_private import GateioPrivateSpotWebsocket
    from .gateio_ws_public_futures import GateioPublicFuturesWebsocket
    from .gateio_ws_private_futures import GateioPrivateFuturesWebsocket
    
    # Register Gate.io WebSocket implementations
    register_ws_public(ExchangeEnum.GATEIO, GateioPublicSpotWebsocket)
    register_ws_private(ExchangeEnum.GATEIO, GateioPrivateSpotWebsocket)
    
    # Register Gate.io futures as separate exchange
    register_ws_public(ExchangeEnum.GATEIO_FUTURES, GateioPublicFuturesWebsocket)
    register_ws_private(ExchangeEnum.GATEIO_FUTURES, GateioPrivateFuturesWebsocket)


# Auto-register when this module is imported (delayed execution)
try:
    register_gateio_websocket_implementations()
except ImportError:
    # If factories are not yet initialized, registration will be retried later
    pass