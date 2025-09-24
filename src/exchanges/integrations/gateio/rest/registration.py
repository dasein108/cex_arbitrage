"""
Gate.io REST Factory Registration

Separate module to handle factory registration and avoid circular imports.
Uses delayed import pattern to prevent circular dependencies during module initialization.
"""

from exchanges.structs import ExchangeEnum

def register_gateio_rest_implementations():
    """
    Register Gate.io REST implementations with factories.
    
    Uses delayed import pattern to avoid circular dependencies.
    This function should be called after the factory modules are fully initialized.
    """
    # Delayed imports to avoid circular dependencies
    from infrastructure.transport_factory import register_rest_public, register_rest_private
    from .gateio_rest_public import GateioPublicSpotRest
    from .gateio_rest_private import GateioPrivateSpotRest
    from .gateio_futures_public import GateioPublicFuturesRest
    from .gateio_futures_private import GateioPrivateFuturesRest
    
    # Register Gate.io REST implementations
    register_rest_public(ExchangeEnum.GATEIO, GateioPublicSpotRest)
    register_rest_private(ExchangeEnum.GATEIO, GateioPrivateSpotRest)
    register_rest_public(ExchangeEnum.GATEIO_FUTURES, GateioPublicFuturesRest)
    register_rest_private(ExchangeEnum.GATEIO_FUTURES, GateioPrivateFuturesRest)


# Auto-register when this module is imported (delayed execution)
try:
    register_gateio_rest_implementations()
except ImportError:
    # If factories are not yet initialized, registration will be retried later
    pass