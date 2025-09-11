#!/usr/bin/env python3
"""
Debug MEXC WebSocket to identify message reading issues
"""

import asyncio
import logging
from typing import Dict, Any

from exchanges.mexc.mexc_ws_public import MexcWebSocketPublicStream
from structs.exchange import Symbol, AssetName, ExchangeName, StreamType
from exchanges.interface.websocket.base_ws import WebSocketConfig

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

async def debug_message_handler(message: Dict[str, Any]):
    """Debug message handler to see what we're receiving"""
    print(f"[DEBUG] Received message: {message}")

async def debug_error_handler(error: Exception):
    """Debug error handler"""
    print(f"[ERROR] WebSocket error: {error}")

async def main():
    """Debug WebSocket message reception"""
    print("Starting MEXC WebSocket debug...")
    
    # Create WebSocket with debug config
    ws_config = WebSocketConfig(
        url="wss://wbs.mexc.com/ws",
        timeout=30.0,
        ping_interval=15.0,
        ping_timeout=5.0,
        close_timeout=3.0,
        max_reconnect_attempts=5,
        reconnect_delay=0.5,
        reconnect_backoff=1.5,
        max_reconnect_delay=30.0,
        max_message_size=2 * 1024 * 1024,
        max_queue_size=5000,
        heartbeat_interval=20.0,
        enable_compression=True
    )
    
    websocket = MexcWebSocketPublicStream(
        message_handler=debug_message_handler,
        error_handler=debug_error_handler,
        config=ws_config
    )
    
    # Start WebSocket
    await websocket.start()
    print("WebSocket started...")
    
    # Subscribe to a simple stream
    streams = ["spot@public.depth.v3.api.pb@BTCUSDT"]
    print(f"Subscribing to: {streams}")
    await websocket.subscribe(streams)
    
    # Wait and monitor for messages
    print("Waiting for messages...")
    for i in range(60):  # Wait 60 seconds max
        await asyncio.sleep(1)
        health = await websocket.get_health_check()
        metrics = websocket.get_performance_metrics()
        
        if i % 10 == 0:  # Every 10 seconds
            print(f"[{i:02d}s] Connected: {health.get('is_connected', False)}, "
                  f"Messages: {metrics.get('mexc_performance', {}).get('messages_parsed', 0)}")
            
            # Check if we got any messages
            if metrics.get('mexc_performance', {}).get('messages_parsed', 0) > 0:
                print("SUCCESS: Messages received!")
                break
    else:
        print("TIMEOUT: No messages received after 60 seconds")
    
    # Stop WebSocket
    await websocket.stop()
    
    # Print final metrics
    final_metrics = websocket.get_performance_metrics()
    print(f"\nFinal metrics:")
    print(f"  Messages parsed: {final_metrics.get('mexc_performance', {}).get('messages_parsed', 0)}")
    print(f"  Parse errors: {final_metrics.get('mexc_performance', {}).get('parse_errors', 0)}")
    print(f"  Messages received: {final_metrics.get('messages_received', 0)}")

if __name__ == "__main__":
    asyncio.run(main())