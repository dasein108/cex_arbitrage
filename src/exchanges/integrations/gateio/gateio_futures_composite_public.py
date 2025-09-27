"""
Gate.io futures public composite exchange implementation.

This implementation follows the composite pattern for Gate.io futures
public operations with futures-specific WebSocket and REST handling.
"""

from typing import List, Optional, Dict, Any
from exchanges.interfaces.composite.spot.base_public_spot_composite import CompositePublicExchange
from exchanges.structs.common import Symbol, SymbolsInfo
from infrastructure.logging import HFTLoggerInterface
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType
from infrastructure.networking.websocket.handlers import PublicWebsocketHandlers
from exchanges.integrations.gateio.rest.gateio_rest_futures_public import GateioPublicFuturesRest
from exchanges.integrations.gateio.ws import GateioPublicFuturesWebsocket


class GateioFuturesCompositePublicExchange(CompositePublicExchange):
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
        """Initialize Gate.io futures public composite exchange."""
        super().__init__(config, logger=logger, handlers=handlers)
        
        # Override tag for futures identification
        self._tag = f'{config.name}_futures_public'

    # Composite pattern implementation - create futures-specific components

    async def _create_public_rest(self) -> GateioPublicFuturesRest:
        """Create Gate.io futures public REST client."""
        return GateioPublicFuturesRest(self.config, self.logger)

    async def _create_public_ws_with_handlers(self, handlers: PublicWebsocketHandlers) -> Optional[GateioPublicFuturesWebsocket]:
        """Create Gate.io futures public WebSocket client."""
        return GateioPublicFuturesWebsocket(self.config, self.logger)

    # Futures-specific data access methods
    # TODO: implement later if needed
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
    #
    # async def get_open_interest(self, symbol: Symbol) -> Dict[str, Any]:
    #     """Get open interest for futures symbol."""
    #     return await self._public_rest.get_open_interest(symbol)

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