"""Public futures REST interface."""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict
from exchanges.structs.common import Symbol, OrderBook, Ticker, SymbolsInfo
from exchanges.interfaces.rest import PublicSpotRest


class PublicFuturesRest(PublicSpotRest):
    """Abstract interface for public futures REST operations."""
    
    # @abstractmethod
    # async def get_funding_rate(self, symbol: Symbol) -> Dict:
    #     """Get current funding rate."""
    #     pass
    #
    # @abstractmethod
    # async def get_mark_price(self, symbol: Symbol) -> float:
    #     """Get current mark price."""
    #     pass