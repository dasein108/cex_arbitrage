from abc import abstractmethod
from datetime import datetime
from typing import Dict, List, Optional
from exchanges.interfaces.rest.base_rest import BaseExchangeRestInterface
from exchanges.services import BaseExchangeMapper
from infrastructure.data_structures.common import (
    Symbol,
    SymbolInfo,
    OrderBook,
    Trade,
    Kline,
    KlineInterval,
    Ticker
)

from infrastructure.config.structs import ExchangeConfig

# HFT Logger Integration
from infrastructure.logging import HFTLoggerInterface


class PublicExchangeSpotRest(BaseExchangeRestInterface):
    """Abstract interface for public exchange operations (market data)"""
    
    def __init__(self, config: ExchangeConfig, mapper: BaseExchangeMapper, logger: Optional[HFTLoggerInterface] = None):
        """Initialize public interface with transport manager and mapper."""
        super().__init__(
            config=config,
            mapper=mapper,
            is_private=False,  # Public API operations
            logger=logger  # Pass logger to parent for specialized public.spot logging
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

    @abstractmethod
    async def get_historical_trades(self, symbol: Symbol, limit: int = 500,
                                    timestamp_from: Optional[int] = None,
                                    timestamp_to: Optional[int] = None) -> List[Trade]:
        """Get historical trades for a symbol
        
        Args:
            symbol: Symbol to get trades for
            limit: Number of trades to retrieve (exchange-specific max)
            timestamp_from: Start timestamp in milliseconds (optional)
            timestamp_to: End timestamp in milliseconds (optional)
            
        Returns:
            List of Trade objects sorted by timestamp
            
        Raises:
            ExchangeAPIError: If unable to fetch trade data
        """
        pass
    
    @abstractmethod
    async def get_ticker_info(self, symbol: Optional[Symbol] = None) -> Dict[Symbol, Ticker]:
        """Get 24hr ticker price change statistics
        
        Args:
            symbol: Specific symbol to get ticker for (optional)
                   If None, returns tickers for all symbols
            
        Returns:
            Dictionary mapping Symbol to Ticker with 24hr statistics
            
        Raises:
            ExchangeAPIError: If unable to fetch ticker data
        """
        pass

