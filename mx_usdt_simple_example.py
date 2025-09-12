#!/usr/bin/env python3
"""
MX/USDT Simple Trading Example - $2 Buy Limit Order

This example uses REST API only to get current price and place orders.
Demonstrates placing a real buy limit order for $2 worth of MX tokens
and then immediately canceling it.

⚠️  WARNING: This places REAL orders on MEXC exchange!
⚠️  Make sure you have the correct API credentials and understand the risks.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Setup imports
sys.path.append(str(Path(__file__).parent / "src"))

from exchanges.interface.structs import Symbol, AssetName, Side
from exchanges.mexc.rest.mexc_public import MexcPublicExchange
from exchanges.mexc.rest.mexc_private import MexcPrivateExchange
from common.exceptions import ExchangeAPIError

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def place_and_cancel_mx_order():
    """Place a $2 MX/USDT buy limit order and then cancel it using REST API only."""
    
    # ⚠️ REPLACE WITH YOUR ACTUAL MEXC API CREDENTIALS
    API_KEY = "your_api_key_here"
    SECRET_KEY = "your_secret_key_here"
    
    # Validate credentials are set
    if API_KEY == "your_api_key_here" or SECRET_KEY == "your_secret_key_here":
        logger.error("❌ Please set your actual MEXC API credentials in the script!")
        logger.error("   Replace 'your_api_key_here' and 'your_secret_key_here' with real values")
        return
    
    # Create MX/USDT symbol
    mx_usdt = Symbol(base=AssetName("MX"), quote=AssetName("USDT"))
    
    try:
        # Initialize REST clients
        public_client = MexcPublicExchange()
        private_client = MexcPrivateExchange(API_KEY, SECRET_KEY)
        
        logger.info("🚀 Connected to MEXC exchange (REST API)")
        
        # Get current market price via REST API
        logger.info("📊 Getting current MX/USDT price...")
        orderbook = await public_client.get_orderbook(mx_usdt, limit=5)
        
        if not orderbook or not orderbook.asks:
            logger.error("❌ No order book data available for MX/USDT")
            return
        
        current_price = orderbook.asks[0].price  # Best ask price
        logger.info(f"📊 Current MX price: ${current_price:.6f}")
        
        # Calculate order parameters for $2 purchase
        target_spend = 2.0  # $2 USDT
        
        # Place buy limit order 5% below current price to avoid immediate fill
        limit_price = current_price * 0.95  # 5% below market
        amount = target_spend / limit_price  # Calculate MX amount
        
        logger.info(f"📋 Order details:")
        logger.info(f"   • Amount: {amount:.2f} MX")
        logger.info(f"   • Price: ${limit_price:.6f}")
        logger.info(f"   • Total: ~${target_spend:.2f}")
        
        # Check account balance first
        logger.info("💰 Checking USDT balance...")
        usdt_balance = await private_client.get_asset_balance(AssetName("USDT"))
        if usdt_balance and usdt_balance.free >= target_spend:
            logger.info(f"✅ Sufficient USDT balance: ${usdt_balance.free:.2f} available")
        else:
            logger.warning(f"⚠️ Insufficient USDT balance: ${usdt_balance.free if usdt_balance else 0:.2f} available")
            logger.warning("   Order may fail due to insufficient funds")
        
        # Place the buy limit order
        logger.info("🔄 Placing buy limit order...")
        order = await private_client.place_order(
            symbol=mx_usdt,
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            amount=amount,
            price=limit_price
        )
        
        logger.info(f"✅ Order placed successfully!")
        logger.info(f"   • Order ID: {order.order_id}")
        logger.info(f"   • Status: {order.status.name}")
        logger.info(f"   • Amount: {order.amount} MX")
        logger.info(f"   • Price: ${order.price}")
        
        # Wait a moment (optional - to see the order in your MEXC interface)
        logger.info("⏳ Waiting 5 seconds before cancellation...")
        await asyncio.sleep(5)
        
        # Cancel the order
        logger.info("🔄 Canceling order...")
        cancelled_order = await private_client.cancel_order(mx_usdt, order.order_id)
        
        logger.info(f"✅ Order cancelled successfully!")
        logger.info(f"   • Order ID: {cancelled_order.order_id}")
        logger.info(f"   • Status: {cancelled_order.status.name}")
        
        # Verify no open orders remain
        open_orders = await private_client.get_open_orders(mx_usdt)
        logger.info(f"📊 Remaining open orders for MX/USDT: {len(open_orders)}")
        
        logger.info("🎉 Example completed successfully!")
        
        # Clean up
        await private_client.close()
        
    except ExchangeAPIError as e:
        logger.error(f"❌ MEXC API Error: {e}")
        logger.error("   Check your API credentials and account permissions")
        
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")


async def check_mx_price_only():
    """Just check MX/USDT price without placing orders (no credentials needed)."""
    logger.info("💡 Price check mode (no credentials required)")
    
    mx_usdt = Symbol(base=AssetName("MX"), quote=AssetName("USDT"))
    
    try:
        public_client = MexcPublicExchange()
        logger.info("📡 Getting MX/USDT price data via REST API...")
        
        # Get order book data
        orderbook = await public_client.get_orderbook(mx_usdt, limit=5)
        
        if orderbook and orderbook.asks and orderbook.bids:
            best_ask = orderbook.asks[0].price
            best_bid = orderbook.bids[0].price
            spread = ((best_ask - best_bid) / best_ask) * 100
            
            logger.info(f"📊 MX/USDT Market Data:")
            logger.info(f"   • Best Bid: ${best_bid:.6f}")
            logger.info(f"   • Best Ask: ${best_ask:.6f}")
            logger.info(f"   • Spread: {spread:.3f}%")
            
            # Calculate what $2 would buy
            mx_amount = 2.0 / best_ask
            logger.info(f"💰 $2.00 would buy ~{mx_amount:.1f} MX tokens")
            
            # Get recent trades
            try:
                recent_trades = await public_client.get_recent_trades(mx_usdt, limit=5)
                if recent_trades:
                    latest_trade = recent_trades[0]
                    logger.info(f"🔄 Latest trade: ${latest_trade.price:.6f} ({latest_trade.side.name})")
            except Exception:
                logger.info("   (Could not get recent trades)")
                
        else:
            logger.warning("⚠️ No order book data received")
            
    except Exception as e:
        logger.error(f"❌ Error getting price data: {e}")


def main():
    """Main entry point - choose mode."""
    print("MX/USDT Simple Trading Example (REST API Only)")
    print("==============================================")
    print()
    print("Choose mode:")
    print("1. Price check only (no API credentials needed)")
    print("2. Place and cancel real $2 order (API credentials required)")
    print()
    
    choice = input("Enter choice (1 or 2): ").strip()
    
    if choice == "1":
        print("\\n🔍 Running price check mode...")
        asyncio.run(check_mx_price_only())
    elif choice == "2":
        print("\\n⚠️  WARNING: This will place a REAL order on MEXC!")
        print("⚠️  Make sure you:")
        print("   • Have set your API credentials in the script")
        print("   • Have at least $2 USDT in your account")
        print("   • Understand this is a real trading operation")
        print()
        confirm = input("Continue with REAL order placement? (yes/no): ").strip().lower()
        if confirm == "yes":
            asyncio.run(place_and_cancel_mx_order())
        else:
            print("❌ Cancelled by user")
    else:
        print("❌ Invalid choice")


if __name__ == "__main__":
    # Import OrderType here to avoid issues in the main function
    from exchanges.interface.structs import OrderType
    main()