"""
MEXC WebSocket Handler Injection Demo

Demonstrates different ways to inject custom handlers into MEXC WebSocket:
1. Function handlers (most common)
2. Class method handlers 
3. Lambda handlers (for simple logic)
4. Default behavior (no handlers)
"""

import asyncio
import logging
from structs.exchange import Symbol, AssetName, OrderBook, Trade
from exchanges.mexc.ws.mexc_ws_public import MexcWebsocketPublic
from common.ws_client import WebSocketConfig
from typing import List

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Example 1: Function handlers
async def custom_orderbook_handler(symbol: Symbol, orderbook: OrderBook):
    """Custom function to handle orderbook updates."""
    logger.info(f"🔷 FUNCTION HANDLER: {symbol.base}/{symbol.quote} orderbook")
    if orderbook.bids and orderbook.asks:
        spread = orderbook.asks[0].price - orderbook.bids[0].price
        logger.info(f"   Spread: ${spread:.4f}")


async def custom_trades_handler(symbol: Symbol, trades: List[Trade]):
    """Custom function to handle trade updates."""
    logger.info(f"🔶 FUNCTION HANDLER: {symbol.base}/{symbol.quote} - {len(trades)} trades")


# Example 2: Class-based handlers
class MarketAnalyzer:
    """Example class with market analysis methods."""
    
    def __init__(self):
        self.trade_count = 0
        self.orderbook_count = 0
    
    async def analyze_orderbook(self, symbol: Symbol, orderbook: OrderBook):
        """Analyze orderbook data."""
        self.orderbook_count += 1
        logger.info(f"📈 CLASS HANDLER: Analyzed {self.orderbook_count} orderbooks for {symbol.base}/{symbol.quote}")
        
        if orderbook.bids and orderbook.asks:
            mid_price = (orderbook.bids[0].price + orderbook.asks[0].price) / 2
            logger.info(f"   Mid price: ${mid_price:.4f}")
    
    async def analyze_trades(self, symbol: Symbol, trades: List[Trade]):
        """Analyze trade data."""
        self.trade_count += len(trades)
        logger.info(f"📊 CLASS HANDLER: Total trades analyzed: {self.trade_count}")


async def demo_function_handlers():
    """Demo 1: Using function handlers."""
    logger.info("\n=== DEMO 1: Function Handlers ===")
    
    config = WebSocketConfig(
        name="MEXC_Function_Demo",
        url="wss://wbs-api.mexc.com/ws",
        timeout=10.0
    )
    
    ws = MexcWebsocketPublic(
        config=config,
        orderbook_handler=custom_orderbook_handler,
        trades_handler=custom_trades_handler
    )
    
    symbols = [Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=False)]
    
    try:
        await ws.init(symbols)
        await asyncio.sleep(10)  # Collect data for 10 seconds
    finally:
        await ws.ws_client.close()


async def demo_class_handlers():
    """Demo 2: Using class method handlers."""
    logger.info("\n=== DEMO 2: Class Method Handlers ===")
    
    config = WebSocketConfig(
        name="MEXC_Class_Demo",
        url="wss://wbs-api.mexc.com/ws", 
        timeout=10.0
    )
    
    analyzer = MarketAnalyzer()
    
    ws = MexcWebsocketPublic(
        config=config,
        orderbook_handler=analyzer.analyze_orderbook,
        trades_handler=analyzer.analyze_trades
    )
    
    symbols = [Symbol(base=AssetName('ETH'), quote=AssetName('USDT'), is_futures=False)]
    
    try:
        await ws.init(symbols)
        await asyncio.sleep(10)
    finally:
        await ws.ws_client.close()


async def demo_lambda_handlers():
    """Demo 3: Using lambda handlers."""
    logger.info("\n=== DEMO 3: Lambda Handlers ===")
    
    config = WebSocketConfig(
        name="MEXC_Lambda_Demo",
        url="wss://wbs-api.mexc.com/ws",
        timeout=10.0
    )
    
    ws = MexcWebsocketPublic(
        config=config,
        orderbook_handler=lambda symbol, orderbook: logger.info(f"🔸 LAMBDA: {symbol} orderbook"),
        trades_handler=lambda symbol, trades: logger.info(f"🔹 LAMBDA: {symbol} - {len(trades)} trades")
    )
    
    symbols = [Symbol(base=AssetName('BNB'), quote=AssetName('USDT'), is_futures=False)]
    
    try:
        await ws.init(symbols)
        await asyncio.sleep(10)
    finally:
        await ws.ws_client.close()


async def demo_default_handlers():
    """Demo 4: Using default handlers (no injection)."""
    logger.info("\n=== DEMO 4: Default Handlers ===")
    
    config = WebSocketConfig(
        name="MEXC_Default_Demo",
        url="wss://wbs-api.mexc.com/ws",
        timeout=10.0
    )
    
    # No handlers injected - will use default logging
    ws = MexcWebsocketPublic(config=config)
    
    symbols = [Symbol(base=AssetName('ADA'), quote=AssetName('USDT'), is_futures=False)]
    
    try:
        await ws.init(symbols)
        await asyncio.sleep(10)
    finally:
        await ws.ws_client.close()


async def main():
    """Run all handler demos."""
    logger.info("🚀 MEXC WebSocket Handler Injection Demos")
    
    try:
        await demo_function_handlers()
        await demo_class_handlers() 
        await demo_lambda_handlers()
        await demo_default_handlers()
        
    except Exception as e:
        logger.error(f"❌ Demo failed: {e}")
    
    logger.info("✅ All demos completed!")


if __name__ == "__main__":
    asyncio.run(main())