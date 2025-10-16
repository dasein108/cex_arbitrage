from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from exchanges.structs.common import (
    Symbol,
    Position, FuturesBalance,
)
from exchanges.structs.types import AssetName


class PrivateFuturesInterface(ABC):
    """
    Futures interface for futures/derivatives exchanges only.

    This interface provides futures trading operations that are only available
    for futures/derivatives exchanges, not for spot exchanges.
    """

    @abstractmethod
    async def get_positions(self, symbol: Optional[Symbol] = None) -> List[Position]:
        """Get futures positions."""
        pass

    @abstractmethod
    async def get_balances(self) -> List[FuturesBalance]:
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
