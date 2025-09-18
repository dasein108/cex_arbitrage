from typing import Optional, Dict, Any
from msgspec import Struct
import msgspec
from structs.common import ExchangeName, ExchangeCredentials


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
    
    def validate(self) -> None:
        """Validate network configuration."""
        if self.request_timeout <= 0:
            raise ValueError("request_timeout must be positive")
        if self.connect_timeout <= 0:
            raise ValueError("connect_timeout must be positive")
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if self.retry_delay < 0:
            raise ValueError("retry_delay cannot be negative")


class RateLimitConfig(Struct, frozen=True):
    """
    Rate limiting configuration.

    Attributes:
        requests_per_second: Maximum requests per second
    """
    requests_per_second: int
    
    def validate(self) -> None:
        """Validate rate limit configuration."""
        if self.requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")


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


class RestTransportConfig(Struct, frozen=True):
    """
    REST transport configuration for the new transport system.
    
    Consolidates transport settings, strategy selection, and performance targets
    into a single configuration structure used by RestTransportManager.
    
    Attributes:
        # Strategy Selection
        exchange_name: Exchange name for strategy selection
        is_private: Whether to use private API strategies (with auth)
        
        # Performance Targets
        max_latency_ms: Maximum acceptable latency in milliseconds
        target_throughput_rps: Target requests per second
        max_retry_attempts: Maximum retry attempts for failed requests
        
        # Connection Settings  
        connection_timeout_ms: Connection timeout in milliseconds
        read_timeout_ms: Read timeout in milliseconds
        max_concurrent_requests: Maximum concurrent requests
        
        # Rate Limiting
        requests_per_second: Maximum requests per second
        burst_capacity: Burst capacity for rate limiting
        
        # Advanced Settings
        enable_connection_pooling: Enable HTTP connection pooling
        enable_compression: Enable request/response compression
        user_agent: Custom user agent string
    """
    # Strategy Selection
    exchange_name: str
    is_private: bool = False
    
    # Performance Targets (HFT-optimized defaults)
    max_latency_ms: float = 50.0
    target_throughput_rps: float = 100.0
    max_retry_attempts: int = 3
    
    # Connection Settings
    connection_timeout_ms: float = 2000.0
    read_timeout_ms: float = 5000.0
    max_concurrent_requests: int = 10
    
    # Rate Limiting (conservative defaults)
    requests_per_second: float = 20.0
    burst_capacity: int = 50
    
    # Advanced Settings
    enable_connection_pooling: bool = True
    enable_compression: bool = True
    user_agent: str = "HFTArbitrageEngine/1.0"
    
    def validate(self) -> None:
        """Validate transport configuration."""
        if not self.exchange_name:
            raise ValueError("exchange_name is required")
        if self.max_latency_ms <= 0:
            raise ValueError("max_latency_ms must be positive")
        if self.target_throughput_rps <= 0:
            raise ValueError("target_throughput_rps must be positive")
        if self.connection_timeout_ms <= 0:
            raise ValueError("connection_timeout_ms must be positive")
        if self.read_timeout_ms <= 0:
            raise ValueError("read_timeout_ms must be positive")
        if self.requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        if self.burst_capacity <= 0:
            raise ValueError("burst_capacity must be positive")
    
    def get_timeout_seconds(self) -> float:
        """Get total timeout in seconds for compatibility."""
        return (self.connection_timeout_ms + self.read_timeout_ms) / 1000.0
    
    def create_strategy_kwargs(self) -> Dict[str, Any]:
        """Create kwargs for strategy constructors."""
        return {
            'max_latency_ms': self.max_latency_ms,
            'target_throughput_rps': self.target_throughput_rps,
            'connection_timeout_ms': self.connection_timeout_ms,
            'read_timeout_ms': self.read_timeout_ms,
            'requests_per_second': self.requests_per_second,
            'burst_capacity': self.burst_capacity,
            'user_agent': self.user_agent
        }


class ExchangeConfig(Struct, frozen=True):
    """
    Complete exchange configuration including credentials and settings.

    Attributes:
        name: Exchange name (e.g., 'mexc', 'gateio')
        credentials: API credentials
        base_url: REST API cex URL
        websocket_url: WebSocket URL
        network: Network configuration (legacy - use transport for new code)
        rate_limit: Rate limiting configuration (legacy - use transport for new code)
        websocket: WebSocket configuration
        transport: REST transport configuration (new transport system)
    """
    name: ExchangeName
    credentials: ExchangeCredentials
    base_url: str
    websocket_url: str
    network: Optional[NetworkConfig] = None
    rate_limit: Optional[RateLimitConfig] = None
    websocket: Optional[WebSocketConfig] = None
    transport: Optional[RestTransportConfig] = None
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
    
    def get_transport_config(self, is_private: bool = False) -> RestTransportConfig:
        """
        Get or create transport configuration for this exchange.
        
        Args:
            is_private: Whether to configure for private API operations
            
        Returns:
            RestTransportConfig with exchange-specific settings
        """
        if self.transport:
            # Create a new config with updated is_private flag
            import msgspec
            data = msgspec.structs.asdict(self.transport)
            data['is_private'] = is_private
            data['exchange_name'] = str(self.name)
            return RestTransportConfig(**data)
        
        # Create default transport config for this exchange
        exchange_defaults = self._get_exchange_transport_defaults()
        return RestTransportConfig(
            exchange_name=self.name,
            is_private=is_private,
            **exchange_defaults
        )
    
    def _get_exchange_transport_defaults(self) -> Dict[str, Any]:
        """Get exchange-specific transport defaults."""
        # Exchange-specific performance tuning
        if str(self.name).lower() == 'mexc':
            return {
                'max_latency_ms': 40.0,  # MEXC is faster
                'target_throughput_rps': 100.0,
                'requests_per_second': 20.0,
                'burst_capacity': 60,
                'connection_timeout_ms': 1500.0,
                'read_timeout_ms': 4000.0
            }
        elif str(self.name).lower() == 'gateio':
            return {
                'max_latency_ms': 60.0,  # Gate.io needs more conservative settings
                'target_throughput_rps': 50.0,
                'requests_per_second': 15.0,
                'burst_capacity': 40,
                'connection_timeout_ms': 3000.0,
                'read_timeout_ms': 8000.0
            }
        else:
            # Conservative defaults for unknown exchanges
            return {
                'max_latency_ms': 50.0,
                'target_throughput_rps': 75.0,
                'requests_per_second': 18.0,
                'burst_capacity': 50,
                'connection_timeout_ms': 2000.0,
                'read_timeout_ms': 5000.0
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
        if self.transport:
            self.transport.validate()
    
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
