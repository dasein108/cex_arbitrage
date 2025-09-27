"""MEXC private exchange implementation using composite pattern."""

from typing import Optional, List
from exchanges.interfaces.composite.spot.base_private_spot_composite import CompositePrivateExchange
from exchanges.interfaces.rest.spot.rest_spot_private import PrivateSpotRest
from exchanges.interfaces.ws.spot.ws_spot_private import PrivateSpotWebsocket
from exchanges.integrations.mexc.rest.mexc_rest_spot_private import MexcPrivateSpotRest
from exchanges.integrations.mexc.ws.mexc_ws_private import MexcPrivateSpotWebsocket
from exchanges.structs.common import Symbol, Order, WithdrawalRequest, WithdrawalResponse
from exchanges.structs.types import AssetName
from exchanges.structs import Side, OrderType
from infrastructure.networking.websocket.handlers import PrivateWebsocketHandlers
from infrastructure.logging import HFTLoggerInterface
from config.structs import ExchangeConfig


class MexcCompositePrivateExchange(CompositePrivateExchange):
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
        super().__init__(config, logger=logger, handlers=handlers)

    # Factory Methods - Return Existing MEXC Clients
    
    async def _create_private_rest(self) -> PrivateSpotRest:
        """Create MEXC private REST client."""
        return MexcPrivateSpotRest(self.config, self.logger)
    
    async def _create_private_ws_with_handlers(self, handlers: PrivateWebsocketHandlers) -> Optional[PrivateSpotWebsocket]:
        """Create MEXC private WebSocket client with handlers."""

        return MexcPrivateSpotWebsocket(
            config=self.config,
            handlers=handlers,
            logger=self.logger
        )

    # WebSocket Handler Implementation
    

    async def withdraw(self, request: WithdrawalRequest) -> WithdrawalResponse:
        """Submit a withdrawal request via MEXC REST API."""
        return await self._private_rest.submit_withdrawal(request)

    async def get_withdrawal_status(self, withdrawal_id: str) -> WithdrawalResponse:
        """Get current status of a withdrawal via MEXC REST API."""
        return await self._private_rest.get_withdrawal_status(withdrawal_id)

    async def get_withdrawal_history(self, asset: Optional[AssetName] = None, limit: int = 100) -> List[WithdrawalResponse]:
        """Get withdrawal history via MEXC REST API."""
        return await self._private_rest.get_withdrawal_history(asset, limit)