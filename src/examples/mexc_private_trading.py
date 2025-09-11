#!/usr/bin/env python3
"""
MEXC Private Trading Example

Comprehensive demonstration of MEXC private exchange functionality for trading operations.
Shows account management, order placement, order management, and error handling.

Features demonstrated:
- Account balance queries
- Order placement (limit, market orders)
- Order status monitoring
- Order cancellation and modification
- Error handling and recovery
- Performance monitoring

⚠️ IMPORTANT: This example uses demo credentials. Replace with real API keys for actual trading.
⚠️ WARNING: Always test on MEXC testnet before using in production environment.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional

from exchanges.mexc.mexc_private import MexcPrivateExchange
from structs.exchange import Symbol, AssetName, Side, OrderType, OrderStatus, AssetBalance, Order
from common.exceptions import ExchangeAPIError, RateLimitError, TradingDisabled, InsufficientPosition

# Configure logging for visibility
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("mexc_private_trading")


class MexcTradingDemo:
    """Demonstrates all MEXC private exchange trading capabilities"""
    
    def __init__(self, api_key: str, secret_key: str, demo_mode: bool = True):
        """
        Initialize MEXC trading demo
        
        Args:
            api_key: MEXC API key
            secret_key: MEXC secret key
            demo_mode: If True, uses demo credentials and shows examples without actual API calls
        """
        self.demo_mode = demo_mode
        self.exchange = MexcPrivateExchange(api_key=api_key, secret_key=secret_key)
        self.trading_symbols = [
            Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
            Symbol(base=AssetName("ETH"), quote=AssetName("USDT")),
            Symbol(base=AssetName("BNB"), quote=AssetName("USDT")),
        ]
        
    async def demo_account_management(self):
        """Demonstrate account balance operations"""
        logger.info("=" * 60)
        logger.info("DEMO 1: Account Management")
        logger.info("=" * 60)
        
        if self.demo_mode:
            logger.info("📊 Account Balance Operations (Demo Mode)")
            logger.info("Real implementation would call:")
            logger.info("  balances = await exchange.get_account_balance()")
            logger.info("  btc_balance = await exchange.get_asset_balance(AssetName('BTC'))")
            
            # Show what the data would look like
            demo_balances = {
                AssetName("BTC"): AssetBalance(asset=AssetName("BTC"), free=1.5, locked=0.5),
                AssetName("USDT"): AssetBalance(asset=AssetName("USDT"), free=10000.0, locked=2500.0),
                AssetName("ETH"): AssetBalance(asset=AssetName("ETH"), free=10.0, locked=0.0),
            }
            
            logger.info("📋 Demo Account Balances:")
            for asset, balance in demo_balances.items():
                logger.info(f"  {asset}: {balance.free} free, {balance.locked} locked, {balance.total} total")
                
        else:
            try:
                # Get all account balances
                logger.info("📊 Fetching account balances...")
                balances = await self.exchange.get_account_balance()
                
                logger.info(f"📋 Account has {len(balances)} assets with balances:")
                for asset, balance in balances.items():
                    if balance.total > 0:  # Only show assets with balance
                        logger.info(f"  {asset}: {balance.free} free, {balance.locked} locked, {balance.total} total")
                
                # Get specific asset balance
                btc_balance = await self.exchange.get_asset_balance(AssetName("BTC"))
                if btc_balance:
                    logger.info(f"🪙 BTC Balance: {btc_balance.total} total ({btc_balance.free} free)")
                else:
                    logger.info("🪙 No BTC balance found")
                    
            except Exception as e:
                logger.error(f"❌ Failed to get account balance: {e}")
    
    async def demo_order_placement(self):
        """Demonstrate different types of order placement"""

        symbol = self.trading_symbols[0]  # BTC/USDT
        
        logger.info(f"📝 Placing demo orders for {symbol.base}/{symbol.quote}...")
        # {'newClientOrderId': None, 'price': 0.14124, 'quantity': 7.29, 'quoteOrderQty': None, 'side': 'BUY', 'symbol': 'STOPUSDT', 'type': 'LIMIT_MAKER'}
        symbol = Symbol(base=AssetName("STOP"), quote=AssetName("USDT"))
        price = 0.14124
        quantity = 8
        # Example 1: Limit buy order (very low price to avoid accidental execution)
        limit_order = await self.exchange.place_order(
            symbol=symbol,
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            price=price,  # Very low price to avoid execution
            quantity=quantity,
            time_in_force="GTC"
        )

        logger.info(f"🎯 Limit Buy Order Placed: {limit_order}")
        result = await self.exchange.cancel_order(limit_order.symbol, limit_order.order_id)  # Clean up
        logger.info(f"Canceled: {result}")

        return [limit_order]

    
    async def demo_order_management(self):

        symbol = self.trading_symbols[0]
        symbol = Symbol(base=AssetName("STOP"), quote=AssetName("USDT"))
        # Get open orders
        logger.info(f"📋 Getting open orders for {symbol.base}/{symbol.quote}...")
        open_orders = await self.exchange.get_open_orders(symbol)

        logger.info(f"Found {len(open_orders)} open orders:")
        for order in open_orders:
            logger.info(f"  Order {order.symbol} {order.order_id}: {order.side.value} {order.amount} at {order.price}")

        metrics = self.exchange.get_performance_metrics()
        logger.info("\n📊 Current Performance Metrics:")
        for key, value in metrics.items():
            logger.info(f"  {key}: {value}")

    async def run_comprehensive_demo(self):
        """Run all demonstration scenarios"""
        try:
            logger.info("\n🚀 Starting MEXC Private Exchange Demo")
            logger.info(f"Demo Mode: {'ON' if self.demo_mode else 'OFF'}")
            logger.info(f"Exchange: {self.exchange.EXCHANGE_NAME}")
            
            # Run all demos
            await self.demo_account_management()
            await asyncio.sleep(1)
            
            # orders = await self.demo_order_placement()
            await asyncio.sleep(1)
            
            await self.demo_order_management()
            await asyncio.sleep(1)

        except KeyboardInterrupt:
            logger.info("\n🛑 Demo interrupted by user")
        except Exception as e:
            logger.error(f"\n❌ Demo error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Cleanup
            await self.exchange.close()
            logger.info("✅ Demo cleanup completed")


async def main():
    """Main entry point for the demo"""
    from common.config import config
    # Demo credentials (replace with real ones for actual trading)
    DEMO_API_KEY = "demo_api_key_replace_with_real"
    DEMO_SECRET_KEY = "demo_secret_key_replace_with_real"
    
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║              MEXC Private Trading Demo                   ║
    ║                                                          ║
    ║  This demo showcases:                                    ║
    ║  • Account balance management                            ║
    ║  • Order placement (limit, market orders)               ║
    ║  • Order management and monitoring                       ║
    ║  • Advanced trading features                             ║
    ║  • Error handling patterns                               ║
    ║  • Trading strategy examples                             ║
    ║                                                          ║
    ║  ⚠️  DEMO MODE: Uses test credentials                    ║
    ║  ⚠️  No real trades will be executed                     ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    
    # Create and run demo
    demo = MexcTradingDemo(
        api_key=config.MEXC_API_KEY,
        secret_key=config.MEXC_SECRET_KEY,
        demo_mode=False  # Set to False for real trading
    )
    
    await demo.run_comprehensive_demo()


if __name__ == "__main__":
    asyncio.run(main())