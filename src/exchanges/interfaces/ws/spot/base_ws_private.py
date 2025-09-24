import traceback
from abc import ABC
from typing import Callable, Optional, Awaitable, Dict

from infrastructure.config.structs import ExchangeConfig
from infrastructure.data_structures.common import Order, AssetBalance, Trade, AssetName
from infrastructure.networking.websocket.structs import MessageType
from exchanges.base.websocket.ws_base import BaseExchangeWebsocketInterface


class BaseExchangePrivateWebsocketInterface(BaseExchangeWebsocketInterface, ABC):
    """Abstract interface for private exchange WebSocket operations (account data)"""
    
    def __init__(self, 
                 config: ExchangeConfig,
                 order_handler: Optional[Callable[[Order], Awaitable[None]]] = None,
                 balance_handler: Optional[Callable[[Dict[AssetName, AssetBalance]], Awaitable[None]]] = None,
                 trade_handler: Optional[Callable[[Trade], Awaitable[None]]] = None,
                 **kwargs):
        """Initialize private WebSocket interface with dependency injection."""
        
        # Store handlers for message routing
        self.order_handler = order_handler
        self.balance_handler = balance_handler
        self.trade_handler = trade_handler
        
        # Initialize base class with private API configuration
        super().__init__(
            config=config,
            is_private=True,  # Private API operations
            message_handler=self._handle_parsed_message
        )

    async def _handle_parsed_message(self, parsed_message) -> None:
        """Handle parsed messages from WebSocket manager with private-specific routing."""
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
                # Use channel from ParsedMessage
                if parsed_message.channel:
                    self.logger.info(f"Private subscription confirmed for channel: {parsed_message.channel}")
                else:
                    self.logger.info("Private subscription confirmed")
                
            elif message_type == MessageType.ERROR:
                # Use channel from ParsedMessage for better error context
                if parsed_message.channel:
                    self.logger.error(f"Private WebSocket error on channel '{parsed_message.channel}': {parsed_message.raw_data}")
                else:
                    self.logger.error(f"Private WebSocket error: {parsed_message.raw_data}")
            else:
                self.logger.debug(f"Unhandled message type: {message_type}")

        except Exception as e:
            self.logger.error(f"Error handling parsed private message: {e}")

    async def _handle_balance_message(self, parsed_message) -> None:
        """Handle balance update messages."""
        try:
            if parsed_message.data and self.balance_handler:
                # Use injected handler if available
                await self.balance_handler(parsed_message.data)
            elif parsed_message.data:
                # Fallback to default handler
                await self.on_balance_update(parsed_message.data)
        except Exception as e:
            traceback.print_exc()
            self.logger.error(f"Error handling balance message: {e}")

    async def _handle_order_message(self, parsed_message) -> None:
        """Handle order update messages."""
        try:
            if parsed_message.data and self.order_handler:
                # Use injected handler if available
                await self.order_handler(parsed_message.data)
            elif parsed_message.data:
                # Fallback to default handler
                await self.on_order_update(parsed_message.data)
        except Exception as e:
            self.logger.error(f"Error handling order message: {e}")

    async def _handle_trade_message(self, parsed_message) -> None:
        """Handle trade execution messages."""
        try:
            if parsed_message.data and self.trade_handler:
                # Use injected handler if available
                await self.trade_handler(parsed_message.data)
            elif parsed_message.data:
                # Fallback to default handler
                await self.on_trade_update(parsed_message.data)
        except Exception as e:
            self.logger.error(f"Error handling trade message: {e}")

    # Default event handlers (can be overridden by subclasses)
    async def on_order_update(self, order: Order):
        """Default order update handler."""
        self.logger.info(f"Order update: {order.order_id} - {order.status} - {order.filled_quantity}/{order.quantity}")

    async def on_balance_update(self, balances: Dict[AssetName, AssetBalance]):
        """Default balance update handler."""
        non_zero_balances = [b for b in balances.values() if b.free > 0 or b.locked > 0]
        self.logger.info(f"Balance update: {len(non_zero_balances)} assets with non-zero balances")

    async def on_trade_update(self, trade: Trade):
        """Default trade update handler."""
        self.logger.info(f"Trade executed: {trade.side.name} {trade.quantity} at {trade.price} ({'maker' if trade.is_maker else 'taker'})")
