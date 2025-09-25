"""
MEXC Private WebSocket Implementation

Clean implementation using handler objects for organized message processing.
Handles authenticated WebSocket streams for account data including:
- Order updates via protobuf
- Account balance changes via protobuf  
- Trade confirmations via protobuf

Features:
- Handler object pattern for clean organization
- HFT-optimized message processing
- Event-driven architecture with structured handlers
- Clean separation of concerns
- MEXC-specific protobuf message parsing

MEXC Private WebSocket Specifications:
- Endpoint: wss://wbs-api.mexc.com/ws
- Authentication: Listen key-based (managed by strategy)
- Keep-alive: Every 30 minutes to prevent expiration
- Auto-cleanup: Listen key deletion on disconnect

Architecture: Handler objects with composite class coordination
"""

from typing import Dict, Optional

from exchanges.structs.common import Order, AssetBalance, Trade
from exchanges.structs.types import AssetName
from exchanges.integrations.mexc.rest.mexc_rest_private import MexcPrivateSpotRest
from config.structs import ExchangeConfig
from exchanges.interfaces.ws import PrivateSpotWebsocket
from infrastructure.networking.websocket.handlers import PrivateWebsocketHandlers
# ExchangeMapperFactory dependency removed - using direct utility functions
from exchanges.structs import ExchangeEnum
from infrastructure.logging import get_exchange_logger

# MEXC-specific protobuf imports for message parsing
from exchanges.integrations.mexc.structs.protobuf.PrivateAccountV3Api_pb2 import PrivateAccountV3Api
from exchanges.integrations.mexc.structs.protobuf.PrivateOrdersV3Api_pb2 import PrivateOrdersV3Api
from exchanges.integrations.mexc.structs.protobuf.PrivateDealsV3Api_pb2 import PrivateDealsV3Api


class MexcPrivateSpotWebsocket(PrivateSpotWebsocket):
    """MEXC private WebSocket client using dependency injection pattern."""

    def __init__(
        self,
        config: ExchangeConfig,
        handlers: PrivateWebsocketHandlers,
        **kwargs
    ):
        """
        Initialize MEXC private WebSocket with handler objects.
        
        Args:
            config: Exchange configuration
            handlers: PrivateWebsocketHandlers object containing message handlers
            **kwargs: Additional arguments passed to base class
        """
        # Create REST client for MEXC-specific operations (e.g., listen key management)
        rest_logger = get_exchange_logger('mexc', 'rest_private')
        self.rest_client = MexcPrivateSpotRest(
            config=config,
            logger=rest_logger
        )
        
        # Initialize via composite class with handler object
        super().__init__(
            config=config,
            handlers=handlers,
            **kwargs
        )
        
        self.logger.info("MEXC private WebSocket initialized with handler objects")


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