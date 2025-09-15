from abc import abstractmethod
from datetime import datetime
from typing import Dict, List, Optional, Callable
from core.cex.rest.common.base_rest import BaseExchangeRestInterface
from structs.exchange import (
    Symbol,
    SymbolInfo,
    OrderBook,
    Trade,
    Kline,
    KlineInterval
)

from structs.config import ExchangeConfig
from core.transport.rest.rest_client import RestConfig

class PublicExchangeSpotRestInterface(BaseExchangeRestInterface):
    """Abstract cex for public exchange operations (market data)"""

    def __init__(self, config: ExchangeConfig, rest_config: RestConfig,
                 custom_exception_handler: Callable = None):
        super().__init__(f'{config.name}_public', config, rest_config, custom_exception_handler)

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

