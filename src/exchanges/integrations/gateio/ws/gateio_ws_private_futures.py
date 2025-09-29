"""
Gate.io Private Futures WebSocket Implementation

Separate exchange implementation treating Gate.io futures private operations as completely 
independent from Gate.io spot. Uses dedicated configuration section 'gateio_futures' with 
its own ExchangeEnum.GATEIO_FUTURES and separate WebSocket endpoints.

Handles private futures WebSocket streams for account data including:
- Futures order updates via JSON
- Futures account balance changes via JSON  
- Futures trade confirmations via JSON
- Futures position updates
- Futures margin updates

Features:
- Completely separate from Gate.io spot configuration
- Dedicated ExchangeEnum.GATEIO_FUTURES with 'gateio_futures' config section
- HFT-optimized message processing for futures trading
- Event-driven architecture with injected handlers
- Clean separation from spot exchange operations
- Gate.io futures-specific JSON message parsing

Gate.io Private Futures WebSocket Specifications:
- Endpoint: wss://fx-ws.gateio.ws/v4/ws/usdt/ (USDT perpetual futures)
- Authentication: API key signature-based (HMAC-SHA512)
- Message Format: JSON with channel-based subscriptions
- Channels: futures.orders, futures.balances, futures.user_trades, futures.positions

Architecture: Independent exchange with separate configuration and factory support
"""

from typing import Dict, Optional, Callable, Awaitable

from exchanges.structs.common import Order, AssetBalance, Trade
from exchanges.structs.types import AssetName
from config.structs import ExchangeConfig
from exchanges.interfaces.ws.futures.ws_private_futures import PrivateFuturesWebsocket
from infrastructure.networking.websocket.handlers import PrivateWebsocketHandlers
from .gateio_ws_common import GateioBaseWebsocket


class GateioPrivateFuturesWebsocket(PrivateFuturesWebsocket, GateioBaseWebsocket):
    """Gate.io private futures WebSocket client using dependency injection pattern."""
    pass
        
