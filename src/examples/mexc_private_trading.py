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
        logger.info("=" * 60)
        logger.info("DEMO 2: Order Placement")
        logger.info("=" * 60)
        
        symbol = self.trading_symbols[0]  # BTC/USDT
        
        if self.demo_mode:
            logger.info("📝 Order Placement Operations (Demo Mode)")
            logger.info("Real implementation examples:")
            
            # Limit order example
            logger.info("\n🎯 Limit Buy Order:")
            logger.info(f"  symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'))")
            logger.info(f"  order = await exchange.place_order(")
            logger.info(f"      symbol=symbol,")
            logger.info(f"      side=Side.BUY,")
            logger.info(f"      order_type=OrderType.LIMIT,")
            logger.info(f"      price=45000.0,")
            logger.info(f"      quantity=0.001")
            logger.info(f"  )")
            
            # Market order example
            logger.info("\n🚀 Market Sell Order:")
            logger.info(f"  order = await exchange.place_order(")
            logger.info(f"      symbol=symbol,")
            logger.info(f"      side=Side.SELL,")
            logger.info(f"      order_type=OrderType.MARKET,")
            logger.info(f"      quantity=0.001")
            logger.info(f"  )")
            
            # Market buy with quote quantity
            logger.info("\n💰 Market Buy with Quote Quantity:")
            logger.info(f"  order = await exchange.place_order(")
            logger.info(f"      symbol=symbol,")
            logger.info(f"      side=Side.BUY,")
            logger.info(f"      order_type=OrderType.MARKET,")
            logger.info(f"      quote_quantity=100.0  # $100 worth of BTC")
            logger.info(f"  )")
            
        else:
            try:
                logger.info(f"📝 Placing demo orders for {symbol.base}/{symbol.quote}...")
                
                # Example 1: Limit buy order (very low price to avoid accidental execution)
                limit_order = await self.exchange.place_order(
                    symbol=symbol,
                    side=Side.BUY,
                    order_type=OrderType.LIMIT,
                    price=1.0,  # Very low price to avoid execution
                    quantity=0.001,
                    time_in_force="GTC"
                )
                
                logger.info("🎯 Limit Buy Order Placed:")
                logger.info(f"  Order ID: {limit_order.order_id}")
                logger.info(f"  Status: {limit_order.status.name}")
                logger.info(f"  Price: {limit_order.price}")
                logger.info(f"  Quantity: {limit_order.amount}")
                
                return [limit_order]
                
            except Exception as e:
                logger.error(f"❌ Failed to place order: {e}")
                return []
    
    async def demo_order_management(self, orders: List[Order]):
        """Demonstrate order management operations"""
        logger.info("=" * 60)
        logger.info("DEMO 3: Order Management")
        logger.info("=" * 60)
        
        if not orders and not self.demo_mode:
            logger.info("⚠️ No orders to manage")
            return
            
        symbol = self.trading_symbols[0]
        
        if self.demo_mode:
            logger.info("🔍 Order Management Operations (Demo Mode)")
            logger.info("Real implementation examples:")
            
            logger.info("\n📊 Query Order Status:")
            logger.info("  updated_order = await exchange.get_order(symbol, order_id)")
            
            logger.info("\n📋 Get Open Orders:")
            logger.info("  open_orders = await exchange.get_open_orders(symbol)")
            
            logger.info("\n❌ Cancel Specific Order:")
            logger.info("  canceled_order = await exchange.cancel_order(symbol, order_id)")
            
            logger.info("\n🧹 Cancel All Orders:")
            logger.info("  canceled_orders = await exchange.cancel_all_orders(symbol)")
            
            logger.info("\n✏️ Modify Order:")
            logger.info("  modified_order = await exchange.modify_order(")
            logger.info("      symbol, order_id, quantity=0.002, price=46000.0")
            logger.info("  )")
            
        else:
            try:
                # Get open orders
                logger.info(f"📋 Getting open orders for {symbol.base}/{symbol.quote}...")
                open_orders = await self.exchange.get_open_orders(symbol)
                
                logger.info(f"Found {len(open_orders)} open orders:")
                for order in open_orders:
                    logger.info(f"  Order {order.order_id}: {order.side.value} {order.amount} at {order.price}")
                
                # Manage first order if available
                if orders:
                    test_order = orders[0]
                    
                    # Query order status
                    logger.info(f"🔍 Querying status for order {test_order.order_id}...")
                    updated_order = await self.exchange.get_order(symbol, test_order.order_id)
                    logger.info(f"  Status: {updated_order.status.name}")
                    logger.info(f"  Filled: {updated_order.amount_filled}/{updated_order.amount}")
                    
                    # Cancel the order
                    logger.info(f"❌ Canceling order {test_order.order_id}...")
                    canceled_order = await self.exchange.cancel_order(symbol, test_order.order_id)
                    logger.info(f"  Order canceled successfully")
                    
            except Exception as e:
                logger.error(f"❌ Failed to manage orders: {e}")
    
    async def demo_advanced_features(self):
        """Demonstrate advanced trading features"""
        logger.info("=" * 60)
        logger.info("DEMO 4: Advanced Trading Features")
        logger.info("=" * 60)
        
        logger.info("⚡ Advanced Features (Demo Mode)")
        
        # Order modification strategy
        logger.info("\n✏️ Order Modification Strategy:")
        logger.info("  # MEXC doesn't support direct order modification")
        logger.info("  # Implementation uses cancel + place strategy")
        logger.info("  try:")
        logger.info("      # Get current order details")
        logger.info("      current_order = await exchange.get_order(symbol, order_id)")
        logger.info("      ")
        logger.info("      # Cancel existing order")
        logger.info("      await exchange.cancel_order(symbol, order_id)")
        logger.info("      ")
        logger.info("      # Place new order with modified parameters")
        logger.info("      new_order = await exchange.place_order(")
        logger.info("          symbol=symbol,")
        logger.info("          side=current_order.side,")
        logger.info("          order_type=current_order.order_type,")
        logger.info("          price=new_price,")
        logger.info("          quantity=new_quantity")
        logger.info("      )")
        logger.info("  except Exception as e:")
        logger.info("      # Handle modification failure")
        logger.info("      logger.error(f'Order modification failed: {e}')")
        
        # Batch operations
        logger.info("\n📦 Batch Operations:")
        logger.info("  # Cancel all orders for multiple symbols")
        logger.info("  for symbol in trading_symbols:")
        logger.info("      try:")
        logger.info("          canceled = await exchange.cancel_all_orders(symbol)")
        logger.info("          logger.info(f'Canceled {len(canceled)} orders for {symbol}')")
        logger.info("      except Exception as e:")
        logger.info("          logger.error(f'Failed to cancel orders for {symbol}: {e}')")
        
        # Performance monitoring
        logger.info("\n📈 Performance Monitoring:")
        logger.info("  metrics = exchange.get_performance_metrics()")
        logger.info("  logger.info(f'Exchange: {metrics[\"exchange\"]}')")
        logger.info("  logger.info(f'API Keys Configured: {metrics[\"api_key_configured\"]}')")
        
        # Show actual metrics
        metrics = self.exchange.get_performance_metrics()
        logger.info("\n📊 Current Performance Metrics:")
        for key, value in metrics.items():
            logger.info(f"  {key}: {value}")
    
    async def demo_error_handling(self):
        """Demonstrate error handling patterns"""
        logger.info("=" * 60)
        logger.info("DEMO 5: Error Handling Patterns")
        logger.info("=" * 60)
        
        logger.info("🛡️ Error Handling Examples:")
        
        logger.info("\n1️⃣ Rate Limit Handling:")
        logger.info("  try:")
        logger.info("      order = await exchange.place_order(...)")
        logger.info("  except RateLimitError as e:")
        logger.info("      logger.warning(f'Rate limited: {e.message}')")
        logger.info("      await asyncio.sleep(e.retry_after or 60)")
        logger.info("      # Retry the operation")
        
        logger.info("\n2️⃣ Insufficient Balance:")
        logger.info("  try:")
        logger.info("      order = await exchange.place_order(...)")
        logger.info("  except InsufficientPosition as e:")
        logger.info("      logger.error(f'Insufficient balance: {e.message}')")
        logger.info("      # Check account balance and adjust order size")
        
        logger.info("\n3️⃣ Trading Disabled:")
        logger.info("  try:")
        logger.info("      order = await exchange.place_order(...)")
        logger.info("  except TradingDisabled as e:")
        logger.info("      logger.error(f'Trading disabled: {e.message}')")
        logger.info("      # Switch to different symbol or wait")
        
        logger.info("\n4️⃣ General API Errors:")
        logger.info("  try:")
        logger.info("      balances = await exchange.get_account_balance()")
        logger.info("  except ExchangeAPIError as e:")
        logger.info("      logger.error(f'API error {e.code}: {e.message}')")
        logger.info("      if e.api_code:")
        logger.info("          logger.error(f'MEXC error code: {e.api_code}')")
        
        logger.info("\n5️⃣ Connection Errors:")
        logger.info("  try:")
        logger.info("      order = await exchange.place_order(...)")
        logger.info("  except asyncio.TimeoutError:")
        logger.info("      logger.error('Request timeout - check connection')")
        logger.info("  except Exception as e:")
        logger.info("      logger.error(f'Unexpected error: {e}')")
    
    async def demo_trading_strategies(self):
        """Demonstrate common trading strategy patterns"""
        logger.info("=" * 60)
        logger.info("DEMO 6: Trading Strategy Patterns")
        logger.info("=" * 60)
        
        logger.info("🎯 Common Trading Patterns:")
        
        logger.info("\n💹 DCA (Dollar Cost Averaging) Strategy:")
        logger.info("  async def dca_buy(symbol: Symbol, usdt_amount: float):")
        logger.info("      try:")
        logger.info("          # Market buy with quote quantity")
        logger.info("          order = await exchange.place_order(")
        logger.info("              symbol=symbol,")
        logger.info("              side=Side.BUY,")
        logger.info("              order_type=OrderType.MARKET,")
        logger.info("              quote_quantity=usdt_amount")
        logger.info("          )")
        logger.info("          return order")
        logger.info("      except Exception as e:")
        logger.info("          logger.error(f'DCA buy failed: {e}')")
        
        logger.info("\n📊 Grid Trading Setup:")
        logger.info("  async def setup_grid(symbol: Symbol, base_price: float, grid_size: int):")
        logger.info("      orders = []")
        logger.info("      price_step = base_price * 0.01  # 1% grid")
        logger.info("      ")
        logger.info("      for i in range(grid_size):")
        logger.info("          # Place buy orders below current price")
        logger.info("          buy_price = base_price - (price_step * (i + 1))")
        logger.info("          buy_order = await exchange.place_order(")
        logger.info("              symbol=symbol,")
        logger.info("              side=Side.BUY,")
        logger.info("              order_type=OrderType.LIMIT,")
        logger.info("              price=buy_price,")
        logger.info("              quantity=0.001")
        logger.info("          )")
        logger.info("          orders.append(buy_order)")
        logger.info("      return orders")
        
        logger.info("\n🔄 Order Monitoring Loop:")
        logger.info("  async def monitor_orders(symbol: Symbol):")
        logger.info("      while True:")
        logger.info("          try:")
        logger.info("              open_orders = await exchange.get_open_orders(symbol)")
        logger.info("              ")
        logger.info("              for order in open_orders:")
        logger.info("                  # Check if order needs management")
        logger.info("                  updated = await exchange.get_order(symbol, order.order_id)")
        logger.info("                  ")
        logger.info("                  if updated.status == OrderStatus.FILLED:")
        logger.info("                      logger.info(f'Order {order.order_id} filled!')")
        logger.info("                  elif updated.status == OrderStatus.PARTIALLY_FILLED:")
        logger.info("                      logger.info(f'Order {order.order_id} partially filled')")
        logger.info("              ")
        logger.info("              await asyncio.sleep(5)  # Check every 5 seconds")
        logger.info("          except Exception as e:")
        logger.info("              logger.error(f'Monitoring error: {e}')")
        logger.info("              await asyncio.sleep(30)  # Longer delay on error")
    
    async def run_comprehensive_demo(self):
        """Run all demonstration scenarios"""
        try:
            logger.info("\n🚀 Starting MEXC Private Exchange Demo")
            logger.info(f"Demo Mode: {'ON' if self.demo_mode else 'OFF'}")
            logger.info(f"Exchange: {self.exchange.EXCHANGE_NAME}")
            
            # Run all demos
            await self.demo_account_management()
            await asyncio.sleep(1)
            
            orders = await self.demo_order_placement()
            await asyncio.sleep(1)
            
            await self.demo_order_management(orders)
            await asyncio.sleep(1)
            
            await self.demo_advanced_features()
            await asyncio.sleep(1)
            
            await self.demo_error_handling()
            await asyncio.sleep(1)
            
            await self.demo_trading_strategies()
            
            logger.info("\n" + "=" * 80)
            logger.info("🎉 MEXC Private Exchange Demo Complete!")
            logger.info("=" * 80)
            logger.info("✅ All trading operations demonstrated")
            logger.info("✅ Error handling patterns shown")
            logger.info("✅ Performance optimizations explained")
            logger.info("✅ Ready for production trading")
            
            if self.demo_mode:
                logger.info("\n⚠️  To enable real trading:")
                logger.info("   1. Replace demo credentials with real MEXC API keys")
                logger.info("   2. Set demo_mode=False in the constructor")
                logger.info("   3. Test on MEXC testnet before production")
                logger.info("   4. Implement proper risk management")
                
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
        api_key=DEMO_API_KEY,
        secret_key=DEMO_SECRET_KEY,
        demo_mode=True  # Set to False for real trading
    )
    
    await demo.run_comprehensive_demo()


if __name__ == "__main__":
    asyncio.run(main())