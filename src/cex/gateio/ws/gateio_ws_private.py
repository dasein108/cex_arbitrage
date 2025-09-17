"""
Gate.io Private WebSocket Implementation

Clean implementation using dependency injection similar to REST pattern.
Handles authenticated WebSocket streams for account data including:
- Order updates via JSON
- Account balance changes via JSON  
- Trade confirmations via JSON

Features:
- Dependency injection via base class (like REST pattern)
- HFT-optimized message processing
- Event-driven architecture with injected handlers
- Clean separation of concerns
- Gate.io-specific JSON message parsing

Gate.io Private WebSocket Specifications:
- Endpoint: wss://api.gateio.ws/ws/v4/
- Authentication: API key signature-based (HMAC-SHA512)
- Message Format: JSON with channel-based subscriptions
- Channels: spot.orders, spot.balances, spot.user_trades

Architecture: Dependency injection with base class coordination
"""

from typing import List, Dict, Optional, Callable, Awaitable

from structs.exchange import Symbol, Order, AssetBalance, Trade, Side, AssetName
from core.config.structs import ExchangeConfig
from core.cex.websocket.spot.base_ws_private import BaseExchangePrivateWebsocketInterface


class GateioWebsocketPrivate(BaseExchangePrivateWebsocketInterface):
    """Gate.io private WebSocket client using dependency injection pattern."""

    def __init__(
        self,
        config: ExchangeConfig,
        order_handler: Optional[Callable[[Order], Awaitable[None]]] = None,
        balance_handler: Optional[Callable[[Dict[AssetName, AssetBalance]], Awaitable[None]]] = None,
        trade_handler: Optional[Callable[[Trade], Awaitable[None]]] = None
    ):
        """
        Initialize Gate.io private WebSocket with dependency injection.
        
        Base class handles all strategy creation, WebSocket manager setup, and dependency injection.
        Only Gate.io-specific initialization logic goes here.
        """
        # Validate Gate.io-specific requirements
        if not config.websocket:
            raise ValueError("Gate.io exchange configuration missing WebSocket settings")
        
        # Initialize via base class dependency injection (like REST pattern)
        super().__init__(
            config=config,
            order_handler=order_handler,
            balance_handler=balance_handler,
            trade_handler=trade_handler
        )
        
        # State management for private subscriptions (for consistency)
        self._is_subscribed = False
        
        self.logger.info("Gate.io private WebSocket initialized with dependency injection")

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

    # Gate.io-specific message handling can be added here if needed
    # Base class handles all common WebSocket operations:
    # - initialize(), close(), is_connected(), get_performance_metrics()
    # - Message routing for BALANCE, ORDER, TRADE, HEARTBEAT, etc.
    # - Default event handlers with dependency injection support
    
    # Override default handlers if Gate.io needs specific behavior
    async def on_order_update(self, order: Order):
        """Gate.io-specific order update handler."""
        self.logger.info(f"Gate.io order update: {order.order_id} - {order.status} - {order.amount_filled}/{order.amount}")

    async def on_balance_update(self, balances: Dict[AssetName, AssetBalance]):
        """Gate.io-specific balance update handler."""
        non_zero_balances = [b for b in balances.values() if b.free > 0 or b.locked > 0]
        self.logger.info(f"Gate.io balance update: {len(non_zero_balances)} assets with non-zero balances")

    async def on_trade_update(self, trade: Trade):
        """Gate.io-specific trade update handler."""
        self.logger.info(f"Gate.io trade executed: {trade.side.name} {trade.amount} at {trade.price} ({'maker' if trade.is_maker else 'taker'})")