"""MEXC public exchange implementation using composite pattern."""

from typing import Optional
from exchanges.interfaces.composite.spot.base_public_spot_composite import CompositePublicSpotExchange
from exchanges.interfaces import PublicSpotRest
from exchanges.interfaces.ws.spot.ws_spot_public import PublicSpotWebsocket
from exchanges.integrations.mexc.rest.mexc_rest_spot_public import MexcPublicSpotRest
from exchanges.integrations.mexc.ws.mexc_ws_public import MexcPublicSpotWebsocket
from infrastructure.networking.websocket.handlers import PublicWebsocketHandlers
from infrastructure.logging import HFTLoggerInterface
from config.structs import ExchangeConfig


class MexcCompositePublicSpotExchange(CompositePublicSpotExchange):
    """
    MEXC public exchange implementation using composite pattern.
    
    Provides market data operations by composing existing MEXC infrastructure:
    - MexcPublicSpotRest for REST API calls
    - MexcPublicSpotWebsocket for real-time streaming
    - Inherits orchestration logic from CompositePublicExchange
    """

    def __init__(self, config: ExchangeConfig, logger: Optional[HFTLoggerInterface] = None,
                 handlers: Optional[PublicWebsocketHandlers] = None):
        """Initialize MEXC public exchange."""
        super().__init__(config, logger, handlers)

    # Factory Methods - Return Existing MEXC Clients
    
    async def _create_public_rest(self) -> PublicSpotRest:
        """Create MEXC public REST client."""
        return MexcPublicSpotRest(self.config, self.logger)
    
    async def _create_public_websocket(self) -> Optional[PublicSpotWebsocket]:
        """Create MEXC public WebSocket client with handlers."""

        return MexcPublicSpotWebsocket(
            config=self.config,
            handlers=self._create_inner_websocket_handlers(),
            logger=self.logger
        )