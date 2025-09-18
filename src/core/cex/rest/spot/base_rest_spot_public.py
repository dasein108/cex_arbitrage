from abc import abstractmethod
from datetime import datetime
from typing import Dict, List, Optional, Callable
from core.cex.rest.base_rest import BaseExchangeRestInterface
from structs.common import (
    Symbol,
    SymbolInfo,
    OrderBook,
    Trade,
    Kline,
    KlineInterval
)

from core.config.structs import ExchangeConfig


class PublicExchangeSpotRestInterface(BaseExchangeRestInterface):
    """Abstract interface for public exchange operations (market data)"""
    
    def __init__(self, config: ExchangeConfig):
        """Initialize public interface with transport manager."""
        super().__init__(
            config=config,
            is_private=False  # Public API operations
        )

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

