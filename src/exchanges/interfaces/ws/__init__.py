"""
WebSocket components for HFT trading systems.

This module provides high-performance WebSocket infrastructure using strategy pattern
composition for exchange-agnostic trading implementations with separated domain architecture.
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

# New separated domain base interfaces
from .base_public_websocket import BasePublicWebsocket
from .base_private_websocket import BasePrivateWebsocket

# Legacy base interface (to be deprecated)
from .ws_base import BaseWebsocketInterface

# Concrete implementations with separated domain architecture
from .spot import PrivateSpotWebsocket, PublicSpotWebsocket
from .futures import PrivateFuturesWebsocket, PublicFuturesWebsocket

# Shared utilities for performance and configuration
from .performance_tracker import (
    WebSocketPerformanceTracker,
    PublicWebSocketPerformanceTracker,
    PrivateWebSocketPerformanceTracker
)
from .constants import HFTConstants, PerformanceConstants, ConnectionConstants
__all__ = [
    # Infrastructure components
    'WebSocketManager',
    'MessageType',
    'SubscriptionAction',
    'ConnectionContext',
    'ConnectionStrategy',
    'SubscriptionStrategy',
    'SubscriptionContext', 
    'ParsedMessage',
    'WebSocketManagerConfig',
    'PerformanceMetrics',
    'MessageParser',
    'ConnectionState',
    'PublicWebsocketHandlers',
    'PrivateWebsocketHandlers',
    
    # New separated domain base interfaces (preferred)
    'BasePublicWebsocket',
    'BasePrivateWebsocket',
    
    # Concrete implementations with separated domain architecture
    'PrivateSpotWebsocket',
    'PublicSpotWebsocket',
    'PrivateFuturesWebsocket',
    'PublicFuturesWebsocket',
    
    # Shared utilities for performance and configuration
    'WebSocketPerformanceTracker',
    'PublicWebSocketPerformanceTracker',
    'PrivateWebSocketPerformanceTracker',
    'HFTConstants',
    'PerformanceConstants',
    'ConnectionConstants',
    
    # Legacy base interface (to be deprecated)
    'BaseWebsocketInterface'
]