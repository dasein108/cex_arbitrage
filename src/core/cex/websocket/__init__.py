"""
WebSocket components for HFT trading systems.

This module provides high-performance WebSocket infrastructure using strategy pattern
composition for exchange-agnostic trading implementations.
"""

from .ws_manager import WebSocketManager
from .strategies import (
    ConnectionStrategy, SubscriptionStrategy, WebSocketStrategySet, WebSocketStrategyFactory
)
from .message_parser import MessageParser
from .structs import (
    MessageType, SubscriptionAction, ConnectionContext, 
    SubscriptionContext, ParsedMessage, WebSocketManagerConfig,
    PerformanceMetrics, ConnectionState
)

from .base_ws import BaseExchangeWebsocketInterface

__all__ = [
    'WebSocketManager',
    'ConnectionStrategy',
    'SubscriptionStrategy',
    'WebSocketStrategySet',
    'WebSocketStrategyFactory',
    'MessageType',
    'SubscriptionAction',
    'ConnectionContext',
    'SubscriptionContext', 
    'ParsedMessage',
    'WebSocketManagerConfig',
    'PerformanceMetrics',
    'BaseExchangeWebsocketInterface',
    'MessageParser',
    'ConnectionState'
]