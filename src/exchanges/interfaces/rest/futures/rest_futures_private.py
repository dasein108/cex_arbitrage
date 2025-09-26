"""Private futures REST interface."""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict
from decimal import Decimal
from exchanges.structs.common import Symbol, Order, Position, AssetBalance, WithdrawalRequest, WithdrawalResponse
from exchanges.structs.types import AssetName, OrderId
from exchanges.structs import Side, OrderType
from exchanges.interfaces.rest import PrivateSpotRest


class PrivateFuturesRest(PrivateSpotRest):
    """Abstract interface for private futures REST operations."""
    
    @abstractmethod
    async def get_positions(self, symbol: Optional[Symbol] = None) -> List[Position]:
        """Get futures positions."""
        pass
    #
    # @abstractmethod
    # async def modify_leverage(self, symbol: Symbol, leverage: float) -> bool:
    #     """Modify leverage for a symbol."""
    #     pass
    #
    # @abstractmethod
    # async def get_funding_rate(self, symbol: Symbol) -> Dict:
    #     """Get funding rate information."""
    #     pass
    #
    # @abstractmethod
    # async def get_mark_price(self, symbol: Symbol) -> float:
    #     """Get mark price."""
    #     pass
