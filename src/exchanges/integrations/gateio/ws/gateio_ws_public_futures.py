"""
Gate.io Public Futures WebSocket Implementation

Separate exchange implementation treating Gate.io futures as completely independent
from Gate.io spot. Uses dedicated configuration section 'gateio_futures' with its own
ExchangeEnum.GATEIO_FUTURES and separate WebSocket endpoints.

Handles public futures WebSocket streams for market data including:
- Futures orderbook depth updates  
- Futures trade stream data
- Real-time futures market information
- Funding rates and mark prices

Features:
- Completely separate from Gate.io spot configuration
- Dedicated ExchangeEnum.GATEIO_FUTURES with 'gateio_futures' config section
- HFT-optimized message processing for futures markets
- Event-driven architecture with injected handlers
- Clean separation from spot exchange operations
- Gate.io futures-specific JSON message parsing

Gate.io Public Futures WebSocket Specifications:
- Primary Endpoint: wss://fx-ws.gateio.ws/v4/ws/usdt/ (USDT perpetual futures)
- Secondary Endpoint: wss://fx-ws.gateio.ws/v4/ws/delivery/ (delivery futures)  
- Protocol: JSON-based message format
- Performance: <80ms latency target for futures operations

Architecture: Independent exchange with separate configuration and factory support
"""

from typing import List, Dict, Optional, Callable, Awaitable, Set

from exchanges.consts import DEFAULT_PUBLIC_WEBSOCKET_CHANNELS
from exchanges.structs.common import Symbol, Trade, OrderBook, BookTicker
from config.structs import ExchangeConfig
from exchanges.interfaces.ws import PublicFuturesWebsocket
from infrastructure.networking.websocket.structs import ConnectionState, PublicWebsocketChannelType
from infrastructure.networking.websocket.handlers import PublicWebsocketHandlers
from infrastructure.logging import HFTLogger
# Symbol validation is now handled at the data collector level
from .gateio_ws_common import GateioBaseWebsocket


class GateioPublicFuturesWebsocket(PublicFuturesWebsocket, GateioBaseWebsocket):
    """Gate.io public futures WebSocket client using dependency injection pattern."""
    pass

