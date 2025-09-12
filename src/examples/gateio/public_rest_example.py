#!/usr/bin/env python3
"""
Gate.io Public REST API Example

Demonstrates usage of Gate.io public REST API for market data retrieval.
This example shows how to use the GateioPublicExchange class to:

1. Get exchange trading information
2. Retrieve orderbook data
3. Fetch recent trades
4. Test connectivity and server time

No API credentials required for public endpoints.

Usage:
    python -m src.examples.gateio.public_rest_example
"""

import asyncio
import logging
from typing import List

from exchanges.gateio.rest.gateio_public import GateioPublicExchange
from exchanges.interface.structs import Symbol, AssetName


async def demonstrate_public_api():
    """Demonstrate Gate.io public API functionality."""
    
    # Configure logging to see API calls
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger = logging.getLogger(__name__)
    
    # Initialize Gate.io public API client
    logger.info("Initializing Gate.io public REST client...")
    client = GateioPublicExchange()
    
    try:
        # Test 1: Ping connectivity
        logger.info("\n=== Test 1: Testing Connectivity ===")
        is_connected = await client.ping()
        logger.info(f"Gate.io connectivity: {'✓ Connected' if is_connected else '✗ Failed'}")
        
        # Test 2: Get server time
        logger.info("\n=== Test 2: Server Time ===")
        server_time = await client.get_server_time()
        logger.info(f"Gate.io server time: {server_time} ms")
        
        # Test 3: Get exchange info
        logger.info("\n=== Test 3: Exchange Info ===")
        exchange_info = await client.get_exchange_info()
        logger.info(f"Retrieved info for {len(exchange_info)} trading pairs")
        
        # Show some popular pairs
        popular_pairs = []
        for symbol, info in exchange_info.items():
            pair_name = f"{symbol.base}/{symbol.quote}"
            if pair_name in ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'ADA/USDT', 'SOL/USDT']:
                popular_pairs.append((symbol, info))
        
        logger.info("Popular trading pairs:")
        for symbol, info in popular_pairs[:5]:
            logger.info(
                f"  {symbol.base}/{symbol.quote}: "
                f"Min base: {info.min_base_amount}, "
                f"Min quote: {info.min_quote_amount}, "
                f"Fee: {info.taker_commission:.4f}%"
            )
        
        # Test 4: Get orderbook data
        logger.info("\n=== Test 4: Orderbook Data ===")
        
        # Use BTC/USDT as example
        btc_usdt = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
        
        if btc_usdt in exchange_info:
            orderbook = await client.get_orderbook(btc_usdt, limit=10)
            logger.info(f"BTC/USDT Orderbook (Top 5 levels):")
            logger.info("  Bids (Buy orders):")
            for i, bid in enumerate(orderbook.bids[:5]):
                logger.info(f"    {i+1}. ${bid.price:,.2f} - {bid.size:.6f} BTC")
            
            logger.info("  Asks (Sell orders):")
            for i, ask in enumerate(orderbook.asks[:5]):
                logger.info(f"    {i+1}. ${ask.price:,.2f} - {ask.size:.6f} BTC")
            
            # Calculate spread
            if orderbook.bids and orderbook.asks:
                spread = orderbook.asks[0].price - orderbook.bids[0].price
                spread_pct = (spread / orderbook.bids[0].price) * 100
                logger.info(f"  Spread: ${spread:.2f} ({spread_pct:.4f}%)")
        else:
            logger.warning("BTC/USDT not found in exchange info")
        
        # Test 5: Get recent trades
        logger.info("\n=== Test 5: Recent Trades ===")
        
        if btc_usdt in exchange_info:
            trades = await client.get_recent_trades(btc_usdt, limit=5)
            logger.info(f"Recent BTC/USDT trades:")
            for i, trade in enumerate(trades[:5]):
                side_emoji = "🟢" if trade.side.name == "BUY" else "🔴"
                logger.info(
                    f"  {i+1}. {side_emoji} {trade.side.name}: "
                    f"{trade.amount:.6f} BTC @ ${trade.price:,.2f} "
                    f"(Time: {trade.timestamp})"
                )
        
        # Test 6: Multi-symbol orderbook comparison
        logger.info("\n=== Test 6: Multi-Symbol Price Comparison ===")
        
        comparison_symbols = [
            Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
            Symbol(base=AssetName("ETH"), quote=AssetName("USDT")),
            Symbol(base=AssetName("BNB"), quote=AssetName("USDT")),
        ]
        
        price_data = []
        for symbol in comparison_symbols:
            if symbol in exchange_info:
                try:
                    ob = await client.get_orderbook(symbol, limit=1)
                    if ob.bids and ob.asks:
                        mid_price = (ob.bids[0].price + ob.asks[0].price) / 2
                        price_data.append((symbol, mid_price))
                except Exception as e:
                    logger.warning(f"Failed to get orderbook for {symbol}: {e}")
        
        logger.info("Current mid prices:")
        for symbol, price in price_data:
            logger.info(f"  {symbol.base}/{symbol.quote}: ${price:,.2f}")
        
        logger.info("\n=== All Tests Completed Successfully ===")
        
    except Exception as e:
        logger.error(f"Error during API demonstration: {e}")
        raise
    
    finally:
        # Clean up resources
        await client.close()
        logger.info("Closed Gate.io public REST client")


def main():
    """Main entry point."""
    print("Gate.io Public REST API Example")
    print("=" * 50)
    print("This example demonstrates Gate.io public market data API usage.")
    print("No API credentials required.")
    print()
    
    # Run the demonstration
    try:
        asyncio.run(demonstrate_public_api())
        print("\n✅ Example completed successfully!")
        
    except KeyboardInterrupt:
        print("\n⚠️ Example interrupted by user")
    
    except Exception as e:
        print(f"\n❌ Example failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()