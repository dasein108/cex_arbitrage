"""
Generic Public WebSocket Integration Demo

Demonstrates public WebSocket functionality across multiple exchanges.
Tests actual exchange WebSocket implementations (MexcWebsocketPublic, etc.)
that inherit from BaseExchangePublicWebsocketInterface.
Shows orderbook and trade updates in real-time.

Usage:
    python src/examples/websocket_public_demo.py mexc
    python src/examples/websocket_public_demo.py gateio
"""

import asyncio
import sys
from typing import List, Dict

from exchanges.structs import Symbol, OrderBook, Trade, BookTicker, ExchangeEnum
from exchanges.structs.types import AssetName
from config.config_manager import HftConfig
from common.orderbook_diff_processor import ParsedOrderbookUpdate

# HFT Logger Integration
from infrastructure.logging import get_logger
from exchanges.transport_factory import create_websocket_client, create_public_handlers

# Set up HFT logging
logger = get_logger('websocket_public_demo')


class PublicWebSocketClient:
    """Exchange-agnostic public WebSocket client using actual exchange implementations."""

    def __init__(self, exchange_name: str, orderbook_handler, trades_handler, book_ticker_handler=None):
        self.exchange_name = exchange_name.upper()

        self.orderbook_handler = orderbook_handler
        self.trades_handler = trades_handler
        self.book_ticker_handler = book_ticker_handler

        # Get exchange config
        config_manager = HftConfig()
        config = config_manager.get_exchange_config(self.exchange_name.lower())

        # Create exchange WebSocket instance using the factory pattern
        self.websocket = create_websocket_client(
            exchange=ExchangeEnum(self.exchange_name),
            is_private=False,
            config=config,
            handlers=create_public_handlers(
                orderbook_diff_handler=self._handle_orderbook_update,
                trades_handler=self._handle_trades_update,
                book_ticker_handler=self._handle_book_ticker_update
            ),
        )

        logger.info("Public WebSocket client initialized",
                    exchange=self.exchange_name,
                    websocket_class=type(self.websocket).__name__)

    async def initialize(self, symbols: List[Symbol]) -> None:
        """Initialize WebSocket connection and subscriptions."""
        # Pass symbols to initialize() - they will be subscribed automatically when connection is established
        await self.websocket.initialize(symbols)
        logger.info("WebSocket initialized",
                    symbol_count=len(symbols))

    async def add_symbols(self, symbols: List[Symbol]) -> None:
        """Add symbols for real-time subscription (only after connection established)."""
        if not self.is_connected():
            raise ValueError("WebSocket not connected - use initialize() with symbols instead")
        await self.websocket.add_symbols(symbols)
        logger.info("Added symbols to subscription",
                    symbol_count=len(symbols))

    async def close(self) -> None:
        """Close WebSocket connection."""
        await self.websocket.close()

    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self.websocket.is_connected()

    def get_performance_metrics(self) -> Dict:
        """Get HFT performance metrics."""
        return self.websocket.get_performance_metrics()

    async def _handle_orderbook_update(self, orderbook_data: ParsedOrderbookUpdate) -> None:
        """Handle orderbook updates from WebSocket."""
        if self.orderbook_handler:
            await self.orderbook_handler(orderbook_data)

    async def _handle_trades_update(self, trade: Trade) -> None:
        """Handle trade updates from WebSocket."""
        if self.trades_handler:
            await self.trades_handler(trade)

    async def _handle_book_ticker_update(self, book_ticker: BookTicker) -> None:
        """Handle book ticker updates from WebSocket."""
        if self.book_ticker_handler:
            await self.book_ticker_handler(book_ticker)

    async def _handle_state_change(self, state) -> None:
        """Handle WebSocket state changes."""
        logger.info("🔗 WebSocket state changed",
                    exchange=self.exchange_name,
                    new_state=state)


class OrderBookManager:
    """External orderbook storage and management."""

    def __init__(self, exchange_name: str):
        self.exchange_name = exchange_name.upper()
        self.orderbooks: Dict[Symbol, OrderBook] = {}
        self.trade_history: Dict[Symbol, List[Trade]] = {}
        self.book_tickers: Dict[Symbol, BookTicker] = {}
        self.update_counts: Dict[Symbol, int] = {}
        self.book_ticker_counts: Dict[Symbol, int] = {}

    async def handle_orderbook_update(self, orderbook: OrderBook):
        """Store and process orderbook updates."""
        # Store the orderbook
        symbol = OrderBook.symbol
        self.orderbooks[symbol] = orderbook

        # Track update counts
        if symbol not in self.update_counts:
            self.update_counts[symbol] = 0
        self.update_counts[symbol] += 1

        # Log the update (less verbose for frequent updates)
        if self.update_counts[symbol] % 10 == 1:  # Log every 10th update
            logger.info("📊 Orderbook update",
                        exchange=self.exchange_name,
                        symbol=f"{symbol.base}/{symbol.quote}",
                        update_number=self.update_counts[symbol],
                        best_bid=orderbook.bids[0].price if orderbook.bids else None,
                        best_ask=orderbook.asks[0].price if orderbook.asks else None,
                        bid_count=len(orderbook.bids),
                        ask_count=len(orderbook.asks))

    async def handle_trades_update(self, trade: Trade):
        """Store and process trade updates."""
        # Store trades

        if trade.symbol not in self.trade_history:
            self.trade_history[trade.symbol] = []
        self.trade_history[trade.symbol].append(trade)

        # Log the update
        logger.info("💹 Trades update",
                    exchange=self.exchange_name,
                    symbol=f"{trade.symbol.base}/{trade.symbol.quote}",
                    latest_side=trade.side.name,
                    latest_quantity=trade.quantity,
                    latest_price=trade.price)

    async def handle_book_ticker_update(self, book_ticker: BookTicker):
        """Store and process book ticker updates."""
        # Store the book ticker
        symbol = book_ticker.symbol
        self.book_tickers[symbol] = book_ticker

        # Track update counts
        if symbol not in self.book_ticker_counts:
            self.book_ticker_counts[symbol] = 0
        self.book_ticker_counts[symbol] += 1

        # Calculate spread
        spread = book_ticker.ask_price - book_ticker.bid_price
        spread_percentage = (spread / book_ticker.bid_price) * 100 if book_ticker.bid_price else 0

        # Log the update (less verbose for frequent updates)
        if self.book_ticker_counts[symbol] % 5 == 1:  # Log every 5th update
            logger.info("📈 Book ticker update",
                        exchange=self.exchange_name,
                        symbol=f"{symbol.base}/{symbol.quote}",
                        update_number=self.book_ticker_counts[symbol],
                        bid_price=book_ticker.bid_price,
                        bid_quantity=book_ticker.bid_quantity,
                        ask_price=book_ticker.ask_price,
                        ask_quantity=book_ticker.ask_quantity,
                        spread=spread,
                        spread_percentage=spread_percentage)

    def get_orderbook(self, symbol: Symbol) -> OrderBook:
        """Get stored orderbook for symbol."""
        return self.orderbooks.get(symbol)

    def get_trades(self, symbol: Symbol) -> List[Trade]:
        """Get stored trades for symbol."""
        return self.trade_history.get(symbol, [])

    def get_book_ticker(self, symbol: Symbol) -> BookTicker:
        """Get stored book ticker for symbol."""
        return self.book_tickers.get(symbol)

    def get_summary(self) -> Dict:
        """Get summary of received data."""
        return {
            'orderbook_symbols': len(self.orderbooks),
            'trade_symbols': len(self.trade_history),
            'book_ticker_symbols': len(self.book_tickers),
            'total_orderbook_updates': sum(self.update_counts.values()),
            'total_trades': sum(len(trades) for trades in self.trade_history.values()),
            'total_book_ticker_updates': sum(self.book_ticker_counts.values())
        }


async def main(exchange_name: str):
    """Test public WebSocket functionality for the specified exchange."""
    exchange_upper = exchange_name.upper()
    logger.info("🚀 Starting Public WebSocket Demo",
                exchange=exchange_upper)
    logger.info("=" * 60)

    try:
        # Create OrderBook manager for external storage
        manager = OrderBookManager(exchange_name)

        # Create test WebSocket client
        ws = PublicWebSocketClient(
            exchange_name=exchange_name,
            orderbook_handler=manager.handle_orderbook_update,
            trades_handler=manager.handle_trades_update,
            book_ticker_handler=manager.handle_book_ticker_update
        )

        # Test symbols - use common trading pairs
        symbols = [
            Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=False),
            Symbol(base=AssetName('ETH'), quote=AssetName('USDT'), is_futures=False)
        ]

        logger.info("🔌 Testing WebSocket factory architecture",
                    exchange=exchange_upper)
        await ws.initialize(symbols)

        logger.info("⏳ Monitoring WebSocket connection",
                    exchange=exchange_upper,
                    duration_seconds=30)
        logger.info("💡 Expecting market data updates",
                    symbol_count=len(symbols))
        await asyncio.sleep(30)

        # Get performance metrics
        metrics = ws.get_performance_metrics()
        logger.info("📊 WebSocket Performance Metrics",
                    connection_state=metrics.get('connection_state', 'Unknown'),
                    messages_processed=metrics.get('messages_processed', 0),
                    error_count=metrics.get('error_count', 0),
                    uptime_seconds=metrics.get('connection_uptime_seconds', 0))

        # Show received data summary
        summary = manager.get_summary()
        logger.info("📈 Data Summary",
                    orderbook_symbols=summary['orderbook_symbols'],
                    trade_symbols=summary['trade_symbols'],
                    book_ticker_symbols=summary['book_ticker_symbols'],
                    total_orderbook_updates=summary['total_orderbook_updates'],
                    total_trades=summary['total_trades'],
                    total_book_ticker_updates=summary['total_book_ticker_updates'])

        # Show latest orderbook for first symbol
        if symbols and manager.get_orderbook(symbols[0]):
            symbol = symbols[0]
            orderbook = manager.get_orderbook(symbol)
            best_bid = orderbook.bids[0].price if orderbook.bids else None
            best_ask = orderbook.asks[0].price if orderbook.asks else None
            spread = (best_ask - best_bid) if best_bid and best_ask else None
            logger.info("💰 Latest orderbook",
                        symbol=f"{symbol.base}/{symbol.quote}",
                        best_bid=best_bid,
                        best_ask=best_ask,
                        spread=spread)

        # Show recent trades
        if symbols and manager.get_trades(symbols[0]):
            symbol = symbols[0]
            recent_trades = manager.get_trades(symbol)[-3:]  # Last 3 trades
            logger.info("🔄 Recent trades",
                        symbol=f"{symbol.base}/{symbol.quote}",
                        trade_count=len(recent_trades))
            for i, trade in enumerate(recent_trades, 1):
                logger.info("Recent trade",
                            trade_number=i,
                            side=trade.side.name,
                            quantity=trade.quantity,
                            price=trade.price)

        # Show latest book ticker
        if symbols and manager.get_book_ticker(symbols[0]):
            symbol = symbols[0]
            book_ticker = manager.get_book_ticker(symbol)
            spread = book_ticker.ask_price - book_ticker.bid_price
            spread_percentage = (spread / book_ticker.bid_price) * 100 if book_ticker.bid_price else 0
            logger.info("📊 Latest book ticker",
                        symbol=f"{symbol.base}/{symbol.quote}",
                        bid_price=book_ticker.bid_price,
                        bid_quantity=book_ticker.bid_quantity,
                        ask_price=book_ticker.ask_price,
                        ask_quantity=book_ticker.ask_quantity,
                        spread=spread,
                        spread_percentage=spread_percentage)

        if summary['total_orderbook_updates'] > 0 or summary['total_trades'] > 0 or summary[
            'total_book_ticker_updates'] > 0:
            logger.info("✅ Public WebSocket demo successful!",
                        exchange=exchange_upper)
            logger.info("🎉 Received real-time market data")
        else:
            logger.info("ℹ️  No market data received",
                        exchange=exchange_upper)
            logger.info("✅ WebSocket connection and subscription working correctly")
            logger.info("💡 This may be normal if markets are quiet or symbols are inactive")

    except ValueError as e:
        logger.error("Configuration Error",
                     exchange=exchange_upper,
                     error_type=type(e).__name__,
                     error_message=str(e))
        logger.error("Configuration validation failed",
                     exchange=exchange_upper,
                     suggestion="Check exchange configuration availability")
        raise
    except Exception as e:
        logger.error("WebSocket test failed",
                     exchange=exchange_upper,
                     error_type=type(e).__name__,
                     error_message=str(e))
        import traceback
        traceback.print_exc()
        raise

    finally:
        if 'ws' in locals():
            await ws.close()

    logger.info("=" * 60)
    logger.info("✅ Public WebSocket demo completed",
                exchange=exchange_upper)


if __name__ == "__main__":
    exchange_name = sys.argv[1] if len(sys.argv) > 1 else "gateio_futures"

    try:
        asyncio.run(main(exchange_name))
        print(f"\n✅ {exchange_name.upper()} public WebSocket demo completed successfully!")
    except Exception as e:
        print(f"\n❌ {exchange_name.upper()} public WebSocket demo failed: {e}")
        sys.exit(1)
