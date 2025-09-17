# This module provides MEXC REST API implementations
# Strategies are auto-registered when imported from the strategies submodule
from .rest_private import MexcPrivateSpotRest
from .rest_public import MexcPublicSpotRest

__all__ = [
    "MexcPublicSpotRest", 
    "MexcPrivateSpotRest"
]