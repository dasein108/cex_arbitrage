"""
WebSocket components for HFT trading systems.

This module provides high-performance WebSocket infrastructure using mixin-based
composition for exchange-agnostic trading implementations.
"""

from infrastructure.networking.websocket.ws_manager import WebSocketManager
# Using mixin-based composition - strategies replaced by mixins
from infrastructure.networking.websocket.mixins import (
    PublicWebSocketMixin, PrivateWebSocketMixin, 
    SubscriptionMixin, ConnectionMixin
)
from infrastructure.networking.websocket.structs import (
    MessageType, SubscriptionAction, ConnectionContext, 
    SubscriptionContext, ParsedMessage, WebSocketManagerConfig,
    PerformanceMetrics, ConnectionState
)
from infrastructure.networking.websocket.handlers import PublicWebsocketHandlers, PrivateWebsocketHandlers

from .ws_base import BaseWebsocketInterface
from .spot import PrivateSpotWebsocket, PublicSpotWebsocket
from .futures import PublicFuturesWebsocket, PrivateFuturesWebsocket
__all__ = [
    'WebSocketManager',
    # Mixin-based architecture
    'PublicWebSocketMixin',
    'PrivateWebSocketMixin', 
    'SubscriptionMixin',
    'ConnectionMixin',
    # Core structures
    'MessageType',
    'SubscriptionAction',
    'ConnectionContext',
    'SubscriptionContext', 
    'ParsedMessage',
    'WebSocketManagerConfig',
    'PerformanceMetrics',
    'ConnectionState',
    # Interfaces
    'BaseWebsocketInterface',
    'PrivateSpotWebsocket',
    'PublicSpotWebsocket',
    'PublicFuturesWebsocket',
    'PublicWebsocketHandlers',
    'PrivateWebsocketHandlers',
    'PrivateFuturesWebsocket'
]