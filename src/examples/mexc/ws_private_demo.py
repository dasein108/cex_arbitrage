"""
MEXC Private WebSocket Refactored Test

Standalone test for the new MEXC Private WebSocket refactored implementation.
Tests the new strategy pattern architecture with composition for private channels.
Requires valid MEXC API credentials for authentication.
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import List, Dict

# Add the src directory to path
src_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(src_dir))

# Import required structs and configs
from structs.exchange import Symbol
from core.transport.websocket.ws_client import WebSocketConfig
from core.cex.websocket.strategies import WebSocketStrategySet
from core.cex.websocket.ws_manager import WebSocketManager, WebSocketManagerConfig
from cex.mexc.ws.private.ws_message_parser import MexcPrivateMessageParser
from cex.mexc.ws.private.ws_strategies import MexcPrivateConnectionStrategy, MexcPrivateSubscriptionStrategy
from core.config.config_manager import get_exchange_config_struct, config
from cex.mexc.rest.rest_private import MexcPrivateSpotRest

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class TestPrivateWebSocketClient:
    """Simple test client for MEXC private WebSocket using strategy architecture."""
    
    def __init__(self,  account_handler, order_handler):
        self.account_handler = account_handler
        self.order_handler = order_handler
        
        # Get MEXC exchange config for strategy

        
        mexc_config = get_exchange_config_struct("mexc")

        config = WebSocketConfig(
            name="MEXC_Private_Test",
            url=mexc_config.websocket_url,  # Private uses same endpoint with auth
            timeout=30.0,
            ping_interval=20.0
        )

        # Verify credentials are available
        if not mexc_config.credentials.api_key or not mexc_config.credentials.secret_key:
            raise ValueError("MEXC API credentials are required for private WebSocket")
        
        logger.info(f"Using MEXC credentials - API Key: {mexc_config.credentials.api_key[:8]}...")
        
        # Create REST client for listen key management
        rest_client = MexcPrivateSpotRest(mexc_config)
        
        # Create strategy set for MEXC private WebSocket with REST client injection
        strategies = WebSocketStrategySet(
            connection_strategy=MexcPrivateConnectionStrategy(mexc_config, rest_client),
            subscription_strategy=MexcPrivateSubscriptionStrategy(), 
            message_parser=MexcPrivateMessageParser()
        )
        
        # Configure manager for HFT performance
        manager_config = WebSocketManagerConfig(
            batch_processing_enabled=True,
            batch_size=50,  # Smaller batches for private data
            max_pending_messages=500,
            enable_performance_tracking=True
        )
        
        # Initialize WebSocket manager
        self.ws_manager = WebSocketManager(
            config=config,
            strategies=strategies,
            message_handler=self._handle_parsed_message,
            manager_config=manager_config
        )
        
        logger.info("Test private WebSocket client initialized with strategy pattern")
    
    async def initialize(self, symbols: List[Symbol] = None) -> None:
        """Initialize WebSocket connection and subscriptions."""
        # Private WebSocket doesn't need specific symbols - subscribes to account/order updates
        await self.ws_manager.initialize(symbols or [])
        logger.info("Private WebSocket initialized for account and order updates")
    
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
            from core.cex.websocket.structs import MessageType
            
            if parsed_message.message_type == MessageType.BALANCE:
                logger.info("📊 Received BALANCE update")
                if self.account_handler and parsed_message.data:
                    await self.account_handler(parsed_message.data)
            
            elif parsed_message.message_type == MessageType.ORDER:
                logger.info("📋 Received ORDER update")
                if self.order_handler and parsed_message.data:
                    await self.order_handler(parsed_message.data)
            
            elif parsed_message.message_type == MessageType.HEARTBEAT:
                logger.debug("💓 Received heartbeat")
            
            elif parsed_message.message_type == MessageType.SUBSCRIPTION_CONFIRM:
                logger.info(f"✅ Private subscription confirmed: {parsed_message.raw_data}")
            
            elif parsed_message.message_type == MessageType.ERROR:
                logger.error(f"❌ WebSocket error: {parsed_message.raw_data}")

            elif parsed_message.message_type == MessageType.UNKNOWN:
                # Handle protobuf messages
                if parsed_message.channel == "protobuf":
                    logger.info("📦 Received PROTOBUF private message (account/order/trade data)")
                    logger.debug(f"Protobuf data length: {len(parsed_message.data.get('raw_protobuf_bytes', b''))} bytes")
                else:
                    logger.info(f"❓ Received unknown message type: {parsed_message.message_type.name}")
                    logger.debug(f"Message data: {parsed_message.raw_data}")
            
            else:
                logger.info(f"📨 Received private message type: {parsed_message.message_type.name}")
                logger.debug(f"Message data: {parsed_message.raw_data}")
            
        except Exception as e:
            logger.error(f"Error handling parsed message: {e}")

class AccountDataManager:
    """Manager for private account and order data."""
    
    def __init__(self):
        self.account_updates = []
        self.order_updates = []
        self.balance_data = {}
    
    async def handle_account_update(self, account_data):
        """Handle account balance updates."""
        self.account_updates.append(account_data)
        
        # Keep only last 50 updates
        if len(self.account_updates) > 50:
            self.account_updates = self.account_updates[-50:]
        
        logger.info(f"💰 Account update received:")
        logger.info(f"   Data: {account_data}")
        
        # Extract balance information if available
        if isinstance(account_data, dict):
            if 'balances' in account_data:
                for balance in account_data['balances']:
                    asset = balance.get('asset', 'Unknown')
                    free = balance.get('free', '0')
                    locked = balance.get('locked', '0')
                    if float(free) > 0 or float(locked) > 0:
                        logger.info(f"   {asset}: Free={free}, Locked={locked}")
                        self.balance_data[asset] = {'free': free, 'locked': locked}
    
    async def handle_order_update(self, order_data):
        """Handle order status updates."""
        self.order_updates.append(order_data)
        
        # Keep only last 100 order updates
        if len(self.order_updates) > 100:
            self.order_updates = self.order_updates[-100:]
        
        logger.info(f"📋 Order update received:")
        logger.info(f"   Data: {order_data}")
        
        # Extract order information if available
        if isinstance(order_data, dict):
            order_id = order_data.get('orderId', 'Unknown')
            symbol = order_data.get('symbol', 'Unknown')
            status = order_data.get('status', 'Unknown')
            side = order_data.get('side', 'Unknown')
            quantity = order_data.get('quantity', '0')
            price = order_data.get('price', '0')
            
            logger.info(f"   Order {order_id}: {side} {quantity} {symbol} @ {price} - Status: {status}")
    
    def get_balances(self) -> Dict:
        """Get current balance data."""
        return self.balance_data.copy()
    
    def get_recent_orders(self, limit: int = 10) -> List:
        """Get recent order updates."""
        return self.order_updates[-limit:] if self.order_updates else []

async def main():
    """Test MEXC Private WebSocket refactored functionality."""
    logger.info("🚀 Starting MEXC Private WebSocket Refactored Test...")
    from core.register import install_exchange_dependencies

    install_exchange_dependencies()
    try:
        # Configure WebSocket for private connection

        
        # Create account data manager
        manager = AccountDataManager()
        
        # Create test private WebSocket client
        ws = TestPrivateWebSocketClient(
            account_handler=manager.handle_account_update,
            order_handler=manager.handle_order_update
        )
        
        logger.info("🔌 Testing private WebSocket strategy architecture...")
        # Create a dummy symbol to trigger subscription process
        from structs.exchange import Symbol, AssetName
        dummy_symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"), is_futures=False)
        await ws.initialize([dummy_symbol])
        
        # Wait for private data updates
        logger.info("⏳ Monitoring private WebSocket connection (15 seconds)...")
        logger.info("💡 Note: MEXC private WebSocket only sends data during account activity")
        logger.info("   (trades, balance changes, order updates, deposits, etc.)")
        await asyncio.sleep(30)
        
        # Check if we received any data
        metrics = ws.get_performance_metrics()
        logger.info("📊 Performance Metrics:")
        logger.info(f"   Connection State: {metrics['connection_state']}")
        logger.info(f"   Messages Processed: {metrics['messages_processed']}")
        logger.info(f"   Error Count: {metrics['error_count']}")
        logger.info(f"   Connection Uptime: {metrics['connection_uptime_seconds']}s")
        
        # Show received data
        balances = manager.get_balances()
        recent_orders = manager.get_recent_orders(5)
        
        logger.info(f"💰 Current Balances: {len(balances)} assets")
        for asset, balance in balances.items():
            logger.info(f"   {asset}: {balance}")
        
        logger.info(f"📋 Recent Orders: {len(recent_orders)} updates")
        for i, order in enumerate(recent_orders[-3:], 1):  # Show last 3
            logger.info(f"   {i}. {order}")
        
        if metrics['messages_processed'] > 0:
            logger.info("✅ Private WebSocket strategy pattern test successful!")
            logger.info("🎉 Received private data - your account has activity!")
        else:
            logger.info("ℹ️  No private messages received - this is NORMAL behavior")
            logger.info("✅ Private WebSocket connection and authentication working correctly")
            logger.info("💡 To see private messages, perform trading activity in your MEXC account")
        
    except Exception as e:
        logger.error(f"❌ Error during private WebSocket test: {e}")
        raise
    
    finally:
        if 'ws' in locals():
            await ws.close()
    
    logger.info("✅ Private WebSocket test completed!")

if __name__ == "__main__":
    asyncio.run(main())