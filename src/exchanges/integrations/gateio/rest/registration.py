"""
Gate.io REST Factory Registration

Separate module to handle factory registration and avoid circular imports.
Uses delayed import pattern to prevent circular dependencies during module initialization.
"""

from infrastructure.data_structures.common import ExchangeEnum


def register_gateio_rest_implementations():
    """
    Register Gate.io REST implementations with factories.
    
    Uses delayed import pattern to avoid circular dependencies.
    This function should be called after the factory modules are fully initialized.
    """
    # Delayed imports to avoid circular dependencies
    from infrastructure.factories.rest.public_rest_factory import PublicRestExchangeFactory
    from infrastructure.factories.rest.private_rest_factory import PrivateRestExchangeFactory
    from .gateio_rest_public import GateioPublicSpotRest
    from .gateio_rest_private import GateioPrivateSpotRest
    from .gateio_futures_public import GateioPublicFuturesRest
    from .gateio_futures_private import GateioPrivateFuturesRest
    
    # Register Gate.io REST implementations
    PublicRestExchangeFactory.register(ExchangeEnum.GATEIO, GateioPublicSpotRest)
    PrivateRestExchangeFactory.register(ExchangeEnum.GATEIO, GateioPrivateSpotRest)
    PublicRestExchangeFactory.register(ExchangeEnum.GATEIO_FUTURES, GateioPublicFuturesRest)
    PrivateRestExchangeFactory.register(ExchangeEnum.GATEIO_FUTURES, GateioPrivateFuturesRest)


# Auto-register when this module is imported (delayed execution)
try:
    register_gateio_rest_implementations()
except ImportError:
    # If factories are not yet initialized, registration will be retried later
    pass