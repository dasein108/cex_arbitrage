"""
WebSocket Mixins Package

This package provides mixin classes that implement common WebSocket functionality
for composition-based handler architecture. Replaces inheritance-based approach
with flexible composition patterns.

Mixins Available:
- PublicWebSocketMixin: Common market data functionality
- PrivateWebSocketMixin: Common trading operations functionality

Architecture Benefits:
- Composition over inheritance
- Flexible handler construction
- Improved testability with isolated mixins
- Performance optimized for HFT requirements
"""

from .public_websocket_mixin import PublicWebSocketMixin
from .private_websocket_mixin import PrivateWebSocketMixin

__all__ = [
    "PublicWebSocketMixin",
    "PrivateWebSocketMixin",
]

# Module metadata
__version__ = "1.0.0"
__author__ = "CEX Arbitrage Engine"
__description__ = "WebSocket mixins for composition-based handler architecture"