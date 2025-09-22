# This module provides MEXC REST API implementations
# Strategies are auto-registered when imported from the strategies submodule
from .mexc_rest_private import MexcPrivateSpotRest
from .mexc_rest_public import MexcPublicSpotRest

# Register REST implementations with factories (auto-registration pattern)
from core.factories.rest.public_rest_factory import PublicRestExchangeFactory
from core.factories.rest.private_rest_factory import PrivateRestExchangeFactory
from structs.common import ExchangeEnum

PublicRestExchangeFactory.register(ExchangeEnum.MEXC, MexcPublicSpotRest)
PrivateRestExchangeFactory.register(ExchangeEnum.MEXC, MexcPrivateSpotRest)

__all__ = [
    "MexcPublicSpotRest", 
    "MexcPrivateSpotRest"
]