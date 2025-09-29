"""
Type definitions for composite exchange generic parameters.

This module provides type variables and constraints for the dependency injection
pattern used in composite exchanges, supporting both REST and WebSocket clients.
"""

from typing import TypeVar, Union

# Import base interfaces for type constraints
from exchanges.interfaces.rest import PublicSpotRest, PrivateSpotRest
from exchanges.interfaces.ws import PrivateBaseWebsocket, PublicBaseWebsocket


# Base type variables with minimal constraints
RestClientType = TypeVar('RestClientType')
WebSocketClientType = TypeVar('WebSocketClientType')

# Specific type variables for spot operations with proper bounds
PublicRestType = TypeVar('PublicRestType', bound=PublicSpotRest)
PrivateRestType = TypeVar('PrivateRestType', bound=PrivateSpotRest)
PublicWebsocketType = TypeVar('PublicWebsocketType', bound=PublicBaseWebsocket)
PrivateWebsocketType = TypeVar('PrivateWebsocketType', bound=PrivateBaseWebsocket)

# Union types for flexibility
AnyRestClient = Union[PublicSpotRest, PrivateSpotRest]
AnyWebSocketClient = Union[PublicWebsocketType, PrivateWebsocketType]

# Type aliases for common patterns
PublicCompositeClients = tuple[PublicRestType, PublicWebsocketType]
PrivateCompositeClients = tuple[PrivateRestType, PrivateWebsocketType]