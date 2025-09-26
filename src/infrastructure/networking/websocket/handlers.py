"""
WebSocket Handler Classes

Provides structured handler objects for WebSocket message processing.
Replaces multiple callback parameters with organized handler classes.

HFT COMPLIANT: Zero-overhead handler dispatch with optional callbacks.
"""

from typing import Optional, Callable, Awaitable, Dict
from dataclasses import dataclass

from exchanges.structs.common import Order, AssetBalance, Trade, OrderBook, BookTicker, Ticker, Kline, Position
from exchanges.structs.types import AssetName


@dataclass
class PublicWebsocketHandlers:
    """
    Handler object for public WebSocket message types.
    
    Mandatory class with optional handler callbacks for clean organization.
    Replaces multiple callback parameters with single handler object.
    """
    
    # Market data handlers
    orderbook_handler: Optional[Callable[[OrderBook], Awaitable[None]]] = None
    ticker_handler: Optional[Callable[[Ticker], Awaitable[None]]] = None
    trades_handler: Optional[Callable[[Trade], Awaitable[None]]] = None  
    kline_handler: Optional[Callable[[Kline], Awaitable[None]]] = None
    book_ticker_handler: Optional[Callable[[BookTicker], Awaitable[None]]] = None
    
    # System handlers
    connection_handler: Optional[Callable[[str, bool], Awaitable[None]]] = None  # (connection_type, is_connected)
    error_handler: Optional[Callable[[Exception], Awaitable[None]]] = None
    
    def __post_init__(self):
        """Validate handler configuration."""
        # All handlers are optional - allow empty configuration
        pass
    
    async def handle_orderbook(self, orderbook: OrderBook) -> None:
        """Handle orderbook update."""
        if self.orderbook_handler:
            await self.orderbook_handler(orderbook)
    
    async def handle_orderbook_diff(self, orderbook_update) -> None:
        """Handle orderbook diff update (used by some WebSocket implementations)."""
        if self.orderbook_handler:
            # Extract orderbook from diff update
            orderbook = getattr(orderbook_update, 'orderbook', orderbook_update)
            await self.orderbook_handler(orderbook)
    
    async def handle_ticker(self, ticker: Ticker) -> None:
        """Handle ticker update."""
        if self.ticker_handler:
            await self.ticker_handler(ticker)
    
    async def handle_trades(self, trade: Trade) -> None:
        """Handle trade data."""
        if self.trades_handler:
            await self.trades_handler(trade)
    
    async def handle_klines(self, kline: Kline) -> None:
        """Handle kline data."""
        if self.kline_handler:
            await self.kline_handler(kline)
            
    async def handle_book_ticker(self, book_ticker: BookTicker) -> None:
        """Handle book ticker data."""
        if self.book_ticker_handler:
            await self.book_ticker_handler(book_ticker)
    
    async def handle_connection(self, connection_type: str, is_connected: bool) -> None:
        """Handle connection status change."""
        if self.connection_handler:
            await self.connection_handler(connection_type, is_connected)
    
    async def handle_error(self, error: Exception) -> None:
        """Handle error."""
        if self.error_handler:
            await self.error_handler(error)


@dataclass 
class PrivateWebsocketHandlers:
    """
    Handler object for private WebSocket message types.
    
    Mandatory class with optional handler callbacks for clean organization.
    Replaces multiple callback parameters with single handler object.
    """
    
    # Trading data handlers
    order_handler: Optional[Callable[[Order], Awaitable[None]]] = None
    balance_handler: Optional[Callable[[Dict[AssetName, AssetBalance]], Awaitable[None]]] = None
    position_handler: Optional[Callable[[Position], Awaitable[None]]] = None
    execution_handler: Optional[Callable[[Trade], Awaitable[None]]] = None
    
    # System handlers
    connection_handler: Optional[Callable[[str, bool], Awaitable[None]]] = None  # (connection_type, is_connected)
    error_handler: Optional[Callable[[Exception], Awaitable[None]]] = None
    
    def __post_init__(self):
        """Validate handler configuration.""" 
        # All handlers are optional - allow empty configuration
        pass
    
    async def handle_order(self, order: Order) -> None:
        """Handle order update."""
        if self.order_handler:
            await self.order_handler(order)
    
    async def handle_balance(self, balances: Dict[AssetName, AssetBalance]) -> None:
        """Handle balance update."""
        if self.balance_handler:
            await self.balance_handler(balances)
    
    async def handle_position(self, position: Position) -> None:
        """Handle position update."""
        if self.position_handler:
            await self.position_handler(position)
            
    async def handle_execution(self, trade: Trade) -> None:
        """Handle execution report/trade data."""
        if self.execution_handler:
            await self.execution_handler(trade)
    
    async def handle_connection(self, connection_type: str, is_connected: bool) -> None:
        """Handle connection status change."""
        if self.connection_handler:
            await self.connection_handler(connection_type, is_connected)
    
    async def handle_error(self, error: Exception) -> None:
        """Handle error."""
        if self.error_handler:
            await self.error_handler(error)


__all__ = [
    'PublicWebsocketHandlers',
    'PrivateWebsocketHandlers'
]