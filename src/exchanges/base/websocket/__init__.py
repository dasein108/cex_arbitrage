"""
WebSocket components for HFT trading systems.

This module provides high-performance WebSocket infrastructure using strategy pattern
composition for exchange-agnostic trading implementations.
"""

from infrastructure.networking.websocket.ws_manager import WebSocketManager
from infrastructure.networking.websocket.strategies import (
    WebSocketStrategyFactory
)
from infrastructure.networking.websocket.strategies.subscription import SubscriptionStrategy
from infrastructure.networking.websocket.strategies.connection import ConnectionStrategy
from infrastructure.networking.websocket.strategies import MessageParser
from infrastructure.networking.websocket.structs import (
    MessageType, SubscriptionAction, ConnectionContext, 
    SubscriptionContext, ParsedMessage, WebSocketManagerConfig,
    PerformanceMetrics, ConnectionState
)

from .ws_base import BaseExchangeWebsocketInterface
from exchanges.base.websocket.spot.base_ws_private import BaseExchangePrivateWebsocketInterface
from exchanges.base.websocket.spot.base_ws_public import BaseExchangePublicWebsocketInterface
from .base_ws_public_futures import BaseWebsocketPublicFutures
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
    'BaseWebsocketPublicFutures'
]