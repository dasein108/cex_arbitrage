"""
Gate.io Private Futures WebSocket Implementation

Separate exchange implementation treating Gate.io futures private operations as completely 
independent from Gate.io spot. Uses dedicated configuration section 'gateio_futures' with 
its own ExchangeEnum.GATEIO_FUTURES and separate WebSocket endpoints.

Handles private futures WebSocket streams for account data including:
- Futures order updates via JSON
- Futures account balance changes via JSON  
- Futures trade confirmations via JSON
- Futures position updates
- Futures margin updates

Features:
- Completely separate from Gate.io spot configuration
- Dedicated ExchangeEnum.GATEIO_FUTURES with 'gateio_futures' config section
- HFT-optimized message processing for futures trading
- Event-driven architecture with injected handlers
- Clean separation from spot exchange operations
- Gate.io futures-specific JSON message parsing

Gate.io Private Futures WebSocket Specifications:
- Endpoint: wss://fx-ws.gateio.ws/v4/ws/usdt/ (USDT perpetual futures)
- Authentication: API key signature-based (HMAC-SHA512)
- Message Format: JSON with channel-based subscriptions
- Channels: futures.orders, futures.balances, futures.user_trades, futures.positions

Architecture: Independent exchange with separate configuration and factory support
"""

from typing import Dict, Optional, Callable, Awaitable

from exchanges.structs.common import Order, AssetBalance, Trade
from exchanges.structs.types import AssetName
from config.structs import ExchangeConfig
from exchanges.interfaces.ws import PrivateSpotWebsocket


class GateioPrivateFuturesWebsocket(PrivateSpotWebsocket):
    """Gate.io private futures WebSocket client using dependency injection pattern."""

    def __init__(
        self,
        config: ExchangeConfig,
        order_handler: Optional[Callable[[Order], Awaitable[None]]] = None,
        balance_handler: Optional[Callable[[Dict[AssetName, AssetBalance]], Awaitable[None]]] = None,
        trade_handler: Optional[Callable[[Trade], Awaitable[None]]] = None,
        **kwargs
    ):
        """
        Initialize Gate.io private futures WebSocket as separate exchange.
        
        Uses dedicated 'gateio_futures' configuration section with separate endpoints
        and performance targets. Completely independent from Gate.io spot operations.
        """
        # Validate Gate.io futures-specific requirements
        if not config.websocket:
            raise ValueError("Gate.io futures exchange configuration missing WebSocket settings")
        
        # Store the actual futures URL (config is immutable)
        self._futures_websocket_url = config.websocket_url
        
        # Initialize via composite class dependency injection (like REST pattern)
        super().__init__(
            config=config,
            order_handler=order_handler,
            balance_handler=balance_handler,
            trade_handler=trade_handler,
            **kwargs
        )
        
        # Store contract type endpoint mapping
        self._contract_endpoints = {
            'perpetual': self._futures_websocket_url,
            'delivery': getattr(config, 'websocket_delivery_url', 
                              "wss://fx-ws.gateio.ws/v4/ws/delivery/")
        }
        
        self.logger.info(f"Gate.io private futures WebSocket initialized as separate exchange with endpoint: {self._futures_websocket_url}")

    # Gate.io futures-specific message handling can be added here if needed
    # Base class handles all common WebSocket operations:
    # - initialize(), close(), is_connected(), get_performance_metrics()
    # - Message routing for BALANCE, ORDER, TRADE, HEARTBEAT, etc.
    # - Default event handlers with dependency injection support
    
    # Override default handlers for Gate.io futures-specific behavior
    async def on_order_update(self, order: Order):
        """Gate.io futures-specific order update handler."""
        contract_type = self._get_contract_type_from_symbol(order.symbol)
        self.logger.info(f"Gate.io futures ({contract_type}) order update: {order.order_id} - {order.status} - {order.filled_quantity}/{order.quantity}")

    async def on_balance_update(self, balances: Dict[AssetName, AssetBalance]):
        """Gate.io futures-specific balance update handler."""
        non_zero_balances = [b for b in balances.values() if b.free > 0 or b.locked > 0]
        self.logger.info(f"Gate.io futures balance update: {len(non_zero_balances)} assets with non-zero balances")

    async def on_trade_update(self, trade: Trade):
        """Gate.io futures-specific trade update handler."""
        contract_type = self._get_contract_type_from_symbol(trade.symbol)
        self.logger.info(f"Gate.io futures ({contract_type}) trade executed: {trade.side.name} {trade.quantity} at {trade.price} ({'maker' if trade.is_maker else 'taker'})")

    # Futures-specific methods
    async def on_position_update(self, position_data: Dict):
        """Gate.io futures-specific position update handler."""
        symbol = position_data.get("symbol", "unknown")
        size = position_data.get("size", 0)
        side = position_data.get("side", "unknown")
        unrealized_pnl = position_data.get("unrealized_pnl", 0)
        self.logger.info(f"Gate.io futures position update for {symbol}: {side} {size}, PnL: {unrealized_pnl}")

    async def on_margin_update(self, margin_data: Dict):
        """Gate.io futures-specific margin update handler."""
        available = margin_data.get("available", 0)
        used = margin_data.get("used", 0)
        margin_ratio = margin_data.get("margin_ratio", 0)
        self.logger.info(f"Gate.io futures margin update: available={available}, used={used}, ratio={margin_ratio}")

    def _get_contract_type_from_symbol(self, symbol) -> str:
        """Get contract type for futures symbol."""
        symbol_str = str(symbol)
        if "_USDT" in symbol_str and len(symbol_str.split("_")) == 2:
            return "perpetual"
        elif len(symbol_str.split("_")) > 2:
            return "delivery"
        else:
            return "unknown"
    
    def get_endpoint_for_contract_type(self, contract_type: str) -> str:
        """Get WebSocket endpoint for specific contract type."""
        return self._contract_endpoints.get(contract_type, self._contract_endpoints['perpetual'])
    
    def is_separate_exchange(self) -> bool:
        """Confirm this is a separate exchange from Gate.io spot."""
        return True
    
    def get_exchange_name(self) -> str:
        """Get the exchange name for this futures implementation."""
        return "GATEIO_FUTURES"