"""
MEXC WebSocket Factory Registration

Separate module to handle factory registration and avoid circular imports.
Uses delayed import pattern to prevent circular dependencies during module initialization.
"""

from exchanges.structs import ExchangeEnum

def register_mexc_websocket_implementations():
    """
    Register MEXC WebSocket implementations with factories.
    
    Uses delayed import pattern to avoid circular dependencies.
    This function should be called after the factory modules are fully initialized.
    """
    # Delayed imports to avoid circular dependencies
    from infrastructure.transport_factory import register_ws_public, register_ws_private
    from .mexc_ws_public import MexcPublicSpotWebsocket
    from .mexc_ws_private import MexcPrivateSpotWebsocket
    
    # Register MEXC WebSocket implementations with correct enum values
    register_ws_public(ExchangeEnum.MEXC, MexcPublicSpotWebsocket)
    register_ws_private(ExchangeEnum.MEXC, MexcPrivateSpotWebsocket)
    
    print(f"✅ Registered MEXC WebSocket implementations: {ExchangeEnum.MEXC.value}")


# Auto-register when this module is imported (delayed execution)
try:
    register_mexc_websocket_implementations()
except ImportError:
    # If factories are not yet initialized, registration will be retried later
    pass