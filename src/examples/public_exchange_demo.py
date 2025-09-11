#!/usr/bin/env python3
"""
Comprehensive demonstration of PublicExchangeInterface functionality
Shows REST API, WebSocket streaming, and real-time orderbook updates
"""

import asyncio
import logging
from typing import List, Dict, Any
from datetime import datetime

from exchanges.mexc.mexc_public import MexcPublicExchange
from structs.exchange import Symbol, AssetName, ExchangeName, OrderBook, Trade

# Configure logging for visibility
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("exchange_demo")


class PublicExchangeDemo:
    """Demonstrates all PublicExchangeInterface capabilities"""
    
    def __init__(self):
        self.exchange = MexcPublicExchange()
        self.symbols: List[Symbol] = []
        self.is_running = True
        
    async def setup_symbols(self):
        """Define symbols for trading"""
        self.symbols = [
            Symbol(base=AssetName("BTC"), quote=AssetName("USDT"), is_futures=False),
            Symbol(base=AssetName("ETH"), quote=AssetName("USDT"), is_futures=False),
            Symbol(base=AssetName("BNB"), quote=AssetName("USDT"), is_futures=False),
        ]
        logger.info(f"Configured {len(self.symbols)} trading symbols")
        
    async def demo_initialization(self):
        """Demonstrate exchange initialization with WebSocket auto-connection"""
        logger.info("=" * 60)
        logger.info("DEMO 1: Exchange Initialization")
        logger.info("=" * 60)
        
        # Initialize exchange - automatically starts WebSocket orderbook streams
        logger.info(f"Initializing exchange with {len(self.symbols)} symbols...")
        await self.exchange.init(self.symbols)
        
        # Check WebSocket health
        health = self.exchange.get_websocket_health()
        logger.info(f"WebSocket Health: {health}")
        
        # Verify active symbols
        active = self.exchange.get_active_symbols()
        logger.info(f"Active symbols: {len(active)}")
        
        # Wait for initial orderbook data
        await asyncio.sleep(3)
        
    async def demo_rest_api(self):
        """Demonstrate REST API functionality"""
        logger.info("=" * 60)
        logger.info("DEMO 2: REST API Operations")
        logger.info("=" * 60)
        
        for symbol in self.symbols[:2]:  # Demo with first 2 symbols
            logger.info(f"\n--- {symbol.base}/{symbol.quote} ---")
            
            # Get exchange info
            try:
                exchange_info = await self.exchange.get_exchange_info()
                if symbol in exchange_info:
                    info = exchange_info[symbol]
                    logger.info(f"  Min base amount: {info.min_base_amount}")
                    logger.info(f"  Min quote amount: {info.min_quote_amount}")
            except Exception as e:
                logger.error(f"  Failed to get exchange info: {e}")
            
            # Get orderbook snapshot via REST
            try:
                orderbook = await self.exchange.get_orderbook(symbol, limit=5)
                if orderbook.bids and orderbook.asks:
                    best_bid = orderbook.bids[0]
                    best_ask = orderbook.asks[0]
                    spread = best_ask.price - best_bid.price
                    logger.info(f"  REST Orderbook:")
                    logger.info(f"    Best bid: {best_bid.price:.2f} @ {best_bid.size:.4f}")
                    logger.info(f"    Best ask: {best_ask.price:.2f} @ {best_ask.size:.4f}")
                    logger.info(f"    Spread: {spread:.2f}")
            except Exception as e:
                logger.error(f"  Failed to get orderbook: {e}")
            
            # Get recent trades
            try:
                trades = await self.exchange.get_recent_trades(symbol, limit=5)
                if trades:
                    logger.info(f"  Recent trades: {len(trades)}")
                    last_trade = trades[0]
                    logger.info(f"    Last: {last_trade.price:.2f} @ {last_trade.amount:.4f} ({last_trade.side.value})")
            except Exception as e:
                logger.error(f"  Failed to get trades: {e}")
        
        # Test connectivity
        try:
            ping_ok = await self.exchange.ping()
            server_time = await self.exchange.get_server_time()
            logger.info(f"\nConnectivity: {'OK' if ping_ok else 'FAILED'}")
            logger.info(f"Server time: {datetime.fromtimestamp(server_time/1000)}")
        except Exception as e:
            logger.error(f"Connectivity test failed: {e}")
            
    async def demo_websocket_streaming(self):
        """Demonstrate real-time WebSocket streaming"""
        logger.info("=" * 60)
        logger.info("DEMO 3: Real-Time WebSocket Streaming")
        logger.info("=" * 60)
        
        logger.info("Monitoring real-time orderbook updates for 10 seconds...")
        
        # Track orderbook changes
        previous_prices: Dict[Symbol, tuple] = {}
        
        for i in range(10):  # Monitor for 10 seconds
            await asyncio.sleep(1)
            
            for symbol in self.symbols:
                # Get real-time orderbook from WebSocket
                realtime_ob = await self.exchange.get_orderbook(symbol)

                if realtime_ob and realtime_ob.bids and realtime_ob.asks:
                    best_bid = realtime_ob.bids[0].price
                    best_ask = realtime_ob.asks[0].price
                    
                    # Check for price changes
                    prev = previous_prices.get(symbol, (0, 0))
                    if prev != (best_bid, best_ask):
                        bid_change = "↑" if best_bid > prev[0] else "↓" if best_bid < prev[0] else "="
                        ask_change = "↑" if best_ask > prev[1] else "↓" if best_ask < prev[1] else "="
                        
                        logger.info(
                            f"  [{symbol.base}/{symbol.quote}] "
                            f"Bid: {best_bid:.2f}{bid_change} | "
                            f"Ask: {best_ask:.2f}{ask_change} | "
                            f"Spread: {best_ask - best_bid:.2f}"
                        )
                        
                        previous_prices[symbol] = (best_bid, best_ask)
                        
    async def demo_dynamic_symbols(self):
        """Demonstrate dynamic symbol management"""
        logger.info("=" * 60)
        logger.info("DEMO 4: Dynamic Symbol Management")
        logger.info("=" * 60)
        
        # Add a new symbol dynamically
        new_symbol = Symbol(base=AssetName("ADA"), quote=AssetName("USDT"), is_futures=False)
        
        logger.info(f"Adding new symbol: {new_symbol.base}/{new_symbol.quote}")
        await self.exchange.start_symbol(new_symbol)
        
        # Wait for data
        await asyncio.sleep(3)
        
        # Check if streaming
        is_active = self.exchange.is_symbol_active(new_symbol)
        logger.info(f"Symbol active: {is_active}")
        
        # Get real-time data for new symbol
        new_ob = self.exchange.get_realtime_orderbook(new_symbol)
        if new_ob and new_ob.bids and new_ob.asks:
            logger.info(f"New symbol orderbook received:")
            logger.info(f"  Best bid: {new_ob.bids[0].price:.4f}")
            logger.info(f"  Best ask: {new_ob.asks[0].price:.4f}")
        
        # Remove a symbol
        remove_symbol = self.symbols[2]  # Remove BNB/USDT
        logger.info(f"\nRemoving symbol: {remove_symbol.base}/{remove_symbol.quote}")
        await self.exchange.stop_symbol(remove_symbol)
        
        # Verify removal
        is_removed = not self.exchange.is_symbol_active(remove_symbol)
        logger.info(f"Symbol removed: {is_removed}")
        
        # Show current active symbols
        active = self.exchange.get_active_symbols()
        logger.info(f"Currently active symbols: {len(active)}")
        for sym in active:
            logger.info(f"  - {sym.base}/{sym.quote}")
            
    async def demo_comparison(self):
        """Compare REST vs WebSocket data access"""
        logger.info("=" * 60)
        logger.info("DEMO 5: REST vs WebSocket Comparison")
        logger.info("=" * 60)
        
        symbol = self.symbols[0]  # Use BTC/USDT
        
        # Get REST snapshot
        rest_start = asyncio.get_event_loop().time()
        rest_ob = await self.exchange.get_orderbook(symbol, limit=10)
        rest_time = (asyncio.get_event_loop().time() - rest_start) * 1000
        
        # Get WebSocket data (already cached)
        ws_start = asyncio.get_event_loop().time()
        ws_ob = self.exchange.get_realtime_orderbook(symbol)
        ws_time = (asyncio.get_event_loop().time() - ws_start) * 1000
        
        logger.info(f"Data access comparison for {symbol.base}/{symbol.quote}:")
        logger.info(f"  REST API latency: {rest_time:.2f}ms")
        logger.info(f"  WebSocket access: {ws_time:.4f}ms")
        logger.info(f"  Speed improvement: {rest_time/ws_time:.0f}x faster")
        
        if rest_ob and ws_ob:
            logger.info(f"\nData freshness:")
            logger.info(f"  REST timestamp: {datetime.fromtimestamp(rest_ob.timestamp)}")
            logger.info(f"  WS timestamp:   {datetime.fromtimestamp(ws_ob.timestamp)}")
            
    async def demo_error_handling(self):
        """Demonstrate error handling and recovery"""
        logger.info("=" * 60)
        logger.info("DEMO 6: Error Handling")
        logger.info("=" * 60)
        
        # Try invalid symbol
        invalid_symbol = Symbol(base=AssetName("INVALID"), quote=AssetName("COIN"), is_futures=False)
        
        try:
            logger.info("Attempting to get orderbook for invalid symbol...")
            ob = await self.exchange.get_orderbook(invalid_symbol)
        except Exception as e:
            logger.info(f"Handled error gracefully: {type(e).__name__}")
            
        # Check WebSocket health after operations
        health = self.exchange.get_websocket_health()
        logger.info(f"\nWebSocket still healthy: {health['is_connected']}")
        logger.info(f"Connection retries: {health['connection_retries']}")
        
    async def monitor_orderbooks(self):
        """Background task to monitor orderbook quality"""
        logger.info("\n[Monitor] Starting orderbook quality monitor...")
        
        while self.is_running:
            await asyncio.sleep(5)
            
            quality_stats = []
            for symbol in self.symbols:
                ob = self.exchange.get_realtime_orderbook(symbol)
                if ob:
                    quality_stats.append({
                        'symbol': f"{symbol.base}/{symbol.quote}",
                        'bid_levels': len(ob.bids),
                        'ask_levels': len(ob.asks),
                        'age': asyncio.get_event_loop().time() - ob.timestamp
                    })
            
            if quality_stats:
                logger.info("[Monitor] Orderbook quality:")
                for stat in quality_stats:
                    logger.info(
                        f"  {stat['symbol']}: "
                        f"{stat['bid_levels']} bids, "
                        f"{stat['ask_levels']} asks, "
                        f"age: {stat['age']:.1f}s"
                    )
                    
    async def run_all_demos(self):
        """Run all demonstration scenarios"""
        try:
            # Setup
            await self.setup_symbols()
            
            # Run demos sequentially
            await self.demo_initialization()
            await asyncio.sleep(2)
            
            await self.demo_rest_api()
            await asyncio.sleep(2)
            
            await self.demo_websocket_streaming()
            await asyncio.sleep(2)
            
            await self.demo_dynamic_symbols()
            await asyncio.sleep(2)
            
            await self.demo_comparison()
            await asyncio.sleep(2)
            
            await self.demo_error_handling()
            
            # Start background monitor
            monitor_task = asyncio.create_task(self.monitor_orderbooks())
            
            logger.info("\n" + "=" * 60)
            logger.info("All demos completed! Monitor running in background.")
            logger.info("Press Ctrl+C to stop...")
            logger.info("=" * 60)
            
            # Keep running until interrupted
            await asyncio.sleep(30)
            
        except KeyboardInterrupt:
            logger.info("\nShutting down...")
        except Exception as e:
            logger.error(f"Demo error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Cleanup
            self.is_running = False
            logger.info("Stopping all connections...")
            await self.exchange.stop_all()
            logger.info("Demo completed!")


async def main():
    """Main entry point"""
    demo = PublicExchangeDemo()
    await demo.run_all_demos()


if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║     Public Exchange Interface Demonstration              ║
    ║                                                          ║
    ║  This demo showcases:                                    ║
    ║  • Exchange initialization with auto WebSocket           ║
    ║  • REST API operations (orderbook, trades, info)         ║
    ║  • Real-time WebSocket streaming                         ║
    ║  • Dynamic symbol management                             ║
    ║  • REST vs WebSocket performance comparison              ║
    ║  • Error handling and recovery                           ║
    ║  • Background orderbook monitoring                       ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    
    asyncio.run(main())