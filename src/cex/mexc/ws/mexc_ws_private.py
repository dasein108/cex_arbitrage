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

import time
from typing import Dict, Optional, Callable, Awaitable

from structs.common import Order, AssetBalance, Trade, Side, AssetName
from cex.mexc.rest.mexc_rest_private import MexcPrivateSpotRest
from core.config.structs import ExchangeConfig
from core.cex.websocket.spot.base_ws_private import BaseExchangePrivateWebsocketInterface
from cex.mexc.services.mapping import status_mapping, type_mapping

# MEXC-specific protobuf imports for message parsing
from cex.mexc.structs.protobuf.PrivateAccountV3Api_pb2 import PrivateAccountV3Api
from cex.mexc.structs.protobuf.PrivateOrdersV3Api_pb2 import PrivateOrdersV3Api
from cex.mexc.structs.protobuf.PrivateDealsV3Api_pb2 import PrivateDealsV3Api


class MexcWebsocketPrivate(BaseExchangePrivateWebsocketInterface):
    """MEXC private WebSocket client using dependency injection pattern."""

    def __init__(
        self,
        private_rest_client: MexcPrivateSpotRest,
        config: ExchangeConfig,
        order_handler: Optional[Callable[[Order], Awaitable[None]]] = None,
        balance_handler: Optional[Callable[[Dict[AssetName, AssetBalance]], Awaitable[None]]] = None,
        trade_handler: Optional[Callable[[Trade], Awaitable[None]]] = None
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
        
        # State management for private subscriptions (for consistency)
        self._is_subscribed = False
        
        self.logger.info("MEXC private WebSocket initialized with dependency injection")

    # Enhanced private subscription management using channel mapping
    async def subscribe_to_private_channels(self) -> None:
        """Subscribe to private channels using enhanced channel mapping."""
        if self._is_subscribed:
            self.logger.info("Already subscribed to private channels")
            return
        
        # Use unified subscription method (no parameters needed for private)
        await self._ws_manager.add_subscription()
        
        self._is_subscribed = True
        self.logger.info("Subscribed to private channels")
    
    async def unsubscribe_from_private_channels(self) -> None:
        """Unsubscribe from private channels using enhanced channel mapping."""
        if not self._is_subscribed:
            self.logger.info("Not subscribed to private channels")
            return
        
        # Use unified subscription removal method (no parameters needed for private)
        await self._ws_manager.remove_subscription()
        
        self._is_subscribed = False
        self.logger.info("Unsubscribed from private channels")
    
    async def restore_subscriptions(self) -> None:
        """Restore private subscriptions after reconnect using ws_manager restoration."""
        if not self._is_subscribed:
            self.logger.info("No private subscriptions to restore")
            return
        
        # ws_manager handles restoration automatically using stored channels
        # No action needed here - channels are restored by ws_manager
        self.logger.info("Private channel subscriptions will be restored by ws_manager")
    
    def is_subscribed(self) -> bool:
        """Check if subscribed to private channels."""
        return self._is_subscribed

    # MEXC-specific message handling can be added here if needed
    # Base class handles all common WebSocket operations:
    # - initialize(), close(), is_connected(), get_performance_metrics()
    # - Message routing for BALANCE, ORDER, TRADE, HEARTBEAT, etc.
    # - Default event handlers with dependency injection support
    
    # Custom order parsing logic using MEXC mappings
    def _parse_mexc_order(self, data: dict) -> Order:
        """Parse MEXC-specific order data using status/type mappings."""
        # Parse order status from numeric value
        status = status_mapping.get(data.get("status", 1))
        order_type = type_mapping.get(data.get("orderType", 1))
        
        # Parse side
        side_str = data.get("side", "BUY")
        side = Side.BUY if side_str == "BUY" else Side.SELL
        
        timestamp = data.get("updateTime", int(time.time() * 1000))
        
        # Create Order object from parsed data
        return Order(
            order_id=data.get("order_id", ""),
            client_order_id="",
            symbol=self._mapper.to_symbol(data.get("symbol", "")) if data.get("symbol") else None,
            side=side,
            order_type=order_type,
            amount=data.get("quantity", 0.0),
            price=data.get("price", 0.0),
            amount_filled=data.get("filled_qty", 0.0),
            status=status,
            timestamp=timestamp
        )
    
    # Override default handlers if MEXC needs specific behavior
    async def on_order_update(self, order: Order):
        """MEXC-specific order update handler."""
        self.logger.info(f"MEXC order update: {order.order_id} - {order.status} - {order.filled_quantity}/{order.quantity}")

    async def on_balance_update(self, balances: Dict[AssetName, AssetBalance]):
        """MEXC-specific balance update handler."""
        non_zero_balances = [b for b in balances.values() if b.free > 0 or b.locked > 0]
        self.logger.info(f"MEXC balance update: {len(non_zero_balances)} assets with non-zero balances")

    async def on_trade_update(self, trade: Trade):
        """MEXC-specific trade update handler."""
        self.logger.info(f"MEXC trade executed: {trade.side.name} {trade.quantity} at {trade.price} ({'maker' if trade.is_maker else 'taker'})")