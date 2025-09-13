from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from exchanges.interface.structs import Symbol, ExchangeName, OrderBook, AssetBalance, Order, Position, ExchangeStatus


class BaseExchangeInterface(ABC):

    @property
    @abstractmethod
    def status(self) -> ExchangeStatus:
        """Status of exchange"""
        pass

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

    @property
    @abstractmethod
    def open_orders(self) -> Dict[Symbol, List[Order]]:
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


    async def positions(self) -> Dict[Symbol, Position]:
        """Get current open positions (for futures)"""
        return {}

    def __init__(self,exchange: str, api_key: Optional[str], secret_key: Optional[str]):
        self.exchange = ExchangeName(exchange)
        self.api_key = api_key
        self.secret_key = secret_key
        self.has_private = bool(api_key and secret_key)

    def place_limit_order(self, symbol: Symbol, side: str, quantity: float, price: float, is_futures: bool = False,
                          **kwargs) -> Order:
        """Place a limit order"""
        pass

    def place_market_order(self, symbol: Symbol, side: str, quantity: float,  is_futures: bool = False,
                           **kwargs) -> Order:
        """Place a market order"""
        pass

    def cancel_order(self, symbol: Symbol, order_id: str, is_futures: bool = False) -> bool:
        """Cancel an order"""
        pass