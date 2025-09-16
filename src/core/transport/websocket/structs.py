from enum import Enum


from typing import Optional
import msgspec


class ConnectionState(Enum):
    """WebSocket connection states"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"
    CLOSING = "closing"
    CLOSED = "closed"


class WebsocketConfig(msgspec.Struct):
    """Configuration for WebSocket connections optimized for trading"""
    # Connection settings
    name: str
    url: Optional[str] = None
    timeout: float = 30.0
    ping_interval: float = 20.0
    ping_timeout: float = 10.0
    close_timeout: float = 5.0

    # Reconnection settings
    max_reconnect_attempts: int = 10
    reconnect_delay: float = 1.0
    reconnect_backoff: float = 2.0
    max_reconnect_delay: float = 60.0

    # Performance settings
    max_message_size: int = 1024 * 1024  # 1MB
    max_queue_size: int = 1000
    heartbeat_interval: float = 30.0

    # Compression and encoding
    enable_compression: bool = True
    text_encoding: str = "utf-8"