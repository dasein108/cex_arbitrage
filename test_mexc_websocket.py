#!/usr/bin/env python3
"""
Test script for MEXC WebSocket public stream implementation
"""

import asyncio
import logging
from typing import Dict, Any

from src.exchanges.mexc.websocket import MexcWebSocketPublicStream
from src.structs.exchange import ExchangeName

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def message_handler(message: Dict[str, Any]):
    """Handle incoming WebSocket messages"""
    print(f"Received message: {message.get('stream_type', 'unknown')} - {message}")

async def on_connected():
    """Called when WebSocket connects"""
    print("WebSocket connected!")

async def on_restart():
    """Called when WebSocket restarts"""
    print("WebSocket restarted!")

async def main():
    """Test the MEXC WebSocket implementation"""
    print("Testing MEXC WebSocket Public Stream")
    
    # Create WebSocket instance
    ws = MexcWebSocketPublicStream(
        exchange_name=ExchangeName("MEXC"),
        on_message=message_handler,
        on_connected=on_connected,
        on_restart=on_restart,
        timeout=30.0,
        max_retries=5
    )
    
    try:
        # Wait a bit for connection
        await asyncio.sleep(2)
        
        # Subscribe to test streams
        test_streams = [
            "BTCUSDT@deal",      # BTC trades
            "ETHUSDT@deal",      # ETH trades
            "BTCUSDT@depth",     # BTC orderbook
            "ETHUSDT@depth"      # ETH orderbook
        ]
        
        print(f"Subscribing to streams: {test_streams}")
        await ws.subscribe(test_streams)
        
        # Let it run for 30 seconds to collect data
        print("Listening for messages for 30 seconds...")
        await asyncio.sleep(30)
        
        # Check health status
        health = ws.get_health_status()
        print(f"Health status: {health}")
        
    except KeyboardInterrupt:
        print("Interrupted by user")
    except Exception as e:
        print(f"Error during test: {e}")
    finally:
        print("Stopping WebSocket...")
        await ws.stop()
        print("Test completed")

if __name__ == "__main__":
    asyncio.run(main())