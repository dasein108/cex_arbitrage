#!/usr/bin/env python3
"""
Simple MEXC Private Trading Example

A minimal example showing basic MEXC private exchange usage for trading operations.
Perfect for getting started with the MEXC private exchange implementation.

⚠️ IMPORTANT: Replace with real API credentials for actual trading.
⚠️ WARNING: Always test on MEXC testnet before using in production.
"""

import asyncio
import logging
from structs.exchange import Symbol, AssetName, Side, OrderType
from exchanges.mexc.mexc_private import MexcPrivateExchange

# Configure simple logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def simple_trading_example():
    """Simple trading example showing basic operations"""
    
    # REPLACE THESE WITH YOUR REAL MEXC API CREDENTIALS
    API_KEY = "your_mexc_api_key_here"
    SECRET_KEY = "your_mexc_secret_key_here"
    
    # Create private exchange instance
    exchange = MexcPrivateExchange(
        api_key=API_KEY,
        secret_key=SECRET_KEY
    )
    
    try:
        logger.info("🚀 Starting simple MEXC trading example...")
        
        # Define trading symbol
        btc_usdt = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
        
        # 1. Check account balance
        logger.info("📊 Getting account balance...")
        # balances = await exchange.get_account_balance()
        # btc_balance = await exchange.get_asset_balance(AssetName("BTC"))
        logger.info("   (Comment out the lines above to use with real API keys)")
        
        # 2. Place a limit buy order
        logger.info("📝 Placing limit buy order...")
        # order = await exchange.place_order(
        #     symbol=btc_usdt,
        #     side=Side.BUY,
        #     order_type=OrderType.LIMIT,
        #     price=30000.0,  # Low price to avoid accidental execution
        #     quantity=0.001
        # )
        logger.info("   (Comment out the lines above to use with real API keys)")
        
        # 3. Check order status
        logger.info("🔍 Checking order status...")
        # updated_order = await exchange.get_order(btc_usdt, order.order_id)
        logger.info("   (Comment out the lines above to use with real API keys)")
        
        # 4. Cancel the order
        logger.info("❌ Canceling order...")
        # canceled_order = await exchange.cancel_order(btc_usdt, order.order_id)
        logger.info("   (Comment out the lines above to use with real API keys)")
        
        logger.info("✅ Example completed successfully!")
        logger.info("💡 To use with real trading:")
        logger.info("   1. Add your real MEXC API credentials")
        logger.info("   2. Uncomment the actual API calls")
        logger.info("   3. Test carefully with small amounts first")
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
    
    finally:
        # Always close the connection
        await exchange.close()
        logger.info("🔒 Connection closed")


async def balance_check_example():
    """Example focused on checking account balances"""
    
    API_KEY = "your_mexc_api_key_here"
    SECRET_KEY = "your_mexc_secret_key_here"
    
    async with MexcPrivateExchange(API_KEY, SECRET_KEY) as exchange:
        logger.info("📊 Balance Check Example")
        
        try:
            # Get all balances
            # balances = await exchange.get_account_balance()
            # 
            # logger.info("Account Balances:")
            # for asset, balance in balances.items():
            #     if balance.total > 0:
            #         logger.info(f"  {asset}: {balance.total} ({balance.free} free, {balance.locked} locked)")
            
            logger.info("   (Uncomment the code above to use with real API keys)")
            
        except Exception as e:
            logger.error(f"Failed to get balances: {e}")


async def order_management_example():
    """Example focused on order management"""
    
    API_KEY = "your_mexc_api_key_here"  
    SECRET_KEY = "your_mexc_secret_key_here"
    
    exchange = MexcPrivateExchange(API_KEY, SECRET_KEY)
    
    try:
        symbol = Symbol(base=AssetName("ETH"), quote=AssetName("USDT"))
        
        logger.info("📋 Order Management Example")
        
        # Get open orders
        # open_orders = await exchange.get_open_orders(symbol)
        # logger.info(f"Open orders for {symbol.base}/{symbol.quote}: {len(open_orders)}")
        
        # Cancel all orders for the symbol
        # canceled_orders = await exchange.cancel_all_orders(symbol)
        # logger.info(f"Canceled {len(canceled_orders)} orders")
        
        logger.info("   (Uncomment the code above to use with real API keys)")
        
    except Exception as e:
        logger.error(f"Order management failed: {e}")
    
    finally:
        await exchange.close()


if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║              Simple MEXC Trading Examples                ║
    ║                                                          ║
    ║  These examples show basic usage patterns:               ║
    ║  • Account balance checking                              ║
    ║  • Order placement and management                        ║
    ║  • Proper resource cleanup                               ║
    ║                                                          ║
    ║  ⚠️  Add your real API credentials to use               ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    
    # Run different examples
    asyncio.run(simple_trading_example())
    asyncio.run(balance_check_example())
    asyncio.run(order_management_example())