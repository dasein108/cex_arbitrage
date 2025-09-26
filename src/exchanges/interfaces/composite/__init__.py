"""Base interface definitions for CEX exchanges."""

from .base_composite import BaseCompositeExchange
from exchanges.interfaces.composite.spot.base_public_spot_composite import CompositePublicExchange
from exchanges.interfaces.composite.spot.base_private_spot_composite import CompositePrivateExchange
from exchanges.interfaces.composite.futures.base_private_futures_composite import CompositePrivateFuturesExchange
from exchanges.interfaces.composite.futures.base_public_futures_composite import CompositePublicFuturesExchange

__all__ = [
    'BaseCompositeExchange',
    'CompositePublicExchange',
    'CompositePrivateExchange',
    'CompositePrivateFuturesExchange',
    'CompositePublicFuturesExchange'
]