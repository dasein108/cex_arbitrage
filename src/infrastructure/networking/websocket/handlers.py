"""
WebSocket Handler Classes

Provides structured handler objects for WebSocket message processing.
Replaces multiple callback parameters with organized handler classes.

HFT COMPLIANT: Zero-overhead handler dispatch with optional callbacks.
"""

from typing import Optional, Callable, Awaitable, Dict
from dataclasses import dataclass

from exchanges.structs.common import Order, AssetBalance, Trade, OrderBook, BookTicker
from exchanges.structs.types import AssetName
from common.orderbook_diff_processor import ParsedOrderbookUpdate


@dataclass
class PublicWebsocketHandlers:
    """
    Handler object for public WebSocket message types.
    
    Mandatory class with optional handler callbacks for clean organization.
    Replaces multiple callback parameters with single handler object.
    """
    
    orderbook_diff_handler: Optional[Callable[[ParsedOrderbookUpdate], Awaitable[None]]] = None
    trades_handler: Optional[Callable[[Trade], Awaitable[None]]] = None  
    book_ticker_handler: Optional[Callable[[BookTicker], Awaitable[None]]] = None
    
    def __post_init__(self):
        """Validate handler configuration."""
        # All handlers are optional - allow empty configuration
        pass
    
    async def handle_orderbook_diff(self, orderbook_update: ParsedOrderbookUpdate) -> None:
        """Handle orderbook difference update."""
        if self.orderbook_diff_handler:
            await self.orderbook_diff_handler(orderbook_update)
    
    async def handle_trades(self, trade: Trade) -> None:
        """Handle trade data."""
        if self.trades_handler:
            await self.trades_handler(trade)
            
    async def handle_book_ticker(self, book_ticker: BookTicker) -> None:
        """Handle book ticker data."""
        if self.book_ticker_handler:
            await self.book_ticker_handler(book_ticker)


@dataclass 
class PrivateWebsocketHandlers:
    """
    Handler object for private WebSocket message types.
    
    Mandatory class with optional handler callbacks for clean organization.
    Replaces multiple callback parameters with single handler object.
    """
    
    order_handler: Optional[Callable[[Order], Awaitable[None]]] = None
    balance_handler: Optional[Callable[[Dict[AssetName, AssetBalance]], Awaitable[None]]] = None
    trade_handler: Optional[Callable[[Trade], Awaitable[None]]] = None
    
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
            
    async def handle_trade(self, trade: Trade) -> None:
        """Handle private trade data."""
        if self.trade_handler:
            await self.trade_handler(trade)


__all__ = [
    'PublicWebsocketHandlers',
    'PrivateWebsocketHandlers'
]