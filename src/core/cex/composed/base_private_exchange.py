from abc import abstractmethod
from typing import Dict, List
from structs.exchange import (Symbol, SymbolsInfo,
                              AssetBalance, Order, OrderBook)
from structs.config import ExchangeConfig
from core.cex.composed.base_exchange import BaseExchangeInterface


class BasePrivateExchangeInterface(BaseExchangeInterface):
    @property
    @abstractmethod
    def balances(self) -> Dict[Symbol, AssetBalance]:
        """Abstract property to get the current account balances"""
        pass

    @property
    @abstractmethod
    def open_orders(self) -> Dict[Symbol, List[Order]]:
        """Abstract property to get the current account balances"""
        pass

    @property
    @abstractmethod
    def orderbooks(self) -> Dict[Symbol, OrderBook]:
        """Abstract property to get the current account balances"""
        pass


    def __init__(self, config: ExchangeConfig):
        super().__init__(config)
        self._balances: Dict[Symbol, AssetBalance] = {}
        self._open_orders: Dict[Symbol, List[Order]] = {}
        self._symbols_info: SymbolsInfo = {}

    async def initialize(self, symbols_info: SymbolsInfo) -> None:
        """Initialize exchange with symbols"""
        self._symbols_info = symbols_info

    async def place_limit_order(self, symbol: Symbol, side: str, quantity: float, price: float, **kwargs) -> Order:
        """Place a limit order"""
        pass

    async def place_market_order(self, symbol: Symbol, side: str, quantity: float, **kwargs) -> Order:
        """Place a market order"""
        pass

    async def cancel_order(self, symbol: Symbol, order_id: str) -> bool:
        """Cancel an order"""
        pass

