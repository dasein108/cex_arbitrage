"""
CEX REST interface exports.

This module provides access to all REST interfaces for cryptocurrency cex.
Includes spot trading, futures trading, and common base interfaces.
"""

# Common base interfaces
from .base_rest import BaseExchangeRestInterface

# Spot trading interfaces
from .spot import (
    PublicExchangeSpotRestInterface,
    PrivateExchangeSpotRestInterface,
)

# Futures trading interfaces
from .futures import (
    PublicExchangeFuturesRestInterface,
    PrivateExchangeFuturesRestInterface,
)

__all__ = [
    # Common
    "BaseExchangeRestInterface",
    
    # Spot trading
    "PublicExchangeSpotRestInterface",
    "PrivateExchangeSpotRestInterface",
    
    # Futures trading
    "PublicExchangeFuturesRestInterface",
    "PrivateExchangeFuturesRestInterface",
]