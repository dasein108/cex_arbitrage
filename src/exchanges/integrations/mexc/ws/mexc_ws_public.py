"""
MEXC Public WebSocket Implementation

Clean implementation using handler objects for organized message processing.
Handles public WebSocket streams for market data including:
- Orderbook depth updates
- Trade stream data
- Real-time market information

Features:
- Handler object pattern for clean organization
- HFT-optimized message processing 
- Event-driven architecture with structured handlers
- Clean separation of concerns
- MEXC-specific protobuf message parsing

MEXC Public WebSocket Specifications:
- Endpoint: wss://wbs.mexc.com/ws
- Protocol: JSON and Protocol Buffers
- Performance: <50ms latency with batch processing

Architecture: Handler objects with composite class coordination
"""

from websockets import connect

from exchanges.interfaces.ws import PublicSpotWebsocket
from exchanges.integrations.mexc.structs.protobuf.PushDataV3ApiWrapper_pb2 import PushDataV3ApiWrapper
from exchanges.integrations.mexc.structs.protobuf.PublicLimitDepthsV3Api_pb2 import PublicLimitDepthsV3Api
from exchanges.integrations.mexc.structs.protobuf.PublicAggreDealsV3Api_pb2 import PublicAggreDealsV3Api


class MexcPublicSpotWebsocket(PublicSpotWebsocket):
    """MEXC public WebSocket client using dependency injection pattern."""

    async def _create_websocket(self):
        return await connect(
            self.config.websocket_url,
            # Performance optimizations for MEXC
            ping_interval=self.config.websocket.ping_interval,
            ping_timeout=self.config.websocket.ping_timeout,
            max_queue=self.config.websocket.max_queue_size,
            # Disable compression for CPU optimization in HFT
            compression=None,
            max_size=self.config.websocket.max_message_size,
        )