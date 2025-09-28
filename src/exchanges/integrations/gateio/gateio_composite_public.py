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
from infrastructure.exceptions.system import InitializationError
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
        """Initialize Gate.io public exchange with direct client injection."""
            # Create clients directly with proper error context
        rest_client = GateioPublicSpotRest(config, logger)
        websocket_client = GateioPublicSpotWebsocket(
            config=config,
            handlers=self.ws_handlers,
            logger=logger
        )
        
        super().__init__(config, logger, handlers, rest_client, websocket_client)
