#!/usr/bin/env python3
"""
Gate.io Public WebSocket API Example

Demonstrates usage of Gate.io public WebSocket API for real-time market data streaming.
This example shows how to use the GateioWebsocketPublic class to:

1. Stream real-time orderbook updates
2. Stream real-time trade data
3. Handle WebSocket connections and reconnections
4. Process high-frequency market data

No API credentials required for public channels.

Usage:
    python -m src.examples.gateio.public_websocket_example
"""

import asyncio
import logging
from typing import List

from exchanges.gateio.ws.gateio_ws_public import GateioWebsocketPublic
from structs.exchange import Symbol, AssetName, OrderBook, Trade
from core.transport.websocket.ws_client import WebSocketConfig


class MarketDataProcessor:
    """Example market data processor for WebSocket streams."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.orderbook_updates = 0
        self.trade_updates = 0
        self.latest_prices = {}
        
    async def handle_orderbook_update(self, symbol: Symbol, orderbook: OrderBook):
        """Handle real-time orderbook updates."""
        self.orderbook_updates += 1
        
        # Calculate mid price if we have both bids and asks
        mid_price = None
        spread = None
        
        if orderbook.bids and orderbook.asks:
            best_bid = orderbook.bids[0].price
            best_ask = orderbook.asks[0].price
            mid_price = (best_bid + best_ask) / 2
            spread = best_ask - best_bid
            spread_pct = (spread / mid_price) * 100
            
            # Store latest price
            self.latest_prices[symbol] = mid_price
            
            # Log every 10th update to avoid spam
            if self.orderbook_updates % 10 == 0:
                self.logger.info(
                    f"📊 {symbol.base}/{symbol.quote} Orderbook #{self.orderbook_updates}: "
                    f"Bid: ${best_bid:,.2f}, Ask: ${best_ask:,.2f}, "
                    f"Mid: ${mid_price:,.2f}, Spread: ${spread:.2f} ({spread_pct:.3f}%)"
                )
    
    async def handle_trade_update(self, symbol: Symbol, trades: List[Trade]):
        """Handle real-time trade updates."""
        self.trade_updates += len(trades)
        
        # Log recent trades
        for trade in trades:
            side_emoji = "🟢" if trade.side.name == "BUY" else "🔴" 
            self.logger.info(
                f"💰 {symbol.base}/{symbol.quote} Trade #{self.trade_updates}: "
                f"{side_emoji} {trade.side.name} {trade.amount:.6f} @ ${trade.price:,.2f}"
            )
    
    def get_stats(self):
        """Get processing statistics."""
        return {
            'orderbook_updates': self.orderbook_updates,
            'trade_updates': self.trade_updates,
            'symbols_tracked': len(self.latest_prices),
            'latest_prices': self.latest_prices.copy()
        }


async def demonstrate_websocket_streaming():
    """Demonstrate Gate.io WebSocket streaming."""
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger = logging.getLogger(__name__)
    
    # Initialize market data processor
    processor = MarketDataProcessor()
    
    # Configure WebSocket client
    ws_config = WebSocketConfig(
        name="gateio_example",
        url="wss://api.gateio.ws/ws/v4/",
        timeout=30.0,
        ping_interval=20.0,
        max_reconnect_attempts=5,
        reconnect_delay=2.0,
        max_queue_size=1000,
        enable_compression=False
    )
    
    # Initialize Gate.io WebSocket client
    logger.info("Initializing Gate.io WebSocket client...")
    ws_client = GateioWebsocketPublic(
        websocket_config=ws_config,
        orderbook_handler=processor.handle_orderbook_update,
        trades_handler=processor.handle_trade_update
    )
    
    # Define symbols to stream
    symbols = [
        Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
        Symbol(base=AssetName("ETH"), quote=AssetName("USDT")),
        # Symbol(cex=AssetName("BNB"), quote=AssetName("USDT")),  # Add more as needed
    ]
    
    try:
        # Start WebSocket streaming
        logger.info("Starting WebSocket streaming...")
        await ws_client.initialize([])
        
        # Wait for connection to stabilize
        logger.info("Waiting for WebSocket connection to stabilize...")
        await asyncio.sleep(2)
        
        # Add symbols one by one
        for symbol in symbols:
            logger.info(f"Starting stream for {symbol.base}/{symbol.quote}...")
            await ws_client.start_symbol(symbol)
            await asyncio.sleep(1)  # Brief delay between subscriptions
        
        logger.info("✅ All streams started successfully!")
        logger.info("Streaming real-time market data... (Press Ctrl+C to stop)")
        
        # Stream for specified duration or until interrupted
        streaming_duration = 30  # seconds
        start_time = asyncio.get_event_loop().time()
        
        # Status reporting task
        async def report_status():
            while True:
                await asyncio.sleep(5)  # Report every 5 seconds
                stats = processor.get_stats()
                ws_stats = ws_client.get_performance_metrics()
                
                logger.info(
                    f"📈 Status: {stats['orderbook_updates']} orderbook updates, "
                    f"{stats['trade_updates']} trades, "
                    f"{ws_stats.get('active_channels', 0)} active channels"
                )
                
                # Show latest prices
                if stats['latest_prices']:
                    logger.info("Latest prices:")
                    for symbol, price in stats['latest_prices'].items():
                        logger.info(f"  {symbol.base}/{symbol.quote}: ${price:,.2f}")
        
        # Start status reporting
        status_task = asyncio.create_task(report_status())
        
        try:
            # Stream for the specified duration
            while asyncio.get_event_loop().time() - start_time < streaming_duration:
                await asyncio.sleep(1)
            
            logger.info(f"⏰ Streaming completed after {streaming_duration} seconds")
            
        except KeyboardInterrupt:
            logger.info("⚠️ Streaming interrupted by user")
        
        finally:
            # Cancel status reporting
            status_task.cancel()
            try:
                await status_task
            except asyncio.CancelledError:
                pass
        
        # Final statistics
        logger.info("\n=== Final Statistics ===")
        final_stats = processor.get_stats()
        ws_metrics = ws_client.get_performance_metrics()
        
        logger.info(f"Orderbook updates processed: {final_stats['orderbook_updates']}")
        logger.info(f"Trade updates processed: {final_stats['trade_updates']}")
        logger.info(f"Symbols tracked: {final_stats['symbols_tracked']}")
        logger.info(f"WebSocket metrics: {ws_metrics}")
        
        if final_stats['latest_prices']:
            logger.info("Final prices:")
            for symbol, price in final_stats['latest_prices'].items():
                logger.info(f"  {symbol.base}/{symbol.quote}: ${price:,.2f}")
        
    except Exception as e:
        logger.error(f"Error during WebSocket streaming: {e}")
        raise
    
    finally:
        # Clean up resources
        logger.info("Closing WebSocket connection...")
        await ws_client.close()
        logger.info("WebSocket connection closed")


async def demonstrate_symbol_management():
    """Demonstrate dynamic symbol subscription management."""
    
    logger = logging.getLogger(__name__)
    processor = MarketDataProcessor()
    
    # Configure minimal WebSocket client
    ws_config = WebSocketConfig(
        name="gateio_symbol_demo",
        url="wss://api.gateio.ws/ws/v4/",
        timeout=30.0,
        ping_interval=20.0,
        max_reconnect_attempts=3,
        reconnect_delay=1.0,
        max_queue_size=500
    )
    
    ws_client = GateioWebsocketPublic(
        websocket_config=ws_config,
        orderbook_handler=processor.handle_orderbook_update,
        trades_handler=None  # Only orderbook for this demo
    )
    
    try:
        logger.info("\n=== Symbol Management Demo ===")
        
        # Start with empty subscriptions
        await ws_client.initialize([])
        
        symbols = [
            Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
            Symbol(base=AssetName("ETH"), quote=AssetName("USDT")),
            Symbol(base=AssetName("SOL"), quote=AssetName("USDT")),
        ]
        
        # Add symbols dynamically
        for symbol in symbols:
            logger.info(f"Adding {symbol.base}/{symbol.quote} to stream...")
            await ws_client.start_symbol(symbol)
            await asyncio.sleep(3)  # Collect some data
            
            stats = processor.get_stats()
            logger.info(f"Updates so far: {stats['orderbook_updates']}")
        
        logger.info("All symbols added. Streaming for 10 seconds...")
        await asyncio.sleep(10)
        
        # Remove symbols dynamically
        for symbol in symbols[:-1]:  # Keep last symbol
            logger.info(f"Removing {symbol.base}/{symbol.quote} from stream...")
            await ws_client.stop_symbol(symbol)
            await asyncio.sleep(2)
        
        logger.info("Symbol management demo completed")
        
    finally:
        await ws_client.close()


def main():
    """Main entry point."""
    print("Gate.io Public WebSocket API Example")
    print("=" * 50)
    print("This example demonstrates Gate.io WebSocket streaming for real-time market data.")
    print("No API credentials required.")
    print()
    
    try:
        # Run main streaming demonstration
        print("🔄 Running WebSocket streaming demo...")
        asyncio.run(demonstrate_websocket_streaming())
        
        print("\n🔄 Running symbol management demo...")
        asyncio.run(demonstrate_symbol_management())
        
        print("\n✅ All WebSocket examples completed successfully!")
        
    except KeyboardInterrupt:
        print("\n⚠️ Examples interrupted by user")
    
    except Exception as e:
        print(f"\n❌ Examples failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()