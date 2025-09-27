"""Gate.io private exchange implementation using composite pattern."""

from typing import Optional, List
from exchanges.interfaces.composite.spot.base_private_spot_composite import CompositePrivateExchange
from exchanges.interfaces.rest.spot.rest_spot_private import PrivateSpotRest
from exchanges.interfaces.ws.spot.ws_spot_private import PrivateSpotWebsocket
from exchanges.integrations.gateio.rest.gateio_rest_spot_private import GateioPrivateSpotRest
from exchanges.integrations.gateio.ws.gateio_ws_private import GateioPrivateSpotWebsocket
from exchanges.structs.common import Symbol, Order, WithdrawalRequest, WithdrawalResponse
from exchanges.structs.types import AssetName
from exchanges.structs import Side, OrderType
from infrastructure.networking.websocket.handlers import PrivateWebsocketHandlers
from infrastructure.logging import HFTLoggerInterface
from config.structs import ExchangeConfig


class GateioCompositePrivateExchange(CompositePrivateExchange):
    """
    Gate.io private exchange implementation using composite pattern.
    
    Provides trading operations by composing existing Gate.io infrastructure:
    - GateioPrivateSpotRest for authenticated REST API calls
    - GateioPrivateSpotWebsocket for private data streaming
    - Inherits trading logic from CompositePrivateExchange
    """

    def __init__(self, config: ExchangeConfig, logger: Optional[HFTLoggerInterface] = None):
        """Initialize Gate.io private exchange."""
        super().__init__(config, logger)

    # Factory Methods - Return Existing Gate.io Clients
    
    async def _create_private_rest(self) -> PrivateSpotRest:
        """Create Gate.io private REST client."""
        return GateioPrivateSpotRest(self.config, self.logger)
    
    async def _create_private_ws_with_handlers(self, handlers: PrivateWebsocketHandlers) -> Optional[PrivateSpotWebsocket]:
        """Create Gate.io private WebSocket client with handlers."""

        return GateioPrivateSpotWebsocket(
            config=self.config,
            handlers=handlers,
            logger=self.logger
        )

    # WebSocket Handler Implementation
    
    def _get_websocket_handlers(self) -> PrivateWebsocketHandlers:
        """Get private WebSocket handlers for Gate.io."""
        return PrivateWebsocketHandlers(
            order_handler=self._order_handler,
            balance_handler=self._balance_handler,
            execution_handler=self._execution_handler,
        )

    async def place_limit_order(self, symbol: Symbol, side: Side, quantity: float, price: float, **kwargs) -> Order:
        """Place a limit order via Gate.io REST API."""
        return await self._private_rest.place_order(symbol, side, OrderType.LIMIT, quantity, price, **kwargs)

    async def place_market_order(self, symbol: Symbol, side: Side, quote_quantity: float, **kwargs) -> Order:
        """Place a market order via Gate.io REST API."""
        return await self._private_rest.place_order(symbol, side, OrderType.MARKET, quote_quantity=quote_quantity, **kwargs)

    async def withdraw(self, request: WithdrawalRequest) -> WithdrawalResponse:
        """Submit a withdrawal request via Gate.io REST API."""
        return await self._private_rest.submit_withdrawal(request)

    async def get_withdrawal_status(self, withdrawal_id: str) -> WithdrawalResponse:
        """Get current status of a withdrawal via Gate.io REST API."""
        return await self._private_rest.get_withdrawal_status(withdrawal_id)

    async def get_withdrawal_history(self, asset: Optional[AssetName] = None, limit: int = 100) -> List[WithdrawalResponse]:
        """Get withdrawal history via Gate.io REST API."""
        return await self._private_rest.get_withdrawal_history(asset, limit)