from abc import ABC

from exchanges.interfaces.rest import PrivateTradingInterface
from exchanges.interfaces.rest.interfaces import PrivateFuturesInterface, WithdrawalInterface, MarketDataInterface
from exchanges.interfaces.rest import BaseRestInterface


class PrivateSpotRest(PrivateTradingInterface, WithdrawalInterface, ABC):
    """
    Spot private REST interface - Trading + Withdrawal capabilities.
    """
    pass


class PublicSpotRest(BaseRestInterface, MarketDataInterface, ABC):
    """Abstract interface for public exchange operations (market data)"""
    pass


class PublicFuturesRest(BaseRestInterface, MarketDataInterface, ABC):
    """Abstract interface for public futures REST operations."""
    pass


class PrivateFuturesRest(PrivateTradingInterface, PrivateFuturesInterface, ABC):
    """Abstract interface for private futures REST operations."""
    pass
