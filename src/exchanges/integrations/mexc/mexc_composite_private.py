"""MEXC private exchange implementation using composite pattern."""

from typing import Optional, List
from exchanges.interfaces.composite.spot.base_private_spot_composite import CompositePrivateSpotExchange
from exchanges.integrations.mexc.rest.mexc_rest_spot_private import MexcPrivateSpotRest
from exchanges.integrations.mexc.ws.mexc_ws_private import MexcPrivateSpotWebsocket
from infrastructure.networking.websocket.handlers import PrivateWebsocketHandlers
from infrastructure.logging import HFTLoggerInterface
from config.structs import ExchangeConfig
from infrastructure.exceptions.system import InitializationError


class MexcCompositePrivateSpotExchange(CompositePrivateSpotExchange):
    """
    MEXC private exchange implementation using composite pattern.

    Provides trading operations by composing existing MEXC infrastructure:
    - MexcPrivateSpotRest for authenticated REST API calls
    - MexcPrivateSpotWebsocket for private data streaming
    - Inherits trading logic from CompositePrivateExchange
    """

    def __init__(self, config: ExchangeConfig, logger: Optional[HFTLoggerInterface] = None,
                 handlers: Optional[PrivateWebsocketHandlers] = None):
        """Initialize MEXC private exchange with direct client injection."""
            # Create clients directly with proper error context
        rest_client = MexcPrivateSpotRest(config, logger)

        # Create inner handlers for websocket client
        websocket_client = MexcPrivateSpotWebsocket(config=config,
                                                    handlers=self.ws_handlers,
                                                    logger=logger)

        # Call parent with clients first, then config
        super().__init__(rest_client, websocket_client, config, logger, handlers)

