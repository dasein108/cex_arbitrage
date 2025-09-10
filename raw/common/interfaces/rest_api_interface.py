from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from exchanges.common import Interval, OrderType, Side
from exchanges.common.entities import AccountBalance, Deal, Kline, Order, SymbolInfo, SymbolStr, Ticker24


class RestApiInterface(ABC):
    si: Dict[SymbolStr, SymbolInfo] = {}

    def __init__(self, api_key, secret_key, host: str | None = None):
        self.api_key = api_key
        self.secret_key = secret_key
        self.host = host

    @abstractmethod
    async def get_balance(self) -> Dict[str, AccountBalance]:
        pass

    @abstractmethod
    async def get_order_book(self, symbol: SymbolStr) -> (List[List[float]], List[List[float]]):
        pass

    @abstractmethod
    async def get_open_orders(self, symbol: SymbolStr) -> List[Order]:
        pass

    @abstractmethod
    async def get_usdt_ticker_24(self) -> Dict[SymbolStr, Ticker24]:
        pass

    @abstractmethod
    async def fetch_order_updates(self, order: Order) -> Order:
        pass

    @abstractmethod
    async def get_all_orders(
        self, symbol: SymbolStr, limit: int = 100, end_timestamp: Optional[datetime] = None
    ) -> List[Order]:
        pass

    @abstractmethod
    async def get_last_deals(
        self, symbol: SymbolStr, limit: int = 100, timestamp: Optional[float] = None
    ) -> List[Deal]:
        pass

    @abstractmethod
    async def get_last_candles(self, symbol: SymbolStr, interval: Interval, limit: int = 100) -> List[Kline]:
        pass

    @abstractmethod
    async def load_symbol_info(self) -> Dict[str, SymbolInfo]:
        pass

    @abstractmethod
    async def get_order_info(self, o: Order) -> Order:
        pass

    @abstractmethod
    async def place_order(
        self,
        symbol: SymbolStr,
        side: Side,
        order_type: OrderType,
        price: Optional[float] = None,
        quantity: Optional[float] = None,
        quote_order_quantity: Optional[float] = None,
        with_check: bool = False,
    ) -> Order:
        pass

    @abstractmethod
    async def cancel_all_open_orders(
        self,
        symbol: SymbolStr,
        side: Optional[Side] = None,
        reporter: Optional[Any] = None,
        logger: Optional[Any] = None,
    ):
        pass

    @abstractmethod
    async def cancel_order(self, order: Order, reporter: Optional[Any] = None, logger: Optional[Any] = None) -> Order:
        pass
