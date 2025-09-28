"""Gate.io public exchange implementation using composite pattern."""

from typing import Optional
from exchanges.interfaces.composite.spot.base_public_spot_composite import CompositePublicSpotExchange
from exchanges.interfaces import PublicSpotRest
from exchanges.interfaces.ws.spot.ws_spot_public import PublicSpotWebsocket
from exchanges.integrations.gateio.rest.gateio_rest_spot_public import GateioPublicSpotRest
from exchanges.integrations.gateio.ws.gateio_ws_public import GateioPublicSpotWebsocket
from exchanges.structs.common import OrderBook, Ticker, Trade, BookTicker
from infrastructure.networking.websocket.handlers import PublicWebsocketHandlers
from infrastructure.logging import HFTLoggerInterface
from config.structs import ExchangeConfig


class GateioCompositePublicSpotExchange(CompositePublicSpotExchange):
    """
    Gate.io public exchange implementation using composite pattern.
    
    Provides market data operations by composing existing Gate.io infrastructure:
    - GateioPublicSpotRest for REST API calls
    - GateioPublicSpotWebsocket for real-time streaming
    - Inherits orchestration logic from CompositePublicExchange
    """

    def __init__(self, config: ExchangeConfig, logger: Optional[HFTLoggerInterface] = None,
                 handlers: Optional[PublicWebsocketHandlers] = None):
        """Initialize Gate.io public exchange."""
        super().__init__(config, logger, handlers)

    # Factory Methods - Return Existing Gate.io Clients
    
    async def _create_public_rest(self) -> PublicSpotRest:
        """Create Gate.io public REST client."""
        return GateioPublicSpotRest(self.config, self.logger)
    
    async def _create_public_websocket(self) -> Optional[PublicSpotWebsocket]:
        """Create Gate.io public WebSocket client with handlers."""

        return GateioPublicSpotWebsocket(
            config=self.config,
            handlers=self._create_inner_websocket_handlers(),
            logger=self.logger
        )

    # Handler method implementations - inherit base behavior but add Gate.io-specific logging
    
    async def _handle_orderbook(self, orderbook: OrderBook) -> None:
        """Handle Gate.io orderbook updates from WebSocket."""
        await super()._handle_orderbook(orderbook)
        self.logger.debug("Gate.io orderbook update processed", 
                         symbol=orderbook.symbol,
                         bids_count=len(orderbook.bids),
                         asks_count=len(orderbook.asks))
    
    async def _handle_ticker(self, ticker: Ticker) -> None:
        """Handle Gate.io ticker updates from WebSocket."""
        await super()._handle_ticker(ticker)
        self.logger.debug("Gate.io ticker update processed", symbol=ticker.symbol)
    
    async def _handle_trade(self, trade: Trade) -> None:
        """Handle Gate.io trade updates from WebSocket."""
        await super()._handle_trade(trade)
        self.logger.debug("Gate.io trade update processed", symbol=trade.symbol)
    
    async def _handle_book_ticker(self, book_ticker: BookTicker) -> None:
        """Handle Gate.io book ticker updates from WebSocket."""
        await super()._handle_book_ticker(book_ticker)
        self.logger.debug("Gate.io book ticker update processed", 
                         symbol=book_ticker.symbol,
                         bid=book_ticker.bid_price,
                         ask=book_ticker.ask_price)