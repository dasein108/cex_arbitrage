"""
WebSocket Message Types

Standard message type enumeration used across all exchange WebSocket implementations
for consistent message routing and processing.
"""

from enum import Enum


class WebSocketMessageType(Enum):
    """Standard WebSocket message types across exchanges."""
    ORDERBOOK = "orderbook"
    TRADE = "trade"
    TICKER = "ticker"
    KLINE = "kline"
    ORDER_UPDATE = "order_update"
    BALANCE_UPDATE = "balance_update"
    POSITION_UPDATE = "position_update"
    PING = "ping"
    PONG = "pong"
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    ERROR = "error"
    UNKNOWN = "unknown"


__all__ = ['WebSocketMessageType']