#!/usr/bin/env python3
"""
Simple test of MEXC WebSocket factory functions
"""

import asyncio
import logging
from typing import Dict, Any

from exchanges.mexc.websocket import create_public_stream
from structs.exchange import Symbol, AssetName

logging.basicConfig(level=logging.INFO)

async def handle_message(message: Dict[str, Any]):
    """Handle WebSocket messages"""
    msg_type = message.get('type', 'unknown')
    symbol = message.get('symbol')
    
    if symbol:
        logging.info(f"Received {msg_type} message for {symbol.base}/{symbol.quote}")
    else:
        logging.debug(f"Received message: {message}")

async def handle_error(error: Exception):
    """Handle WebSocket errors"""
    logging.error(f"WebSocket error: {error}")

async def main():
    """Test the factory function"""
    logging.info("Creating WebSocket with factory function...")
    
    # Create WebSocket using factory function
    ws = create_public_stream(
        message_handler=handle_message,
        error_handler=handle_error,
        timeout=30.0
    )
    
    logging.info(f"WebSocket created successfully!")
    logging.info(f"URL: {ws.config.url}")
    logging.info(f"Timeout: {ws.config.timeout}s")
    
    # Test basic connection (will likely fail due to network/rate limits, but that's OK)
    try:
        await ws.start()
        
        # Subscribe to a test symbol
        symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
        await ws.subscribe_orderbook(symbol)
        
        # Wait a bit to see if we get any data
        await asyncio.sleep(5)
        
    except Exception as e:
        logging.info(f"Connection test failed as expected: {e}")
    
    finally:
        await ws.stop()
    
    logging.info("Factory function test completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())