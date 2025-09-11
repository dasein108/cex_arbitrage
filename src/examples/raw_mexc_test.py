#!/usr/bin/env python3
"""
Raw MEXC WebSocket test to see what's actually happening
"""

import asyncio
import logging
import websockets
import json

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

async def main():
    """Test raw WebSocket connection to MEXC"""
    print("Testing raw WebSocket connection to MEXC...")
    
    url = "wss://wbs.mexc.com/ws"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept': '*/*',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Origin': 'https://www.mexc.com',
        'Referer': 'https://www.mexc.com/'
    }
    
    try:
        async with websockets.connect(
            url,
            extra_headers=headers,
            origin='https://www.mexc.com',
            ping_interval=15,
            ping_timeout=5,
            compression=None,
            max_size=2 * 1024 * 1024,
        ) as websocket:
            print("WebSocket connected!")
            
            # Send subscription message
            subscription_msg = {
                "method": "SUBSCRIPTION",
                "params": ["spot@public.depth.v3.api.pb@BTCUSDT"],
                "id": 1
            }
            
            await websocket.send(json.dumps(subscription_msg))
            print(f"Sent subscription: {subscription_msg}")
            
            # Wait for messages
            message_count = 0
            async for message in websocket:
                message_count += 1
                print(f"[{message_count}] Received message type: {type(message)}")
                
                if isinstance(message, str):
                    print(f"  String message: {message[:200]}")
                elif isinstance(message, bytes):
                    print(f"  Bytes message (len={len(message)}): {message[:50].hex()}")
                    # Try to decode as string
                    try:
                        decoded = message.decode('utf-8')
                        print(f"  Decoded: {decoded[:200]}")
                    except:
                        print(f"  Not valid UTF-8")
                
                if message_count >= 10:  # Stop after 10 messages
                    break
                    
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())