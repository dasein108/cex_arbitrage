"""
Spot trading REST interface exports.
"""

from .base_rest_spot_public import PublicExchangeSpotRestInterface
from .base_rest_spot_private import PrivateExchangeSpotRestInterface

__all__ = [
    "PublicExchangeSpotRestInterface",
    "PrivateExchangeSpotRestInterface",
]