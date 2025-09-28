"""
Futures WebSocket interfaces for HFT trading systems.

This module provides high-performance WebSocket infrastructure for futures trading
with separated domain architecture and sub-millisecond performance requirements.
"""

from .ws_private_futures import PrivateFuturesWebsocket
from .ws_public_futures import PublicFuturesWebsocket

__all__ = [
    'PrivateFuturesWebsocket',
    'PublicFuturesWebsocket'
]