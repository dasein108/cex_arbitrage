#!/usr/bin/env python3
"""
Test script to demonstrate the WebSocket integration with the PublicExchangeInterface.

This script shows how the enhanced PublicExchangeInterface now provides:
1. Automatic WebSocket connection to orderbook streams during initialization
2. Real-time orderbook updates stored in self.order_book
3. Dynamic symbol management with start_symbol() and stop_symbol()
4. Health monitoring and cleanup capabilities
"""

import asyncio
import logging
from src.structs.exchange import Symbol, AssetName, ExchangeName
from src.exchanges.mexc.mexc_public import MexcPublicExchange

# Set up logging to see the integration in action
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_websocket_integration():
    """Test the WebSocket integration with MEXC exchange."""
    
    # Create symbols for testing
    btc_usdt = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
    eth_usdt = Symbol(base=AssetName("ETH"), quote=AssetName("USDT"))
    symbols = [btc_usdt, eth_usdt]
    
    # Initialize MEXC exchange
    exchange = MexcPublicExchange()
    
    try:
        print("=== Testing WebSocket Integration ===")
        
        # Step 1: Initialize with symbols (this will start WebSocket streams)
        print(f"\n1. Initializing exchange with symbols: {symbols}")
        await exchange.init(symbols)
        
        # Give WebSocket time to connect and receive initial data
        print("   Waiting for WebSocket connection and initial data...")
        await asyncio.sleep(5)
        
        # Step 2: Check WebSocket health
        print(f"\n2. WebSocket Health Status:")
        health = exchange.get_websocket_health()
        for key, value in health.items():
            print(f"   {key}: {value}")
        
        # Step 3: Check active symbols
        print(f"\n3. Active symbols: {exchange.get_active_symbols()}")
        
        # Step 4: Check if we have real-time orderbook data
        print(f"\n4. Real-time orderbook data:")
        for symbol in symbols:
            orderbook = exchange.get_realtime_orderbook(symbol)
            if orderbook:
                print(f"   {symbol}: {len(orderbook.bids)} bids, {len(orderbook.asks)} asks")
                if orderbook.bids and orderbook.asks:
                    print(f"     Best bid: {orderbook.bids[0].price:.4f}")
                    print(f"     Best ask: {orderbook.asks[0].price:.4f}")
            else:
                print(f"   {symbol}: No orderbook data yet")
        
        # Step 5: Add a new symbol dynamically
        ada_usdt = Symbol(base=AssetName("ADA"), quote=AssetName("USDT"))
        print(f"\n5. Adding new symbol: {ada_usdt}")
        await exchange.start_symbol(ada_usdt)
        
        print("   Waiting for new symbol data...")
        await asyncio.sleep(3)
        
        print(f"   Active symbols now: {exchange.get_active_symbols()}")
        orderbook = exchange.get_realtime_orderbook(ada_usdt)
        if orderbook:
            print(f"   {ada_usdt}: {len(orderbook.bids)} bids, {len(orderbook.asks)} asks")
        
        # Step 6: Remove a symbol
        print(f"\n6. Removing symbol: {eth_usdt}")
        await exchange.stop_symbol(eth_usdt)
        
        print(f"   Active symbols now: {exchange.get_active_symbols()}")
        print(f"   ETH/USDT orderbook exists: {exchange.get_realtime_orderbook(eth_usdt) is not None}")
        
        # Step 7: Demonstrate both REST API and WebSocket data access
        print(f"\n7. Comparing REST API vs WebSocket data for {btc_usdt}:")
        
        # Get data via REST API
        rest_orderbook = await exchange.get_orderbook(btc_usdt, limit=10)
        print(f"   REST API - {len(rest_orderbook.bids)} bids, {len(rest_orderbook.asks)} asks")
        if rest_orderbook.bids:
            print(f"     REST best bid: {rest_orderbook.bids[0].price:.4f}")
        
        # Get data via WebSocket (real-time)
        ws_orderbook = exchange.get_realtime_orderbook(btc_usdt)
        if ws_orderbook:
            print(f"   WebSocket - {len(ws_orderbook.bids)} bids, {len(ws_orderbook.asks)} asks")
            if ws_orderbook.bids:
                print(f"     WebSocket best bid: {ws_orderbook.bids[0].price:.4f}")
        
        print(f"\n8. Final WebSocket health check:")
        final_health = exchange.get_websocket_health()
        for key, value in final_health.items():
            print(f"   {key}: {value}")
            
    except Exception as e:
        print(f"Error during test: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Step 8: Clean shutdown
        print(f"\n9. Shutting down...")
        await exchange.stop_all()
        await exchange.close()
        print("   Test completed successfully!")

if __name__ == "__main__":
    print("WebSocket Integration Test for PublicExchangeInterface")
    print("====================================================")
    print("")
    print("This test demonstrates the new WebSocket functionality:")
    print("- Automatic orderbook stream connections during init()")
    print("- Real-time orderbook updates stored in self.order_book")
    print("- Dynamic symbol management")
    print("- Health monitoring and graceful shutdown")
    print("")
    
    asyncio.run(test_websocket_integration())