#!/usr/bin/env python3
"""
MEXC Private Trading Example - Production Ready

Simple, production-ready example showing MEXC private API functionality.
Demonstrates real trading operations with proper error handling and authentication.

Features:
- Account balance queries
- Order placement and management
- Real API calls with proper authentication
- Comprehensive error handling
- Performance monitoring

⚠️ WARNING: This uses REAL API calls and can execute actual trades.
⚠️ Ensure you test on MEXC testnet before production use.
"""

import asyncio
import logging
from typing import Dict, List, Optional

from exchanges.mexc.mexc_private import MexcPrivateExchange
from structs.exchange import Symbol, AssetName, Side, OrderType, OrderStatus, AssetBalance
from common.exceptions import ExchangeAPIError, RateLimitError, TradingDisabled, InsufficientPosition
from common.config import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("mexc_trading")


async def test_account_access(exchange: MexcPrivateExchange):
    """Test account access and balance retrieval."""
    logger.info("Testing account access...")
    
    try:
        # Get all account balances
        balances = await exchange.get_account_balance()
        
        logger.info(f"Successfully retrieved account data")
        logger.info(f"Account has {len(balances)} assets with balances")
        
        # Show assets with non-zero balances
        for asset, balance in balances.items():
            if balance.total > 0:
                logger.info(f"  {asset}: {balance.free} free, {balance.locked} locked, {balance.total} total")
        
        # Test specific asset query
        usdt_balance = await exchange.get_asset_balance(AssetName("USDT"))
        if usdt_balance:
            logger.info(f"USDT Balance: {usdt_balance.total} total ({usdt_balance.free} free)")
        else:
            logger.info("No USDT balance found")
            
        return True
        
    except Exception as e:
        logger.error(f"Account access failed: {e}")
        return False


async def test_order_operations(exchange: MexcPrivateExchange):
    """Test order placement and management."""
    logger.info("Testing order operations...")
    
    symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
    
    try:
        # Place a very low limit buy order (unlikely to execute)
        logger.info(f"Placing test limit order for {symbol.base}/{symbol.quote}...")
        
        order = await exchange.place_order(
            symbol=symbol,
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            price=1.0,  # Very low price to avoid execution
            quantity=0.001,
            time_in_force="GTC"
        )
        
        logger.info("Order placed successfully:")
        logger.info(f"  Order ID: {order.order_id}")
        logger.info(f"  Status: {order.status.name}")
        logger.info(f"  Price: {order.price}")
        logger.info(f"  Quantity: {order.amount}")
        
        # Query order status
        logger.info("Querying order status...")
        updated_order = await exchange.get_order(symbol, order.order_id)
        logger.info(f"Order status: {updated_order.status.name}")
        
        # Get open orders
        logger.info("Getting open orders...")
        open_orders = await exchange.get_open_orders(symbol)
        logger.info(f"Found {len(open_orders)} open orders")
        
        # Cancel the test order
        logger.info("Canceling test order...")
        canceled_order = await exchange.cancel_order(symbol, order.order_id)
        logger.info("Order canceled successfully")
        
        return True
        
    except Exception as e:
        logger.error(f"Order operations failed: {e}")
        return False


async def test_error_handling(exchange: MexcPrivateExchange):
    """Test error handling scenarios."""
    logger.info("Testing error handling...")
    
    # Test with invalid symbol
    invalid_symbol = Symbol(base=AssetName("INVALID"), quote=AssetName("TEST"))
    
    try:
        await exchange.get_open_orders(invalid_symbol)
        logger.warning("Expected error for invalid symbol, but request succeeded")
    except ExchangeAPIError as e:
        logger.info(f"Correctly caught API error for invalid symbol: {e.message}")
    except Exception as e:
        logger.warning(f"Unexpected error type for invalid symbol: {e}")
    
    # Test insufficient balance scenario (place large order)
    symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
    
    try:
        await exchange.place_order(
            symbol=symbol,
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quote_quantity=999999999.0  # Very large amount
        )
        logger.warning("Expected insufficient balance error, but order succeeded")
    except InsufficientPosition as e:
        logger.info(f"Correctly caught insufficient balance error: {e.message}")
    except ExchangeAPIError as e:
        logger.info(f"Caught API error (might be insufficient balance): {e.message}")
    except Exception as e:
        logger.warning(f"Unexpected error type for large order: {e}")


async def monitor_performance(exchange: MexcPrivateExchange):
    """Monitor exchange performance metrics."""
    logger.info("Performance metrics:")
    
    metrics = exchange.get_performance_metrics()
    for key, value in metrics.items():
        logger.info(f"  {key}: {value}")


async def main():
    """Main trading example."""
    logger.info("🚀 Starting MEXC Private Trading Example")
    
    # Validate configuration
    if not config.MEXC_API_KEY or not config.MEXC_SECRET_KEY:
        logger.error("❌ MEXC API credentials not configured")
        logger.error("Please set MEXC_API_KEY and MEXC_SECRET_KEY environment variables")
        return
    
    logger.info("✅ API credentials loaded")
    logger.info(f"Exchange: MEXC")
    logger.info(f"Environment: {config.ENVIRONMENT.value}")
    
    # Create exchange instance
    async with MexcPrivateExchange() as exchange:
        logger.info("✅ Exchange client initialized")
        
        # Run tests
        tests = [
            ("Account Access", test_account_access),
            ("Order Operations", test_order_operations),
            ("Error Handling", test_error_handling),
        ]
        
        results = {}
        
        for test_name, test_func in tests:
            logger.info(f"\n{'='*50}")
            logger.info(f"Running: {test_name}")
            logger.info(f"{'='*50}")
            
            try:
                success = await test_func(exchange)
                results[test_name] = success
                status = "✅ PASSED" if success else "❌ FAILED"
                logger.info(f"{test_name}: {status}")
                
            except KeyboardInterrupt:
                logger.info("🛑 Test interrupted by user")
                break
            except Exception as e:
                logger.error(f"❌ {test_name} failed with error: {e}")
                results[test_name] = False
            
            # Small delay between tests
            await asyncio.sleep(1)
        
        # Performance monitoring
        logger.info(f"\n{'='*50}")
        logger.info("Performance Monitoring")
        logger.info(f"{'='*50}")
        await monitor_performance(exchange)
        
        # Summary
        logger.info(f"\n{'='*50}")
        logger.info("Test Summary")
        logger.info(f"{'='*50}")
        
        for test_name, success in results.items():
            status = "✅ PASSED" if success else "❌ FAILED"
            logger.info(f"{test_name}: {status}")
        
        passed = sum(1 for success in results.values() if success is True)
        total = len(results)
        logger.info(f"\nOverall: {passed}/{total} tests passed")
        
        if passed == total:
            logger.info("🎉 All tests passed! MEXC API integration working correctly.")
        else:
            logger.warning("⚠️ Some tests failed. Check logs for details.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Example interrupted by user")
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()