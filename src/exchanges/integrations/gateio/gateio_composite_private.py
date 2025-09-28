"""Gate.io private exchange implementation using composite pattern."""

from typing import Optional, List
from exchanges.interfaces.composite.spot.base_private_spot_composite import CompositePrivateSpotExchange
from exchanges.integrations.gateio.rest.gateio_rest_spot_private import GateioPrivateSpotRest
from exchanges.integrations.gateio.ws.gateio_ws_private import GateioPrivateSpotWebsocket
from exchanges.structs.common import Symbol, Order, WithdrawalRequest, WithdrawalResponse
from exchanges.structs.types import AssetName
from exchanges.structs import Side, OrderType
from infrastructure.networking.websocket.handlers import PrivateWebsocketHandlers
from infrastructure.logging import HFTLoggerInterface
from config.structs import ExchangeConfig
from infrastructure.exceptions.system import InitializationError


class GateioCompositePrivateSpotExchange(CompositePrivateSpotExchange):
    """
    Gate.io private exchange implementation using composite pattern.
    
    Provides trading operations by composing existing Gate.io infrastructure:
    - GateioPrivateSpotRest for authenticated REST API calls
    - GateioPrivateSpotWebsocket for private data streaming
    - Inherits trading logic from CompositePrivateExchange
    """

    def __init__(self, config: ExchangeConfig, logger: Optional[HFTLoggerInterface] = None,
                 handlers: Optional[PrivateWebsocketHandlers] = None):
        """Initialize Gate.io private exchange with direct client injection."""
        # Create clients directly with proper error context
        rest_client = GateioPrivateSpotRest(config, logger)

        # Initialize parent first to make _create_inner_websocket_handlers available
        # We'll provide a temporary WebSocket client and update it after initialization
        websocket_client = GateioPrivateSpotWebsocket(config=config,
                                                           handlers=self.ws_handlers,  # Will be set later
                                                           logger=logger)

        # Call parent with clients first, then config
        super().__init__(rest_client, websocket_client, config, logger, handlers)
