"""
Public futures exchange interface for futures market data operations.

This interface extends the base public interface with futures-specific
functionality like funding rates, open interest, and futures-specific
orderbook management.
"""

from abc import abstractmethod
from typing import Dict, List
from decimal import Decimal

from infrastructure.data_structures.common import Symbol
from .base_public_exchange import BasePublicExchangeInterface


class BasePublicFuturesExchangeInterface(BasePublicExchangeInterface):
    """
    Base interface for public futures exchange operations.
    
    Extends public exchange functionality with futures-specific features:
    - Funding rate tracking
    - Open interest monitoring
    - Futures-specific symbol information
    - Mark price and index price data
    
    This interface does not require authentication and focuses on
    public futures market data.
    """

    def __init__(self, config):
        """
        Initialize public futures exchange interface.
        
        Args:
            config: Exchange configuration
        """
        super().__init__(config)
        
        # Override tag to indicate futures operations
        self._tag = f'{config.name}_public_futures'
        
        # Futures-specific data (using generic Dict structures for now)
        self._funding_rates: Dict[Symbol, Dict] = {}
        self._open_interest: Dict[Symbol, Dict] = {}
        self._mark_prices: Dict[Symbol, Decimal] = {}
        self._index_prices: Dict[Symbol, Decimal] = {}

    # Abstract properties for futures data

    @property
    @abstractmethod
    def funding_rates(self) -> Dict[Symbol, Dict]:
        """
        Get current funding rates for all tracked symbols.
        
        Returns:
            Dictionary mapping symbols to funding rate information
        """
        pass

    @property
    @abstractmethod
    def open_interest(self) -> Dict[Symbol, Dict]:
        """
        Get current open interest for all tracked symbols.
        
        Returns:
            Dictionary mapping symbols to open interest information
        """
        pass

    @property
    @abstractmethod
    def mark_prices(self) -> Dict[Symbol, Decimal]:
        """
        Get current mark prices for all tracked symbols.
        
        Returns:
            Dictionary mapping symbols to mark prices
        """
        pass

    @property
    @abstractmethod
    def index_prices(self) -> Dict[Symbol, Decimal]:
        """
        Get current index prices for all tracked symbols.
        
        Returns:
            Dictionary mapping symbols to index prices
        """
        pass

    # Abstract futures data loading methods

    @abstractmethod
    async def _load_funding_rates(self, symbols: List[Symbol]) -> None:
        """
        Load funding rates for symbols from REST API.
        
        Args:
            symbols: List of symbols to load funding rates for
        """
        pass

    @abstractmethod
    async def _load_open_interest(self, symbols: List[Symbol]) -> None:
        """
        Load open interest data for symbols from REST API.
        
        Args:
            symbols: List of symbols to load open interest for
        """
        pass

    @abstractmethod
    async def _load_mark_prices(self, symbols: List[Symbol]) -> None:
        """
        Load mark prices for symbols from REST API.
        
        Args:
            symbols: List of symbols to load mark prices for
        """
        pass

    @abstractmethod
    async def _load_index_prices(self, symbols: List[Symbol]) -> None:
        """
        Load index prices for symbols from REST API.
        
        Args:
            symbols: List of symbols to load index prices for
        """
        pass

    @abstractmethod
    async def get_funding_rate_history(
        self, 
        symbol: Symbol,
        limit: int = 100
    ) -> List[Dict]:
        """
        Get historical funding rates for a symbol.
        
        Args:
            symbol: Symbol to get funding rate history for
            limit: Maximum number of records to return
            
        Returns:
            List of historical funding rates
        """
        pass

    # Enhanced initialization for futures

    async def initialize(self, symbols: List[Symbol] = None) -> None:
        """
        Initialize futures exchange with symbols and futures-specific data.
        
        Args:
            symbols: Optional list of symbols to track
        """
        # Initialize base public functionality
        await super().initialize(symbols)

        if symbols:
            try:
                # Load futures-specific data
                await self._load_funding_rates(symbols)
                await self._load_open_interest(symbols)
                await self._load_mark_prices(symbols)
                await self._load_index_prices(symbols)

                self.logger.info(f"{self._tag} futures data initialized for {len(symbols)} symbols")

            except Exception as e:
                self.logger.error(f"Failed to initialize futures data for {self._tag}: {e}")
                raise

    # Enhanced data refresh for reconnections

    async def _refresh_exchange_data(self) -> None:
        """
        Refresh all exchange data after reconnection.
        
        Refreshes both standard market data and futures-specific data.
        """
        # Refresh base market data
        await super()._refresh_exchange_data()

        if self._active_symbols:
            try:
                # Refresh futures-specific data
                await self._load_funding_rates(self._active_symbols)
                await self._load_open_interest(self._active_symbols)
                await self._load_mark_prices(self._active_symbols)
                await self._load_index_prices(self._active_symbols)

                self.logger.info(f"{self._tag} futures data refreshed")

            except Exception as e:
                self.logger.error(f"Failed to refresh futures data for {self._tag}: {e}")
                raise

    # Futures data update methods

    def _update_funding_rate(self, symbol: Symbol, funding_rate: Dict) -> None:
        """
        Update internal funding rate state.
        
        Args:
            symbol: Symbol that was updated
            funding_rate: New funding rate information
        """
        self._funding_rates[symbol] = funding_rate
        self.logger.debug(f"Updated funding rate for {symbol}: {funding_rate}")

    def _update_open_interest(self, symbol: Symbol, open_interest: Dict) -> None:
        """
        Update internal open interest state.
        
        Args:
            symbol: Symbol that was updated
            open_interest: New open interest information
        """
        self._open_interest[symbol] = open_interest
        self.logger.debug(f"Updated open interest for {symbol}: {open_interest}")

    def _update_mark_price(self, symbol: Symbol, mark_price: Decimal) -> None:
        """
        Update internal mark price state.
        
        Args:
            symbol: Symbol that was updated
            mark_price: New mark price
        """
        self._mark_prices[symbol] = mark_price
        self.logger.debug(f"Updated mark price for {symbol}: {mark_price}")

    def _update_index_price(self, symbol: Symbol, index_price: Decimal) -> None:
        """
        Update internal index price state.
        
        Args:
            symbol: Symbol that was updated
            index_price: New index price
        """
        self._index_prices[symbol] = index_price
        self.logger.debug(f"Updated index price for {symbol}: {index_price}")

    # Enhanced monitoring for futures

    def get_futures_stats(self) -> Dict[str, any]:
        """
        Get futures-specific statistics for monitoring.
        
        Returns:
            Dictionary with futures market data statistics
        """
        base_stats = self.get_orderbook_stats()
        
        futures_stats = {
            'tracked_funding_rates': len(self._funding_rates),
            'tracked_open_interest': len(self._open_interest),
            'tracked_mark_prices': len(self._mark_prices),
            'tracked_index_prices': len(self._index_prices),
        }
        
        return {**base_stats, **futures_stats}