"""
CEX REST interface exports.

This module provides access to all REST interfaces for cryptocurrency exchanges.
Includes spot trading, futures trading, and common composite interfaces.
"""

# Common composite interfaces
from .rest_base import BaseRestInterface
from exchanges.interfaces.rest.interfaces.trading_interface import PrivateTradingInterface
from exchanges.interfaces.rest.interfaces.withdrawal_interface import WithdrawalInterface

# Spot trading interfaces
from .rest_interfaces import PrivateSpotRestInterface, PublicSpotRestInterface, PublicFuturesRestInterface, PrivateFuturesRestInterface

# Futures trading interfaces

__all__ = [
    # Common
    "BaseRestInterface",
    "PrivateTradingInterface",
    "WithdrawalInterface",
    'PublicSpotRestInterface',
    'PrivateSpotRestInterface',
    'PublicFuturesRestInterface',
    'PrivateFuturesRestInterface'
]