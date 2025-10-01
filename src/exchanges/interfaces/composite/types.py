"""
Type definitions for composite exchange generic parameters.

This module provides type variables and constraints for the dependency injection
pattern used in composite exchanges, supporting both REST and WebSocket clients.
"""

from typing import TypeVar, Union

# Import base interfaces for type constraints
from exchanges.interfaces.rest import PublicSpotRestInterface, PrivateSpotRestInterface
from exchanges.interfaces.ws import PrivateBaseWebsocket, PublicBaseWebsocket


# Base type variables with minimal constraints
RestClientType = TypeVar('RestClientType')
WebSocketClientType = TypeVar('WebSocketClientType')

# Specific type variables for spot operations with proper bounds
PublicRestType = TypeVar('PublicRestType', bound=PublicSpotRestInterface)
PrivateRestType = TypeVar('PrivateRestType', bound=PrivateSpotRestInterface)
PublicWebsocketType = TypeVar('PublicWebsocketType', bound=PublicBaseWebsocket)
PrivateWebsocketType = TypeVar('PrivateWebsocketType', bound=PrivateBaseWebsocket)

# Union types for flexibility
AnyRestClient = Union[PublicSpotRestInterface, PrivateSpotRestInterface]
AnyWebSocketClient = Union[PublicWebsocketType, PrivateWebsocketType]

# Type aliases for common patterns
PublicCompositeClients = tuple[PublicRestType, PublicWebsocketType]
PrivateCompositeClients = tuple[PrivateRestType, PrivateWebsocketType]