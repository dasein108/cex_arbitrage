"""
WebSocket components for HFT trading systems.

This module provides high-performance WebSocket infrastructure using mixin-based
composition for exchange-agnostic trading implementations.
"""

from infrastructure.networking.websocket.ws_manager import WebSocketManager
# Factory pattern removed - using direct instantiation

from .ws_base import BaseWebsocketInterface
from .ws_base_public import PublicBaseWebsocket
from .ws_base_private import PrivateBaseWebsocket
__all__ = [
    'WebSocketManager',
    'PublicBaseWebsocket',
    'PrivateBaseWebsocket',
    'BaseWebsocketInterface'
]