"""
CEX REST interface exports.

This module provides access to all REST interfaces for cryptocurrency exchanges.
Includes spot trading, futures trading, and common composite interfaces.
"""

# Common composite interfaces
from .rest_base import BaseRestInterface

# Spot trading interfaces
from .spot import (
    PublicSpotRest,
    PrivateSpotRest,
)

# Futures trading interfaces
from .futures import (
    PublicFuturesRest,
    PrivateFuturesRest,
)

__all__ = [
    # Common
    "BaseRestInterface",
    
    # Spot trading
    "PublicSpotRest",
    "PrivateSpotRest",
    
    # Futures trading
    "PublicFuturesRest",
    "PrivateFuturesRest",
]