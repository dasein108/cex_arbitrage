"""MEXC public exchange implementation using composite pattern."""

from typing import Optional
from exchanges.interfaces.composite.spot.base_public_spot_composite import CompositePublicSpotExchange
from exchanges.interfaces import PublicSpotRest
from exchanges.interfaces.ws.spot.ws_spot_public import PublicSpotWebsocket
from exchanges.integrations.mexc.rest.mexc_rest_spot_public import MexcPublicSpotRest
from exchanges.integrations.mexc.ws.mexc_ws_public import MexcPublicSpotWebsocket
from infrastructure.networking.websocket.handlers import PublicWebsocketHandlers
from infrastructure.logging import HFTLoggerInterface
from infrastructure.exceptions.system import InitializationError
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
        """Initialize MEXC public exchange with direct client injection."""
        try:
            # Create clients directly with proper error context
            rest_client = MexcPublicSpotRest(config, logger)
            websocket_client = MexcPublicSpotWebsocket(
                config=config,
                handlers=self.ws_handlers,
                logger=logger
            )
            
            super().__init__(config, logger, handlers, rest_client, websocket_client)
            
        except Exception as e:
            # Use logger if available, otherwise fall back to basic logging
            if logger:
                logger.error(f"Failed to create {self.__class__.__name__}", error=str(e))
            raise InitializationError(f"MEXC exchange construction failed: {e}") from e

    # Factory methods removed - clients are now injected directly during construction