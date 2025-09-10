from abc import ABC, abstractmethod
from typing import Dict, List
from structs.exchange import Symbol, ExchangeName


class BaseExchangeInterface(ABC):
    exchange = ExchangeName("abstract")

    """Base interface containing common methods for both public and private exchange operations"""
    @abstractmethod
    async def init(self, symbols: List[Symbol]) -> None:
        """Initialize exchange with symbols"""
        pass

    @abstractmethod
    async def start_symbol(self, symbol: Symbol) -> None:
        """Start symbol data streaming"""
        pass

    @abstractmethod
    async def stop_symbol(self, symbol: Symbol) -> None:
        """Stop symbol data streaming"""
        pass
    
    @abstractmethod
    def get_websocket_health(self) -> Dict:
        """Get WebSocket connection health status"""
        pass