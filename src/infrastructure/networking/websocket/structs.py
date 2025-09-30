import time
from dataclasses import dataclass
from enum import IntEnum, Enum
from typing import Dict, Optional, Any, List, Union

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


class PublicWebsocketChannelType(IntEnum):
    """Channel type classification."""
    ORDERBOOK = 1
    PUB_TRADE = 2
    BOOK_TICKER = 3
    TICKER = 4

class PrivateWebsocketChannelType(IntEnum):
    """Channel type classification."""
    EXECUTION = 5
    BALANCE = 6  # Fixed duplicate value
    ORDER = 7
    POSITION = 8

class ServiceWebsocketChannelType(IntEnum):
    """Service channel types."""
    HEARTBEAT = 999

class WebsocketChannelType(IntEnum):
    """Unified channel type classification."""
    # Public channels
    ORDERBOOK = PublicWebsocketChannelType.ORDERBOOK.value
    PUB_TRADE = PublicWebsocketChannelType.PUB_TRADE.value
    BOOK_TICKER = PublicWebsocketChannelType.BOOK_TICKER.value
    TICKER = PublicWebsocketChannelType.TICKER.value

    # Private channels
    EXECUTION = PrivateWebsocketChannelType.EXECUTION.value
    BALANCE = PrivateWebsocketChannelType.BALANCE.value
    ORDER = PrivateWebsocketChannelType.ORDER.value
    POSITION = PrivateWebsocketChannelType.POSITION.value
    HEARTBEAT = ServiceWebsocketChannelType.HEARTBEAT.value


class MessageType(IntEnum):
    """Message type classification for fast routing."""
    # Copy channel values
    ORDERBOOK = PublicWebsocketChannelType.ORDERBOOK.value
    TRADES = PublicWebsocketChannelType.PUB_TRADE.value
    BOOK_TICKER = PublicWebsocketChannelType.BOOK_TICKER.value
    TICKER = PublicWebsocketChannelType.TICKER.value
    # Additional message types
    TRADE = PrivateWebsocketChannelType.EXECUTION.value
    BALANCE = PrivateWebsocketChannelType.BALANCE.value
    ORDER = PrivateWebsocketChannelType.ORDER.value
    POSITION = PrivateWebsocketChannelType.POSITION.value
    SUBSCRIPTION_CONFIRM = 0
    HEARTBEAT = 999
    ERROR = -1
    SUBSCRIPTION_ERROR = -2
    OTHER = 888  # For valid but specialized data types (funding rates, mark prices, etc.)
    UNKNOWN = -999


class SubscriptionAction(IntEnum):
    """WebSocket subscription actions."""
    SUBSCRIBE = 1
    UNSUBSCRIBE = 2


@dataclass(frozen=True)
class ConnectionContext:
    """Connection configuration for WebSocket strategies."""
    url: str
    headers: Dict[str, str]
    auth_required: bool = False
    auth_params: Optional[Dict[str, Any]] = None
    ping_interval: float = 30
    ping_timeout: float = 10
    max_reconnect_attempts: int = 10
    reconnect_delay: float = 1.0
    ping_message: Optional[str] = None


@dataclass(frozen=True)
class SubscriptionContext:
    """Subscription configuration for specific symbols."""
    channels: List[str]
    parameters: Dict[str, Any] = None
    subscription_id: Optional[str] = None


@dataclass
class ParsedMessage:
    """Parsed WebSocket message with routing information."""
    message_type: MessageType
    symbol: Optional[Any] = None  # Symbol type from exchanges.structs.common
    channel: Optional[str] = None
    data: Optional[Any] = None
    timestamp: float = 0.0
    raw_data: Optional[Union[Dict[str, Any], List[Any]]] = None

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.perf_counter()


@dataclass
class WebSocketManagerConfig:
    """Configuration for WebSocket manager."""
    max_reconnect_attempts: int = 10
    reconnect_delay: float = 1.0
    message_timeout: float = 30.0
    enable_performance_tracking: bool = True
    max_pending_messages: int = 1000
    batch_processing_enabled: bool = True
    batch_size: int = 100


@dataclass
class PerformanceMetrics:
    """HFT performance tracking metrics."""
    messages_processed: int = 0
    messages_per_second: float = 0.0
    avg_processing_time_ms: float = 0.0
    max_processing_time_ms: float = 0.0
    last_message_time: float = 0.0
    connection_uptime: float = 0.0
    reconnection_count: int = 0
    error_count: int = 0

    # HFT-specific metrics
    sub_1ms_messages: int = 0  # Messages processed under 1ms
    orderbook_updates: int = 0
    latency_violations: int = 0  # Messages over 1ms

    def update_processing_time(self, processing_time_ms: float):
        """Update processing time metrics with HFT compliance tracking."""
        self.messages_processed += 1
        self.last_message_time = time.perf_counter()

        # Running average calculation
        if self.avg_processing_time_ms == 0:
            self.avg_processing_time_ms = processing_time_ms
        else:
            # Exponentially weighted moving average
            alpha = 0.1
            self.avg_processing_time_ms = (
                alpha * processing_time_ms +
                (1 - alpha) * self.avg_processing_time_ms
            )

        # Track maximum
        if processing_time_ms > self.max_processing_time_ms:
            self.max_processing_time_ms = processing_time_ms

        # HFT compliance tracking
        if processing_time_ms < 1.0:
            self.sub_1ms_messages += 1
        else:
            self.latency_violations += 1
