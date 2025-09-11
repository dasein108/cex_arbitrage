"""
Simple MEXC WebSocket Implementation

A minimal, working WebSocket implementation for MEXC that focuses on message reception.
Based on the working raw implementation but simplified for easy use.

Stream format support: spot@public.aggre.deals.v3.api.protobuf@10ms@BTCUSDT
"""

import asyncio
import logging
import json
import time
from typing import Any, Callable, Dict, List, Optional, Union
from websockets import connect, ConnectionClosedError

# Protobuf support
try:
    from exchanges.mexc.protobuf.PushDataV3ApiWrapper_pb2 import PushDataV3ApiWrapper
    from google.protobuf import json_format

    PROTOBUF_AVAILABLE = True
except ImportError:
    PROTOBUF_AVAILABLE = False
    logging.warning("Protobuf support not available, will only handle JSON messages")


class SimpleMexcWebSocket:
    """
    Simple MEXC WebSocket client that actually works.
    
    Features:
    - Simple connection and message reception
    - Support for both JSON and Protobuf messages
    - Automatic reconnection
    - Easy subscription management
    """

    def __init__(
            self,
            url: str = "wss://wbs.mexc.com/ws",  # Corrected URL based on ccxt
            message_handler: Optional[Callable[[Dict[str, Any]], None]] = None,
            ping_interval: float = 20.0,
            max_queue: int = 5000,
            name: str = "SimpleMexcWS"
    ):
        self.url = url
        self.message_handler = message_handler or self._default_message_handler
        self.ping_interval = ping_interval
        self.max_queue = max_queue
        self.name = name

        # Connection state
        self.ws = None
        self.running = False
        self.logger = logging.getLogger(f"{__name__}.{name}")

        # Subscription tracking
        self.subscriptions = set()

        # Statistics
        self.messages_received = 0
        self.json_messages = 0
        self.protobuf_messages = 0
        self.errors = 0
        self.start_time = time.time()

    def _default_message_handler(self, message: Dict[str, Any]):
        """Default message handler that just logs messages."""
        self.logger.info(f"Received message: {message}")

    async def connect(self):
        """Establish WebSocket connection."""
        try:
            self.logger.info(f"Connecting to {self.url}")

            # Use same connection parameters as working implementation
            self.ws = await connect(
                self.url,
                ping_interval=self.ping_interval,
                max_queue=self.max_queue,
            )

            self.logger.info("WebSocket connected successfully")
            return True

        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            return False

    async def disconnect(self):
        """Close WebSocket connection."""
        self.running = False
        if self.ws:
            await self.ws.close()
            self.ws = None
        self.logger.info("WebSocket disconnected")

    async def subscribe(self, streams: List[str]):
        """Subscribe to streams."""
        if not self.ws:
            self.logger.error("Not connected, cannot subscribe")
            return False

        try:
            # MEXC subscription format (correct method from ccxt)
            message = {
                "method": "SUBSCRIPTION",  # Corrected: should be SUBSCRIPTION, not SUBSCRIBE
                "params": streams,
                "id": 1
            }

            # Send as JSON string (MEXC expects this format)
            message_str = json.dumps(message)
            await self.ws.send(message_str)

            # Track subscriptions
            for stream in streams:
                self.subscriptions.add(stream)

            self.logger.info(f"Subscribed to {len(streams)} streams: {streams}")
            return True

        except Exception as e:
            self.logger.error(f"Subscription failed: {e}")
            return False

    async def unsubscribe(self, streams: List[str]):
        """Unsubscribe from streams."""
        if not self.ws:
            self.logger.error("Not connected, cannot unsubscribe")
            return False

        try:
            message = {
                "method": "UNSUBSCRIBE",
                "params": streams,
                "id": 1
            }

            message_str = json.dumps(message)
            await self.ws.send(message_str)

            # Remove from tracking
            for stream in streams:
                self.subscriptions.discard(stream)

            self.logger.info(f"Unsubscribed from {len(streams)} streams")
            return True

        except Exception as e:
            self.logger.error(f"Unsubscribe failed: {e}")
            return False

    async def _read_messages(self):
        """
        Read messages from WebSocket using the correct pattern.
        
        This is the key fix - use simple while loop with recv(), not async for.
        """
        self.logger.info("Starting message reader")

        try:
            while self.running and self.ws:
                # This is the correct pattern from the working implementation
                message = await self.ws.recv()

                try:
                    await self._process_message(message)
                    self.messages_received += 1

                except Exception as e:
                    self.errors += 1
                    self.logger.error(f"Error processing message: {e}")
                    # Continue processing other messages

        except ConnectionClosedError as e:
            self.logger.warning(f"Connection closed: {e}")
        except Exception as e:
            self.logger.error(f"Message reader error: {e}")
            import traceback
            traceback.print_exc()

    async def _process_message(self, raw_message: Union[str, bytes]):
        """Process incoming message."""
        if isinstance(raw_message, str):
            # JSON message
            await self._process_json_message(raw_message)

        elif isinstance(raw_message, bytes):
            # Try protobuf first, then JSON
            if PROTOBUF_AVAILABLE and await self._process_protobuf_message(raw_message):
                self.protobuf_messages += 1
            else:
                # Try as JSON bytes
                try:
                    json_str = raw_message.decode('utf-8')
                    await self._process_json_message(json_str)
                except UnicodeDecodeError:
                    self.logger.debug("Could not decode bytes as JSON")

    async def _process_json_message(self, message_str: str):
        """Process JSON message."""
        try:
            # Parse JSON
            data = json.loads(message_str.strip())
            self.json_messages += 1

            # Skip heartbeat/pong messages
            if self._is_heartbeat_message(data):
                self.logger.debug("Received heartbeat message")
                return

            # Call message handler
            if asyncio.iscoroutinefunction(self.message_handler):
                await self.message_handler(data)
            else:
                self.message_handler(data)

        except json.JSONDecodeError as e:
            self.logger.debug(f"JSON decode error: {e}")
        except Exception as e:
            self.logger.error(f"JSON message processing error: {e}")

    async def _process_protobuf_message(self, message_bytes: bytes) -> bool:
        """Process protobuf message."""
        if not PROTOBUF_AVAILABLE:
            return False

        try:
            # Parse protobuf wrapper
            wrapper = PushDataV3ApiWrapper()
            wrapper.ParseFromString(message_bytes)

            # Convert to dict
            data = json_format.MessageToDict(wrapper, preserving_proto_field_name=True)

            # Call message handler
            if asyncio.iscoroutinefunction(self.message_handler):
                await self.message_handler(data)
            else:
                self.message_handler(data)

            return True

        except Exception as e:
            self.logger.debug(f"Protobuf processing error: {e}")
            return False

    def _is_heartbeat_message(self, data: Dict[str, Any]) -> bool:
        """Check if message is a heartbeat."""
        # Common heartbeat patterns
        msg_str = str(data).lower()
        return (
                'pong' in msg_str or
                'ping' in msg_str or
                data.get('type') == 'heartbeat' or
                (data.get('id') == 1 and 'result' in data)  # Subscription response
        )

    async def run(self):
        """Run the WebSocket client with automatic reconnection."""
        self.running = True

        while self.running:
            try:
                # Connect
                if not await self.connect():
                    await asyncio.sleep(5)
                    continue

                # Re-subscribe to previous subscriptions
                if self.subscriptions:
                    await self.subscribe(list(self.subscriptions))

                # Start reading messages
                await self._read_messages()

            except Exception as e:
                self.logger.error(f"Connection error: {e}")
                import traceback
                traceback.print_exc()

            # Reconnection delay
            if self.running:
                self.logger.info("Reconnecting in 5 seconds...")
                await asyncio.sleep(5)

    async def start(self):
        """Start the WebSocket client in background."""
        task = asyncio.create_task(self.run())
        # Give it a moment to connect
        await asyncio.sleep(1)
        return task

    def get_stats(self) -> Dict[str, Any]:
        """Get connection statistics."""
        uptime = time.time() - self.start_time

        return {
            'connected': self.ws is not None and not self.ws.closed,
            'running': self.running,
            'messages_received': self.messages_received,
            'json_messages': self.json_messages,
            'protobuf_messages': self.protobuf_messages,
            'errors': self.errors,
            'subscriptions': list(self.subscriptions),
            'uptime_seconds': uptime,
            'messages_per_second': self.messages_received / max(uptime, 1),
            'error_rate': self.errors / max(self.messages_received, 1)
        }


# Test script functionality
async def check_simple_websocket():
    """Test the simple WebSocket implementation."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    logger = logging.getLogger(__name__)

    def message_handler(message: Dict[str, Any]):
        logger.info(f"GOT MESSAGE: {message}")
        print(f"MESSAGE: {message}")

    # Create WebSocket
    ws = SimpleMexcWebSocket(message_handler=message_handler)

    try:
        # Start WebSocket
        task = await ws.start()

        # Test different streams (corrected formats based on ccxt)
        check_streams = [
            # Correct MEXC formats without .protobuf suffix and with proper intervals
            # "spot@public.aggre.deals.v3.api.pb@10ms@STOPUSDT"
            # "spot@public.limit.depth.v3.api.pb@STOPUSDT@5",
            "spot@public.limit.depth.v3.api.pb@STOPUSDT@5",
            "spot@public.aggre.deals.v3.api.pb@100ms@BTCUSDT"
        ]

        for stream in check_streams:
            logger.info(f"Testing stream: {stream}")
            await ws.subscribe([stream])

            # Wait for messages
            await asyncio.sleep(10)

            stats = ws.get_stats()
            logger.info(f"Stats: {stats}")

            if stats['messages_received'] > 0:
                logger.info(f"SUCCESS: Got {stats['messages_received']} messages!")
                break
            else:
                logger.warning("No messages received, trying next stream...")
                await ws.unsubscribe([stream])

        # Wait a bit more for final messages
        await asyncio.sleep(5)

        final_stats = ws.get_stats()
        logger.info(f"Final stats: {final_stats}")

        if final_stats['messages_received'] == 0:
            logger.error("FAILURE: No messages received from any stream")
        else:
            logger.info(f"SUCCESS: Received {final_stats['messages_received']} total messages")

    finally:
        await ws.disconnect()


if __name__ == "__main__":
    asyncio.run(check_simple_websocket())
