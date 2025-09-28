"""
Public WebSocket Mixin

Provides common functionality for public WebSocket handlers that process
market data streams (orderbooks, trades, tickers) without requiring authentication.

This mixin replaces the inheritance-based PublicWebSocketHandler with a
composition-based approach for cleaner, more testable code.

Design Principles:
- No authentication required
- Read-only market data operations  
- High-frequency optimized for sub-millisecond processing
- Clear separation from private trading operations
- Composition over inheritance
"""

from typing import Any, Dict, List, Optional, Set
from abc import ABC, abstractmethod

from infrastructure.logging import get_logger
from exchanges.structs.common import Symbol, OrderBook, Trade, BookTicker

# Import WebSocketMessageType from the base module
from infrastructure.networking.websocket.message_types import WebSocketMessageType


class PublicWebSocketMixin:
    """
    Mixin providing common public WebSocket functionality.
    
    Handles market data streams including:
    - Orderbook updates (bids/asks)
    - Trade feeds (executed trades)
    - Ticker data (24h stats, best bid/ask)
    - Symbol information updates
    
    Performance Requirements:
    - <50μs per orderbook update for HFT compliance
    - <30μs per trade update processing
    - <20μs per ticker update handling
    - Zero allocation in hot paths where possible
    
    Usage:
        class ExchangePublicHandler(PublicWebSocketMixin):
            def __init__(self):
                self.exchange_name = "exchange_name"
                self.setup_public_websocket()
                
            # Implement abstract methods...
    """
    
    def setup_public_websocket(self, subscribed_symbols: Optional[Set[Symbol]] = None):
        """
        Initialize public WebSocket mixin functionality.
        
        Args:
            subscribed_symbols: Set of symbols to subscribe to
            
        Call this from your handler's __init__ method.
        """
        # Initialize logger
        if not hasattr(self, 'logger'):
            self.logger = get_logger(f"websocket.public.{getattr(self, 'exchange_name', 'unknown')}")
        
        # Initialize state
        self.subscribed_symbols = subscribed_symbols or set()
        self._orderbook_callbacks: List[callable] = []
        self._trade_callbacks: List[callable] = []
        self._ticker_callbacks: List[callable] = []
        
        # Performance tracking
        self.message_count = 0
        self.is_connected = False
        
        self.logger.info("Public WebSocket mixin initialized",
                        exchange=getattr(self, 'exchange_name', 'unknown'))
    
    # Abstract methods that implementing classes must provide
    async def _parse_orderbook_update(self, raw_message: Any) -> Optional[OrderBook]:
        """
        Parse orderbook message from exchange-specific format.
        
        Args:
            raw_message: Raw WebSocket message
            
        Returns:
            OrderBook object or None if parsing failed
            
        Performance: Must complete in <50μs
        """
        raise NotImplementedError("Subclass must implement _parse_orderbook_update")
    
    async def _parse_trade_message(self, raw_message: Any) -> Optional[List[Trade]]:
        """
        Parse trade message from exchange-specific format.
        
        Args:
            raw_message: Raw WebSocket message
            
        Returns:
            List of Trade objects or None if parsing failed
            
        Performance: Must complete in <30μs
        """
        raise NotImplementedError("Subclass must implement _parse_trade_message")
    
    async def _parse_ticker_update(self, raw_message: Any) -> Optional[BookTicker]:
        """
        Parse ticker message from exchange-specific format.
        
        Args:
            raw_message: Raw WebSocket message
            
        Returns:
            BookTicker object or None if parsing failed
            
        Performance: Must complete in <20μs
        """
        raise NotImplementedError("Subclass must implement _parse_ticker_update")
    
    async def _detect_message_type(self, raw_message: Any) -> WebSocketMessageType:
        """
        Detect the type of incoming message.
        
        Args:
            raw_message: Raw WebSocket message
            
        Returns:
            WebSocketMessageType enum value
            
        Performance: Must complete in <10μs
        """
        raise NotImplementedError("Subclass must implement _detect_message_type")
    
    # Template method implementation
    async def _handle_message(self, raw_message: Any) -> None:
        """
        Handle incoming public WebSocket message.
        
        This method implements the template pattern by:
        1. Detecting message type
        2. Routing to appropriate parser
        3. Calling registered callbacks
        4. Updating internal state
        
        Args:
            raw_message: Raw WebSocket message
        """
        try:
            self.message_count += 1
            
            # Fast message type detection
            message_type = await self._detect_message_type(raw_message)
            
            # Route to appropriate handler based on type
            if message_type == WebSocketMessageType.ORDERBOOK:
                orderbook = await self._parse_orderbook_update(raw_message)
                if orderbook:
                    await self._on_orderbook_update(orderbook)
                    await self._notify_orderbook_callbacks(orderbook)
            
            elif message_type == WebSocketMessageType.TRADE:
                trades = await self._parse_trade_message(raw_message)
                if trades:
                    for trade in trades:
                        await self._on_trade_update(trade)
                        await self._notify_trade_callbacks(trade)
            
            elif message_type == WebSocketMessageType.TICKER:
                ticker = await self._parse_ticker_update(raw_message)
                if ticker:
                    await self._on_ticker_update(ticker)
                    await self._notify_ticker_callbacks(ticker)
            
            elif message_type == WebSocketMessageType.PING:
                await self._handle_ping(raw_message)
            
            elif message_type == WebSocketMessageType.SUBSCRIBE:
                await self._handle_subscription(raw_message)
            
            elif message_type == WebSocketMessageType.ERROR:
                await self._handle_exchange_error(raw_message)
            
            else:
                self.logger.warning(f"Unknown message type: {message_type}")
                
        except Exception as e:
            await self._handle_error(raw_message, e)
    
    # Event handlers (can be overridden by implementing classes)
    async def _on_orderbook_update(self, orderbook: OrderBook) -> None:
        """Handle orderbook update event."""
        pass
    
    async def _on_trade_update(self, trade: Trade) -> None:
        """Handle trade update event."""
        pass
    
    async def _on_ticker_update(self, ticker: BookTicker) -> None:
        """Handle ticker update event."""
        pass
    
    # Callback management for external consumers
    def add_orderbook_callback(self, callback: callable) -> None:
        """Add callback for orderbook updates."""
        self._orderbook_callbacks.append(callback)
    
    def add_trade_callback(self, callback: callable) -> None:
        """Add callback for trade updates."""
        self._trade_callbacks.append(callback)
    
    def add_ticker_callback(self, callback: callable) -> None:
        """Add callback for ticker updates."""
        self._ticker_callbacks.append(callback)
    
    # Internal callback notification
    async def _notify_orderbook_callbacks(self, orderbook: OrderBook) -> None:
        """Notify all registered orderbook callbacks."""
        for callback in self._orderbook_callbacks:
            try:
                await callback(orderbook)
            except Exception as e:
                self.logger.error(f"Error in orderbook callback: {e}")
    
    async def _notify_trade_callbacks(self, trade: Trade) -> None:
        """Notify all registered trade callbacks."""
        for callback in self._trade_callbacks:
            try:
                await callback(trade)
            except Exception as e:
                self.logger.error(f"Error in trade callback: {e}")
    
    async def _notify_ticker_callbacks(self, ticker: BookTicker) -> None:
        """Notify all registered ticker callbacks."""
        for callback in self._ticker_callbacks:
            try:
                await callback(ticker)
            except Exception as e:
                self.logger.error(f"Error in ticker callback: {e}")
    
    # Protocol-specific handlers (can be overridden)
    async def _handle_ping(self, raw_message: Any) -> None:
        """Handle ping messages (exchange-specific implementation)."""
        pass
    
    async def _handle_subscription(self, raw_message: Any) -> None:
        """Handle subscription confirmation messages."""
        pass
    
    async def _handle_exchange_error(self, raw_message: Any) -> None:
        """Handle exchange error messages."""
        self.logger.error(f"Exchange error received: {raw_message}")
    
    async def _handle_error(self, raw_message: Any, error: Exception) -> None:
        """Handle processing errors."""
        self.logger.error(f"Error processing message: {error}", 
                         message_preview=str(raw_message)[:100])
    
    # Symbol management
    def add_symbol(self, symbol: Symbol) -> None:
        """Add symbol to subscription set."""
        self.subscribed_symbols.add(symbol)
    
    def remove_symbol(self, symbol: Symbol) -> None:
        """Remove symbol from subscription set."""
        self.subscribed_symbols.discard(symbol)
    
    def get_subscribed_symbols(self) -> Set[Symbol]:
        """Get current set of subscribed symbols."""
        return self.subscribed_symbols.copy()
    
    # Health monitoring
    def get_health_status(self) -> Dict[str, Any]:
        """Get current health status of the public handler."""
        return {
            "is_connected": getattr(self, 'is_connected', False),
            "message_count": getattr(self, 'message_count', 0),
            "subscribed_symbols_count": len(getattr(self, 'subscribed_symbols', set())),
            "active_callbacks": {
                "orderbook": len(getattr(self, '_orderbook_callbacks', [])),
                "trade": len(getattr(self, '_trade_callbacks', [])),
                "ticker": len(getattr(self, '_ticker_callbacks', []))
            },
            "type": "public",
            "mixin_version": "1.0.0"
        }