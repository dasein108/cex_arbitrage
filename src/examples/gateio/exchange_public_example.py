#!/usr/bin/env python3
"""
Gate.io Exchange Interface Example (Public Operations)

Demonstrates usage of the main GateioExchange class for public market operations.
This example shows the high-level interface that combines REST and WebSocket functionality.

Features demonstrated:
1. Exchange initialization and symbol management
2. Real-time orderbook streaming via WebSocket
3. REST API integration for exchange info and market data
4. Performance monitoring and metrics
5. Proper resource management with context managers

No API credentials required for public-only operations.

Usage:
    python -m src.examples.gateio.exchange_public_example
"""

import asyncio
import logging
from typing import List

from exchanges.gateio import GateioExchange
from exchanges.interface.structs import Symbol, AssetName


async def demonstrate_exchange_interface():
    """Demonstrate the Gate.io exchange interface for public operations."""
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger = logging.getLogger(__name__)
    
    # Define symbols for demonstration
    demo_symbols = [
        Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
        Symbol(base=AssetName("ETH"), quote=AssetName("USDT")),
    ]
    
    logger.info("Initializing Gate.io exchange...")
    
    # Initialize exchange without credentials (public-only mode)
    exchange = GateioExchange()
    
    try:
        # Method 1: Using context manager (recommended)
        logger.info("\n=== Method 1: Context Manager Usage ===")
        
        async with exchange.session(symbols=demo_symbols) as session:
            logger.info(f"Exchange initialized: {session}")
            logger.info(f"Active symbols: {len(session.active_symbols)}")
            
            # Wait for initial WebSocket connections and data
            logger.info("Waiting for initial market data...")
            await asyncio.sleep(5)
            
            # Check orderbook data
            logger.info("\n--- Current Orderbook Data ---")
            all_orderbooks = session.get_all_orderbooks()
            
            for symbol, orderbook in all_orderbooks.items():
                if orderbook.bids and orderbook.asks:
                    best_bid = orderbook.bids[0].price
                    best_ask = orderbook.asks[0].price
                    mid_price = (best_bid + best_ask) / 2
                    spread = best_ask - best_bid
                    
                    logger.info(
                        f"{symbol.base}/{symbol.quote}: "
                        f"Bid ${best_bid:,.2f}, Ask ${best_ask:,.2f}, "
                        f"Mid ${mid_price:,.2f}, Spread ${spread:.2f}"
                    )
                else:
                    logger.info(f"{symbol.base}/{symbol.quote}: No orderbook data yet")
            
            # Get latest orderbook from property
            latest_ob = session.orderbook
            if latest_ob.bids and latest_ob.asks:
                logger.info(f"\nLatest orderbook update: {latest_ob.timestamp}")
                logger.info(f"Levels: {len(latest_ob.bids)} bids, {len(latest_ob.asks)} asks")
            
            # Performance metrics
            logger.info("\n--- Performance Metrics ---")
            metrics = session.get_performance_metrics()
            for key, value in metrics.items():
                logger.info(f"{key}: {value}")
        
        # Context manager automatically closes connections
        logger.info("✅ Context manager example completed")
        
    except Exception as e:
        logger.error(f"Error during exchange interface demonstration: {e}")
        raise


async def demonstrate_symbol_management():
    """Demonstrate dynamic symbol subscription management."""
    
    logger = logging.getLogger(__name__)
    
    logger.info("\n=== Method 2: Manual Symbol Management ===")
    
    exchange = GateioExchange()
    
    try:
        # Initialize with no symbols
        await exchange.init()
        logger.info("Exchange initialized with no symbols")
        
        # Add symbols dynamically
        symbols_to_add = [
            Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
            Symbol(base=AssetName("ETH"), quote=AssetName("USDT")),
            Symbol(base=AssetName("SOL"), quote=AssetName("USDT")),
        ]
        
        for symbol in symbols_to_add:
            logger.info(f"Adding {symbol.base}/{symbol.quote}...")
            await exchange.add_symbol(symbol)
            
            # Check if orderbook is available
            await asyncio.sleep(2)
            orderbook = exchange.get_orderbook(symbol)
            
            if orderbook and orderbook.bids and orderbook.asks:
                logger.info(f"✅ {symbol.base}/{symbol.quote} orderbook active")
            else:
                logger.info(f"⏳ {symbol.base}/{symbol.quote} waiting for data...")
        
        logger.info(f"\nActive symbols: {len(exchange.active_symbols)}")
        
        # Stream data for a while
        logger.info("Streaming data for 15 seconds...")
        await asyncio.sleep(15)
        
        # Show collected data
        logger.info("\n--- Collected Market Data ---")
        for symbol in exchange.active_symbols:
            orderbook = exchange.get_orderbook(symbol)
            if orderbook and orderbook.bids and orderbook.asks:
                best_bid = orderbook.bids[0].price
                best_ask = orderbook.asks[0].price
                timestamp = orderbook.timestamp
                
                logger.info(
                    f"{symbol.base}/{symbol.quote}: "
                    f"${(best_bid + best_ask) / 2:,.2f} "
                    f"(last update: {timestamp})"
                )
        
        # Remove some symbols
        logger.info("\n--- Removing Symbols ---")
        symbols_to_remove = symbols_to_add[:-1]  # Keep last one
        
        for symbol in symbols_to_remove:
            logger.info(f"Removing {symbol.base}/{symbol.quote}...")
            await exchange.remove_symbol(symbol)
        
        logger.info(f"Remaining active symbols: {len(exchange.active_symbols)}")
        
        # Final metrics
        logger.info("\n--- Final Metrics ---")
        final_metrics = exchange.get_performance_metrics()
        for key, value in final_metrics.items():
            logger.info(f"{key}: {value}")
        
    finally:
        # Manual cleanup
        await exchange.close()
        logger.info("✅ Manual management example completed")


async def demonstrate_error_handling():
    """Demonstrate error handling and recovery."""
    
    logger = logging.getLogger(__name__)
    
    logger.info("\n=== Method 3: Error Handling Demo ===")
    
    exchange = GateioExchange()
    
    try:
        # Test invalid symbol handling
        logger.info("Testing invalid symbol handling...")
        
        await exchange.init()
        
        # Try to add an invalid symbol (should handle gracefully)
        try:
            invalid_symbol = Symbol(base=AssetName("INVALID"), quote=AssetName("TOKEN"))
            await exchange.add_symbol(invalid_symbol)
            logger.info("Invalid symbol added (unexpectedly)")
        except Exception as e:
            logger.info(f"Expected error for invalid symbol: {type(e).__name__}")
        
        # Test double initialization
        logger.info("Testing double initialization...")
        try:
            await exchange.init()  # Should be safe
            logger.info("Double initialization handled gracefully")
        except Exception as e:
            logger.warning(f"Unexpected error on double init: {e}")
        
        # Test symbol operations without initialization
        logger.info("Testing operations without proper setup...")
        
        fresh_exchange = GateioExchange()
        try:
            test_symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
            await fresh_exchange.add_symbol(test_symbol)  # Should fail
        except Exception as e:
            logger.info(f"Expected error for uninitialized exchange: {type(e).__name__}")
        finally:
            await fresh_exchange.close()
        
        logger.info("✅ Error handling tests completed")
        
    finally:
        await exchange.close()


def main():
    """Main entry point."""
    print("Gate.io Exchange Interface Example (Public Operations)")
    print("=" * 60)
    print("This example demonstrates the high-level Gate.io exchange interface.")
    print("No API credentials required for public operations.")
    print()
    
    try:
        # Run all demonstrations
        asyncio.run(demonstrate_exchange_interface())
        asyncio.run(demonstrate_symbol_management()) 
        asyncio.run(demonstrate_error_handling())
        
        print("\n✅ All exchange interface examples completed successfully!")
        print("\nKey Features Demonstrated:")
        print("  - Context manager usage (recommended)")
        print("  - Dynamic symbol subscription management")
        print("  - Real-time orderbook streaming")
        print("  - Performance monitoring")
        print("  - Error handling and recovery")
        print("  - Proper resource cleanup")
        
    except KeyboardInterrupt:
        print("\n⚠️ Examples interrupted by user")
    
    except Exception as e:
        print(f"\n❌ Examples failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()