from typing import Optional, Dict, Any
from msgspec import Struct
import msgspec
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
    Unified WebSocket configuration settings.

    Combines connection, performance, and reconnection settings
    for HFT-optimized WebSocket connections.

    Attributes:
        # Connection settings
        url: WebSocket URL (injected from exchange config)
        connect_timeout: WebSocket connection timeout in seconds
        ping_interval: Ping interval in seconds
        ping_timeout: Ping timeout in seconds
        close_timeout: Connection close timeout in seconds
        
        # Reconnection settings
        max_reconnect_attempts: Maximum reconnection attempts
        reconnect_delay: Base delay between reconnection attempts in seconds
        reconnect_backoff: Backoff multiplier for reconnection delays
        max_reconnect_delay: Maximum reconnection delay in seconds
        
        # Performance settings
        max_message_size: Maximum message size in bytes
        max_queue_size: Maximum message queue size
        heartbeat_interval: Heartbeat interval in seconds
        
        # Optimization settings
        enable_compression: Enable WebSocket compression
        text_encoding: Text encoding for messages
    """
    # Connection settings
    url: str
    connect_timeout: float = 10.0
    ping_interval: float = 20.0
    ping_timeout: float = 10.0
    close_timeout: float = 5.0
    
    # Reconnection settings
    max_reconnect_attempts: int = 10
    reconnect_delay: float = 1.0
    reconnect_backoff: float = 2.0
    max_reconnect_delay: float = 60.0
    
    # Performance settings
    max_message_size: int = 1048576  # 1MB
    max_queue_size: int = 1000
    heartbeat_interval: float = 30.0
    
    # Optimization settings
    enable_compression: bool = True
    text_encoding: str = "utf-8"

    def with_url(self, new_url: str) -> "WebSocketConfig":
        """Create a new config instance with updated URL in case of dynamic url."""
        data = msgspec.structs.asdict(self)
        data['url'] = new_url
        return WebSocketConfig(**data)


class ExchangeConfig(Struct, frozen=True):
    """
    Complete exchange configuration including credentials and settings.

    Attributes:
        name: Exchange name (e.g., 'mexc', 'gateio')
        credentials: API credentials
        base_url: REST API cex URL
        websocket_url: WebSocket URL
        network: Network configuration
        rate_limit: Rate limiting configuration
        websocket: WebSocket configuration
    """
    name: ExchangeName
    credentials: ExchangeCredentials
    base_url: str
    websocket_url: str
    network: Optional[NetworkConfig] = None
    rate_limit: Optional[RateLimitConfig] = None
    websocket: Optional[WebSocketConfig] = None
    enabled: bool = True

    def has_credentials(self) -> bool:
        """
        Check if exchange has valid credentials for private operations.
        
        Returns:
            True if exchange has valid API credentials
        """
        return self.credentials.is_configured()
    
    def is_public_only(self) -> bool:
        """
        Check if exchange is configured for public-only operations.
        
        Returns:
            True if exchange has no credentials (public-only mode)
        """
        return not self.has_credentials()
    
    def is_ready_for_trading(self) -> bool:
        """
        Check if exchange is ready for live trading operations.
        
        Returns:
            True if exchange is enabled and has valid credentials
        """
        return self.enabled and self.has_credentials()
    
    def get_capabilities(self) -> Dict[str, bool]:
        """
        Get exchange capabilities based on configuration.
        
        Returns:
            Dictionary of capability flags
        """
        return {
            "public_data": True,  # Always available
            "private_data": self.has_credentials(),
            "trading": self.is_ready_for_trading(),
            "websocket": bool(self.websocket_url),
            "rest_api": bool(self.base_url)
        }
    
    def validate(self) -> None:
        """
        Comprehensive validation of exchange configuration.
        
        Raises:
            ValueError: If configuration is invalid
        """
        # Validate URLs
        if not self.base_url or not isinstance(self.base_url, str):
            raise ValueError(f"Invalid base_url: {self.base_url}")
        if not (self.base_url.startswith('http://') or self.base_url.startswith('https://')):
            raise ValueError(f"base_url must start with http:// or https://: {self.base_url}")
            
        if not self.websocket_url or not isinstance(self.websocket_url, str):
            raise ValueError(f"Invalid websocket_url: {self.websocket_url}")
        if not (self.websocket_url.startswith('ws://') or self.websocket_url.startswith('wss://')):
            raise ValueError(f"websocket_url must start with ws:// or wss://: {self.websocket_url}")
        
        # Validate exchange name
        if not self.name or not isinstance(self.name, str):
            raise ValueError(f"Invalid exchange name: {self.name}")
        
        # Validate sub-components
        self.credentials.validate()
        if self.network:
            self.network.validate()
        if self.rate_limit:
            self.rate_limit.validate()
    
    def get_summary(self) -> str:
        """
        Get a human-readable summary of exchange configuration.
        
        Returns:
            Formatted configuration summary
        """
        capabilities = self.get_capabilities()
        enabled_caps = [cap for cap, enabled in capabilities.items() if enabled]
        
        return (
            f"Exchange: {self.name.upper()}\n"
            f"  Status: {'Enabled' if self.enabled else 'Disabled'}\n"
            f"  Mode: {'Trading' if self.is_ready_for_trading() else 'Public-only'}\n"
            f"  Capabilities: {', '.join(enabled_caps)}\n"
            f"  Credentials: {self.credentials.get_preview()}"
        )
