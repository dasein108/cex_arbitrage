from typing import List, Dict

from exchanges.interface.base_exchange import BaseExchangeInterface
from structs import OrderBook, Symbol, AssetBalance


class MexcExchange(BaseExchangeInterface):
    @property
    def balances(self) -> Dict[Symbol, AssetBalance]:
        pass

    @property
    def active_symbols(self) -> List[Symbol]:
        pass

    @property
    def orderbook(self) -> OrderBook:
        pass

    def __init__(self, api_key: str = None, secret_key: str = None):
        super().__init__('MEXC', api_key, secret_key)

    async def init(self, symbols: List[Symbol] = None) -> None:
        pass

    async def add_symbol(self, symbol: Symbol) -> None:
        pass

    async def remove_symbol(self, symbol: Symbol) -> None:
        pass


