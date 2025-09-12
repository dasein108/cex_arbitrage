"""
MEXC Private WebSocket Simple Check

Simple test to verify MEXC private WebSocket implementation works.
Tests listen key creation, connection, subscription, and private event handling.
"""

import asyncio
import logging
from typing import List
from exchanges.interface.structs import Order, AssetBalance, Trade
from exchanges.mexc.ws.mexc_ws_private import MexcWebsocketPrivate
from exchanges.mexc.rest.mexc_private import MexcPrivateExchange
from common.ws_client import WebSocketConfig

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class PrivateEventManager:
    """External private event storage and management."""
    
    def __init__(self):
        self.orders: List[Order] = []
        self.balances: List[AssetBalance] = []
        self.trades: List[Trade] = []
    
    async def handle_order_update(self, order: Order):
        """Store and process order updates."""
        self.orders.append(order)
        
        logger.info(f"📋 Order update:")
        logger.info(f"   ID: {order.order_id}")
        logger.info(f"   Symbol: {order.symbol.base}/{order.symbol.quote}")
        logger.info(f"   Side: {order.side.name}")
        logger.info(f"   Status: {order.status.name}")
        logger.info(f"   Amount: {order.amount} (Filled: {order.amount_filled})")
        logger.info(f"   Price: {order.price}")
    
    async def handle_balance_update(self, balances: List[AssetBalance]):
        """Store and process balance updates."""
        # Keep only latest balance update
        self.balances = balances
        
        logger.info(f"💰 Balance update: {len(balances)} assets")
        for balance in balances:
            if balance.free > 0 or balance.locked > 0:
                logger.info(f"   {balance.asset}: Free={balance.free}, Locked={balance.locked}")
    
    async def handle_trade_update(self, trade: Trade):
        """Store and process trade updates."""
        self.trades.append(trade)
        
        logger.info(f"💹 Trade executed:")
        logger.info(f"   Side: {trade.side.name}")
        logger.info(f"   Amount: {trade.amount}")
        logger.info(f"   Price: {trade.price}")
        logger.info(f"   Type: {'Maker' if trade.is_maker else 'Taker'}")
    
    def get_summary(self):
        """Get summary of captured events."""
        return {
            'orders': len(self.orders),
            'balance_updates': 1 if self.balances else 0,
            'trades': len(self.trades),
            'latest_balances': len([b for b in self.balances if b.free > 0 or b.locked > 0])
        }


async def main():
    """Test MEXC Private WebSocket functionality."""
    logger.info("🚀 Starting MEXC Private WebSocket test...")
    
    try:
        # Load config to get API credentials
        from common.config import config
        
        # Create private REST client for listen key management
        logger.info("🔑 Creating MEXC private client...")
        private_client = MexcPrivateExchange(
            api_key=config.MEXC_API_KEY,
            secret_key=config.MEXC_SECRET_KEY
        )
        
        # Test basic API connectivity first
        logger.info("🧪 Testing API connectivity...")
        account_balance = await private_client.get_account_balance()
        logger.info(f"✅ API connected. Account has {len(account_balance)} non-zero balances")
        
        # Configure WebSocket (URL will be overridden by private config)
        config = WebSocketConfig(
            name="MEXC_Private_Test",
            url="placeholder",  # Will be overridden
            timeout=30.0,
            ping_interval=20.0,
            max_reconnect_attempts=3
        )
        
        # Create event manager for external storage
        manager = PrivateEventManager()
        
        # Create private WebSocket instance with injected handlers
        ws = MexcWebsocketPrivate(
            private_client=private_client,
            config=config,
            order_handler=manager.handle_order_update,
            balance_handler=manager.handle_balance_update,
            trade_handler=manager.handle_trade_update,
            keep_alive_interval=1800  # 30 minutes
        )
        
        logger.info("🔌 Connecting to MEXC Private WebSocket...")
        
        # Initialize private WebSocket (creates listen key automatically)
        await ws.init()
        
        logger.info("✅ Private WebSocket connected with listen key!")
        logger.info("📡 Waiting for private events (60 seconds)...")
        logger.info("💡 To see events, place some orders or have account activity")
        
        # Wait for private events
        await asyncio.sleep(60)
        
        # Check captured events
        summary = manager.get_summary()
        logger.info("\n📊 Event Summary:")
        logger.info(f"   Orders received: {summary['orders']}")
        logger.info(f"   Balance updates: {summary['balance_updates']}")
        logger.info(f"   Trades received: {summary['trades']}")
        logger.info(f"   Assets with balance: {summary['latest_balances']}")
        
        if summary['orders'] > 0:
            logger.info("✅ Order events captured successfully!")
        if summary['balance_updates'] > 0:
            logger.info("✅ Balance events captured successfully!")
        if summary['trades'] > 0:
            logger.info("✅ Trade events captured successfully!")
        
        if sum(summary.values()) == 0:
            logger.info("ℹ️  No private events received (normal if no trading activity)")
        
    except Exception as e:
        logger.error(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        logger.info("🔚 Cleaning up...")
        try:
            # Stop WebSocket and cleanup listen key
            await ws.stop()
            
            # Close private client
            await private_client.close()
            
        except Exception as cleanup_error:
            logger.error(f"⚠️  Cleanup error: {cleanup_error}")
    
    logger.info("✅ Private WebSocket test completed!")


if __name__ == "__main__":
    asyncio.run(main())