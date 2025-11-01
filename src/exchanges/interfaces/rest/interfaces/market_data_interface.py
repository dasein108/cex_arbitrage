from abc import abstractmethod, ABC
from datetime import datetime
from typing import Dict, List, Optional, Union
from exchanges.structs.common import (
    Symbol,
    SymbolInfo,
    OrderBook,
    Trade,
    Kline,
    AssetName,
    Ticker, FuturesTicker
)
from exchanges.structs.enums import KlineInterval

from config.structs import ExchangeConfig

# HFT Logger Integration
from infrastructure.logging import HFTLoggerInterface

class MarketDataInterface(ABC):
    @abstractmethod
    async def get_symbols_info(self) -> Dict[Symbol, SymbolInfo]:
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
    async def get_ticker_info(self, symbol: Optional[Symbol] = None,
                              quote_asset: Optional[AssetName]= None) -> Dict[Symbol, Union[Ticker, FuturesTicker]]:
        """Get 24hr ticker price change statistics

        Args:
            symbol: Specific symbol to get ticker for (optional)
                   If None, returns tickers for all symbols
            quote_asset: Asset to filter

        Returns:
            Dictionary mapping Symbol to Ticker with 24hr statistics

        Raises:
            ExchangeAPIError: If unable to fetch ticker data
        """
        pass