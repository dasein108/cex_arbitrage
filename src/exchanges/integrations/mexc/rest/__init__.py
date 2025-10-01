# This module provides MEXC REST API implementations
from .mexc_rest_spot_private import MexcPrivateSpotRestInterface
from .mexc_rest_spot_public import MexcPublicSpotRestInterface

__all__ = [
    "MexcPublicSpotRestInterface",
    "MexcPrivateSpotRestInterface"
]