# This module provides MEXC REST API implementations
# Strategies are auto-registered when imported from the strategies submodule
from .mexc_rest_private import MexcPrivateSpotRest
from .mexc_rest_public import MexcPublicSpotRest

__all__ = [
    "MexcPublicSpotRest", 
    "MexcPrivateSpotRest"
]