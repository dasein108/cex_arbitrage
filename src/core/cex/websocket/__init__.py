"""
WebSocket components for HFT trading systems.

This module provides high-performance WebSocket infrastructure using strategy pattern
composition for exchange-agnostic trading implementations.
"""

from core.transport.websocket.ws_manager import WebSocketManager
from core.transport.websocket.strategies import (
    WebSocketStrategyFactory
)
from core.transport.websocket.strategies.subscription import SubscriptionStrategy
from core.transport.websocket.strategies.connection import ConnectionStrategy
from core.transport.websocket.strategies import MessageParser
from core.transport.websocket.structs import (
    MessageType, SubscriptionAction, ConnectionContext, 
    SubscriptionContext, ParsedMessage, WebSocketManagerConfig,
    PerformanceMetrics, ConnectionState
)

from .ws_base import BaseExchangeWebsocketInterface
from core.cex.websocket.spot.base_ws_private import BaseExchangePrivateWebsocketInterface
from core.cex.websocket.spot.base_ws_public import BaseExchangePublicWebsocketInterface

__all__ = [
    'WebSocketManager',
    'WebSocketStrategyFactory',
    'MessageType',
    'SubscriptionAction',
    'ConnectionContext',
    'ConnectionStrategy',
    'SubscriptionStrategy',
    'SubscriptionContext', 
    'ParsedMessage',
    'WebSocketManagerConfig',
    'PerformanceMetrics',
    'BaseExchangeWebsocketInterface',
    'MessageParser',
    'ConnectionState',
    'BaseExchangePrivateWebsocketInterface',
    'BaseExchangePublicWebsocketInterface',
]