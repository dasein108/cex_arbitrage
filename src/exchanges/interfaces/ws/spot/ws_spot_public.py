"""
Base Public WebSocket Interface - Refactored

Clean composite class for public WebSocket implementations using the new
strategy-driven architecture with handler objects.

HFT COMPLIANCE: Optimized for sub-millisecond message processing.
"""

import logging
from typing import List, Dict, Optional, Set, Callable, Awaitable
from abc import ABC

from exchanges.consts import DEFAULT_PUBLIC_WEBSOCKET_CHANNELS
from exchanges.structs.common import Symbol, OrderBook, Trade, BookTicker
from config.structs import ExchangeConfig
from infrastructure.logging import HFTLogger
from infrastructure.networking.websocket.structs import ConnectionState, MessageType, ParsedMessage, PublicWebsocketChannelType
from infrastructure.networking.websocket.handlers import PublicWebsocketHandlers
import traceback
from exchanges.interfaces.ws.ws_base import BaseWebsocketInterface

class PublicSpotWebsocket(BaseWebsocketInterface, ABC):
    """
    Base class for exchange public WebSocket implementations.
    
    Simplified architecture:
    - Uses new WebSocketManager V2
    - Delegates all subscription logic to strategies
    - Focuses on message routing and event handling
    """
    
    def __init__(
        self,
        config: ExchangeConfig,
        handlers: PublicWebsocketHandlers,
        logger: HFTLogger,
        connection_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None,
    ):
        super().__init__(config=config, is_private=False, logger=logger)
        """
        Initialize composite public WebSocket with handler object.
        
        Args:
            config: Exchange configuration
            handlers: PublicWebsocketHandlers object containing all message handlers
            logger: HFT logger instance
            connection_handler: Callback for connection state changes
        """
        self.config = config
        self.exchange_name = config.name.lower()
        
        # Store handler object and state change handler
        self.handlers = handlers
        self._state_change_handler = connection_handler
        

        # State management for symbols (moved from WebSocket manager)
        self._active_symbols: Set[Symbol] = set()

        self.logger.info(f"Initialized {self.exchange_name} public WebSocket with strategy-driven architecture")
    
    async def initialize(self, symbols: List[Symbol],
                         channels: List[PublicWebsocketChannelType]=DEFAULT_PUBLIC_WEBSOCKET_CHANNELS) -> None:
        """
        Initialize WebSocket connection and subscribe to symbols.
        
        Args:
            symbols: List of symbols to subscribe to
            :param symbols:  Symbols to subscribe to
            :param channels:  Channels to subscribe to
        """
        try:
            # Initialize manager with symbols
            await self._ws_manager.initialize(symbols=symbols, default_channels=channels)
            self.logger.info(f"WebSocket initialized for {self.exchange_name} with {len(symbols)} symbols")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize WebSocket: {e}")
            raise
    
    async def subscribe(self, symbols: List[Symbol]) -> None:
        """
        Add symbols to subscription.
        
        Args:
            symbols: Symbols to add
        """
        if not symbols:
            return
        
        try:
            await self._ws_manager.subscribe(symbols=symbols)

            # Move from pending to active on successful subscription
            self._active_symbols.update(symbols)

            self.logger.info(f"Added {len(symbols)} symbols: {[str(s) for s in symbols]}")

        except Exception as e:
            self.logger.error(f"Failed to add symbols: {e}")
            raise

    async def unsubscribe(self, symbols: List[Symbol]) -> None:
        """Remove symbols from subscription using enhanced symbol-channel mapping."""
        if not symbols:
            return

        # Filter to only remove symbols we actually have
        symbols_to_remove = [s for s in symbols if s in self._active_symbols]
        if not symbols_to_remove:
            return

        # Use unified subscription removal method with symbols parameter
        await self._ws_manager.unsubscribe(symbols=symbols_to_remove)

        # Remove from active state
        self._active_symbols.difference_update(symbols_to_remove)

        self.logger.info(f"Removed {len(symbols_to_remove)} symbols: {[str(s) for s in symbols_to_remove]}")

    def get_active_symbols(self) -> Set[Symbol]:
        """Get currently active symbols."""
        return self._active_symbols.copy()

    async def _handle_message(self, message: ParsedMessage) -> None:
        """
        Route parsed messages to appropriate handlers.
        
        Args:
            message: Parsed message from WebSocket
        """
        try:
            # Route based on message type using handler objects
            if message.message_type == MessageType.ORDERBOOK:
                if message.data:
                    # Convert message data to ParsedOrderbookUpdate format
                    from common.orderbook_diff_processor import ParsedOrderbookUpdate
                    # TODO:Incorrect
                    if isinstance(message.data, dict):
                        orderbook_update = ParsedOrderbookUpdate(
                            orderbook=message.data.get('orderbook'),
                            symbol=message.data.get('symbol')
                        )
                    else:
                        # Direct orderbook object with symbol attribute
                        orderbook_update = ParsedOrderbookUpdate(
                            orderbook=message.data,
                            symbol=getattr(message.data, 'symbol', message.symbol)
                        )
                    await self.handlers.handle_orderbook_diff(orderbook_update)
                        
            elif message.message_type == MessageType.TRADE:
                if message.data:
                    # Handle both single trade and list of trades
                    if isinstance(message.data, list):
                        for trade in message.data:
                            await self.handlers.handle_trade(trade)
                    else:
                        await self.handlers.handle_trade(message.data)
                        
            elif message.message_type == MessageType.BOOK_TICKER:
                if message.data:
                    await self.handlers.handle_book_ticker(message.data)
                        
            elif message.message_type == MessageType.SUBSCRIPTION_CONFIRM:
                # Use channel from ParsedMessage
                if message.channel:
                    self.logger.debug(f"Subscription confirmed for channel: {message.channel}")
                else:
                    self.logger.debug(f"Subscription incorrect {message.raw_data}")
                
            elif message.message_type == MessageType.ERROR:
                # Use channel from ParsedMessage for better error context
                if message.channel:
                    self.logger.error(f"WebSocket error on channel '{message.channel}': {message.raw_data}")
                else:
                    self.logger.error(f"WebSocket error: {message.raw_data}")
                
        except Exception as e:
            self.logger.error(f"Error handling parsed message: {e}")
            self.logger.debug(f"Full traceback: {traceback.format_exc()}")
    
    async def _connection_handler(self, state: ConnectionState) -> None:
        """
        Handle connection state changes.
        
        Args:
            state: New connection state
        """
        self.logger.info(f"WebSocket state changed: {state.name}")
        
        if self._state_change_handler:
            try:
                await self._state_change_handler(state)
            except Exception as e:
                self.logger.error(f"Error in state change handler: {e}")
    
    async def close(self) -> None:
        """Close WebSocket connection."""
        try:
            await self._ws_manager.close()
            self.logger.info(f"{self.exchange_name} public WebSocket closed")
        except Exception as e:
            self.logger.error(f"Error closing WebSocket: {e}")
    
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._ws_manager.is_connected()
    
    def get_performance_metrics(self) -> Dict[str, any]:
        """Get performance metrics."""
        return self._ws_manager.get_performance_metrics()