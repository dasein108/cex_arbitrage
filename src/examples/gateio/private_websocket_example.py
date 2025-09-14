#!/usr/bin/env python3
"""
Gate.io Private WebSocket API Example

Demonstrates usage of Gate.io private WebSocket API for real-time account data streaming.
This example shows how to use the GateioWebsocketPrivate class to:

1. Stream real-time order updates
2. Stream real-time balance changes
3. Handle WebSocket connections and reconnections
4. Process high-frequency account data

API credentials required for private channels.

Usage:
    python -m src.examples.gateio.private_websocket_example
    
Requirements:
    - Configure GATEIO_API_KEY and GATEIO_SECRET_KEY in config.yaml
    - See config.yaml example for proper format
"""

import asyncio
import logging
from typing import List

from exchanges.gateio.ws.gateio_ws_private import GateioWebsocketPrivate
from exchanges.interface.structs import Symbol, AssetName, Order, AssetBalance
from common.ws_client import WebSocketConfig
from common.config import config


class AccountDataProcessor:
    """Example account data processor for private WebSocket streams."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.order_updates = 0
        self.balance_updates = 0
        self.latest_orders = {}
        self.latest_balances = {}
        
    async def handle_order_update(self, symbol: Symbol, order: Order):
        """Handle real-time order updates."""
        self.order_updates += 1
        
        # Store latest order for this symbol
        self.latest_orders[symbol] = order
        
        # Log every order update with detailed information
        status_emoji = {
            1: "🆕",  # NEW
            2: "✅",  # FILLED
            3: "🔄",  # PARTIALLY_FILLED
            4: "❌",  # CANCELED
            5: "⚠️",  # PARTIALLY_CANCELED
            6: "⏰",  # EXPIRED
            7: "🚫",  # REJECTED
        }.get(order.status.value, "❓")
        
        side_emoji = "🟢" if order.side.value == 1 else "🔴"  # BUY=1, SELL=2
        
        fill_pct = (order.amount_filled / order.amount * 100) if order.amount > 0 else 0
        
        self.logger.info(
            f"🔔 {symbol.base}/{symbol.quote} Order #{self.order_updates}: "
            f"{status_emoji} {order.status.name} {side_emoji} {order.side.name} "
            f"{order.amount:.6f} @ ${order.price:,.2f} "
            f"(Filled: {order.amount_filled:.6f} - {fill_pct:.1f}%)"
        )
        
        if order.order_id:
            self.logger.info(f"   📋 Order ID: {order.order_id}")
        if order.fee > 0:
            self.logger.info(f"   💰 Fee: ${order.fee:.6f}")
    
    async def handle_balance_update(self, balance: AssetBalance):
        """Handle real-time balance updates."""
        self.balance_updates += 1
        
        # Store latest balance for this asset
        self.latest_balances[balance.asset] = balance
        
        # Only log significant balances (> 0.001)
        if balance.total > 0.001:
            self.logger.info(
                f"💼 Balance Update #{self.balance_updates}: "
                f"{balance.asset} - Total: {balance.total:.6f} "
                f"(Free: {balance.free:.6f}, Locked: {balance.locked:.6f})"
            )
    
    def get_stats(self):
        """Get processing statistics."""
        return {
            'order_updates': self.order_updates,
            'balance_updates': self.balance_updates,
            'symbols_with_orders': len(self.latest_orders),
            'assets_with_balance': len(self.latest_balances),
            'latest_orders': self.latest_orders.copy(),
            'latest_balances': self.latest_balances.copy()
        }


async def demonstrate_private_websocket_streaming():
    """Demonstrate Gate.io private WebSocket streaming."""
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger = logging.getLogger(__name__)
    
    # Get API credentials from config
    gateio_credentials = config.get_exchange_credentials('gateio')
    api_key = gateio_credentials['api_key']
    secret_key = gateio_credentials['secret_key']
    
    if not api_key or not secret_key:
        logger.error("❌ Missing Gate.io API credentials!")
        logger.error("Please configure GATEIO_API_KEY and GATEIO_SECRET_KEY in config.yaml")
        logger.error("Example config.yaml:")
        logger.error("  gateio:")
        logger.error("    api_key: 'your_api_key_here'")
        logger.error("    secret_key: 'your_secret_here'")
        return
    
    # Initialize account data processor
    processor = AccountDataProcessor()
    
    # Configure WebSocket client
    ws_config = WebSocketConfig(
        name="gateio_private_example",
        url="wss://api.gateio.ws/ws/v4/",
        timeout=30.0,
        ping_interval=20.0,
        max_reconnect_attempts=5,
        reconnect_delay=2.0,
        max_queue_size=1000,
        enable_compression=False
    )
    
    # Initialize Gate.io private WebSocket client
    logger.info("Initializing Gate.io private WebSocket client...")
    ws_client = GateioWebsocketPrivate(
        config=ws_config,
        api_key=api_key,
        secret_key=secret_key,
        order_handler=processor.handle_order_update,
        balance_handler=processor.handle_balance_update
    )
    
    # Define symbols to monitor (for order updates - balances are account-wide)
    symbols = [
        Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
        Symbol(base=AssetName("ETH"), quote=AssetName("USDT")),
        # Symbol(base=AssetName("BNB"), quote=AssetName("USDT")),  # Add more as needed
    ]
    
    try:
        # Start WebSocket streaming
        logger.info("Starting private WebSocket streaming...")
        await ws_client.init([])  # Private channels are account-wide, no symbols needed
        
        # Wait for connection to stabilize
        logger.info("Waiting for WebSocket connection to stabilize...")
        await asyncio.sleep(2)
        
        # Add symbols one by one (though private channels are account-wide)
        for symbol in symbols:
            logger.info(f"Monitoring orders for {symbol.base}/{symbol.quote}...")
            await ws_client.start_symbol(symbol)
            await asyncio.sleep(1)  # Brief delay between subscriptions
        
        logger.info("✅ All private streams started successfully!")
        logger.info("Streaming real-time account data... (Press Ctrl+C to stop)")
        logger.info("💡 To see order updates, place/cancel orders on Gate.io")
        logger.info("💡 Balance updates will show when trades execute or deposits/withdrawals occur")
        
        # Stream for specified duration or until interrupted
        streaming_duration = 60  # seconds
        start_time = asyncio.get_event_loop().time()
        
        # Status reporting task
        async def report_status():
            while True:
                await asyncio.sleep(10)  # Report every 10 seconds
                stats = processor.get_stats()
                ws_stats = ws_client.get_performance_metrics()
                
                logger.info(
                    f"📈 Status: {stats['order_updates']} order updates, "
                    f"{stats['balance_updates']} balance updates, "
                    f"{ws_stats.get('active_channels', 0)} active channels"
                )
                
                # Show latest orders
                if stats['latest_orders']:
                    logger.info("Recent orders:")
                    for symbol, order in list(stats['latest_orders'].items())[-3:]:  # Show last 3
                        logger.info(f"  {symbol.base}/{symbol.quote}: {order.status.name} {order.side.name} {order.amount:.6f} @ ${order.price:,.2f}")
                
                # Show significant balances
                significant_balances = {asset: balance for asset, balance in stats['latest_balances'].items() if balance.total > 0.001}
                if significant_balances:
                    logger.info("Current balances:")
                    for asset, balance in list(significant_balances.items())[-5:]:  # Show last 5
                        logger.info(f"  {asset}: {balance.total:.6f} (Free: {balance.free:.6f})")
        
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
        
        logger.info(f"Order updates processed: {final_stats['order_updates']}")
        logger.info(f"Balance updates processed: {final_stats['balance_updates']}")
        logger.info(f"Symbols monitored: {final_stats['symbols_with_orders']}")
        logger.info(f"Assets with balances: {final_stats['assets_with_balance']}")
        logger.info(f"WebSocket metrics: {ws_metrics}")
        
        if final_stats['latest_orders']:
            logger.info("Final order states:")
            for symbol, order in final_stats['latest_orders'].items():
                logger.info(f"  {symbol.base}/{symbol.quote}: {order.status.name} {order.side.name} {order.amount:.6f} @ ${order.price:,.2f}")
        
        if final_stats['latest_balances']:
            logger.info("Final balances:")
            for asset, balance in final_stats['latest_balances'].items():
                if balance.total > 0.001:
                    logger.info(f"  {asset}: {balance.total:.6f}")
        
    except Exception as e:
        logger.error(f"Error during private WebSocket streaming: {e}")
        raise
    
    finally:
        # Clean up resources
        logger.info("Closing private WebSocket connection...")
        await ws_client.close()
        logger.info("Private WebSocket connection closed")


async def demonstrate_symbol_management():
    """Demonstrate dynamic symbol subscription management for private channels."""
    
    logger = logging.getLogger(__name__)
    processor = AccountDataProcessor()
    
    # Get API credentials from config
    gateio_credentials = config.get_exchange_credentials('gateio')
    api_key = gateio_credentials['api_key']
    secret_key = gateio_credentials['secret_key']
    
    if not api_key or not secret_key:
        logger.error("❌ Missing Gate.io API credentials for symbol management demo!")
        return
    
    # Configure minimal WebSocket client
    ws_config = WebSocketConfig(
        name="gateio_private_symbol_demo",
        url="wss://api.gateio.ws/ws/v4/",
        timeout=30.0,
        ping_interval=20.0,
        max_reconnect_attempts=3,
        reconnect_delay=1.0,
        max_queue_size=500
    )
    
    ws_client = GateioWebsocketPrivate(
        config=ws_config,
        api_key=api_key,
        secret_key=secret_key,
        order_handler=processor.handle_order_update,
        balance_handler=None  # Only orders for this demo
    )
    
    try:
        logger.info("\n=== Private Symbol Management Demo ===")
        
        # Start with empty subscriptions
        await ws_client.init([])
        
        symbols = [
            Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
            Symbol(base=AssetName("ETH"), quote=AssetName("USDT")),
            Symbol(base=AssetName("SOL"), quote=AssetName("USDT")),
        ]
        
        # Add symbols dynamically (note: private channels are account-wide)
        for symbol in symbols:
            logger.info(f"Adding {symbol.base}/{symbol.quote} to monitoring...")
            await ws_client.start_symbol(symbol)
            await asyncio.sleep(3)  # Collect some data
            
            stats = processor.get_stats()
            logger.info(f"Updates so far: {stats['order_updates']} orders, {stats['balance_updates']} balances")
        
        logger.info("All symbols added. Monitoring for 15 seconds...")
        await asyncio.sleep(15)
        
        # Remove symbols dynamically
        for symbol in symbols[:-1]:  # Keep last symbol
            logger.info(f"Removing {symbol.base}/{symbol.quote} from monitoring...")
            await ws_client.stop_symbol(symbol)
            await asyncio.sleep(2)
        
        logger.info("Private symbol management demo completed")
        
    finally:
        await ws_client.close()


def main():
    """Main entry point."""
    print("Gate.io Private WebSocket API Example")
    print("=" * 50)
    print("This example demonstrates Gate.io private WebSocket streaming for real-time account data.")
    print("API credentials from config.yaml are required.")
    print()
    
    try:
        # Run main private streaming demonstration
        print("🔄 Running private WebSocket streaming demo...")
        asyncio.run(demonstrate_private_websocket_streaming())
        
        print("\n🔄 Running private symbol management demo...")
        asyncio.run(demonstrate_symbol_management())
        
        print("\n✅ All private WebSocket examples completed successfully!")
        
    except KeyboardInterrupt:
        print("\n⚠️ Examples interrupted by user")
    
    except Exception as e:
        print(f"\n❌ Examples failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()