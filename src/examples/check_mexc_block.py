#!/usr/bin/env python3
"""
Check MEXC blocking response details
"""

import asyncio
import websockets
import json

async def main():
    """Check MEXC blocking response"""
    url = "wss://wbs.mexc.com/ws"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Origin': 'https://www.mexc.com',
    }
    
    try:
        async with websockets.connect(url, extra_headers=headers, origin='https://www.mexc.com') as websocket:
            print("Connected to MEXC WebSocket")
            
            # Send subscription
            subscription = {
                "method": "SUBSCRIPTION",
                "params": ["spot@public.depth.v3.api.pb@BTCUSDT"],
                "id": 1
            }
            
            await websocket.send(json.dumps(subscription))
            print(f"Sent: {subscription}")
            
            # Wait for first message
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=10)
                print(f"Received: {response}")
                
                # Parse response
                try:
                    parsed = json.loads(response)
                    print(f"Parsed response: {parsed}")
                    
                    if "Blocked" in response:
                        print("\n=== MEXC BLOCKING DETECTED ===")
                        print("MEXC is blocking WebSocket connections from this IP/region.")
                        print("This is a server-side restriction, not a client issue.")
                        print("Possible solutions:")
                        print("1. Use a VPN to change IP location")
                        print("2. Try alternative MEXC WebSocket endpoints")
                        print("3. Use MEXC REST API instead of WebSocket")
                        print("4. Test from different network/region")
                        print("================================")
                        
                except json.JSONDecodeError:
                    print(f"Not JSON: {response}")
                    
            except asyncio.TimeoutError:
                print("No response received within 10 seconds")
                
    except Exception as e:
        print(f"Connection error: {e}")

if __name__ == "__main__":
    asyncio.run(main())