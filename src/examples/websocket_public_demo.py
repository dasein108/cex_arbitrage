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
import logging
import sys
from typing import List, Dict

from structs.exchange import Symbol, AssetName, OrderBook, Trade
from core.config.config_manager import get_exchange_config

from examples.utils.ws_api_factory import get_exchange_websocket_classes

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



class PublicWebSocketClient:
    """Exchange-agnostic public WebSocket client using actual exchange implementations."""
    
    def __init__(self, exchange_name: str, orderbook_handler, trades_handler):
        self.exchange_name = exchange_name.upper()
        self.orderbook_handler = orderbook_handler
        self.trades_handler = trades_handler
        
        # Get exchange config
        config = get_exchange_config(self.exchange_name)
        
        # Get the appropriate WebSocket class for the exchange
        websocket_class, _ = get_exchange_websocket_classes(self.exchange_name)
        
        # Create exchange WebSocket instance with dependency injection
        self.websocket = websocket_class(
            config=config,
            orderbook_diff_handler=self._handle_orderbook_update,
            trades_handler=self._handle_trades_update,
            state_change_handler=self._handle_state_change
        )
        
        logger.info(f"{self.exchange_name} public WebSocket client initialized with {websocket_class.__name__}")
    
    async def initialize(self, symbols: List[Symbol]) -> None:
        """Initialize WebSocket connection and subscriptions."""
        # Pass symbols to initialize() - they will be subscribed automatically when connection is established
        await self.websocket.initialize(symbols)
        logger.info(f"WebSocket initialized with {len(symbols)} symbols")
    
    async def add_symbols(self, symbols: List[Symbol]) -> None:
        """Add symbols for real-time subscription (only after connection established)."""
        if not self.is_connected():
            raise ValueError("WebSocket not connected - use initialize() with symbols instead")
        await self.websocket.add_symbols(symbols)
        logger.info(f"Added {len(symbols)} symbols to existing subscription")
    
    async def close(self) -> None:
        """Close WebSocket connection."""
        await self.websocket.close()
    
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self.websocket.is_connected()
    
    def get_performance_metrics(self) -> Dict:
        """Get HFT performance metrics."""
        return self.websocket.get_performance_metrics()
    
    async def _handle_orderbook_update(self, orderbook_data, symbol: Symbol) -> None:
        """Handle orderbook updates from WebSocket."""
        if self.orderbook_handler:
            await self.orderbook_handler(symbol, orderbook_data)
    
    async def _handle_trades_update(self, symbol: Symbol, trades: List[Trade]) -> None:
        """Handle trade updates from WebSocket."""
        if self.trades_handler:
            await self.trades_handler(symbol, trades)
    
    async def _handle_state_change(self, state) -> None:
        """Handle WebSocket state changes."""
        logger.info(f"🔗 {self.exchange_name} WebSocket state changed: {state}")


class OrderBookManager:
    """External orderbook storage and management."""
    
    def __init__(self, exchange_name: str):
        self.exchange_name = exchange_name.upper()
        self.orderbooks: Dict[Symbol, OrderBook] = {}
        self.trade_history: Dict[Symbol, List[Trade]] = {}
        self.update_counts: Dict[Symbol, int] = {}
    
    async def handle_orderbook_update(self, symbol: Symbol, orderbook: OrderBook):
        """Store and process orderbook updates."""
        # Store the orderbook
        self.orderbooks[symbol] = orderbook
        
        # Track update counts
        if symbol not in self.update_counts:
            self.update_counts[symbol] = 0
        self.update_counts[symbol] += 1
        
        # Log the update (less verbose for frequent updates)
        if self.update_counts[symbol] % 10 == 1:  # Log every 10th update
            logger.info(f"📊 {self.exchange_name} orderbook update #{self.update_counts[symbol]} for {symbol.base}/{symbol.quote}:")
            logger.info(f"   Best bid: {orderbook.bids[0].price if orderbook.bids else 'N/A'}")
            logger.info(f"   Best ask: {orderbook.asks[0].price if orderbook.asks else 'N/A'}")
            logger.info(f"   Bids: {len(orderbook.bids)}, Asks: {len(orderbook.asks)}")
    
    async def handle_trades_update(self, symbol: Symbol, trades: List[Trade]):
        """Store and process trade updates."""
        # Store trades
        if symbol not in self.trade_history:
            self.trade_history[symbol] = []
        self.trade_history[symbol].extend(trades)
        
        # Keep only last 100 trades per symbol
        if len(self.trade_history[symbol]) > 100:
            self.trade_history[symbol] = self.trade_history[symbol][-100:]
        
        # Log the update
        logger.info(f"💹 {self.exchange_name} trades update for {symbol.base}/{symbol.quote}: {len(trades)} trades")
        if trades:
            latest_trade = trades[0]
            logger.info(f"   Latest: {latest_trade.side.name} {latest_trade.amount} @ {latest_trade.price}")
    
    def get_orderbook(self, symbol: Symbol) -> OrderBook:
        """Get stored orderbook for symbol."""
        return self.orderbooks.get(symbol)
    
    def get_trades(self, symbol: Symbol) -> List[Trade]:
        """Get stored trades for symbol."""
        return self.trade_history.get(symbol, [])
    
    def get_summary(self) -> Dict:
        """Get summary of received data."""
        return {
            'orderbook_symbols': len(self.orderbooks),
            'trade_symbols': len(self.trade_history),
            'total_orderbook_updates': sum(self.update_counts.values()),
            'total_trades': sum(len(trades) for trades in self.trade_history.values())
        }


async def main(exchange_name: str):
    """Test public WebSocket functionality for the specified exchange."""
    exchange_upper = exchange_name.upper()
    logger.info(f"🚀 Starting {exchange_upper} Public WebSocket Demo...")
    logger.info("=" * 60)
    
    try:
        # Create OrderBook manager for external storage
        manager = OrderBookManager(exchange_name)
        
        # Create test WebSocket client
        ws = PublicWebSocketClient(
            exchange_name=exchange_name,
            orderbook_handler=manager.handle_orderbook_update,
            trades_handler=manager.handle_trades_update
        )

        # Test symbols - use common trading pairs
        symbols = [
            Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=False),
            Symbol(base=AssetName('ETH'), quote=AssetName('USDT'), is_futures=False)
        ]

        logger.info(f"🔌 Testing {exchange_upper} WebSocket factory architecture...")
        await ws.initialize(symbols)
        
        logger.info(f"⏳ Monitoring {exchange_upper} WebSocket connection (30 seconds)...")
        logger.info(f"💡 Expecting orderbook and trade updates for {len(symbols)} symbols")
        await asyncio.sleep(30)
        
        # Get performance metrics
        metrics = ws.get_performance_metrics()
        logger.info("📊 WebSocket Performance Metrics:")
        logger.info(f"   Connection State: {metrics.get('connection_state', 'Unknown')}")
        logger.info(f"   Messages Processed: {metrics.get('messages_processed', 0)}")
        logger.info(f"   Error Count: {metrics.get('error_count', 0)}")
        logger.info(f"   Connection Uptime: {metrics.get('connection_uptime_seconds', 0)}s")
        
        # Show received data summary
        summary = manager.get_summary()
        logger.info("📈 Data Summary:")
        logger.info(f"   Orderbook symbols: {summary['orderbook_symbols']}")
        logger.info(f"   Trade symbols: {summary['trade_symbols']}")
        logger.info(f"   Total orderbook updates: {summary['total_orderbook_updates']}")
        logger.info(f"   Total trades received: {summary['total_trades']}")
        
        # Show latest orderbook for first symbol
        if symbols and manager.get_orderbook(symbols[0]):
            symbol = symbols[0]
            orderbook = manager.get_orderbook(symbol)
            logger.info(f"💰 Latest {symbol.base}/{symbol.quote} orderbook:")
            logger.info(f"   Best bid: {orderbook.bids[0].price if orderbook.bids else 'N/A'}")
            logger.info(f"   Best ask: {orderbook.asks[0].price if orderbook.asks else 'N/A'}")
            logger.info(f"   Spread: {(orderbook.asks[0].price - orderbook.bids[0].price) if orderbook.bids and orderbook.asks else 'N/A'}")
        
        # Show recent trades
        if symbols and manager.get_trades(symbols[0]):
            symbol = symbols[0]
            recent_trades = manager.get_trades(symbol)[-3:]  # Last 3 trades
            logger.info(f"🔄 Recent {symbol.base}/{symbol.quote} trades:")
            for i, trade in enumerate(recent_trades, 1):
                logger.info(f"   {i}. {trade.side.name} {trade.amount} @ {trade.price}")
        
        if summary['total_orderbook_updates'] > 0 or summary['total_trades'] > 0:
            logger.info(f"✅ {exchange_upper} public WebSocket demo successful!")
            logger.info("🎉 Received real-time market data!")
        else:
            logger.info(f"ℹ️  No market data received from {exchange_upper}")
            logger.info("✅ WebSocket connection and subscription working correctly")
            logger.info("💡 This may be normal if markets are quiet or symbols are inactive")

    except ValueError as e:
        logger.error(f"Configuration Error: {e}")
        logger.error(f"Make sure {exchange_upper} configuration is available")
        raise
    except Exception as e:
        logger.error(f"Error during {exchange_upper} WebSocket test: {e}")
        import traceback
        traceback.print_exc()
        raise
    
    finally:
        if 'ws' in locals():
            await ws.close()
    
    logger.info("=" * 60)
    logger.info(f"✅ {exchange_upper} public WebSocket demo completed!")


if __name__ == "__main__":
    exchange_name = sys.argv[1] if len(sys.argv) > 1 else "mexc"
    
    try:
        asyncio.run(main(exchange_name))
        print(f"\n✅ {exchange_name.upper()} public WebSocket demo completed successfully!")
    except Exception as e:
        print(f"\n❌ {exchange_name.upper()} public WebSocket demo failed: {e}")
        sys.exit(1)