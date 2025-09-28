"""
WebSocket components for HFT trading systems.

This module provides high-performance WebSocket infrastructure using mixin-based
composition for exchange-agnostic trading implementations.
"""

from infrastructure.networking.websocket.ws_manager import WebSocketManager
# Factory pattern removed - using direct instantiation
from infrastructure.networking.websocket.strategies.subscription import SubscriptionStrategy
from infrastructure.networking.websocket.strategies.connection import ConnectionStrategy
from infrastructure.networking.websocket.strategies import MessageParser
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
# Factory removed
    'MessageType',
    'SubscriptionAction',
    'ConnectionContext',
    'ConnectionStrategy',
    'SubscriptionStrategy',
    'SubscriptionContext', 
    'ParsedMessage',
    'WebSocketManagerConfig',
    'PerformanceMetrics',
    'BaseWebsocketInterface',
    'MessageParser',
    'ConnectionState',
    'PrivateSpotWebsocket',
    'PublicSpotWebsocket',
    'PublicFuturesWebsocket',
    'PublicWebsocketHandlers',
    'PrivateWebsocketHandlers',
    'PrivateFuturesWebsocket'
]