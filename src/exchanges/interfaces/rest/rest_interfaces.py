from typing import Optional
from abc import ABC
from config.structs import ExchangeConfig
from exchanges.interfaces.rest.rest_base import BaseRestInterface
from exchanges.interfaces.rest.interfaces.trading_interface import PrivateTradingInterface
from exchanges.interfaces.rest.interfaces.withdrawal_interface import WithdrawalInterface
from exchanges.interfaces.rest.interfaces import MarketDataInterface, PrivateFuturesInterface
from infrastructure.logging import HFTLoggerInterface


class PrivateSpotRest(BaseRestInterface, PrivateTradingInterface, WithdrawalInterface, ABC):
    """
    Abstract interface for private exchange operations (trading, account data, withdrawals)
    """
    pass

class PublicSpotRest(BaseRestInterface, MarketDataInterface, ABC):
    """Abstract interface for public exchange operations (market data)"""
    pass

class PrivateFuturesRest(BaseRestInterface, PrivateTradingInterface, PrivateFuturesInterface, ABC):
    """Abstract interface for private futures REST operations."""
    pass

class PublicFuturesRest(BaseRestInterface, MarketDataInterface, ABC):
    """Abstract interface for public futures REST operations."""
    pass
