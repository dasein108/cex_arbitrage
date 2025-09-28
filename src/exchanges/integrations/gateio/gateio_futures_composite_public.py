"""
Gate.io futures public composite exchange implementation.

This implementation follows the composite pattern for Gate.io futures
public operations with futures-specific WebSocket and REST handling.
"""

from typing import List, Optional, Dict, Any
from exchanges.interfaces.composite.futures.base_public_futures_composite import CompositePublicFuturesExchange
from exchanges.interfaces import PublicFuturesRest
from exchanges.interfaces.ws.futures.ws_public_futures import PublicFuturesWebsocket
from exchanges.structs.common import Symbol
from infrastructure.logging import HFTLoggerInterface
from infrastructure.networking.websocket.handlers import PublicWebsocketHandlers
from exchanges.integrations.gateio.ws import GateioPublicFuturesWebsocket
from exchanges.integrations.gateio.rest.gateio_rest_futures_public import GateioPublicFuturesRest
from infrastructure.exceptions.system import InitializationError


class GateioFuturesCompositePublicExchange(CompositePublicFuturesExchange):
    """
    Gate.io futures public composite exchange.
    
    Provides futures market data operations including:
    - Futures orderbook data
    - Futures trade data  
    - Funding rate information
    - Mark price data
    - Index price data
    
    Extends base composite with futures-specific WebSocket channels
    and REST endpoints optimized for futures trading.
    """

    def __init__(self, config, logger: Optional[HFTLoggerInterface] = None,
                 handlers: Optional[PublicWebsocketHandlers] = None):
        """Initialize Gate.io futures public composite exchange with direct client injection."""
            # Create clients directly with proper error context
        rest_client = GateioPublicFuturesRest(config, logger)
        websocket_client = GateioPublicFuturesWebsocket(config, self._get_inner_websocket_handlers(), logger)

        super().__init__(config, logger=logger, handlers=handlers,
                         rest_client=rest_client, websocket_client=websocket_client)


    # Factory methods removed - clients are now injected directly during construction

    def _get_inner_websocket_handlers(self) -> PublicWebsocketHandlers:
        handlers = super()._get_inner_websocket_handlers()
        # Add futures-specific channel handlers if needed
        return handlers

    # Futures-specific data access methods

    # async def get_funding_rate(self, symbol: Symbol) -> Dict[str, Any]:
    #     """Get current funding rate for futures symbol."""
    #     return await self._public_rest.get_funding_rate(symbol)
    #
    # async def get_funding_rate_history(self, symbol: Symbol, limit: int = 100) -> List[Dict[str, Any]]:
    #     """Get funding rate history for futures symbol."""
    #     return await self._public_rest.get_funding_rate_history(symbol, limit)
    #
    # async def get_mark_price(self, symbol: Symbol) -> Dict[str, Any]:
    #     """Get current mark price for futures symbol."""
    #     return await self._public_rest.get_mark_price(symbol)
    #
    # async def get_index_price(self, symbol: Symbol) -> Dict[str, Any]:
    #     """Get current index price for futures symbol."""
    #     return await self._public_rest.get_index_price(symbol)

    # async def get_open_interest(self, symbol: Symbol) -> Dict[str, Any]:
    #     """Get open interest for futures symbol."""
    #     return await self._public_rest.get_open_interest(symbol)
    #
    # async def get_liquidation_orders(self, symbol: Symbol, limit: int = 100) -> List[Dict[str, Any]]:
    #     """Get recent liquidation orders for futures symbol."""
    #     return await self._public_rest.get_liquidation_orders(symbol, limit)

    # Futures-specific channel support for WebSocket

    # Enhanced initialization for futures-specific data

    async def initialize(self, symbols: List[Symbol] = None) -> None:
        """Initialize futures exchange with symbols and funding rate subscriptions."""
        await super().initialize(symbols)
        
        self.logger.debug(f"{self._tag} futures public exchange initialized with {len(symbols)} symbols")

    # Futures-specific trading stats

    def get_trading_stats(self) -> Dict[str, Any]:
        """Get trading stats including futures-specific metrics."""
        base_stats = super().get_trading_stats()
        base_stats['exchange_type'] = 'futures'
        return base_stats