from msgspec import Struct


class WebSocketConnectionSettings(Struct, frozen=True):
    """WebSocket connection settings for an exchange."""
    ping_interval: int
    ping_timeout: int
    max_queue_size: int
    max_message_size: int
    write_limit: int


class RestConnectionSettings(Struct, frozen=True):
    """REST connection settings for an exchange."""
    recv_window: int
    timeout: int
    max_retries: int


class ReconnectionSettings(Struct, frozen=True):
    """Reconnection policy settings for an exchange."""
    max_attempts: int
    initial_delay: float
    backoff_factor: float
    max_delay: float
    reset_on_1005: bool
