from abc import ABC, abstractmethod
from typing import Dict, List
from structs.exchange import Symbol, ExchangeName, OrderBook, AssetBalance


class BaseExchangeInterface(ABC):
    """Base interface containing common methods for both public and private exchange operations"""

    @property
    @abstractmethod
    def orderbook(self) -> OrderBook:
        """Abstract property to get the current orderbook"""
        pass

    @property
    @abstractmethod
    def balances(self) -> Dict[Symbol, AssetBalance]:
        """Abstract property to get the current account balances"""
        pass

    @property
    @abstractmethod
    def active_symbols(self) -> List[Symbol]:
        """Abstract property to get the current account balances"""
        pass


    @abstractmethod
    async def init(self, symbols: List[Symbol] = None) -> None:
        """Initialize exchange with symbols"""
        pass

    @abstractmethod
    async def add_symbol(self, symbol: Symbol) -> None:
        """Start symbol data streaming"""
        pass

    @abstractmethod
    async def remove_symbol(self, symbol: Symbol) -> None:
        """Stop symbol data streaming"""
        pass