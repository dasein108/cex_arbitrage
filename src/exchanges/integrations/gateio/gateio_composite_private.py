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
        """Initialize Gate.io private exchange."""
        super().__init__(config, logger, handlers)

    # Factory Methods - Return Existing Gate.io Clients
    
    async def _create_private_rest(self) -> GateioPrivateSpotRest:
        """Create Gate.io private REST client."""
        return GateioPrivateSpotRest(self.config, self.logger)
    
    async def _create_private_websocket(self) -> Optional[GateioPrivateSpotWebsocket]:
        """Create Gate.io private WebSocket client with handlers."""

        return GateioPrivateSpotWebsocket(
            config=self.config,
            handlers=self._create_inner_websocket_handlers(),
            logger=self.logger
        )
