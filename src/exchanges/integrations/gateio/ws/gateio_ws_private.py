"""
Gate.io Private WebSocket Implementation

Clean implementation using handler objects for organized message processing.
Handles authenticated WebSocket streams for account data including:
- Order updates via JSON
- Account balance changes via JSON  
- Trade confirmations via JSON

Features:
- Handler object pattern for clean organization
- HFT-optimized message processing
- Event-driven architecture with structured handlers
- Clean separation of concerns
- Gate.io-specific JSON message parsing

Gate.io Private WebSocket Specifications:
- Endpoint: wss://api.gateio.ws/ws/v4/
- Authentication: API key signature-based (HMAC-SHA512)
- Message Format: JSON with channel-based subscriptions
- Channels: spot.orders, spot.balances, spot.user_trades

Architecture: Handler objects with composite class coordination
"""

from typing import Dict, Optional, Callable, Awaitable

from exchanges.structs.common import Order, AssetBalance, Trade
from exchanges.structs.types import AssetName
from config.structs import ExchangeConfig
from exchanges.interfaces.ws import PrivateSpotWebsocket
from infrastructure.networking.websocket.handlers import PrivateWebsocketHandlers
from .gateio_ws_common import GateioBaseWebsocket

class GateioPrivateSpotWebsocket(PrivateSpotWebsocket, GateioBaseWebsocket):
    """Gate.io private WebSocket client using dependency injection pattern."""
    pass
