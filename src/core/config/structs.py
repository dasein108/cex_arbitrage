from typing import Optional
from msgspec import Struct
from structs.exchange import ExchangeName

class ExchangeCredentials(Struct, frozen=True):
    """
    Type-safe exchange API credentials.

    Attributes:
        api_key: Exchange API key
        secret_key: Exchange secret key
    """
    api_key: str
    secret_key: str

    def is_configured(self) -> bool:
        """Check if both credentials are provided."""
        return bool(self.api_key) and bool(self.secret_key)

    def get_preview(self) -> str:
        """Get safe preview of credentials for logging."""
        if not self.api_key:
            return "Not configured"
        if len(self.api_key) > 8:
            return f"{self.api_key[:4]}...{self.api_key[-4:]}"
        return "***"


class NetworkConfig(Struct, frozen=True):
    """
    Network configuration settings.

    Attributes:
        request_timeout: HTTP request timeout in seconds
        connect_timeout: Connection timeout in seconds
        max_retries: Maximum number of retry attempts
        retry_delay: Delay between retries in seconds
    """
    request_timeout: float
    connect_timeout: float
    max_retries: int
    retry_delay: float


class RateLimitConfig(Struct, frozen=True):
    """
    Rate limiting configuration.

    Attributes:
        requests_per_second: Maximum requests per second
    """
    requests_per_second: int


class WebSocketConfig(Struct, frozen=True):
    """
    WebSocket configuration settings.

    Attributes:
        connect_timeout: WebSocket connection timeout
        heartbeat_interval: Heartbeat interval in seconds
        max_reconnect_attempts: Maximum reconnection attempts
        reconnect_delay: Delay between reconnection attempts
    """
    connect_timeout: float
    heartbeat_interval: float
    max_reconnect_attempts: int
    reconnect_delay: float


class ExchangeConfig(Struct, frozen=True):
    """
    Complete exchange configuration including credentials and settings.

    Attributes:
        name: Exchange name (e.g., 'mexc', 'gateio')
        credentials: API credentials
        base_url: REST API cex URL
        websocket_url: WebSocket URL
        testnet_base_url: Testnet REST API URL (optional)
        testnet_websocket_url: Testnet WebSocket URL (optional)
        network: Network configuration
        rate_limit: Rate limiting configuration
    """
    name: ExchangeName
    credentials: ExchangeCredentials
    base_url: str
    websocket_url: str
    testnet_base_url: Optional[str] = None
    testnet_websocket_url: Optional[str] = None
    network: Optional[NetworkConfig] = None
    rate_limit: Optional[RateLimitConfig] = None
    enabled: bool = True

    def has_credentials(self) -> bool:
        """Check if exchange has valid credentials."""
        return self.credentials.is_configured()
