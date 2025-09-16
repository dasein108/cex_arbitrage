#!/usr/bin/env python3
"""
Gate.io Private REST API Example

Demonstrates usage of Gate.io private REST API for trading operations.
This example shows how to use the GateioPrivateExchange class to:

1. Get account balance information
2. Place and manage orders
3. Query order status and history
4. Handle authentication and error cases

⚠️ REQUIRES API CREDENTIALS: You need valid Gate.io API key and secret.
Set credentials in config.yaml or provide them when initializing the exchange.

Usage:
    python -m src.examples.gateio.private_rest_example
"""

import asyncio
import logging

from exchanges.gateio.rest.gateio_private import GateioPrivateExchangeSpot
from structs.exchange import Symbol, AssetName, Side, OrderType, TimeInForce
from config import config


async def demonstrate_private_api():
    """Demonstrate Gate.io private API functionality."""
    
    # Configure logging to see API calls
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger = logging.getLogger(__name__)
    
    # Check for API credentials
    if not config.has_gateio_credentials():
        logger.error("❌ Gate.io API credentials not configured!")
        logger.info("Please set GATEIO_API_KEY and GATEIO_SECRET_KEY in config.yaml")
        logger.info("Or provide them when initializing GateioPrivateExchange")
        return False
    
    logger.info("✅ Gate.io API credentials found")
    
    # Initialize Gate.io private API client
    logger.info("Initializing Gate.io private REST client...")
    gateio_credentials = config.get_exchange_credentials('gateio')
    client = GateioPrivateExchangeSpot(
        api_key=gateio_credentials['api_key'],
        secret_key=gateio_credentials['secret_key']
    )
    
    try:
        logger.info("\n== Fees")
        fees = await client.get_trading_fees()
        for symbol, fee in list(fees.items())[:5]:
            logger.info(f"  {symbol}: Maker: {fee.maker:.4f}%, Taker: {fee.taker:.4f}%")

        # Test 1: Get account balances
        logger.info("\n=== Test 1: Account Balances ===")
        balances = await client.get_account_balance()
        logger.info(f"Retrieved balances for {len(balances)} assets")
        
        # Show non-zero balances
        significant_balances = [b for b in balances if b.total > 0.001]
        if significant_balances:
            logger.info("Significant balances:")
            for balance in significant_balances[:10]:  # Show top 10
                logger.info(
                    f"  {balance.asset}: Available: {balance.available:.6f}, "
                    f"Locked: {balance.locked:.6f}, Total: {balance.total:.6f}"
                )
        else:
            logger.info("No significant balances found")
        
        # Test 2: Get specific asset balance
        logger.info("\n=== Test 2: Specific Asset Balance ===")
        usdt_balance = await client.get_asset_balance(AssetName("USDT"))
        if usdt_balance:
            logger.info(f"USDT Balance: {usdt_balance.total:.2f} USDT")
        else:
            logger.info("No USDT balance found")
        
        # Test 3: Get open orders
        logger.info("\n=== Test 3: Open Orders ===")
        open_orders = await client.get_open_orders()
        logger.info(f"Found {len(open_orders)} open orders")
        
        if open_orders:
            for order in open_orders[:5]:  # Show first 5
                logger.info(
                    f"  Order {order.order_id}: {order.side.name} {order.amount} "
                    f"{order.symbol.base} @ {order.price} {order.symbol.quote} "
                    f"(Status: {order.status.name})"
                )
        
        # Test 4: Place test order (if we have sufficient balance)
        logger.info("\n=== Test 4: Test Order Placement ===")
        
        # Define test symbol and parameters
        test_symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
        
        # Check if we have sufficient USDT balance for a small test order
        if usdt_balance and usdt_balance.available >= 20:  # At least $20 USDT
            logger.info("Placing small test limit buy order...")
            
            try:
                # Place a limit buy order well below market price (unlikely to fill)
                test_order = await client.place_order(
                    symbol=test_symbol,
                    side=Side.BUY,
                    order_type=OrderType.LIMIT,
                    amount=0.0001,  # Very small amount
                    price=30000,    # Well below market price
                    time_in_force=TimeInForce.GTC
                )
                
                logger.info(f"✅ Test order placed: {test_order.order_id}")
                logger.info(
                    f"Order details: {test_order.side.name} {test_order.amount} "
                    f"{test_order.symbol.base} @ {test_order.price} {test_order.symbol.quote}"
                )
                
                # Test 5: Query order status
                logger.info("\n=== Test 5: Query Order Status ===")
                order_status = await client.get_order(test_symbol, test_order.order_id)
                logger.info(f"Order status: {order_status.status.name}")
                logger.info(f"Filled amount: {order_status.amount_filled}/{order_status.amount}")
                
                # Test 6: Cancel the test order
                logger.info("\n=== Test 6: Cancel Test Order ===")
                cancelled_order = await client.cancel_order(test_symbol, test_order.order_id)
                logger.info(f"✅ Order cancelled: {cancelled_order.order_id}")
                logger.info(f"Final status: {cancelled_order.status.name}")
                
            except Exception as e:
                logger.warning(f"Test order operations failed: {e}")
                logger.info("This might be normal for testing accounts or insufficient permissions")
        
        else:
            logger.info("Insufficient USDT balance for test order (need at least $20)")
            logger.info("Skipping order placement tests")
        
        # Test 7: Order modification example (for educational purposes)
        logger.info("\n=== Test 7: Order Modification (Educational) ===")
        logger.info("Note: Gate.io doesn't support direct order modification")
        logger.info("modify_order() cancels the old order and places a new one")
        logger.info("This is demonstrated conceptually without actual execution")
        
        # Test 8: Get order history for a symbol
        logger.info("\n=== Test 8: Order History ===")
        try:
            # Get recent orders for BTC/USDT
            btc_orders = await client.get_open_orders(test_symbol)
            logger.info(f"Open orders for {test_symbol.base}/{test_symbol.quote}: {len(btc_orders)}")
            
            if btc_orders:
                for order in btc_orders[:3]:
                    logger.info(
                        f"  {order.order_id}: {order.side.name} {order.amount} @ {order.price} "
                        f"(Status: {order.status.name})"
                    )
        except Exception as e:
            logger.info(f"Order history query failed: {e}")
        
        logger.info("\n=== All Private API Tests Completed ===")
        return True
        
    except Exception as e:
        logger.error(f"Error during private API demonstration: {e}")
        logger.error("This could be due to:")
        logger.error("  - Invalid API credentials")
        logger.error("  - Insufficient API permissions")
        logger.error("  - Network connectivity issues")
        logger.error("  - Rate limiting")
        raise
    
    finally:
        # Clean up resources
        await client.close()
        logger.info("Closed Gate.io private REST client")


async def demonstrate_batch_operations():
    """Demonstrate batch operations and advanced features."""
    
    logger = logging.getLogger(__name__)
    
    if not config.has_gateio_credentials():
        logger.info("Skipping batch operations demo - no credentials")
        return
    
    logger.info("\n=== Batch Operations Demo ===")
    
    gateio_credentials = config.get_exchange_credentials('gateio')
    client = GateioPrivateExchangeSpot(
        api_key=gateio_credentials['api_key'],
        secret_key=gateio_credentials['secret_key']
    )
    
    try:
        # Get balances for multiple assets efficiently
        assets_to_check = [AssetName("BTC"), AssetName("ETH"), AssetName("USDT"), AssetName("BNB")]
        
        logger.info("Checking balances for multiple assets...")
        
        # Use asyncio.gather for concurrent requests (if needed)
        balance_tasks = [client.get_asset_balance(asset) for asset in assets_to_check]
        balances_results = await asyncio.gather(*balance_tasks, return_exceptions=True)
        
        for asset, result in zip(assets_to_check, balances_results):
            if isinstance(result, Exception):
                logger.warning(f"{asset}: Error - {result}")
            elif result and result.total > 0:
                logger.info(f"{asset}: {result.total:.6f}")
            else:
                logger.info(f"{asset}: 0.000000")
        
        # Cancel all open orders for a symbol (demonstration)
        logger.info("\nDemonstrating cancel all orders functionality...")
        test_symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
        
        try:
            cancelled_orders = await client.cancel_all_orders(test_symbol)
            logger.info(f"Cancelled {len(cancelled_orders)} orders for {test_symbol.base}/{test_symbol.quote}")
        except Exception as e:
            logger.info(f"Cancel all orders result: {e}")
        
    finally:
        await client.close()


def main():
    """Main entry point."""
    print("Gate.io Private REST API Example")
    print("=" * 50)
    print("This example demonstrates Gate.io private API operations for trading.")
    print("⚠️  REQUIRES API CREDENTIALS - Set in config.yaml")
    print()
    
    try:
        # Run main demonstration
        success = asyncio.run(demonstrate_private_api())
        
        if success:
            # Run advanced features demo
            asyncio.run(demonstrate_batch_operations())
            print("\n✅ All private API examples completed successfully!")
        else:
            print("\n⚠️ Private API examples skipped due to missing credentials")
        
        print("\nSecurity Reminders:")
        print("  - Never hardcode API credentials in source code")
        print("  - Use environment variables or secure config files")
        print("  - Restrict API key permissions to minimum required")
        print("  - Monitor API key usage and rotate regularly")
        
    except KeyboardInterrupt:
        print("\n⚠️ Examples interrupted by user")
    
    except Exception as e:
        print(f"\n❌ Examples failed with error: {e}")
        print("\nTroubleshooting:")
        print("  - Verify API credentials are correct and active")
        print("  - Check API key permissions include spot trading")
        print("  - Ensure sufficient account balance for test operations")
        print("  - Verify network connectivity to Gate.io API")


if __name__ == "__main__":
    from core.register import install_exchange_dependencies
    install_exchange_dependencies()
    main()