"""
Public futures exchange interface for futures market data operations.

This interface extends the composite public interface with futures-specific
functionality like funding rates, open interest, and futures-specific
orderbook management.
"""

from abc import abstractmethod
from typing import Dict, List, Optional, Any
from decimal import Decimal

from exchanges.structs.common import Symbol
from exchanges.interfaces.composite.base_public_composite import BasePublicComposite
from infrastructure.logging import HFTLoggerInterface
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType


class CompositePublicFuturesExchange(BasePublicComposite):
    """
    Base interface for public futures exchange operations.
    

    This interface does not require authentication and focuses on
    public futures market data.
    """

    def __init__(self, config, rest_client=None, websocket_client=None, logger: Optional[HFTLoggerInterface] = None):
        """
        Initialize public futures exchange interface.

        Args:
            config: Exchange configuration
            rest_client: Injected REST client for dependency injection
            websocket_client: Injected WebSocket client for dependency injection
            logger: Optional injected HFT logger (auto-created if not provided)
            handlers: Optional WebSocket handlers for custom event handling
        """
        super().__init__(config, rest_client=rest_client, websocket_client=websocket_client, logger=logger)

        # Override tag to indicate futures operations
        self._tag = f'{config.name}_public_futures'


    async def initialize(self, symbols: List[Symbol] = None, channels: List[PublicWebsocketChannelType]=None) -> None:
        """
        Initialize futures exchange with symbols and futures-specific data.
        
        Args:
            symbols: Optional list of symbols to track
            channels: Optional list of WebSocket channels to subscribe to
        """
        # Initialize composite public functionality
        await super().initialize(symbols, channels)

        if symbols:
            try:
                # Load futures-specific data

                self.logger.info(f"{self._tag} futures data initialized for {len(symbols)} symbols")

            except Exception as e:
                self.logger.error(f"Failed to initialize futures data for {self._tag}: {e}")
                raise

    # Enhanced data refresh for reconnections

    async def refresh_exchange_data(self) -> None:
        """
        Refresh all exchange data after reconnection.
        
        Refreshes both standard market data and futures-specific data.
        """
        # Refresh composite market data
        await super().refresh_exchange_data()

        if self.active_symbols:
            active_symbols_list = list(self.active_symbols)
            try:
                pass
            except Exception as e:
                self.logger.error(f"Failed to refresh futures data for {self._tag}: {e}")
                raise
    
    async def is_tradable(self, symbol: Symbol) -> bool:
        """
        Check if a symbol is tradable on this futures exchange.
        
        Args:
            symbol: Symbol to check
            
        Returns:
            True if symbol is tradable for futures, False otherwise
        """
        if not self._symbols_info:
            await self.load_symbols_info()
        
        if symbol not in self._symbols_info:
            return False
            
        symbol_info = self._symbols_info[symbol]
        return not symbol_info.inactive

