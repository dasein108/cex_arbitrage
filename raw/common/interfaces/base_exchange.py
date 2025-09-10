from abc import ABC, abstractmethod
from typing import Dict

from exchanges.common.entities import AccountBalance, Order, SymbolInfo, SymbolStr
from exchanges.common.interfaces.rest_api_interface import RestApiInterface

# Import moved to avoid circular import - will be imported locally where needed


class BaseSyncExchange(ABC):
    tag = "base"

    @property
    @abstractmethod
    def symbol_info(self) -> Dict[SymbolStr, SymbolInfo]:
        pass

    @property
    @abstractmethod
    def ob(self) -> Dict[SymbolStr, object]:  # AlgoOrderbook
        pass

    @property
    @abstractmethod
    def balance(self) -> Dict[str, AccountBalance]:
        pass

    @property
    @abstractmethod
    def rest_api(self) -> RestApiInterface:
        pass

    @property
    @abstractmethod
    def balance_free_usdt(self) -> float:
        pass

    @abstractmethod
    async def refresh_tickers(self) -> None:
        pass

    @abstractmethod
    async def force_update_tickers(self) -> None:
        pass

    @abstractmethod
    async def init(self) -> "BaseSyncExchange":
        pass

    @abstractmethod
    def get_last_price(self, symbol: SymbolStr) -> float:
        pass

    @abstractmethod
    async def start_symbol(self, symbol: SymbolStr, with_deals: bool = False) -> None:
        pass

    @abstractmethod
    async def stop_symbol(self, symbol: SymbolStr) -> None:
        pass

    @abstractmethod
    async def force_update_orderbook(self, symbol: SymbolStr) -> None:
        pass

    @abstractmethod
    async def force_update_balances(self) -> None:
        pass

    @abstractmethod
    async def stop(self) -> None:
        pass

    @abstractmethod
    async def restart(self) -> None:
        pass

    @abstractmethod
    def get_order_cache(self, order: Order) -> Order:
        pass

    @abstractmethod
    def get_change_24h(self, symbol: SymbolStr) -> Dict:
        pass

    @abstractmethod
    def get_ticker_price(self, symbol: SymbolStr) -> float:
        pass
