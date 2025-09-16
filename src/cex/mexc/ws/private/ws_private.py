"""
MEXC Private WebSocket Implementation (Refactored)

Modernized implementation using the new strategy pattern architecture.
Handles authenticated WebSocket streams for account data including:
- Order updates via protobuf
- Account balance changes via protobuf  
- Trade confirmations via protobuf

Features:
- Strategy pattern architecture with composition
- HFT-optimized message processing with WebSocketManager
- Event-driven architecture with dependency injection handlers
- Unified protobuf parsing with public implementation
- Clean separation of concerns

MEXC Private WebSocket Specifications:
- Endpoint: wss://wbs-api.mexc.com/ws
- Authentication: Listen key-based (managed by strategy)
- Keep-alive: Every 30 minutes to prevent expiration
- Auto-cleanup: Listen key deletion on disconnect

Architecture: Strategy pattern with WebSocketManager coordination
"""

import time
from typing import List, Dict, Optional, Callable, Awaitable
from common.logging import getLogger

from structs.exchange import Symbol, Order, AssetBalance, Trade, Side, AssetName
from cex.mexc.rest.rest_private import MexcPrivateSpotRest
from .mapping import status_mapping, type_mapping
# Strategy pattern imports
from core.cex.websocket.strategies import WebSocketStrategySet
from core.cex.websocket.ws_manager import WebSocketManager, WebSocketManagerConfig
from core.cex.websocket import MessageType, BaseExchangeWebsocketInterface
from cex.mexc.ws.private.ws_message_parser import MexcPrivateMessageParser
from cex.mexc.ws.private.ws_strategies import MexcPrivateConnectionStrategy, MexcPrivateSubscriptionStrategy

from cex.mexc.structs.protobuf.PrivateAccountV3Api_pb2 import PrivateAccountV3Api
from cex.mexc.structs.protobuf.PrivateOrdersV3Api_pb2 import PrivateOrdersV3Api
from cex.mexc.structs.protobuf.PrivateDealsV3Api_pb2 import PrivateDealsV3Api
from core.config.structs import ExchangeConfig

class MexcWebsocketPrivate(BaseExchangeWebsocketInterface):
    """MEXC private WebSocket client using strategy pattern architecture."""

    def __init__(
        self,
        private_rest_client: MexcPrivateSpotRest,
        config: ExchangeConfig,
        order_handler: Optional[Callable[[Order], Awaitable[None]]] = None,
        balance_handler: Optional[Callable[[Dict[AssetName, AssetBalance]], Awaitable[None]]] = None,
        trade_handler: Optional[Callable[[Trade], Awaitable[None]]] = None
    ):
        super().__init__(config)
        self.logger = getLogger(f"{__name__}.{self.__class__.__name__}")
        self.rest_client = private_rest_client
        self.order_handler = order_handler
        self.balance_handler = balance_handler
        self.trade_handler = trade_handler
        

        # Create strategy set for MEXC private WebSocket
        strategies = WebSocketStrategySet(
            connection_strategy=MexcPrivateConnectionStrategy(config, private_rest_client),
            subscription_strategy=MexcPrivateSubscriptionStrategy(),
            message_parser=MexcPrivateMessageParser()
        )
        
        # Configure manager for HFT performance
        manager_config = WebSocketManagerConfig(
            batch_processing_enabled=True,
            batch_size=100,
            max_pending_messages=1000,
            enable_performance_tracking=True
        )
        
        # Initialize WebSocket manager with strategy pattern
        self.ws_manager = WebSocketManager(
            config=config.websocket,
            strategies=strategies,
            message_handler=self._handle_parsed_message,
            manager_config=manager_config
        )
        
        self.logger.info("MEXC private WebSocket initialized with strategy pattern")

    async def _handle_parsed_message(self, parsed_message) -> None:
        """Handle parsed messages from WebSocketManager."""
        try:
            message_type = parsed_message.message_type
            
            if message_type == MessageType.BALANCE:
                await self._handle_balance_message(parsed_message)
                    
            elif message_type == MessageType.ORDER:
                await self._handle_order_message(parsed_message)
                    
            elif message_type == MessageType.TRADE:
                await self._handle_trade_message(parsed_message)
                    
            elif message_type == MessageType.HEARTBEAT:
                self.logger.debug("Received private heartbeat")
                
            elif message_type == MessageType.SUBSCRIPTION_CONFIRM:
                self.logger.info("Private subscription confirmed")
                
            elif message_type == MessageType.ERROR:
                self.logger.error(f"Private WebSocket error: {parsed_message.raw_data}")

        except Exception as e:
            self.logger.error(f"Error handling parsed private message: {e}")

    async def initialize(self, symbols: List[Symbol] = None) -> None:
        """
        Initialize private WebSocket connection using strategy pattern.
        
        Note: Private streams don't use symbols for subscription - they use listen keys
        for authentication and receive ALL account events.
        """
        try:
            await self.ws_manager.initialize(symbols or [])
            self.logger.info("Private WebSocket initialized with strategy pattern")
        except Exception as e:
            self.logger.error(f"Failed to initialize private WebSocket: {e}")
            raise

    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self.ws_manager.is_connected()
        
    def get_performance_metrics(self) -> Dict:
        """Get HFT performance metrics."""
        return self.ws_manager.get_performance_metrics()

    async def close(self) -> None:
        """Close WebSocket connection."""
        self.logger.info("Stopping private WebSocket connection")
        await self.ws_manager.close()
        self.logger.info("Private WebSocket stopped")

    async def _handle_balance_message(self, parsed_message) -> None:
        """Handle balance update messages."""
        try:
            data = parsed_message.data
            if not data:
                return
                
            # Create AssetBalance object from parsed data
            asset_balance = AssetBalance(
                asset=data.get("asset", ""),
                free=data.get("free", 0.0),
                locked=data.get("locked", 0.0)
            )
            
            # Create balance dict compatible with existing interface
            balances = {asset_balance.asset: asset_balance}
            
            if self.balance_handler:
                await self.balance_handler(balances)
            else:
                await self.on_balance_update([asset_balance])
                
        except Exception as e:
            self.logger.error(f"Error handling balance message: {e}")
    
    async def _handle_order_message(self, parsed_message) -> None:
        """Handle order update messages."""
        try:
            data = parsed_message.data
            if not data:
                return
                
            # Parse order status from numeric value
            status = status_mapping.get( data.get("status", 1))

            order_type = type_mapping.get(data.get("orderType", 1))
            
            # Parse side
            side_str = data.get("side", "BUY")
            side = Side.BUY if side_str == "BUY" else Side.SELL

            timestamp = data.get("updateTime", int(time.time() * 1000))
            
            # Create Order object from parsed data
            order = Order(
                order_id=data.get("order_id", ""),
                client_order_id="",
                symbol=self.symbol_mapper.pair_to_symbol(data.get("symbol", "")) if data.get("symbol") else None,
                side=side,
                order_type=order_type,
                amount=data.get("quantity", 0.0),
                price=data.get("price", 0.0),
                amount_filled=data.get("filled_qty", 0.0),
                status=status,
                timestamp=timestamp
            )
            
            if self.order_handler:
                await self.order_handler(order)
            else:
                await self.on_order_update(order)
                
        except Exception as e:
            self.logger.error(f"Error handling order message: {e}")
    
    async def _handle_trade_message(self, parsed_message) -> None:
        """Handle trade execution messages."""
        try:
            data = parsed_message.data
            if not data:
                return
                
            # Parse side
            side_str = data.get("side", "BUY")
            side = Side.BUY if side_str == "BUY" else Side.SELL
            
            # Create Trade object from parsed data
            trade = Trade(
                price=data.get("price", 0.0),
                amount=data.get("quantity", 0.0),
                side=side,
                timestamp=data.get("timestamp", int(time.time() * 1000)),
                is_maker=data.get("is_maker", False)
            )
            
            if self.trade_handler:
                await self.trade_handler(trade)
            else:
                await self.on_trade_update(trade)
                
        except Exception as e:
            self.logger.error(f"Error handling trade message: {e}")

    # Default event handlers (can be overridden by dependency injection)
    
    async def on_order_update(self, order: Order):
        """Default order update handler."""
        self.logger.info(f"Order update: {order.order_id} - {order.status} - {order.amount_filled}/{order.amount}")

    async def on_balance_update(self, balances: List[AssetBalance]):
        """Default balance update handler."""
        non_zero_balances = [b for b in balances if b.free > 0 or b.locked > 0]
        self.logger.info(f"Balance update: {len(non_zero_balances)} assets with non-zero balances")

    async def on_trade_update(self, trade: Trade):
        """Default trade update handler."""
        self.logger.info(f"Trade executed: {trade.side.name} {trade.amount} at {trade.price} ({'maker' if trade.is_maker else 'taker'})")