from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from src.structs.exchange import (
    Symbol,
    SymbolInfo,
    OrderBook,
    Trade,
    ExchangeName
)


class PublicExchangeInterface(ABC):
    """Abstract interface for public exchange operations (market data)"""
    
    def __init__(self, exchange: ExchangeName, base_url: str):
        self.exchange = exchange
        self.base_url = base_url
        
    @property
    @abstractmethod
    def exchange_name(self) -> ExchangeName:
        """Return the exchange name identifier"""
        pass

    @staticmethod
    async def symbol_to_pair(symbol: Symbol) -> str:
        """Convert Symbol to exchange-specific trading pair string"""
        pass

    @staticmethod
    async def pair_to_symbol(symbol: str) -> Symbol:
        """Convert exchange-specific trading pair string to Symbol"""
        pass
    
    @abstractmethod
    async def get_exchange_info(self) -> Dict[Symbol, SymbolInfo]:
        """Get exchange trading rules and symbol information"""
        pass
    
    @abstractmethod
    async def get_orderbook(self, symbol: Symbol, limit: int = 100) -> OrderBook:
        """Get order book for a symbol"""
        pass
    

    @abstractmethod
    async def get_recent_trades(self, symbol: Symbol, limit: int = 500) -> List[Trade]:
        """Get recent trades for a symbol"""
        pass
    

    @abstractmethod
    async def get_server_time(self) -> int:
        """Get server timestamp"""
        pass
    
    @abstractmethod
    async def ping(self) -> bool:
        """Test connectivity to the exchange"""
        pass