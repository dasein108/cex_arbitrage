"""
Type definitions for composite exchange generic parameters.

This module provides type variables and constraints for the dependency injection
pattern used in composite exchanges, supporting both REST and WebSocket clients.
"""

from typing import TypeVar, Union, Optional

# Import base interfaces for type constraints
try:
    from exchanges.interfaces.rest.spot.rest_spot_public import PublicSpotRest
    from exchanges.interfaces.rest.spot.rest_spot_private import PrivateSpotRest
    from exchanges.interfaces.ws.spot.ws_spot_public import PublicSpotWebsocket
    from exchanges.interfaces.ws.spot.ws_spot_private import PrivateSpotWebsocket
except ImportError:
    # For type checking when interfaces may not be available
    PublicSpotRest = object
    PrivateSpotRest = object
    PublicSpotWebsocket = object
    PrivateSpotWebsocket = object

# Base type variables with minimal constraints
RestClientType = TypeVar('RestClientType')
WebSocketClientType = TypeVar('WebSocketClientType')

# Specific type variables for spot operations with proper bounds
PublicRestType = TypeVar('PublicRestType', bound=PublicSpotRest)
PrivateRestType = TypeVar('PrivateRestType', bound=PrivateSpotRest)
PublicWebSocketType = TypeVar('PublicWebSocketType', bound=PublicSpotWebsocket)
PrivateWebSocketType = TypeVar('PrivateWebSocketType', bound=PrivateSpotWebsocket)

# Union types for flexibility
AnyRestClient = Union[PublicSpotRest, PrivateSpotRest]
AnyWebSocketClient = Union[PublicSpotWebsocket, PrivateSpotWebsocket]

# Type aliases for common patterns
PublicCompositeClients = tuple[PublicRestType, Optional[PublicWebSocketType]]
PrivateCompositeClients = tuple[PrivateRestType, Optional[PrivateWebSocketType]]