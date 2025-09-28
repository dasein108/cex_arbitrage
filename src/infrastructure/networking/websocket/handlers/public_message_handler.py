"""
PublicMessageHandler - Specialized Handler for Public Market Data

Specialized message handler for public WebSocket messages including orderbook
updates, trade feeds, ticker data, and system messages. Extends BaseMessageHandler
with public market data specific routing and processing.

Key Features:
- Specialized routing for public message types (orderbook, trades, ticker)
- Integration with PublicWebSocketMixin callback system
- Performance optimized for market data processing
- Ping/pong and subscription confirmation handling
- HFT optimized: <50μs orderbook, <30μs trades, <20μs ticker

HFT COMPLIANCE: Sub-millisecond processing for all market data types.
"""

import asyncio
from typing import Any, Dict, List, Optional, Callable, Awaitable

from .base_message_handler import BaseMessageHandler
from infrastructure.networking.websocket.message_types import WebSocketMessageType
from infrastructure.networking.websocket.mixins import PublicWebSocketMixin
from infrastructure.logging import get_logger
from exchanges.structs.common import OrderBook, Trade, BookTicker


class PublicMessageHandler(BaseMessageHandler, PublicWebSocketMixin):
    """
    Specialized handler for public market data messages.
    
    Extends BaseMessageHandler with public-specific message routing and
    integrates with PublicWebSocketMixin for callback management. Handles
    orderbook updates, trade feeds, ticker data, and system messages.
    
    Message Types Handled:
    - ORDERBOOK: Orderbook snapshots and updates (bids/asks)
    - TRADE: Trade feeds (executed trades)
    - TICKER: Ticker data (24h stats, best bid/ask)
    - PING: Heartbeat/ping messages
    - SUBSCRIBE: Subscription confirmations
    - ERROR: Error messages
    
    Performance Specifications:
    - Orderbook routing: <5μs, processing target depends on exchange
    - Trade routing: <3μs, processing target depends on exchange
    - Ticker routing: <2μs, processing target depends on exchange
    """
    
    def __init__(self, exchange_name: str, subscribed_symbols=None, logger=None):
        """
        Initialize public message handler.
        
        Args:
            exchange_name: Name of the exchange for logging and metrics
            subscribed_symbols: Optional set of symbols for subscription management
            logger: Optional logger instance for dependency injection
        """
        # Initialize both parent classes
        BaseMessageHandler.__init__(self, exchange_name, logger)
        PublicWebSocketMixin.__init__(self, subscribed_symbols)
        
        # Public-specific performance targets (in microseconds)
        self.orderbook_routing_target_us = 5
        self.trade_routing_target_us = 3
        self.ticker_routing_target_us = 2
        
        # Message-specific metrics
        self.orderbook_count = 0
        self.trade_count = 0
        self.ticker_count = 0
        self.ping_count = 0
        self.subscription_count = 0
        self.error_count = 0
        
        self.logger.info(f"PublicMessageHandler initialized for {exchange_name}",
                        exchange=exchange_name,
                        handler_type="public",
                        performance_tracking=True)
    
    async def _route_message(self, message_type: WebSocketMessageType, raw_message: Any) -> None:
        """
        Route public messages to appropriate parsers and callbacks.
        
        Performance-optimized routing for public market data with specialized
        handling for each message type. Integrates with PublicWebSocketMixin
        callback system for data distribution.
        
        Args:
            message_type: Detected message type
            raw_message: Raw message from WebSocket
            
        Raises:
            ValueError: If message type is not supported for public handler
        """
        if message_type == WebSocketMessageType.ORDERBOOK:
            await self._handle_orderbook_message(raw_message)
            
        elif message_type == WebSocketMessageType.TRADE:
            await self._handle_trade_message(raw_message)
            
        elif message_type == WebSocketMessageType.TICKER:
            await self._handle_ticker_message(raw_message)
            
        elif message_type == WebSocketMessageType.PING:
            await self._handle_ping_message(raw_message)
            
        elif message_type == WebSocketMessageType.SUBSCRIBE:
            await self._handle_subscription_message(raw_message)
            
        elif message_type == WebSocketMessageType.ERROR:
            await self._handle_error_message(raw_message)
            
        else:
            # Track unsupported message types
            self.logger.warning("Unsupported message type in public handler",
                              message_type=str(message_type),
                              exchange=self.exchange_name)
            
            self.logger.metric("ws_public_handler_unsupported_message", 1,
                             tags={"exchange": self.exchange_name, 
                                   "message_type": str(message_type)})
            
            raise ValueError(f"Unsupported message type for public handler: {message_type}")
    
    # Message-specific handlers
    
    async def _handle_orderbook_message(self, raw_message: Any) -> None:
        """
        Handle orderbook update messages.
        
        Parses orderbook updates and triggers registered callbacks through
        PublicWebSocketMixin. Performance target varies by exchange implementation.
        
        Args:
            raw_message: Raw orderbook message
        """
        self.orderbook_count += 1
        
        try:
            # Parse orderbook using exchange-specific implementation
            orderbook = await self._parse_orderbook_update(raw_message)
            
            if orderbook:
                # Trigger callbacks through PublicWebSocketMixin
                await self._notify_orderbook_callbacks(orderbook)
                
                self.logger.debug("Orderbook update processed",
                                exchange=self.exchange_name,
                                symbol=str(orderbook.symbol) if hasattr(orderbook, 'symbol') else 'unknown',
                                bids_count=len(orderbook.bids) if hasattr(orderbook, 'bids') else 0,
                                asks_count=len(orderbook.asks) if hasattr(orderbook, 'asks') else 0)
            else:
                self.logger.warning("Orderbook parsing returned None",
                                  exchange=self.exchange_name)
                
        except Exception as e:
            self.logger.error("Error processing orderbook message",
                            error_type=type(e).__name__,
                            error_message=str(e),
                            exchange=self.exchange_name)
            
            self.logger.metric("ws_public_handler_orderbook_errors", 1,
                             tags={"exchange": self.exchange_name})
            raise
    
    async def _handle_trade_message(self, raw_message: Any) -> None:
        """
        Handle trade feed messages.
        
        Parses trade data and triggers registered callbacks through
        PublicWebSocketMixin. Performance target varies by exchange implementation.
        
        Args:
            raw_message: Raw trade message
        """
        self.trade_count += 1
        
        try:
            # Parse trades using exchange-specific implementation
            trades = await self._parse_trade_message(raw_message)
            
            if trades:
                # Handle both single trade and list of trades
                if isinstance(trades, list):
                    for trade in trades:
                        await self._notify_trade_callbacks(trade)
                else:
                    await self._notify_trade_callbacks(trades)
                
                trade_count = len(trades) if isinstance(trades, list) else 1
                self.logger.debug("Trade message processed",
                                exchange=self.exchange_name,
                                trades_count=trade_count)
            else:
                self.logger.warning("Trade parsing returned None",
                                  exchange=self.exchange_name)
                
        except Exception as e:
            self.logger.error("Error processing trade message",
                            error_type=type(e).__name__,
                            error_message=str(e),
                            exchange=self.exchange_name)
            
            self.logger.metric("ws_public_handler_trade_errors", 1,
                             tags={"exchange": self.exchange_name})
            raise
    
    async def _handle_ticker_message(self, raw_message: Any) -> None:
        """
        Handle ticker data messages.
        
        Parses ticker data and triggers registered callbacks through
        PublicWebSocketMixin. Performance target varies by exchange implementation.
        
        Args:
            raw_message: Raw ticker message
        """
        self.ticker_count += 1
        
        try:
            # Parse ticker using exchange-specific implementation
            ticker = await self._parse_ticker_update(raw_message)
            
            if ticker:
                # Trigger callbacks through PublicWebSocketMixin
                await self._notify_ticker_callbacks(ticker)
                
                self.logger.debug("Ticker update processed",
                                exchange=self.exchange_name,
                                symbol=str(ticker.symbol) if hasattr(ticker, 'symbol') else 'unknown')
            else:
                self.logger.warning("Ticker parsing returned None",
                                  exchange=self.exchange_name)
                
        except Exception as e:
            self.logger.error("Error processing ticker message",
                            error_type=type(e).__name__,
                            error_message=str(e),
                            exchange=self.exchange_name)
            
            self.logger.metric("ws_public_handler_ticker_errors", 1,
                             tags={"exchange": self.exchange_name})
            raise
    
    async def _handle_ping_message(self, raw_message: Any) -> None:
        """
        Handle ping/heartbeat messages.
        
        Processes ping messages and responds if required by the exchange.
        
        Args:
            raw_message: Raw ping message
        """
        self.ping_count += 1
        
        try:
            # Handle ping using PublicWebSocketMixin
            await self._handle_ping(raw_message)
            
            self.logger.debug("Ping message handled",
                            exchange=self.exchange_name)
            
        except Exception as e:
            self.logger.error("Error handling ping message",
                            error_type=type(e).__name__,
                            error_message=str(e),
                            exchange=self.exchange_name)
            
            self.logger.metric("ws_public_handler_ping_errors", 1,
                             tags={"exchange": self.exchange_name})
            # Don't re-raise ping errors as they're not critical
    
    async def _handle_subscription_message(self, raw_message: Any) -> None:
        """
        Handle subscription confirmation messages.
        
        Processes subscription confirmations and updates subscription state.
        
        Args:
            raw_message: Raw subscription confirmation message
        """
        self.subscription_count += 1
        
        try:
            # Handle subscription confirmation
            await self._handle_subscription_confirmation(raw_message)
            
            self.logger.debug("Subscription confirmation handled",
                            exchange=self.exchange_name)
            
        except Exception as e:
            self.logger.error("Error handling subscription message",
                            error_type=type(e).__name__,
                            error_message=str(e),
                            exchange=self.exchange_name)
            
            self.logger.metric("ws_public_handler_subscription_errors", 1,
                             tags={"exchange": self.exchange_name})
            # Don't re-raise subscription errors as they're not critical
    
    async def _handle_error_message(self, raw_message: Any) -> None:
        """
        Handle error messages from the exchange.
        
        Processes error messages and logs appropriate warnings or errors.
        
        Args:
            raw_message: Raw error message
        """
        try:
            # Parse and log error message
            error_info = await self._parse_error_message(raw_message)
            
            self.logger.warning("Exchange error message received",
                              exchange=self.exchange_name,
                              error_info=error_info)
            
            self.logger.metric("ws_public_handler_exchange_errors", 1,
                             tags={"exchange": self.exchange_name})
            
        except Exception as e:
            self.logger.error("Error processing error message",
                            error_type=type(e).__name__,
                            error_message=str(e),
                            exchange=self.exchange_name)
    
    # Abstract methods that exchanges must implement
    
    async def _parse_orderbook_update(self, raw_message: Any) -> Optional[OrderBook]:
        """
        Parse orderbook update from raw message.
        
        Exchange-specific implementation must parse the raw message into
        an OrderBook structure. Performance target varies by exchange.
        
        Args:
            raw_message: Raw orderbook message
            
        Returns:
            OrderBook instance or None if parsing failed
        """
        # Default implementation - exchanges should override
        self.logger.warning("Using default orderbook parser - should be overridden",
                          exchange=self.exchange_name)
        return None
    
    async def _parse_trade_message(self, raw_message: Any) -> Optional[List[Trade]]:
        """
        Parse trade data from raw message.
        
        Exchange-specific implementation must parse the raw message into
        Trade structures. Performance target varies by exchange.
        
        Args:
            raw_message: Raw trade message
            
        Returns:
            List of Trade instances or None if parsing failed
        """
        # Default implementation - exchanges should override
        self.logger.warning("Using default trade parser - should be overridden",
                          exchange=self.exchange_name)
        return None
    
    async def _parse_ticker_update(self, raw_message: Any) -> Optional[BookTicker]:
        """
        Parse ticker data from raw message.
        
        Exchange-specific implementation must parse the raw message into
        a BookTicker structure. Performance target varies by exchange.
        
        Args:
            raw_message: Raw ticker message
            
        Returns:
            BookTicker instance or None if parsing failed
        """
        # Default implementation - exchanges should override
        self.logger.warning("Using default ticker parser - should be overridden",
                          exchange=self.exchange_name)
        return None
    
    async def _parse_error_message(self, raw_message: Any) -> Dict[str, Any]:
        """
        Parse error message from raw message.
        
        Exchange-specific implementation should parse the raw message into
        a structured error format.
        
        Args:
            raw_message: Raw error message
            
        Returns:
            Dictionary with error information
        """
        # Default implementation
        return {"raw_error": str(raw_message)}
    
    # Callback notification methods (delegated to PublicWebSocketMixin)
    
    async def _notify_orderbook_callbacks(self, orderbook: OrderBook) -> None:
        """Notify registered orderbook callbacks."""
        if hasattr(self, 'orderbook_callbacks') and self.orderbook_callbacks:
            await asyncio.gather(*[
                callback(orderbook) for callback in self.orderbook_callbacks
            ], return_exceptions=True)
    
    async def _notify_trade_callbacks(self, trade: Trade) -> None:
        """Notify registered trade callbacks."""
        if hasattr(self, 'trade_callbacks') and self.trade_callbacks:
            await asyncio.gather(*[
                callback(trade) for callback in self.trade_callbacks
            ], return_exceptions=True)
    
    async def _notify_ticker_callbacks(self, ticker: BookTicker) -> None:
        """Notify registered ticker callbacks."""
        if hasattr(self, 'ticker_callbacks') and self.ticker_callbacks:
            await asyncio.gather(*[
                callback(ticker) for callback in self.ticker_callbacks
            ], return_exceptions=True)
    
    # Performance metrics override
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics including public-specific statistics.
        
        Returns:
            Dictionary with performance and message statistics
        """
        base_metrics = super().get_performance_metrics()
        
        # Add public-specific metrics
        base_metrics.update({
            'handler_type': 'public',
            'message_breakdown': {
                'orderbook_count': self.orderbook_count,
                'trade_count': self.trade_count,
                'ticker_count': self.ticker_count,
                'ping_count': self.ping_count,
                'subscription_count': self.subscription_count
            },
            'callback_counts': {
                'orderbook_callbacks': len(self.orderbook_callbacks) if hasattr(self, 'orderbook_callbacks') else 0,
                'trade_callbacks': len(self.trade_callbacks) if hasattr(self, 'trade_callbacks') else 0,
                'ticker_callbacks': len(self.ticker_callbacks) if hasattr(self, 'ticker_callbacks') else 0
            }
        })
        
        return base_metrics