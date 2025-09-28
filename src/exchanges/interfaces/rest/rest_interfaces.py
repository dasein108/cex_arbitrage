from abc import ABC
from typing import Optional

from config.structs import ExchangeConfig
from exchanges.interfaces.rest.rest_base import BaseRestInterface
from exchanges.interfaces.rest.interfaces.trading_interface import PrivateTradingInterface
from exchanges.interfaces.rest.interfaces.withdrawal_interface import WithdrawalInterface
from exchanges.interfaces.rest.interfaces import MarketDataInterface, PrivateFuturesInterface
from infrastructure.logging import HFTLoggerInterface


class PrivateSpotRest(PrivateTradingInterface, WithdrawalInterface, ABC):
    """
    Spot private REST interface - Trading + Withdrawal capabilities.
    """
    def __init__(self, config: ExchangeConfig, logger: Optional[HFTLoggerInterface] = None, **kwargs):
        """Initialize public interface with transport manager."""
        super().__init__(
            config=config,
            is_private=True,  # Public API operations
            logger=logger  # Pass logger to parent for specialized public.spot logging
        )


class PublicSpotRest(BaseRestInterface, MarketDataInterface, ABC):
    """Abstract interface for public exchange operations (market data)"""

    def __init__(self, config: ExchangeConfig, logger: Optional[HFTLoggerInterface] = None, **kwargs):
        """Initialize public interface with transport manager."""
        super().__init__(
            config=config,
            is_private=False,  # Public API operations
            logger=logger  # Pass logger to parent for specialized public.spot logging
        )


class PrivateFuturesRest(PrivateTradingInterface, PrivateFuturesInterface, ABC):
    """Abstract interface for private futures REST operations."""
    pass


class PublicFuturesRest(BaseRestInterface, MarketDataInterface, ABC):
    """Abstract interface for public futures REST operations."""
    pass
