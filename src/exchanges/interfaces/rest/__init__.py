"""
CEX REST interface exports.

This module provides access to all REST interfaces for cryptocurrency exchanges.
Includes spot trading, futures trading, and common composite interfaces.
"""

# Common composite interfaces
from .rest_base import BaseRestInterface
from .trading_interface import PrivateTradingInterface
from .withdrawal_interface import WithdrawalInterface

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
    "PrivateTradingInterface",
    "WithdrawalInterface",
    
    # Spot trading
    "PublicSpotRest",
    "PrivateSpotRest",
    
    # Futures trading
    "PublicFuturesRest",
    "PrivateFuturesRest",
]