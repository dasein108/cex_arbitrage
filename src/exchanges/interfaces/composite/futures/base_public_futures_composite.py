"""
Public futures exchange interface for futures market data operations.

This interface extends the composite public interface with futures-specific
functionality like funding rates, open interest, and futures-specific
orderbook management.
"""

from abc import abstractmethod
from typing import Dict, List, Optional, Any
from decimal import Decimal

from exchanges.structs import ExchangeType
from exchanges.structs.common import Symbol
from exchanges.interfaces.composite.base_public_composite import BasePublicComposite
from exchanges.interfaces import PublicFuturesRest
from exchanges.interfaces.ws.futures.ws_public_futures import PublicFuturesWebsocket
from infrastructure.logging import HFTLoggerInterface
from infrastructure.networking.websocket.handlers import PublicWebsocketHandlers


class CompositePublicFuturesExchange(BasePublicComposite[PublicFuturesRest, PublicFuturesWebsocket]):
    """
    Public futures exchange interface with futures-specific market data operations.
    
    This class extends BasePublicComposite with futures-specific functionality:
    - Funding rate tracking and history
    - Open interest monitoring
    - Mark price and index price data
    - Futures-specific symbol information
    
    Maintains separated domain architecture where this interface handles ONLY
    public futures market data operations without any trading capabilities.
    
    ## Implementation Requirements
    
    Concrete futures exchanges must implement:
    1. `_create_public_rest()`: Factory for PublicFuturesRest client
    2. `_create_public_websocket()`: Factory for PublicFuturesWebsocket client
    3. All futures-specific abstract methods for funding rates, open interest, etc.
    """

    def __init__(self, config, logger: Optional[HFTLoggerInterface] = None,
                 handlers: Optional[PublicWebsocketHandlers] = None):
        """
        Initialize public futures exchange interface.
        
        Args:
            config: Exchange configuration
            logger: Optional injected HFT logger (auto-created if not provided)
            handlers: Optional PublicWebsocketHandlers for custom event handling
        """
        super().__init__(config, ExchangeType.FUTURES, logger=logger, handlers=handlers)

        # Futures-specific data (using generic Dict structures for now)
        self._funding_rates: Dict[Symbol, Dict] = {}

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
        # Initialize composite public functionality
        await super().initialize(symbols)

        if symbols:
            try:
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
        # Refresh composite market data
        await super()._refresh_exchange_data()

        if self.active_symbols:
            active_symbols_list = list(self.active_symbols)


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

    def get_futures_stats(self) -> Dict[str, Any]:
        """
        Get futures-specific statistics for monitoring.
        
        Returns:
            Dictionary with futures market data statistics
        """
        base_stats = self.get_orderbook_stats()
        
        futures_stats = {
            'tracked_funding_rates': len(self._funding_rates),
        }
        
        return {**base_stats, **futures_stats}