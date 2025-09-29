"""
Generic Private WebSocket Integration Demo

Demonstrates private WebSocket functionality across multiple exchanges.
Tests actual exchange WebSocket implementations (MexcWebsocketPrivate, etc.)
that inherit from BaseExchangePrivateWebsocketInterface.
Shows account balance, order, and trade updates in real-time.
Requires valid API credentials for authentication.

Usage:
    python src/examples/websocket_private_demo.py mexc
    python src/examples/websocket_private_demo.py gateio
"""

import asyncio
import logging
import sys
from typing import List, Dict

from exchanges.structs.common import Order, AssetBalance, Trade
from config.config_manager import HftConfig
from exchanges.exchange_factory import create_websocket_client, create_private_handlers
from exchanges.utils.exchange_utils import get_exchange_enum
from exchanges.consts import DEFAULT_PRIVATE_WEBSOCKET_CHANNELS
# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PrivateWebSocketClient:
    """Exchange-agnostic private WebSocket client using actual exchange implementations."""

    def __init__(self, exchange_name: str, account_handler, order_handler, trade_handler=None):
        self.exchange_name = exchange_name.upper()
        self.account_handler = account_handler
        self.order_handler = order_handler
        self.trade_handler = trade_handler

        # Get exchange config
        config_manager = HftConfig()
        config = config_manager.get_exchange_config(self.exchange_name.lower())

        # Verify credentials are available
        if not config.credentials.api_key or not config.credentials.secret_key:
            raise ValueError(f"{self.exchange_name} API credentials are required for private WebSocket")

        logger.info(f"Using {self.exchange_name} credentials - API Key: {config.credentials.api_key[:8]}...")

        # Create exchange WebSocket instance using the factory pattern
        self.websocket = create_websocket_client(
            exchange=get_exchange_enum(exchange_name),
            is_private=True,
            config=config
        )

        self.websocket.order_handler=self._handle_order_update
        self.websocket.balance_handler=self._handle_balance_update
        self.websocket.trade_handler=self._handle_trade_update



        logger.info(f"{self.exchange_name} private WebSocket client initialized with {type(self.websocket).__name__}")

    async def initialize(self) -> None:
        """Initialize WebSocket connection and subscriptions."""
        # For private WebSocket, pass empty list to initialize() - private channels will be subscribed automatically
        await self.websocket.initialize()

        logger.info(f"{self.exchange_name} private WebSocket initialized for account and order updates")

    async def close(self) -> None:
        """Close WebSocket connection and REST client."""
        await self.websocket.close()

    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self.websocket.is_connected()

    async def _handle_order_update(self, order: Order) -> None:
        """Handle order updates from WebSocket."""
        logger.info(f"📋 {self.exchange_name} ORDER update")
        if self.order_handler:
            await self.order_handler(order)

    async def _handle_balance_update(self, balances) -> None:
        """Handle balance updates from WebSocket."""
        logger.info(f"📊 {self.exchange_name} BALANCE update")
        if self.account_handler:
            # Handle different balance formats
            if isinstance(balances, dict):
                # If it's a dict of balances, pass individual balance
                for balance in balances.values():
                    await self.account_handler(balance)
            else:
                # Single balance update
                await self.account_handler(balances)

    async def _handle_trade_update(self, trade: Trade) -> None:
        """Handle trade updates from WebSocket."""
        logger.info(f"💹 {self.exchange_name} TRADE update")
        if self.trade_handler:
            await self.trade_handler(trade)


class AccountDataManager:
    """Manager for private account and order data."""

    def __init__(self, exchange_name: str):
        self.exchange_name = exchange_name.upper()
        self.account_updates = []
        self.order_updates = []
        self.trade_updates = []
        self.balance_data = {}

    async def handle_account_update(self, account_data):
        """Handle account balance updates."""
        self.account_updates.append(account_data)

        # Keep only last 50 updates
        if len(self.account_updates) > 50:
            self.account_updates = self.account_updates[-50:]

        logger.info(f"💰 {self.exchange_name} account update received:")

        # Handle unified AssetBalance type
        if isinstance(account_data, AssetBalance):
            asset = account_data.asset
            free = account_data.available
            locked = account_data.locked

            if free > 0 or locked > 0:
                logger.info(f"   {asset}: Free={free}, Locked={locked}, Total={account_data.total}")
                self.balance_data[asset] = {
                    'free': free,
                    'locked': locked,
                    'total': account_data.total
                }
        else:
            # Handle other data formats (dict, etc.)
            logger.info(f"   Data: {account_data}")
            if isinstance(account_data, dict) and 'balances' in account_data:
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

        logger.info(f"📋 {self.exchange_name} order update received:")

        # Handle unified Order type
        if isinstance(order_data, Order):
            logger.info(f"   Order {order_data.order_id}: {order_data.side.name} {order_data.quantity}")
            logger.info(f"   Symbol: {order_data.symbol.base}/{order_data.symbol.quote}")
            logger.info(f"   Price: {order_data.price}, Filled: {order_data.filled_quantity}")
            logger.info(f"   Status: {order_data.status.name}")
        else:
            # Handle other data formats (dict, etc.)
            logger.info(f"   Data: {order_data}")
            if isinstance(order_data, dict):
                order_id = order_data.get('orderId', order_data.get('order_id', 'Unknown'))
                symbol = order_data.get('symbol', 'Unknown')
                status = order_data.get('status', 'Unknown')
                side = order_data.get('side', 'Unknown')
                quantity = order_data.get('quantity', order_data.get('amount', '0'))
                price = order_data.get('price', '0')

                logger.info(f"   Order {order_id}: {side} {quantity} {symbol} @ {price} - Status: {status}")

    async def handle_trade_update(self, trade_data):
        """Handle trade execution updates."""
        self.trade_updates.append(trade_data)

        # Keep only last 100 trade updates
        if len(self.trade_updates) > 100:
            self.trade_updates = self.trade_updates[-100:]

        logger.info(f"💹 {self.exchange_name} trade update received:")

        # Handle unified Trade type
        if isinstance(trade_data, Trade):
            logger.info(f"   {trade_data.side.name} {trade_data.amount} @ {trade_data.price}")
            logger.info(f"   Maker: {trade_data.is_maker}, Timestamp: {trade_data.timestamp}")
        else:
            # Handle other data formats (dict, etc.)
            logger.info(f"   Data: {trade_data}")

    def get_balances(self) -> Dict:
        """Get current balance data."""
        return self.balance_data.copy()

    def get_recent_orders(self, limit: int = 10) -> List:
        """Get recent order updates."""
        return self.order_updates[-limit:] if self.order_updates else []

    def get_recent_trades(self, limit: int = 10) -> List:
        """Get recent trade updates."""
        return self.trade_updates[-limit:] if self.trade_updates else []

    def get_summary(self) -> Dict:
        """Get summary of received data."""
        return {
            'account_updates': len(self.account_updates),
            'order_updates': len(self.order_updates),
            'trade_updates': len(self.trade_updates),
            'balance_assets': len(self.balance_data)
        }


async def main(exchange_name: str):
    """Test private WebSocket functionality for the specified exchange."""
    exchange_upper = exchange_name.upper()
    logger.info(f"🚀 Starting {exchange_upper} Private WebSocket Demo...")
    logger.info("=" * 60)

    try:
        # Create account data manager
        manager = AccountDataManager(exchange_name)

        # Create test private WebSocket client
        ws = PrivateWebSocketClient(
            exchange_name=exchange_name,
            account_handler=manager.handle_account_update,
            order_handler=manager.handle_order_update,
            trade_handler=manager.handle_trade_update
        )

        logger.info(f"🔌 Testing {exchange_upper} private WebSocket factory architecture...")

        await ws.initialize()

        # Wait for private data updates
        logger.info(f"⏳ Monitoring {exchange_upper} private WebSocket connection (30 seconds)...")
        logger.info(f"💡 Note: {exchange_upper} private WebSocket only sends data during account activity")
        logger.info("   (trades, balance changes, order updates, deposits, withdrawals, etc.)")
        await asyncio.sleep(30)

        # Show received data summary
        summary = manager.get_summary()
        logger.info("📈 Data Summary:")
        logger.info(f"   Account updates: {summary['account_updates']}")
        logger.info(f"   Order updates: {summary['order_updates']}")
        logger.info(f"   Trade updates: {summary['trade_updates']}")
        logger.info(f"   Balance assets: {summary['balance_assets']}")

        # Show current balances
        balances = manager.get_balances()
        if balances:
            logger.info(f"💰 Current Balances ({len(balances)} assets):")
            for asset, balance in list(balances.items())[:5]:  # Show first 5
                logger.info(f"   {asset}: {balance}")

        # Show recent orders
        recent_orders = manager.get_recent_orders(3)
        if recent_orders:
            logger.info(f"📋 Recent Orders (showing {len(recent_orders)}):")
            for i, order in enumerate(recent_orders, 1):
                if isinstance(order, Order):
                    logger.info(f"   {i}. {order.order_id} - {order.status}")
                else:
                    logger.info(f"   {i}. {order}")

        # Show recent trades
        recent_trades = manager.get_recent_trades(3)
        if recent_trades:
            logger.info(f"💹 Recent Trades (showing {len(recent_trades)}):")
            for i, trade in enumerate(recent_trades, 1):
                if isinstance(trade, Trade):
                    logger.info(f"   {i}. {trade.side.name} {trade.quantity} @ {trade.price}")
                else:
                    logger.info(f"   {i}. {trade}")

        total_updates = summary['account_updates'] + summary['order_updates'] + summary['trade_updates']

        if total_updates > 0:
            logger.info(f"✅ {exchange_upper} private WebSocket demo successful!")
            logger.info("🎉 Received private account data - your account has activity!")
        else:
            logger.info(f"ℹ️  No private messages received from {exchange_upper} - this is NORMAL behavior")
            logger.info("✅ Private WebSocket connection and authentication working correctly")
            logger.info(f"💡 To see private messages, perform trading activity in your {exchange_upper} account")
            logger.info("   (place orders, make trades, deposits, withdrawals, etc.)")

    except ValueError as e:
        logger.error(f"Configuration Error: {e}")
        logger.error(f"Make sure {exchange_upper} API credentials are configured")
        raise
    except Exception as e:
        logger.error(f"Error during {exchange_upper} private WebSocket test: {e}")
        import traceback
        traceback.print_exc()
        raise

    finally:
        if 'ws' in locals():
            await ws.close()

    logger.info("=" * 60)
    logger.info(f"✅ {exchange_upper} private WebSocket demo completed!")


if __name__ == "__main__":
    exchange_name = sys.argv[1] if len(sys.argv) > 1 else "mexc_spot"

    try:
        asyncio.run(main(exchange_name))
        print(f"\n✅ {exchange_name.upper()} private WebSocket demo completed successfully!")
    except Exception as e:
        print(f"\n❌ {exchange_name.upper()} private WebSocket demo failed: {e}")
        sys.exit(1)
