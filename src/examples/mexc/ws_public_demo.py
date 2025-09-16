"""
MEXC Public WebSocket Refactored Test

Standalone test for the new MEXC WebSocket refactored implementation.
Tests the new strategy pattern architecture with composition.
Avoids circular imports by being completely self-contained.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add the src directory to path
src_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(src_dir))

# Import required structs and configs
from structs.exchange import Symbol, AssetName, OrderBook, Trade
from core.transport.websocket.ws_client import WebSocketConfig
from typing import List, Dict

# Import strategy components directly
from core.cex.websocket.strategies import WebSocketStrategySet
from core.cex.websocket.ws_manager import WebSocketManager, WebSocketManagerConfig
from exchanges.mexc.ws.public.parser import MexcPublicMessageParser
from exchanges.mexc.ws.public.ws_strategies import MexcPublicConnectionStrategy, MexcPublicSubscriptionStrategy

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class TestWebSocketClient:
    """Simple test client using the new strategy architecture."""
    
    def __init__(self, config: WebSocketConfig, orderbook_handler, trades_handler):
        self.config = config
        self.orderbook_handler = orderbook_handler
        self.trades_handler = trades_handler
        
        # Get MEXC exchange config for strategy
        from config import get_exchange_config_struct
        mexc_config = get_exchange_config_struct("mexc")
        
        # Create strategy set for MEXC public WebSocket
        strategies = WebSocketStrategySet(
            connection_strategy=MexcPublicConnectionStrategy(mexc_config),
            subscription_strategy=MexcPublicSubscriptionStrategy(), 
            message_parser=MexcPublicMessageParser()
        )
        
        # Configure manager for HFT performance
        manager_config = WebSocketManagerConfig(
            batch_processing_enabled=True,
            batch_size=100,
            max_pending_messages=1000,
            enable_performance_tracking=True
        )
        
        # Initialize WebSocket manager
        self.ws_manager = WebSocketManager(
            config=config,
            strategies=strategies,
            message_handler=self._handle_parsed_message,
            manager_config=manager_config
        )
        
        logger.info("Test WebSocket client initialized with strategy pattern")
    
    async def initialize(self, symbols: List[Symbol]) -> None:
        """Initialize WebSocket connection and subscriptions."""
        await self.ws_manager.initialize(symbols)
        logger.info(f"WebSocket initialized with {len(symbols)} symbols")
    
    async def close(self) -> None:
        """Close WebSocket connection."""
        await self.ws_manager.close()
    
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self.ws_manager.is_connected()
    
    def get_performance_metrics(self) -> Dict:
        """Get HFT performance metrics."""
        return self.ws_manager.get_performance_metrics()
    
    async def _handle_parsed_message(self, parsed_message) -> None:
        """Handle parsed messages from WebSocketManager."""
        try:
            from core.cex.websocket import MessageType
            
            if parsed_message.message_type == MessageType.ORDERBOOK:
                if self.orderbook_handler and parsed_message.symbol and parsed_message.data:
                    await self.orderbook_handler(parsed_message.symbol, parsed_message.data)
            
            elif parsed_message.message_type == MessageType.TRADE:
                if self.trades_handler and parsed_message.symbol and parsed_message.data:
                    await self.trades_handler(parsed_message.symbol, parsed_message.data)
            
            elif parsed_message.message_type == MessageType.HEARTBEAT:
                logger.debug("Received heartbeat")
            
            elif parsed_message.message_type == MessageType.SUBSCRIPTION_CONFIRM:
                logger.debug("Subscription confirmed")
            
            elif parsed_message.message_type == MessageType.ERROR:
                logger.error(f"WebSocket error: {parsed_message.raw_data}")
            
        except Exception as e:
            logger.error(f"Error handling parsed message: {e}")

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
    """Test MEXC WebSocket refactored functionality."""
    logger.info("🚀 Starting MEXC WebSocket Refactored Test...")
    
    # Configure WebSocket
    config = WebSocketConfig(
        name="MEXC_Refactored_Test",
        url="wss://wbs.mexc.com/ws",
        timeout=30.0,
        ping_interval=20.0
    )
    
    # Create OrderBook manager for external storage
    manager = OrderBookManager()
    
    # Create test WebSocket client
    ws = TestWebSocketClient(
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
        logger.info("🔌 Testing WebSocket strategy architecture...")
        await ws.initialize(symbols)
        await asyncio.sleep(30)
        # The client was successfully created with the strategy pattern
        logger.info("✅ Strategy pattern architecture test successful!")
        

    except Exception as e:
        logger.error(f"❌ Error during test: {e}")
        raise
    
    finally:
        await ws.close()
    
    logger.info("✅ Test completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())