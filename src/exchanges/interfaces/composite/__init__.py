"""
Composite exchange interfaces.

Architecture:
- BaseCompositeExchange: Common public operations (market data)
- BasePrivateComposite: Common private operations (orders, balances, WebSocket)
- CompositePrivateExchange (spot): Adds withdrawal functionality via WithdrawalMixin
- CompositePrivateFuturesExchange: Adds futures-specific functionality (positions, leverage)
"""

from .base_composite import BaseCompositeExchange
from .base_private_composite import BasePrivateComposite
from .base_public_composite import BasePublicComposite
from exchanges.interfaces.composite.spot.base_public_spot_composite import CompositePublicSpotExchange
from exchanges.interfaces.composite.spot.base_private_spot_composite import CompositePrivateSpotExchange
from exchanges.interfaces.composite.futures.base_private_futures_composite import CompositePrivateFuturesExchange
from exchanges.interfaces.composite.futures.base_public_futures_composite import CompositePublicFuturesExchange

__all__ = [
    'BaseCompositeExchange',
    'BasePrivateComposite',
    'BasePublicComposite',
    'CompositePublicSpotExchange',
    'CompositePrivateSpotExchange',
    'CompositePrivateFuturesExchange',
    'CompositePublicFuturesExchange'
]