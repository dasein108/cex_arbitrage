from abc import ABC
from typing import Callable, Optional, Awaitable, List
from core.config.structs import ExchangeConfig
from structs.common import Symbol, Trade, OrderBook
from core.transport.websocket.structs import ConnectionState, MessageType
from core.cex.websocket.ws_base import BaseExchangeWebsocketInterface


class BaseExchangePublicWebsocketInterface(BaseExchangeWebsocketInterface, ABC):
    """Abstract interface for public exchange WebSocket operations (market data)"""
    
    def __init__(self, 
                 config: ExchangeConfig,
                 orderbook_diff_handler: Optional[Callable[[any, Symbol], Awaitable[None]]] = None,
                 trades_handler: Optional[Callable[[Symbol, List[Trade]], Awaitable[None]]] = None,
                 state_change_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None):
        """Initialize public WebSocket interface with dependency injection."""
        
        # Store handlers for message routing
        self.orderbook_diff_handler = orderbook_diff_handler
        self.trades_handler = trades_handler
        
        # Initialize base class with public API configuration
        super().__init__(
            config=config,
            is_private=False,  # Public API operations
            message_handler=self._handle_parsed_message,
            state_change_handler=state_change_handler
        )

    async def _handle_parsed_message(self, parsed_message) -> None:
        """Handle parsed messages from WebSocket manager with public-specific routing."""
        try:
            message_type = parsed_message.message_type
            
            if message_type == MessageType.ORDERBOOK:
                await self._handle_orderbook_message(parsed_message)
                    
            elif message_type == MessageType.TRADE:
                await self._handle_trades_message(parsed_message)
                    
            elif message_type == MessageType.HEARTBEAT:
                self.logger.debug("Received public heartbeat")
                
            elif message_type == MessageType.SUBSCRIPTION_CONFIRM:
                self.logger.info(f"Public subscription confirmed {parsed_message.raw_data}")
                
            elif message_type == MessageType.ERROR:
                self.logger.error(f"Public WebSocket error: {parsed_message.raw_data}")
            else:
                self.logger.debug(f"Unhandled message type: {message_type}")

        except Exception as e:
            self.logger.error(f"Error handling parsed public message: {e}")

    async def _handle_orderbook_message(self, parsed_message) -> None:
        """Handle orderbook update messages."""
        try:
            if parsed_message.symbol and self.orderbook_diff_handler:
                # Use injected handler if available
                await self.orderbook_diff_handler(parsed_message.data, parsed_message.symbol)
            elif parsed_message.symbol and parsed_message.data:
                # Fallback to default handler
                await self.on_orderbook_update(parsed_message.symbol, parsed_message.data)
        except Exception as e:
            self.logger.error(f"Error handling orderbook message: {e}")

    async def _handle_trades_message(self, parsed_message) -> None:
        """Handle trade update messages."""
        try:
            if parsed_message.symbol and parsed_message.data and self.trades_handler:
                # Use injected handler if available
                await self.trades_handler(parsed_message.symbol, parsed_message.data)
            elif parsed_message.symbol and parsed_message.data:
                # Fallback to default handler
                await self.on_trades_update(parsed_message.symbol, parsed_message.data)
        except Exception as e:
            self.logger.error(f"Error handling trades message: {e}")

    # Default event handlers (can be overridden by subclasses)
    async def on_orderbook_update(self, symbol: Symbol, orderbook: OrderBook):
        """Default orderbook update handler."""
        self.logger.info(f"Orderbook update for {symbol}: {len(orderbook.bids)} bids, {len(orderbook.asks)} asks")

    async def on_trades_update(self, symbol: Symbol, trades: List[Trade]):
        """Default trade update handler."""
        self.logger.info(f"Trades update for {symbol}: {len(trades)} trades")