"""
MEXC REST Factory Registration

Separate module to handle factory registration and avoid circular imports.
Uses delayed import pattern to prevent circular dependencies during module initialization.
"""

from infrastructure.data_structures.common import ExchangeEnum


def register_mexc_rest_implementations():
    """
    Register MEXC REST implementations with factories.
    
    Uses delayed import pattern to avoid circular dependencies.
    This function should be called after the factory modules are fully initialized.
    """
    # Delayed imports to avoid circular dependencies
    from infrastructure.factories.rest.public_rest_factory import PublicRestExchangeFactory
    from infrastructure.factories.rest.private_rest_factory import PrivateRestExchangeFactory
    from .mexc_rest_public import MexcPublicSpotRest
    from .mexc_rest_private import MexcPrivateSpotRest
    
    # Register MEXC REST implementations
    PublicRestExchangeFactory.register(ExchangeEnum.MEXC, MexcPublicSpotRest)
    PrivateRestExchangeFactory.register(ExchangeEnum.MEXC, MexcPrivateSpotRest)


# Auto-register when this module is imported (delayed execution)
try:
    register_mexc_rest_implementations()
except ImportError:
    # If factories are not yet initialized, registration will be retried later
    pass