#!/usr/bin/env python3
"""
Test MEXC blocking detection and error handling
"""

import asyncio
import logging
from typing import Dict, Any

from exchanges.mexc.mexc_ws_public import MexcWebSocketPublicStream
from exchanges.interface.websocket.base_ws import WebSocketConfig
from common.exceptions import ExchangeAPIError

logging.basicConfig(level=logging.DEBUG)

async def message_handler(message: Dict[str, Any]):
    """Debug message handler"""
    print(f"[MESSAGE] {message}")

async def error_handler(error: Exception):
    """Debug error handler"""
    print(f"[ERROR] {error}")

async def main():
    """Test blocking detection"""
    print("Testing MEXC blocking detection...")
    
    # Create WebSocket with very short timeout to fail fast
    config = WebSocketConfig(
        url="wss://wbs.mexc.com/ws",
        timeout=5.0,
        ping_interval=10.0,
        ping_timeout=3.0,
        close_timeout=1.0,
        max_reconnect_attempts=1,  # Single attempt
        reconnect_delay=1.0,
        reconnect_backoff=1.0,
        max_reconnect_delay=5.0,
        max_message_size=1024 * 1024,
        max_queue_size=100,
        heartbeat_interval=10.0,
        enable_compression=True
    )
    
    try:
        websocket = MexcWebSocketPublicStream(
            message_handler=message_handler,
            error_handler=error_handler,
            config=config
        )
        
        print("Starting WebSocket...")
        await websocket.start()
        
        print("Subscribing to test stream...")
        await websocket.subscribe(["spot@public.depth.v3.api.pb@BTCUSDT"])
        
        # Wait for blocking response
        print("Waiting for blocking response...")
        for i in range(10):
            await asyncio.sleep(1)
            metrics = websocket.get_performance_metrics()
            messages_parsed = metrics.get('mexc_performance', {}).get('messages_parsed', 0)
            parse_errors = metrics.get('mexc_performance', {}).get('parse_errors', 0)
            
            print(f"[{i+1}s] Messages: {messages_parsed}, Errors: {parse_errors}")
            
            if parse_errors > 0:
                print("Parse errors detected - likely blocking!")
                break
        
        print("Stopping WebSocket...")
        await websocket.stop()
        
    except ExchangeAPIError as e:
        print(f"CAUGHT BLOCKING ERROR: {e}")
    except Exception as e:
        print(f"Other error: {e}")

if __name__ == "__main__":
    asyncio.run(main())