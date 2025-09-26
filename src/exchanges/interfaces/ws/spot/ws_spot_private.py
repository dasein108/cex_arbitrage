import traceback
from abc import ABC
from typing import Optional, Dict

from config.structs import ExchangeConfig
from exchanges.structs.common import Order, AssetBalance, Trade
from exchanges.structs.types import AssetName
from infrastructure.networking.websocket.structs import MessageType
from infrastructure.networking.websocket.handlers import PrivateWebsocketHandlers
from exchanges.interfaces.ws.ws_base import BaseWebsocketInterface


class PrivateSpotWebsocket(BaseWebsocketInterface, ABC):
    """Abstract interface for private exchange WebSocket operations (account data)"""
    
    def __init__(self, 
                 config: ExchangeConfig,
                 handlers: PrivateWebsocketHandlers,
                 **kwargs):
        """Initialize private WebSocket interface with handler object."""
        
        # Store handler object for message routing
        self.handlers = handlers
        
        # Initialize composite class with private API configuration
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
            if parsed_message.data:
                # Use handler object
                await self.handlers.handle_balance(parsed_message.data)
        except Exception as e:
            traceback.print_exc()
            self.logger.error(f"Error handling balance message: {e}")

    async def _handle_order_message(self, parsed_message) -> None:
        """Handle order update messages."""
        try:
            if parsed_message.data:
                # Use handler object
                await self.handlers.handle_order(parsed_message.data)
        except Exception as e:
            self.logger.error(f"Error handling order message: {e}")

    async def _handle_trade_message(self, parsed_message) -> None:
        """Handle trade execution messages."""
        try:
            if parsed_message.data:
                # Use handler object
                await self.handlers.handle_execution(parsed_message.data)
        except Exception as e:
            self.logger.error(f"Error handling trade message: {e}")