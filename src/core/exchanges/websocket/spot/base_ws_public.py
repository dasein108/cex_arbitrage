"""
Base Public WebSocket Interface - Refactored

Clean base class for public WebSocket implementations using the new
strategy-driven architecture.

HFT COMPLIANCE: Optimized for sub-millisecond message processing.
"""

import logging
from typing import List, Dict, Optional, Callable, Awaitable, Set
from abc import ABC

from exchanges.consts import DEFAULT_PUBLIC_WEBSOCKET_CHANNELS
from structs.common import Symbol, OrderBook, Trade, BookTicker
from core.config.structs import ExchangeConfig
from core.transport.websocket.structs import ConnectionState, MessageType, ParsedMessage, PublicWebsocketChannelType
import traceback

class BaseExchangePublicWebsocketInterface(ABC):
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
        orderbook_diff_handler: Optional[Callable[[OrderBook, Symbol], Awaitable[None]]] = None,
        trades_handler: Optional[Callable[[Symbol, List[Trade]], Awaitable[None]]] = None,
        book_ticker_handler: Optional[Callable[[Symbol, BookTicker], Awaitable[None]]] = None,
        state_change_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None,
    ):
        """
        Initialize base public WebSocket.
        
        Args:
            config: Exchange configuration
            orderbook_diff_handler: Callback for orderbook updates
            trades_handler: Callback for trade updates
            book_ticker_handler: Callback for book ticker updates
            state_change_handler: Callback for connection state changes
        """
        self.config = config
        self.exchange_name = config.name.lower()
        
        # Store event handlers
        self._orderbook_handler = orderbook_diff_handler
        self._trades_handler = trades_handler
        self._book_ticker_handler = book_ticker_handler
        self._state_change_handler = state_change_handler
        
        # Logger
        self.logger = logging.getLogger(f"{__name__}.{self.exchange_name}_public")
        
        # Create WebSocket manager using dependency injection
        from core.transport.websocket.utils import create_websocket_manager
        
        self._ws_manager = create_websocket_manager(
            exchange_config=config,
            is_private=False,
            message_handler=self._handle_parsed_message,
            state_change_handler=self._handle_state_change
        )

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
            await self._ws_manager.initialize(symbols=symbols, channels=channels)
            self.logger.info(f"WebSocket initialized for {self.exchange_name} with {len(symbols)} symbols")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize WebSocket: {e}")
            raise
    
    async def add_symbols(self, symbols: List[Symbol]) -> None:
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

    async def remove_symbols(self, symbols: List[Symbol]) -> None:
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

    async def _handle_parsed_message(self, message: ParsedMessage) -> None:
        """
        Route parsed messages to appropriate handlers.
        
        Args:
            message: Parsed message from WebSocket
        """
        try:
            # Route based on message type
            if message.message_type == MessageType.ORDERBOOK:
                if self._orderbook_handler and message.data:
                    # Handle both dict format and direct object format
                    if isinstance(message.data, dict):
                        orderbook = message.data.get('orderbook')
                        symbol = message.data.get('symbol')
                        if orderbook and symbol:
                            await self._orderbook_handler(orderbook, symbol)
                    else:
                        # Direct orderbook object with symbol attribute
                        if hasattr(message.data, 'symbol'):
                            await self._orderbook_handler(message.data, message.symbol)
                        
            elif message.message_type == MessageType.TRADE:
                if self._trades_handler and message.data:
                    # Handle both dict format and direct list format
                    if isinstance(message.data, dict):
                        trades = message.data.get('trades', [])
                        symbol = message.data.get('symbol')
                        if trades and symbol:
                            await self._trades_handler(symbol, trades)
                    elif isinstance(message.data, list):
                        # Direct trades list - get symbol from first trade
                        if message.data and hasattr(message.data[0], 'symbol'):
                            await self._trades_handler(message.data[0].symbol, message.data)
                        
            elif message.message_type == MessageType.BOOK_TICKER:
                if self._book_ticker_handler and message.data:
                    # Handle both dict format and direct object format
                    if isinstance(message.data, dict):
                        book_ticker = message.data.get('book_ticker')
                        symbol = message.data.get('symbol')
                        if book_ticker and symbol:
                            await self._book_ticker_handler(symbol, book_ticker)
                    else:
                        # Direct BookTicker object with symbol attribute
                        if hasattr(message.data, 'symbol'):
                            await self._book_ticker_handler(message.data.symbol, message.data)
                        
            elif message.message_type == MessageType.SUBSCRIPTION_CONFIRM:
                # Use channel from ParsedMessage
                if message.channel:
                    self.logger.debug(f"Subscription confirmed for channel: {message.channel}")
                else:
                    self.logger.debug(f"Subscription incorrect {message.raw_data}")
                
            elif message.message_type == MessageType.ERROR:
                # Use channel from ParsedMessage for better error context
                if message.channel:
                    self.logger.error(f"WebSocket error on channel '{message.channel}': {message.data}")
                    traceback.print_exc()
                else:
                    self.logger.error(f"WebSocket error: {message.data}")
                
        except Exception as e:
            self.logger.error(f"Error handling parsed message: {e}")
            self.logger.debug(f"Full traceback: {traceback.format_exc()}")
    
    async def _handle_state_change(self, state: ConnectionState) -> None:
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