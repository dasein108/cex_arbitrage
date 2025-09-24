"""
MEXC Private WebSocket Implementation

Clean implementation using dependency injection similar to REST pattern.
Handles authenticated WebSocket streams for account data including:
- Order updates via protobuf
- Account balance changes via protobuf  
- Trade confirmations via protobuf

Features:
- Dependency injection via base class (like REST pattern)
- HFT-optimized message processing
- Event-driven architecture with injected handlers
- Clean separation of concerns
- MEXC-specific protobuf message parsing

MEXC Private WebSocket Specifications:
- Endpoint: wss://wbs-api.mexc.com/ws
- Authentication: Listen key-based (managed by strategy)
- Keep-alive: Every 30 minutes to prevent expiration
- Auto-cleanup: Listen key deletion on disconnect

Architecture: Dependency injection with base class coordination
"""

from typing import Dict, Optional, Callable, Awaitable

from infrastructure.data_structures.common import Order, AssetBalance, Trade, AssetName
from exchanges.integrations.mexc.rest.mexc_rest_private import MexcPrivateSpotRest
from infrastructure.config.structs import ExchangeConfig
from exchanges.base.websocket.spot.base_ws_private import BaseExchangePrivateWebsocketInterface
# Mappings now consolidated in MexcUnifiedMappings

# MEXC-specific protobuf imports for message parsing
from exchanges.integrations.mexc.structs.protobuf.PrivateAccountV3Api_pb2 import PrivateAccountV3Api
from exchanges.integrations.mexc.structs.protobuf.PrivateOrdersV3Api_pb2 import PrivateOrdersV3Api
from exchanges.integrations.mexc.structs.protobuf.PrivateDealsV3Api_pb2 import PrivateDealsV3Api


class MexcWebsocketPrivate(BaseExchangePrivateWebsocketInterface):
    """MEXC private WebSocket client using dependency injection pattern."""

    def __init__(
        self,
        private_rest_client: MexcPrivateSpotRest,
        config: ExchangeConfig,
        order_handler: Optional[Callable[[Order], Awaitable[None]]] = None,
        balance_handler: Optional[Callable[[Dict[AssetName, AssetBalance]], Awaitable[None]]] = None,
        trade_handler: Optional[Callable[[Trade], Awaitable[None]]] = None,
        **kwargs
    ):
        """
        Initialize MEXC private WebSocket with dependency injection.
        
        Base class handles all strategy creation, WebSocket manager setup, and dependency injection.
        Only MEXC-specific initialization logic and REST client management goes here.
        """
        # Store REST client for MEXC-specific operations
        self.rest_client = private_rest_client
        
        # Initialize via base class dependency injection (like REST pattern)
        super().__init__(
            config=config,
            order_handler=order_handler,
            balance_handler=balance_handler,
            trade_handler=trade_handler
        )
        
        self.logger.info("MEXC private WebSocket initialized with dependency injection")


    # Override default handlers if MEXC needs specific behavior
    async def on_order_update(self, order: Order):
        """MEXC-specific order update handler."""
        self.logger.info(f"MEXC order update: {order.order_id} - {order.status} - {order.filled_quantity}/{order.quantity}")

    async def on_balance_update(self, balance: AssetBalance):
        """MEXC-specific balance update handler."""
        self.logger.info(f"MEXC balance update: {balance}")

    async def on_trade_update(self, trade: Trade):
        """MEXC-specific trade update handler."""
        self.logger.info(f"MEXC trade executed: {trade.side.name} {trade.quantity} at {trade.price} ({'maker' if trade.is_maker else 'taker'})")