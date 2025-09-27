# Network Configuration Specification

Complete specification for network and transport layer configuration supporting the CEX Arbitrage Engine's HFT requirements with separated domain architecture integration.

## Overview

The **Network Configuration** system provides comprehensive management for all network-related settings including HTTP timeouts, WebSocket connections, transport layer optimization, and performance tuning. Designed to support both public (market data) and private (trading) operations with sub-millisecond performance targets.

## Architecture

### Core Design Principles

1. **HFT Performance Optimization** - Network settings tuned for sub-50ms operation targets
2. **Separated Domain Support** - Different network configurations for public vs private operations
3. **Transport Layer Abstraction** - Modern transport system with strategy-based optimization
4. **Exchange-Specific Tuning** - Per-exchange network optimization based on exchange characteristics
5. **Comprehensive Validation** - Type-safe configuration with performance requirement enforcement
6. **Flexible Configuration** - Global defaults with exchange-specific overrides

### Network Configuration Hierarchy
```
NetworkConfig (Global Defaults) → ExchangeConfig (Per-Exchange) → TransportConfig (Strategy-Specific)
      ↓                               ↓                               ↓
WebSocketConfig (Connection) → RestTransportConfig (HTTP) → Performance Optimization
```

## NetworkConfig Structure

### Core Network Configuration
```python
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
```

### HFT-Optimized Defaults
```yaml
# Global network configuration
network:
  request_timeout: 10.0     # 10 seconds maximum request time
  connect_timeout: 5.0      # 5 seconds connection timeout
  max_retries: 3           # Maximum 3 retry attempts
  retry_delay: 1.0         # 1 second between retries
```

### Network Configuration Parsing
```python
def parse_network_config(part_config: Dict[str, Any]) -> NetworkConfig:
    """
    Parse network configuration from dictionary with comprehensive validation.

    Args:
        part_config: Dictionary with network configuration keys

    Returns:
        NetworkConfig struct with parsed and validated values
        
    Raises:
        ConfigurationError: If configuration values are invalid
    """
    try:
        return NetworkConfig(
            request_timeout=safe_get_config_value(part_config, 'request_timeout', 10.0, float, 'network'),
            connect_timeout=safe_get_config_value(part_config, 'connect_timeout', 5.0, float, 'network'),
            max_retries=safe_get_config_value(part_config, 'max_retries', 3, int, 'network'),
            retry_delay=safe_get_config_value(part_config, 'retry_delay', 1.0, float, 'network')
        )
    except Exception as e:
        raise ConfigurationError(f"Failed to parse network configuration: {e}", "network") from e
```

## WebSocketConfig Structure

### Comprehensive WebSocket Configuration
```python
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
    heartbeat_interval: Optional[float] = 30.0
    
    # Optimization settings
    enable_compression: bool = True
    text_encoding: str = "utf-8"

    @property
    def has_heartbeat(self) -> bool:
        """Check if heartbeat is enabled."""
        return self.heartbeat_interval is not None and self.heartbeat_interval > 0

    def with_url(self, new_url: str) -> "WebSocketConfig":
        """Create a new config instance with updated URL in case of dynamic url."""
        data = msgspec.structs.asdict(self)
        data['url'] = new_url
        return WebSocketConfig(**data)
```

### WebSocket Configuration Examples
```yaml
# Global WebSocket template
ws:
  connect_timeout: 10.0
  ping_interval: 20.0
  ping_timeout: 10.0
  close_timeout: 5.0
  max_reconnect_attempts: 10
  reconnect_delay: 1.0
  reconnect_backoff: 2.0
  max_reconnect_delay: 60.0
  max_message_size: 1048576  # 1MB
  max_queue_size: 1000
  heartbeat_interval: 30.0
  enable_compression: true
  text_encoding: "utf-8"

# Exchange-specific WebSocket override
exchanges:
  mexc_spot:
    websocket_config:
      connect_timeout: 8.0      # Faster connection for MEXC
      ping_interval: 15.0       # More frequent pings
      max_queue_size: 2000      # Larger queue for high volume
```

### WebSocket Configuration Parsing
```python
def parse_websocket_config(part_config: Dict[str, Any], websocket_url: str) -> WebSocketConfig:
    """
    Parse WebSocket configuration from dictionary with URL injection and validation.

    Args:
        part_config: Dictionary with WebSocket configuration keys
        websocket_url: WebSocket URL from exchange configuration

    Returns:
        WebSocketConfig struct with parsed, validated values and injected URL
        
    Raises:
        ConfigurationError: If configuration values are invalid
    """
    try:
        # Validate WebSocket URL
        if not websocket_url or not isinstance(websocket_url, str):
            raise ConfigurationError(
                f"Invalid WebSocket URL: {websocket_url}",
                "websocket_url"
            )
        if not (websocket_url.startswith('ws://') or websocket_url.startswith('wss://')):
            raise ConfigurationError(
                f"WebSocket URL must start with ws:// or wss://, got: {websocket_url}",
                "websocket_url"
            )
        
        return WebSocketConfig(
            # Injected URL from exchange config
            url=websocket_url,
            
            # Connection settings with validation
            connect_timeout=safe_get_config_value(part_config, 'connect_timeout', 10.0, float, 'ws'),
            ping_interval=safe_get_config_value(part_config, 'ping_interval', 20.0, float, 'ws'),
            ping_timeout=safe_get_config_value(part_config, 'ping_timeout', 10.0, float, 'ws'),
            close_timeout=safe_get_config_value(part_config, 'close_timeout', 5.0, float, 'ws'),
            
            # Reconnection settings with validation
            max_reconnect_attempts=safe_get_config_value(part_config, 'max_reconnect_attempts', 10, int, 'ws'),
            reconnect_delay=safe_get_config_value(part_config, 'reconnect_delay', 1.0, float, 'ws'),
            reconnect_backoff=safe_get_config_value(part_config, 'reconnect_backoff', 2.0, float, 'ws'),
            max_reconnect_delay=safe_get_config_value(part_config, 'max_reconnect_delay', 60.0, float, 'ws'),
            
            # Performance settings with validation
            max_message_size=safe_get_config_value(part_config, 'max_message_size', 1048576, int, 'ws'),  # 1MB
            max_queue_size=safe_get_config_value(part_config, 'max_queue_size', 1000, int, 'ws'),
            heartbeat_interval=safe_get_config_value(part_config, 'heartbeat_interval', 30.0, float, 'ws'),
            
            # Optimization settings with validation
            enable_compression=safe_get_config_value(part_config, 'enable_compression', True, bool, 'ws'),
            text_encoding=safe_get_config_value(part_config, 'text_encoding', 'utf-8', str, 'ws')
        )
    except Exception as e:
        raise ConfigurationError(f"Failed to parse WebSocket configuration: {e}", "ws") from e
```

## RestTransportConfig Structure

### Modern Transport System Configuration
```python
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
```

### Transport Configuration Examples
```yaml
# Global transport defaults
transport:
  max_latency_ms: 50.0
  target_throughput_rps: 100.0
  max_retry_attempts: 3
  connection_timeout_ms: 2000.0
  read_timeout_ms: 5000.0
  max_concurrent_requests: 10
  requests_per_second: 20.0
  burst_capacity: 50
  enable_connection_pooling: true
  enable_compression: true
  user_agent: "HFTArbitrageEngine/1.0"

# Exchange-specific transport tuning
exchanges:
  mexc_spot:
    transport:
      max_latency_ms: 40.0      # MEXC is faster
      target_throughput_rps: 120.0
      requests_per_second: 25.0
      burst_capacity: 60
      connection_timeout_ms: 1500.0
      read_timeout_ms: 4000.0
      
  gateio_spot:
    transport:
      max_latency_ms: 60.0      # Gate.io needs more conservative settings
      target_throughput_rps: 80.0
      requests_per_second: 15.0
      burst_capacity: 40
      connection_timeout_ms: 3000.0
      read_timeout_ms: 8000.0
```

### Transport Configuration Parsing
```python
def parse_transport_config(part_config: Dict[str, Any], exchange_name: str, is_private: bool = False) -> RestTransportConfig:
    """
    Parse REST transport configuration from dictionary with validation.

    Args:
        part_config: Dictionary with transport configuration keys
        exchange_name: Exchange name for strategy selection
        is_private: Whether this is for private API operations

    Returns:
        RestTransportConfig struct with parsed and validated values
        
    Raises:
        ConfigurationError: If configuration values are invalid
    """
    try:
        return RestTransportConfig(
            # Strategy Selection
            exchange_name=exchange_name,
            is_private=is_private,
            
            # Performance Targets
            max_latency_ms=safe_get_config_value(part_config, 'max_latency_ms', 50.0, float, 'transport'),
            target_throughput_rps=safe_get_config_value(part_config, 'target_throughput_rps', 100.0, float, 'transport'),
            max_retry_attempts=safe_get_config_value(part_config, 'max_retry_attempts', 3, int, 'transport'),
            
            # Connection Settings
            connection_timeout_ms=safe_get_config_value(part_config, 'connection_timeout_ms', 2000.0, float, 'transport'),
            read_timeout_ms=safe_get_config_value(part_config, 'read_timeout_ms', 5000.0, float, 'transport'),
            max_concurrent_requests=safe_get_config_value(part_config, 'max_concurrent_requests', 10, int, 'transport'),
            
            # Rate Limiting
            requests_per_second=safe_get_config_value(part_config, 'requests_per_second', 20.0, float, 'transport'),
            burst_capacity=safe_get_config_value(part_config, 'burst_capacity', 50, int, 'transport'),
            
            # Advanced Settings
            enable_connection_pooling=safe_get_config_value(part_config, 'enable_connection_pooling', True, bool, 'transport'),
            enable_compression=safe_get_config_value(part_config, 'enable_compression', True, bool, 'transport'),
            user_agent=safe_get_config_value(part_config, 'user_agent', "HFTArbitrageEngine/1.0", str, 'transport')
        )
    except Exception as e:
        raise ConfigurationError(f"Failed to parse transport configuration for {exchange_name}: {e}", f"{exchange_name}.transport") from e
```

## RateLimitConfig Structure

### Rate Limiting Configuration
```python
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
```

### Rate Limiting Configuration Parsing
```python
def parse_rate_limit_config(part_config: Dict[str, Any]) -> RateLimitConfig:
    """
    Parse rate limiting configuration from dictionary with validation.

    Args:
        part_config: Dictionary with rate limiting configuration keys

    Returns:
        RateLimitConfig struct with parsed and validated values
        
    Raises:
        ConfigurationError: If configuration values are invalid
    """
    try:
        requests_per_second = safe_get_config_value(part_config, 'requests_per_second', 15, int, 'rate_limiting')
        
        # HFT validation: Ensure reasonable rate limits
        if requests_per_second <= 0:
            raise ConfigurationError(
                f"requests_per_second must be positive, got: {requests_per_second}",
                "rate_limiting.requests_per_second"
            )
        if requests_per_second > 1000:  # Reasonable upper bound
            raise ConfigurationError(
                f"requests_per_second exceeds reasonable limit (1000), got: {requests_per_second}",
                "rate_limiting.requests_per_second"
            )
            
        return RateLimitConfig(requests_per_second=requests_per_second)
    except Exception as e:
        raise ConfigurationError(f"Failed to parse rate limiting configuration: {e}", "rate_limiting") from e
```

## Exchange-Specific Network Optimization

### Performance Tuning by Exchange

#### MEXC Optimization
```python
def get_mexc_network_defaults() -> Dict[str, Any]:
    """Get MEXC-specific network optimization."""
    return {
        'network': {
            'request_timeout': 8.0,      # MEXC is generally faster
            'connect_timeout': 3.0,
            'max_retries': 3,
            'retry_delay': 0.5
        },
        'transport': {
            'max_latency_ms': 40.0,      # MEXC target: 40ms
            'target_throughput_rps': 120.0,
            'requests_per_second': 25.0,
            'burst_capacity': 60,
            'connection_timeout_ms': 1500.0,
            'read_timeout_ms': 4000.0
        },
        'websocket': {
            'connect_timeout': 8.0,
            'ping_interval': 15.0,
            'max_queue_size': 2000       # Higher volume handling
        }
    }
```

#### Gate.io Optimization
```python
def get_gateio_network_defaults() -> Dict[str, Any]:
    """Get Gate.io-specific network optimization."""
    return {
        'network': {
            'request_timeout': 12.0,     # Gate.io needs more conservative settings
            'connect_timeout': 6.0,
            'max_retries': 3,
            'retry_delay': 1.5
        },
        'transport': {
            'max_latency_ms': 60.0,      # Gate.io target: 60ms
            'target_throughput_rps': 80.0,
            'requests_per_second': 15.0,
            'burst_capacity': 40,
            'connection_timeout_ms': 3000.0,
            'read_timeout_ms': 8000.0
        },
        'websocket': {
            'connect_timeout': 12.0,
            'ping_interval': 25.0,
            'max_reconnect_attempts': 15  # More aggressive reconnection
        }
    }
```

### Dynamic Network Optimization
```python
class NetworkConfigOptimizer:
    """Optimizes network configuration based on exchange characteristics."""
    
    def __init__(self, base_config: NetworkConfig):
        self.base_config = base_config
        self.exchange_profiles = {
            'mexc': self._get_mexc_profile(),
            'gateio': self._get_gateio_profile(),
            'binance': self._get_binance_profile()
        }
    
    def optimize_for_exchange(self, exchange_name: str, is_private: bool = False) -> Dict[str, Any]:
        """Generate optimized network configuration for specific exchange."""
        profile = self.exchange_profiles.get(exchange_name.lower(), self._get_default_profile())
        
        # Apply private API optimizations
        if is_private:
            profile = self._apply_private_optimizations(profile)
        
        return profile
    
    def _apply_private_optimizations(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """Apply optimizations specific to private API operations."""
        # Private APIs typically need faster timeouts for trading
        if 'transport' in profile:
            profile['transport']['max_latency_ms'] *= 0.8  # 20% faster for trading
            profile['transport']['connection_timeout_ms'] *= 0.7  # Faster connection
        
        return profile
```

## Separated Domain Architecture Support

### Public Domain Network Configuration
```python
def get_public_domain_network_config(exchange_config: ExchangeConfig) -> Dict[str, Any]:
    """
    Get network configuration optimized for public domain operations.
    
    Public domain focuses on:
    - Market data streaming (WebSocket optimization)
    - Symbol information retrieval
    - Orderbook and trade data
    """
    return {
        'websocket': {
            'max_queue_size': 5000,      # Large queue for market data
            'max_message_size': 2097152, # 2MB for large orderbooks
            'enable_compression': True,   # Reduce bandwidth for market data
            'heartbeat_interval': 30.0
        },
        'transport': {
            'max_latency_ms': 100.0,     # More relaxed for market data
            'requests_per_second': 30.0, # Higher rate for symbol queries
            'burst_capacity': 100,
            'enable_compression': True
        }
    }
```

### Private Domain Network Configuration
```python
def get_private_domain_network_config(exchange_config: ExchangeConfig) -> Dict[str, Any]:
    """
    Get network configuration optimized for private domain operations.
    
    Private domain focuses on:
    - Order placement and management
    - Balance and position queries
    - Account management operations
    """
    return {
        'websocket': {
            'max_queue_size': 1000,      # Smaller queue for trading events
            'ping_interval': 15.0,       # More frequent pings for trading
            'max_reconnect_attempts': 20, # Aggressive reconnection for trading
            'heartbeat_interval': 20.0
        },
        'transport': {
            'max_latency_ms': 30.0,      # Strict latency for trading
            'requests_per_second': 20.0, # Conservative for trading APIs
            'burst_capacity': 40,
            'max_retry_attempts': 5,     # More retries for critical operations
            'enable_connection_pooling': True
        }
    }
```

## Complete Configuration Examples

### Production Network Configuration
```yaml
# Global network defaults
network:
  request_timeout: 10.0
  connect_timeout: 5.0
  max_retries: 3
  retry_delay: 1.0

# Global WebSocket template
ws:
  connect_timeout: 10.0
  ping_interval: 20.0
  ping_timeout: 10.0
  close_timeout: 5.0
  max_reconnect_attempts: 10
  reconnect_delay: 1.0
  reconnect_backoff: 2.0
  max_reconnect_delay: 60.0
  max_message_size: 1048576
  max_queue_size: 1000
  heartbeat_interval: 30.0
  enable_compression: true
  text_encoding: "utf-8"

# Exchange-specific optimizations
exchanges:
  mexc_spot:
    base_url: "https://api.mexc.com"
    websocket_url: "wss://wbs-api.mexc.com/ws"
    
    # MEXC-specific network optimization
    network_config:
      request_timeout: 8.0
      connect_timeout: 3.0
      retry_delay: 0.5
    
    # MEXC-specific WebSocket optimization
    websocket_config:
      connect_timeout: 8.0
      ping_interval: 15.0
      max_queue_size: 2000
    
    # MEXC-specific transport optimization
    transport:
      max_latency_ms: 40.0
      target_throughput_rps: 120.0
      requests_per_second: 25.0
      burst_capacity: 60
      connection_timeout_ms: 1500.0
      read_timeout_ms: 4000.0
      
  gateio_spot:
    base_url: "https://api.gateio.ws/api/v4"
    websocket_url: "wss://api.gateio.ws/ws/v4/"
    
    # Gate.io-specific network optimization
    network_config:
      request_timeout: 12.0
      connect_timeout: 6.0
      retry_delay: 1.5
    
    # Gate.io-specific WebSocket optimization
    websocket_config:
      connect_timeout: 12.0
      ping_interval: 25.0
      max_reconnect_attempts: 15
    
    # Gate.io-specific transport optimization
    transport:
      max_latency_ms: 60.0
      target_throughput_rps: 80.0
      requests_per_second: 15.0
      burst_capacity: 40
      connection_timeout_ms: 3000.0
      read_timeout_ms: 8000.0
```

### Development Network Configuration
```yaml
# Development environment - more relaxed settings
network:
  request_timeout: 30.0      # Longer timeout for debugging
  connect_timeout: 10.0
  max_retries: 5             # More retries for development
  retry_delay: 2.0

ws:
  connect_timeout: 20.0      # Longer WebSocket timeouts
  ping_interval: 30.0
  max_reconnect_attempts: 20 # More reconnection attempts
  reconnect_delay: 2.0

# Development transport settings
transport:
  max_latency_ms: 200.0      # Relaxed latency for development
  target_throughput_rps: 50.0
  requests_per_second: 10.0  # Lower rate for development
  burst_capacity: 30
  connection_timeout_ms: 5000.0
  read_timeout_ms: 15000.0
```

## Usage Examples

### Basic Network Configuration Access
```python
from src.config.config_manager import get_config

# Get configuration instance
config = get_config()

# Network configuration
network_config = config.get_network_config()

# WebSocket configuration from exchange
mexc_config = config.get_exchange_config('mexc_spot')
websocket_config = mexc_config.websocket

# Transport configuration for private operations
transport_config = mexc_config.get_transport_config(is_private=True)
```

### Dynamic Configuration for Separated Domains
```python
def create_domain_specific_config(exchange_name: str, is_private: bool) -> Dict[str, Any]:
    """Create domain-specific network configuration."""
    config = get_config()
    exchange_config = config.get_exchange_config(exchange_name)
    
    if is_private:
        # Private domain: Trading operations
        return {
            'transport': exchange_config.get_transport_config(is_private=True),
            'websocket': exchange_config.websocket.with_url(exchange_config.websocket_url),
            'network': exchange_config.network
        }
    else:
        # Public domain: Market data operations
        return {
            'transport': exchange_config.get_transport_config(is_private=False),
            'websocket': exchange_config.websocket.with_url(exchange_config.websocket_url),
            'network': exchange_config.network
        }

# Usage
public_config = create_domain_specific_config('mexc_spot', is_private=False)
private_config = create_domain_specific_config('mexc_spot', is_private=True)
```

### Performance Monitoring Integration
```python
class NetworkPerformanceMonitor:
    """Monitor network performance against configuration thresholds."""
    
    def __init__(self, network_config: NetworkConfig, transport_config: RestTransportConfig):
        self.network_config = network_config
        self.transport_config = transport_config
    
    def validate_performance(self, metrics: NetworkMetrics) -> bool:
        """Validate network performance against configuration thresholds."""
        # Check latency against transport configuration
        if metrics.avg_latency_ms > self.transport_config.max_latency_ms:
            logger.warning(f"Network latency {metrics.avg_latency_ms}ms exceeds target {self.transport_config.max_latency_ms}ms")
            return False
        
        # Check throughput against transport configuration
        if metrics.requests_per_second > self.transport_config.requests_per_second:
            logger.warning(f"Request rate {metrics.requests_per_second} exceeds limit {self.transport_config.requests_per_second}")
            return False
        
        # Check timeout compliance
        if metrics.avg_request_time > self.network_config.request_timeout:
            logger.warning(f"Request time {metrics.avg_request_time}s exceeds timeout {self.network_config.request_timeout}s")
            return False
        
        return True
```

---

*This Network Configuration specification provides comprehensive management for all network and transport layer settings while supporting HFT performance requirements and separated domain architecture with exchange-specific optimization.*