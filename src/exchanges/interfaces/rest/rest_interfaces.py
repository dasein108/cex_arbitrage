from abc import ABC

from exchanges.interfaces.rest import PrivateTradingInterface
from exchanges.interfaces.rest.interfaces import PrivateFuturesInterface, WithdrawalInterface, MarketDataInterface
from infrastructure.networking.http.rest_base_new import BaseRestClient


class PrivateSpotRestInterface(PrivateTradingInterface, WithdrawalInterface, ABC):
    """
    Spot private REST interface - Trading + Withdrawal capabilities.
    Uses the new BaseRestClient architecture.
    """
    pass


class PublicSpotRestInterface(MarketDataInterface, ABC):
    """
    Abstract interface for public exchange operations (market data).
    Uses the new BaseRestClient architecture instead of legacy BaseRestInterface.
    """
    pass


class PublicFuturesRestInterface(MarketDataInterface, ABC):
    """
    Abstract interface for public futures REST operations.
    Uses the new BaseRestClient architecture instead of legacy BaseRestInterface.
    """
    pass


class PrivateFuturesRestInterface(PrivateTradingInterface, PrivateFuturesInterface, ABC):
    """
    Abstract interface for private futures REST operations.
    Uses the new BaseRestClient architecture.
    """
    pass
