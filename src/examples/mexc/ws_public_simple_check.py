"""
MEXC Public WebSocket Simple Check

Simple test to verify MEXC public WebSocket implementation works.
Tests connection, subscription, and basic message handling.
"""

import asyncio
import logging
from structs.exchange import Symbol, AssetName, OrderBook, Trade
from exchanges.mexc.ws.mexc_ws_public import MexcWebsocketPublic
from common.ws_client import WebSocketConfig
from typing import List, Dict

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class OrderBookManager:
    """External orderbook storage and management."""
    
    def __init__(self):
        self.orderbooks: Dict[Symbol, OrderBook] = {}
        self.trade_history: Dict[Symbol, List[Trade]] = {}
    
    async def handle_orderbook_update(self, symbol: Symbol, orderbook: OrderBook):
        """Store and process orderbook updates."""
        # Store the orderbook
        self.orderbooks[symbol] = orderbook
        
        # Log the update
        logger.info(f"📊 Orderbook update for {symbol.base}/{symbol.quote}:")
        logger.info(f"   Best bid: {orderbook.bids[0].price if orderbook.bids else 'N/A'}")
        logger.info(f"   Best ask: {orderbook.asks[0].price if orderbook.asks else 'N/A'}")
        logger.info(f"   Bids: {len(orderbook.bids)}, Asks: {len(orderbook.asks)}")
    
    async def handle_trades_update(self, symbol: Symbol, trades: List[Trade]):
        """Store and process trade updates."""
        # Store trades
        if symbol not in self.trade_history:
            self.trade_history[symbol] = []
        self.trade_history[symbol].extend(trades)
        
        # Keep only last 100 trades
        if len(self.trade_history[symbol]) > 100:
            self.trade_history[symbol] = self.trade_history[symbol][-100:]
        
        # Log the update
        logger.info(f"💹 Trades update for {symbol.base}/{symbol.quote}: {len(trades)} trades")
        if trades:
            latest_trade = trades[0]
            logger.info(f"   Latest: {latest_trade.side.name} {latest_trade.amount} @ {latest_trade.price}")
    
    def get_orderbook(self, symbol: Symbol) -> OrderBook:
        """Get stored orderbook for symbol."""
        return self.orderbooks.get(symbol)
    
    def get_trades(self, symbol: Symbol) -> List[Trade]:
        """Get stored trades for symbol."""
        return self.trade_history.get(symbol, [])


async def main():
    """Test MEXC WebSocket functionality."""
    logger.info("🚀 Starting MEXC WebSocket test...")
    
    # Configure WebSocket
    config = WebSocketConfig(
        name="MEXC_Public_Test",
        url="wss://wbs-api.mexc.com/ws",
        timeout=30.0,
        ping_interval=20.0,
        max_reconnect_attempts=3
    )
    
    # Create OrderBook manager for external storage
    manager = OrderBookManager()
    
    # Create WebSocket instance with injected handlers from manager
    ws = MexcWebsocketPublic(
        config=config,
        orderbook_handler=manager.handle_orderbook_update,
        trades_handler=manager.handle_trades_update
    )
    
    # Test symbols
    symbols = [
        Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=False),
        Symbol(base=AssetName('ETH'), quote=AssetName('USDT'), is_futures=False)
    ]
    
    try:
        logger.info(f"🔌 Connecting to MEXC WebSocket...")
        
        # Initialize and start streaming
        await ws.init(symbols)
        
        logger.info(f"✅ Connected! Subscribed to {len(symbols)} symbols")
        logger.info("📡 Waiting for data (30 seconds)...")
        
        # Wait for some data
        await asyncio.sleep(30)
        
        # Check stored orderbooks in manager
        logger.info("\n📋 Final orderbook status:")
        for symbol in symbols:
            orderbook = manager.get_orderbook(symbol)
            if orderbook:
                logger.info(f"   {symbol.base}/{symbol.quote}: ✅ Available")
                logger.info(f"      Best bid: ${orderbook.bids[0].price if orderbook.bids else 'N/A'}")
                logger.info(f"      Best ask: ${orderbook.asks[0].price if orderbook.asks else 'N/A'}")
            else:
                logger.info(f"   {symbol.base}/{symbol.quote}: ❌ No data")
        
        # Check stored trades
        logger.info("\n📈 Trade history:")
        for symbol in symbols:
            trades = manager.get_trades(symbol)
            logger.info(f"   {symbol.base}/{symbol.quote}: {len(trades)} trades stored")
        
    except Exception as e:
        logger.error(f"❌ Error during test: {e}")
    
    finally:
        logger.info("🔚 Closing WebSocket connection...")
        if hasattr(ws, 'ws_client'):
            await ws.ws_client.stop()
    
    logger.info("✅ Test completed!")


if __name__ == "__main__":
    asyncio.run(main())