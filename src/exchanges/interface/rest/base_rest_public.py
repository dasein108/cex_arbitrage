import logging
from abc import abstractmethod
from datetime import datetime
from typing import Dict, List, Optional
from .base_rest import BaseExchangeInterface
from exchanges.interface.structs import (
    Symbol,
    SymbolInfo,
    OrderBook,
    Trade,
    Kline,
    ExchangeName,
    KlineInterval
)

class PublicExchangeInterface(BaseExchangeInterface):
    """Abstract interface for public exchange operations (market data)"""


    def __init__(self, exchange: ExchangeName, base_url: str):
        super().__init__(exchange, base_url)
        self.logger = logging.getLogger(f"public_exchange_{exchange}")
        
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
    async def get_klines_batch(self, symbol: Symbol, timeframe: KlineInterval,
                         date_from: Optional[datetime], date_to: Optional[datetime]) -> List[Kline]:
        """Get recent trades for a symbol"""
        pass


    @abstractmethod
    async def get_klines(self, symbol: Symbol, timeframe: KlineInterval,
                         date_from: Optional[datetime], date_to: Optional[datetime]) -> List[Kline]:
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

