#!/usr/bin/env python3
"""
Simple test script to validate MEXC WebSocket functionality.

This script will test the current WebSocket implementation to identify any issues
with message reception for the stream format: spot@public.aggre.deals.v3.api.protobuf@10ms@BTCUSDT
"""
import asyncio
import logging
import signal
import sys
import time
from typing import Any, Dict
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Configure logging first
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import the current MEXC implementation
try:
    from exchanges.mexc.ws.legacy.mexc_ws_public_old import MexcWebSocketPublicStream
    from common.ws_client import WebSocketConfig
    
    logger.info("Successfully imported MEXC WebSocket implementation")
    
except ImportError as e:
    logger.error(f"Failed to import MEXC WebSocket: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Global variables for signal handling
websocket_client = None
running = True

async def message_handler(message: Dict[str, Any]):
    """Handle incoming WebSocket messages."""
    logger.info(f"Received message: {message}")
    print(f"MESSAGE: {message}")

async def error_handler(error: Exception):
    """Handle WebSocket errors."""
    logger.error(f"WebSocket error: {error}")
    print(f"ERROR: {error}")

def signal_handler(signum, frame):
    """Handle shutdown signals."""
    global running, websocket_client
    logger.info("Received shutdown signal, cleaning up...")
    running = False
    if websocket_client:
        asyncio.create_task(websocket_client.stop())

async def test_mexc_websocket():
    """Test MEXC WebSocket with the specified stream format."""
    global websocket_client, running
    
    try:
        # Create WebSocket configuration
        config = WebSocketConfig(
            url="wss://wbs-api.mexc.com/ws",
            timeout=10.0,
            ping_interval=20.0,
            ping_timeout=10.0,
            close_timeout=5.0,
            max_reconnect_attempts=5,
            reconnect_delay=1.0,
            reconnect_backoff=2.0,
            max_reconnect_delay=30.0,
            max_message_size=1024 * 1024,
            max_queue_size=1000,
            heartbeat_interval=30.0,
            enable_compression=False  # Disable for debugging
        )
        
        # Create WebSocket client
        logger.info("Creating MEXC WebSocket client...")
        websocket_client = MexcWebSocketPublicStream(
            message_handler=message_handler,
            error_handler=error_handler,
            config=config
        )
        
        # Start the WebSocket connection
        logger.info("Starting WebSocket connection...")
        await websocket_client.start()
        
        # Wait a moment for connection
        await asyncio.sleep(2)
        
        # Test different stream formats
        test_streams = [
            # Original format request
            "spot@public.aggre.deals.v3.api.protobuf@10ms@BTCUSDT",
            # Standard MEXC format
            "spot@public.deals.v3.api.protobuf@BTCUSDT",
            # Depth stream
            "spot@public.depth.v3.api.protobuf@BTCUSDT",
        ]
        
        for stream in test_streams:
            logger.info(f"Testing subscription to: {stream}")
            try:
                await websocket_client.subscribe([stream])
                logger.info(f"Successfully subscribed to {stream}")
                
                # Wait for messages
                logger.info("Waiting 10 seconds for messages...")
                await asyncio.sleep(10)
                

                # Unsubscribe and try next
                await websocket_client.unsubscribe([stream])
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"Error testing stream {stream}: {e}")
        
        # Keep connection alive for final testing
        logger.info("Final test: subscribing to simple depth stream...")
        await websocket_client.subscribe(["spot@public.depth.v3.api.protobuf@BTCUSDT"])
        
        # Wait for messages
        start_time = time.time()
        while running and (time.time() - start_time) < 30:
            await asyncio.sleep(1)
            metrics = websocket_client.get_performance_metrics()
            messages_received = metrics.get('mexc_performance', {}).get('messages_parsed', 0)
            if messages_received > 0:
                logger.info(f"SUCCESS: Received {messages_received} messages!")
                break
        else:
            logger.error("FAILURE: No messages received in 30 seconds")
            
    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if websocket_client:
            logger.info("Stopping WebSocket client...")
            await websocket_client.stop()

async def main():
    """Main test function."""
    logger.info("Starting MEXC WebSocket test...")
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await test_mexc_websocket()
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    except Exception as e:
        logger.error(f"Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
    finally:
        logger.info("Test completed")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Program interrupted")
    except Exception as e:
        logger.error(f"Program failed: {e}")
        sys.exit(1)