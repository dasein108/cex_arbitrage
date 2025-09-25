"""
WebSocket Handler Objects Usage Example

Demonstrates how to use the new PublicWebsocketHandlers and PrivateWebsocketHandlers
classes to organize WebSocket message processing.

This replaces the old pattern of multiple callback parameters with structured handler objects.
"""

import asyncio
from typing import Dict

from infrastructure.networking.websocket.handlers import PublicWebsocketHandlers, PrivateWebsocketHandlers
from exchanges.structs.common import Trade, BookTicker, Order, AssetBalance
from exchanges.structs.types import AssetName
from common.orderbook_diff_processor import ParsedOrderbookUpdate
from config.structs import ExchangeConfig, ExchangeCredentials


class ExampleTrader:
    """Example trader class showing how to use handler objects."""
    
    def __init__(self):
        self.received_orderbooks = []
        self.received_trades = []
        self.received_tickers = []
        self.received_orders = []
        self.received_balances = []
        self.received_private_trades = []

    # Public WebSocket Handlers
    async def handle_orderbook_update(self, orderbook_update: ParsedOrderbookUpdate) -> None:
        """Handle orderbook difference updates."""
        print(f"📊 Orderbook update for {orderbook_update.symbol}")
        self.received_orderbooks.append(orderbook_update)
        
        # Your trading logic here
        # - Check for arbitrage opportunities
        # - Update internal orderbook state
        # - Trigger orders based on price levels
    
    async def handle_trade_data(self, trade: Trade) -> None:
        """Handle public trade data."""
        print(f"💱 Trade: {trade.symbol} {trade.side} {trade.quantity}@{trade.price}")
        self.received_trades.append(trade)
        
        # Your trading logic here
        # - Monitor market direction
        # - Track volume patterns
        # - Detect large trades
    
    async def handle_book_ticker(self, book_ticker: BookTicker) -> None:
        """Handle book ticker updates."""
        print(f"📈 Ticker: {book_ticker.symbol} Bid:{book_ticker.bid_price} Ask:{book_ticker.ask_price}")
        self.received_tickers.append(book_ticker)
        
        # Your trading logic here
        # - Track spread changes
        # - Monitor best bid/ask
        # - Calculate fair value
    
    # Private WebSocket Handlers
    async def handle_order_update(self, order: Order) -> None:
        """Handle order status updates.""" 
        print(f"📋 Order Update: {order.order_id} - {order.status} - {order.filled_quantity}/{order.quantity}")
        self.received_orders.append(order)
        
        # Your trading logic here
        # - Update order tracking
        # - Handle partial fills
        # - Manage position size
    
    async def handle_balance_update(self, balances: Dict[AssetName, AssetBalance]) -> None:
        """Handle account balance updates."""
        print(f"💰 Balance Update: {len(balances)} assets")
        self.received_balances.append(balances)
        
        # Your trading logic here
        # - Update available funds
        # - Calculate position sizes
        # - Risk management checks
    
    async def handle_private_trade(self, trade: Trade) -> None:
        """Handle private trade executions."""
        print(f"✅ Trade Executed: {trade.symbol} {trade.side} {trade.quantity}@{trade.price}")
        self.received_private_trades.append(trade)
        
        # Your trading logic here
        # - Update positions
        # - Calculate P&L
        # - Portfolio rebalancing


async def public_websocket_example():
    """Example of using PublicWebsocketHandlers."""
    
    trader = ExampleTrader()
    
    # Create handler object with optional callbacks
    public_handlers = PublicWebsocketHandlers(
        orderbook_diff_handler=trader.handle_orderbook_update,
        trades_handler=trader.handle_trade_data,
        book_ticker_handler=trader.handle_book_ticker
    )
    
    print("✅ PublicWebsocketHandlers created with all handlers")
    
    # You can also create with only some handlers
    minimal_handlers = PublicWebsocketHandlers(
        trades_handler=trader.handle_trade_data  # Only handle trades
    )
    
    print("✅ PublicWebsocketHandlers created with minimal handlers")
    
    # Example of using the handlers directly
    from exchanges.structs.common import Symbol, Trade, Side
    from exchanges.structs.types import AssetName
    
    # Simulate trade data
    test_trade = Trade(
        symbol=Symbol(base=AssetName("BTC"), quote=AssetName("USDT"), is_futures=False),
        price=50000.0,
        quantity=0.1,
        quote_quantity=5000.0,
        side=Side.BUY,
        timestamp=1642000000000,
        trade_id="12345",
        is_maker=False
    )
    
    # Call handler directly
    await public_handlers.handle_trades(test_trade)
    print(f"📊 Processed {len(trader.received_trades)} trades")


async def private_websocket_example():
    """Example of using PrivateWebsocketHandlers."""
    
    trader = ExampleTrader()
    
    # Create handler object with optional callbacks  
    private_handlers = PrivateWebsocketHandlers(
        order_handler=trader.handle_order_update,
        balance_handler=trader.handle_balance_update,
        trade_handler=trader.handle_private_trade
    )
    
    print("✅ PrivateWebsocketHandlers created with all handlers")
    
    # You can create empty handlers (all optional)
    empty_handlers = PrivateWebsocketHandlers()
    print("✅ PrivateWebsocketHandlers created with no handlers (all optional)")
    
    # Example of using handlers directly
    from exchanges.structs.common import Order, OrderStatus, OrderType
    from exchanges.structs.types import OrderId
    
    # Simulate order update
    test_order = Order(
        symbol=Symbol(base=AssetName("BTC"), quote=AssetName("USDT"), is_futures=False),
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=0.1,
        price=49000.0,
        filled_quantity=0.05,
        remaining_quantity=0.05,
        order_id=OrderId("order_123"),
        status=OrderStatus.PARTIALLY_FILLED,
        timestamp=1642000000000
    )
    
    # Call handler directly
    await private_handlers.handle_order(test_order)
    print(f"📋 Processed {len(trader.received_orders)} order updates")


async def websocket_interface_usage_example():
    """Example of how WebSocket interfaces would use handlers."""
    
    trader = ExampleTrader()
    
    # Create handler objects
    public_handlers = PublicWebsocketHandlers(
        trades_handler=trader.handle_trade_data,
        book_ticker_handler=trader.handle_book_ticker
    )
    
    private_handlers = PrivateWebsocketHandlers(
        order_handler=trader.handle_order_update,
        balance_handler=trader.handle_balance_update
    )
    
    # This is how you would initialize WebSocket interfaces:
    """
    # OLD WAY (multiple parameters):
    public_ws = MexcPublicSpotWebsocket(
        config=config,
        logger=logger,
        trades_handler=trader.handle_trade_data,
        book_ticker_handler=trader.handle_book_ticker,
        orderbook_diff_handler=trader.handle_orderbook_update
    )
    
    # NEW WAY (handler object):
    public_ws = MexcPublicSpotWebsocket(
        config=config,
        handlers=public_handlers,
        logger=logger
    )
    
    # OLD WAY (multiple parameters):
    private_ws = MexcPrivateSpotWebsocket(
        config=config,
        logger=logger,
        order_handler=trader.handle_order_update,
        balance_handler=trader.handle_balance_update,
        trade_handler=trader.handle_private_trade
    )
    
    # NEW WAY (handler object):  
    private_ws = MexcPrivateSpotWebsocket(
        config=config,
        handlers=private_handlers,
        logger=logger
    )
    """
    
    print("✅ Handler objects provide clean, organized WebSocket initialization")


async def main():
    """Run all examples."""
    print("🚀 WebSocket Handler Objects Example")
    print("=" * 50)
    
    print("\n1. Public WebSocket Handlers Example:")
    await public_websocket_example()
    
    print("\n2. Private WebSocket Handlers Example:")
    await private_websocket_example()
    
    print("\n3. WebSocket Interface Usage Example:")
    await websocket_interface_usage_example()
    
    print("\n✅ All examples completed successfully!")
    print("\nKey Benefits:")
    print("  • Cleaner constructor signatures")
    print("  • Better organization of callback functions")
    print("  • Type safety for handler objects")
    print("  • Optional handlers - only set what you need")
    print("  • Easier to pass handlers between components")


if __name__ == "__main__":
    asyncio.run(main())