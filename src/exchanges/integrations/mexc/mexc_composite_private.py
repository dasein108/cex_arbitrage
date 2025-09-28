"""MEXC private exchange implementation using composite pattern."""

from typing import Optional, List
from exchanges.interfaces.composite.spot.base_private_spot_composite import CompositePrivateSpotExchange
from exchanges.integrations.mexc.rest.mexc_rest_spot_private import MexcPrivateSpotRest
from exchanges.integrations.mexc.ws.mexc_ws_private import MexcPrivateSpotWebsocket
from infrastructure.networking.websocket.handlers import PrivateWebsocketHandlers
from infrastructure.logging import HFTLoggerInterface
from config.structs import ExchangeConfig


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
        """Initialize MEXC private exchange."""
        super().__init__(config, logger, handlers)

    # Factory Methods - Return Existing MEXC Clients
    
    async def _create_private_rest(self) -> MexcPrivateSpotRest:
        """Create MEXC private REST client."""
        return MexcPrivateSpotRest(self.config, self.logger)
    
    async def _create_private_websocket(self) -> Optional[MexcPrivateSpotWebsocket]:
        """Create MEXC private WebSocket client with handlers."""

        return MexcPrivateSpotWebsocket(
            config=self.config,
            handlers=self._create_inner_websocket_handlers(),
            logger=self.logger
        )

    # Withdrawal operations are inherited from WithdrawalMixin which delegates to _private_rest