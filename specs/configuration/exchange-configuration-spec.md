# Exchange Configuration Specification

Complete specification for the ExchangeConfigManager that handles exchange-specific configuration with support for separated domain architecture and dynamic exchange scaling.

## Overview

The **ExchangeConfigManager** provides specialized configuration management for exchange settings including API endpoints, credentials, WebSocket connections, rate limiting, and transport configuration. Designed to support the separated domain architecture where public (market data) and private (trading) operations are completely isolated.

## Architecture

### Core Design Principles

1. **Unified Dictionary Pattern** - Single `exchanges:` configuration supports all exchange types
2. **Dynamic Exchange Support** - New exchanges require only YAML configuration, no code changes
3. **Separated Domain Support** - Configuration supports both public and private operations
4. **Environment Variable Integration** - Secure credential management via substitution
5. **HFT Performance Optimization** - Exchange-specific transport tuning
6. **Comprehensive Validation** - Type-safe access with error handling

### Manager Integration
```
HftConfig → ExchangeConfigManager → ExchangeConfig Structs → Factory Creation
    ↓              ↓                       ↓                    ↓
Network Config → Credential Management → Transport Config → Domain Separation
```

## ExchangeConfigManager Class Specification

### Class Definition
```python
class ExchangeConfigManager:
    """
    Manages exchange-specific configuration settings.
    
    Provides unified configuration management for all exchanges with support for:
    - Dynamic exchange creation from YAML configuration
    - Separated domain architecture (public/private operations)
    - Environment variable-based credential management
    - Exchange-specific performance optimization
    - Comprehensive validation and error handling
    """
    
    def __init__(self, config_data: Dict[str, Any], network_config: NetworkConfig, websocket_template: Dict[str, Any]):
        self.config_data = config_data
        self.network_config = network_config
        self.websocket_template = websocket_template
        self._exchange_configs: Optional[Dict[str, ExchangeConfig]] = None
        self._logger = logging.getLogger(__name__)
```

### Configuration Building

#### Exchange Configuration Parsing
```python
def _build_exchange_configs(self) -> Dict[str, ExchangeConfig]:
    """Build exchange configurations from config data."""
    exchanges_data = self.config_data.get('exchanges', {})
    configs = {}
    
    if not exchanges_data:
        raise ConfigurationError(
            "No exchanges configured. At least one exchange must be configured.",
            "exchanges"
        )
    
    for exchange_name, exchange_data in exchanges_data.items():
        try:
            config = self._build_single_exchange_config(exchange_name, exchange_data)
            if config:
                # Store config with the original config name (mexc, gateio) for backward compatibility
                configs[exchange_name.lower()] = config
        except Exception as e:
            raise ConfigurationError(
                f"Failed to configure exchange '{exchange_name}': {e}",
                f"exchanges.{exchange_name}"
            ) from e
    
    return configs

def _build_single_exchange_config(self, exchange_name: str, data: Dict[str, Any]) -> ExchangeConfig:
    """Build configuration for single exchange. Trust config structure, fail fast if wrong."""
    # Trust config structure, let KeyError fail if missing required fields
    credentials = self._extract_credentials_from_config(data)
    
    # Use exchange-specific network config or global fallback
    network_config = data.get('network_config', self.network_config)
    if isinstance(network_config, dict):
        network_config = self._parse_network_config(network_config)
        
    # Extract rate limiting from transport section  
    if 'transport' in data and 'requests_per_second' in data['transport']:
        requests_per_second = data['transport']['requests_per_second']
        rate_limit = self._parse_rate_limit_config({'requests_per_second': requests_per_second})
    else:
        # Fallback to default rate limiting if not specified in transport
        rate_limit = self._parse_rate_limit_config({'requests_per_second': 10.0})

    # Use exchange-specific websocket config or global template
    websocket_config_data = data.get('websocket_config', self.websocket_template)
    websocket_config = self._parse_websocket_config(websocket_config_data, data['websocket_url'])

    # Parse transport config if present
    transport_config = None
    if 'transport' in data:
        transport_config = self._parse_transport_config(data['transport'], exchange_name, is_private=False)

    exchange_config = ExchangeConfig(
        name=ExchangeName(exchange_name.upper()),
        credentials=credentials,
        base_url=data['base_url'],
        websocket_url=data['websocket_url'],
        enabled=data.get('enabled', True),
        network=network_config,
        rate_limit=rate_limit,
        websocket=websocket_config,
        transport=transport_config
    )

    self._logger.debug(f"Configured exchange: {exchange_name} (enabled: {exchange_config.enabled})")
    return exchange_config
```

### Credential Management

#### Environment Variable-Based Credentials
```python
def _extract_credentials_from_config(self, data: Dict[str, Any]) -> ExchangeCredentials:
    """
    Extract credentials from exchange configuration data.
    
    This reads from the YAML config data which has already been processed
    with environment variable substitution (e.g., "${MEXC_API_KEY}" -> actual value).
    
    Args:
        data: Exchange configuration data from YAML
        
    Returns:
        ExchangeCredentials with api_key and secret_key (empty strings if not found)
    """
    api_key = data.get('api_key', '')
    secret_key = data.get('secret_key', '')
    
    # Ensure we have strings (environment substitution might return None)
    if api_key is None:
        api_key = ''
    if secret_key is None:
        secret_key = ''
        
    return ExchangeCredentials(api_key=str(api_key), secret_key=str(secret_key))
```

### Configuration Parsing Methods

#### Network Configuration Parsing
```python
def _parse_network_config(self, part_config: Dict[str, Any]) -> NetworkConfig:
    """Parse network configuration from dictionary with comprehensive validation."""
    try:
        return NetworkConfig(
            request_timeout=self._safe_get_config_value(part_config, 'request_timeout', 10.0, float, 'network'),
            connect_timeout=self._safe_get_config_value(part_config, 'connect_timeout', 5.0, float, 'network'),
            max_retries=self._safe_get_config_value(part_config, 'max_retries', 3, int, 'network'),
            retry_delay=self._safe_get_config_value(part_config, 'retry_delay', 1.0, float, 'network')
        )
    except Exception as e:
        raise ConfigurationError(f"Failed to parse network configuration: {e}", "network") from e
```

#### Rate Limiting Configuration
```python
def _parse_rate_limit_config(self, part_config: Dict[str, Any]) -> RateLimitConfig:
    """Parse rate limiting configuration. Trust config values, validate HFT requirements."""
    requests_per_second = int(part_config['requests_per_second'])
    
    # Enforce HFT requirements - fail fast
    if requests_per_second <= 0:
        raise ValueError(f"requests_per_second must be positive, got: {requests_per_second}")
    if requests_per_second > 1000:
        raise ValueError(f"requests_per_second {requests_per_second} > 1000 violates HFT requirements")
        
    return RateLimitConfig(requests_per_second=requests_per_second)
```

#### WebSocket Configuration Parsing
```python
def _parse_websocket_config(self, part_config: Dict[str, Any], websocket_url: str) -> WebSocketConfig:
    """Parse WebSocket configuration. Allow defaults for optional fields, fail on URL format."""
    # Basic URL format validation - trust config provides valid URLs
    if not (websocket_url.startswith('ws://') or websocket_url.startswith('wss://')):
        raise ValueError(f"WebSocket URL must start with ws:// or wss://, got: {websocket_url}")
    
    return WebSocketConfig(
        url=websocket_url,
        connect_timeout=float(part_config.get('connect_timeout', 10.0)),
        ping_interval=float(part_config.get('ping_interval', 20.0)),
        ping_timeout=float(part_config.get('ping_timeout', 10.0)),
        close_timeout=float(part_config.get('close_timeout', 5.0)),
        max_reconnect_attempts=int(part_config.get('max_reconnect_attempts', 10)),
        reconnect_delay=float(part_config.get('reconnect_delay', 1.0)),
        reconnect_backoff=float(part_config.get('reconnect_backoff', 2.0)),
        max_reconnect_delay=float(part_config.get('max_reconnect_delay', 60.0)),
        max_message_size=int(part_config.get('max_message_size', 1048576)),
        max_queue_size=int(part_config.get('max_queue_size', 1000)),
        heartbeat_interval=float(part_config.get('heartbeat_interval', 30.0)),
        enable_compression=bool(part_config.get('enable_compression', True)),
        text_encoding=part_config.get('text_encoding', 'utf-8')
    )
```

#### Transport Configuration Parsing
```python
def _parse_transport_config(self, part_config: Dict[str, Any], exchange_name: str, is_private: bool = False) -> RestTransportConfig:
    """Parse REST transport configuration from dictionary with validation."""
    try:
        return RestTransportConfig(
            # Strategy Selection
            exchange_name=exchange_name,
            is_private=is_private,
            
            # Performance Targets
            max_latency_ms=self._safe_get_config_value(part_config, 'max_latency_ms', 50.0, float, 'transport'),
            target_throughput_rps=self._safe_get_config_value(part_config, 'target_throughput_rps', 100.0, float, 'transport'),
            max_retry_attempts=self._safe_get_config_value(part_config, 'max_retry_attempts', 3, int, 'transport'),
            
            # Connection Settings
            connection_timeout_ms=self._safe_get_config_value(part_config, 'connection_timeout_ms', 2000.0, float, 'transport'),
            read_timeout_ms=self._safe_get_config_value(part_config, 'read_timeout_ms', 5000.0, float, 'transport'),
            max_concurrent_requests=self._safe_get_config_value(part_config, 'max_concurrent_requests', 10, int, 'transport'),
            
            # Rate Limiting
            requests_per_second=self._safe_get_config_value(part_config, 'requests_per_second', 20.0, float, 'transport'),
            burst_capacity=self._safe_get_config_value(part_config, 'burst_capacity', 50, int, 'transport'),
            
            # Advanced Settings
            enable_connection_pooling=self._safe_get_config_value(part_config, 'enable_connection_pooling', True, bool, 'transport'),
            enable_compression=self._safe_get_config_value(part_config, 'enable_compression', True, bool, 'transport'),
            user_agent=self._safe_get_config_value(part_config, 'user_agent', "HFTArbitrageEngine/1.0", str, 'transport')
        )
    except Exception as e:
        raise ConfigurationError(f"Failed to parse transport configuration for {exchange_name}: {e}", f"{exchange_name}.transport") from e
```

## Public API Methods

### Configuration Access
```python
def get_exchange_configs(self) -> Dict[str, ExchangeConfig]:
    """
    Get all exchange configurations.
    
    Returns:
        Dictionary mapping exchange names to ExchangeConfig structs
    """
    if self._exchange_configs is None:
        self._exchange_configs = self._build_exchange_configs()
    return self._exchange_configs

def get_exchange_config(self, exchange_name: str) -> Optional[ExchangeConfig]:
    """
    Get configuration for specific exchange.
    
    Args:
        exchange_name: Exchange name (e.g., 'mexc', 'gateio')
        
    Returns:
        ExchangeConfig struct or None if not configured
    """
    configs = self.get_exchange_configs()
    return configs.get(exchange_name.lower())

def get_all_exchange_configs(self) -> Dict[str, ExchangeConfig]:
    """
    Get all configured exchanges (alias for get_exchange_configs for backward compatibility).
    
    Returns:
        Dictionary mapping exchange names to ExchangeConfig structs
    """
    return self.get_exchange_configs()

def get_configured_exchanges(self) -> List[str]:
    """
    Get list of configured exchange names.
    
    Returns:
        List of exchange names that have been configured
    """
    return list(self.get_exchange_configs().keys())
```

### Exchange Status Methods
```python
def get_enabled_exchanges(self) -> List[str]:
    """
    Get list of enabled exchange names.
    
    Returns:
        List of exchange names that are enabled
    """
    return [name for name, config in self.get_exchange_configs().items() if config.enabled]

def get_trading_ready_exchanges(self) -> List[str]:
    """
    Get list of exchanges ready for trading (enabled + credentials).
    
    Returns:
        List of exchange names ready for trading operations
    """
    return [name for name, config in self.get_exchange_configs().items() if config.is_ready_for_trading()]

def has_trading_exchanges(self) -> bool:
    """
    Check if any exchanges are configured for trading.
    
    Returns:
        True if at least one exchange is ready for trading
    """
    return len(self.get_trading_ready_exchanges()) > 0
```

## Validation and Diagnostics

### Exchange Configuration Validation
```python
def validate_exchange_configs(self) -> Dict[str, List[str]]:
    """
    Validate all exchange configurations.
    
    Returns:
        Dictionary mapping exchange names to lists of warning messages
    """
    configs = self.get_exchange_configs()
    validation_results = {}
    
    for exchange_name, config in configs.items():
        warnings = []
        
        try:
            # Use struct validation method
            config.validate()
        except ValueError as e:
            warnings.append(f"Configuration validation failed: {e}")
        
        # HFT-specific validation
        if config.rate_limit and config.rate_limit.requests_per_second < 10:
            warnings.append("Rate limit < 10 may be too restrictive for HFT operations")
        
        if config.network and config.network.request_timeout > 10:
            warnings.append("Request timeout > 10s may cause trading delays")
        
        if not config.has_credentials():
            warnings.append("No credentials configured - trading operations disabled")
        
        if not config.enabled:
            warnings.append("Exchange is disabled")
            
        # Transport-specific validation
        if config.transport:
            if config.transport.max_latency_ms > 100:
                warnings.append(f"max_latency_ms ({config.transport.max_latency_ms}ms) exceeds HFT requirements")
            
            if config.transport.requests_per_second < 10:
                warnings.append(f"Transport requests_per_second ({config.transport.requests_per_second}) may be too restrictive")
        
        validation_results[exchange_name] = warnings
    
    return validation_results
```

### Credential Diagnostics
```python
def get_credentials_summary(self) -> Dict[str, Dict[str, Any]]:
    """
    Get summary of credential availability (for diagnostics).
    
    Returns:
        Dictionary with credential availability information
    """
    summary = {}
    
    configs = self.get_exchange_configs()
    
    for exchange_name, config in configs.items():
        credentials = config.credentials
        
        if credentials and credentials.has_private_api:
            summary[exchange_name] = {
                "available": True,
                "valid": True,  # If loaded from config, assumed valid
                "preview": credentials.get_preview(),
                "has_private_api": credentials.has_private_api
            }
        else:
            summary[exchange_name] = {
                "available": False,
                "valid": False,
                "preview": "Not configured",
                "has_private_api": False,
                "note": "Credentials should be set in config.yaml with environment variable substitution (e.g., '${MEXC_API_KEY}')"
            }
    
    return summary
```

## ExchangeConfig Struct Specification

### Core ExchangeConfig Structure
```python
class ExchangeConfig(Struct, frozen=True):
    """
    Complete exchange configuration including credentials and settings.

    Attributes:
        name: Exchange name (e.g., 'mexc', 'gateio')
        credentials: API credentials
        base_url: REST API exchanges URL
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
```

### Capability Methods
```python
def has_credentials(self) -> bool:
    """
    Check if exchange has valid credentials for private operations.
    
    Returns:
        True if exchange has valid API credentials
    """
    return self.credentials.has_private_api

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
        "ws": bool(self.websocket_url),
        "rest_api": bool(self.base_url)
    }
```

### Transport Configuration Integration
```python
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
```

## Separated Domain Architecture Support

### Domain Separation Principles
The exchange configuration system supports the separated domain architecture where:

**Public Domain (Market Data)**:
- No authentication required
- Access to symbol information, orderbooks, trades, tickers
- Uses public REST endpoints and WebSocket connections
- Configuration shared: base URLs, WebSocket URLs, symbol mappings

**Private Domain (Trading Operations)**:
- Authentication required (API credentials)
- Access to balances, orders, positions, trading operations
- Uses private REST endpoints and authenticated WebSocket connections
- Configuration includes: credentials, private endpoints, authenticated transport

### Configuration Usage in Separated Domains
```python
# Public domain usage (market data only)
def create_public_exchange(exchange_name: str, config: ExchangeConfig):
    """Create public exchange for market data operations."""
    # Uses: base_url, websocket_url, symbol mappings
    # Does NOT use: credentials (public mode)
    return PublicExchange(
        base_url=config.base_url,
        websocket_url=config.websocket_url,
        transport_config=config.get_transport_config(is_private=False)
    )

# Private domain usage (trading operations)
def create_private_exchange(exchange_name: str, config: ExchangeConfig):
    """Create private exchange for trading operations."""
    if not config.has_credentials():
        raise ConfigurationError(f"Exchange {exchange_name} has no credentials for private operations")
    
    # Uses: credentials, base_url, private endpoints
    return PrivateExchange(
        credentials=config.credentials,
        base_url=config.base_url,
        transport_config=config.get_transport_config(is_private=True)
    )
```

## Configuration Examples

### YAML Exchange Configuration
```yaml
exchanges:
  mexc_spot:
    api_key: "${MEXC_API_KEY}"
    secret_key: "${MEXC_SECRET_KEY}"
    base_url: "https://api.mexc.com"
    websocket_url: "wss://wbs-api.mexc.com/ws"
    enabled: true
    transport:
      max_latency_ms: 40.0
      target_throughput_rps: 100.0
      requests_per_second: 20.0
      burst_capacity: 60
      connection_timeout_ms: 1500.0
      read_timeout_ms: 4000.0
    websocket_config:
      connect_timeout: 10.0
      ping_interval: 20.0
      max_reconnect_attempts: 10
      enable_compression: true
      
  gateio_spot:
    api_key: "${GATEIO_API_KEY}"
    secret_key: "${GATEIO_SECRET_KEY}"
    base_url: "https://api.gateio.ws/api/v4"
    websocket_url: "wss://api.gateio.ws/ws/v4/"
    enabled: true
    transport:
      max_latency_ms: 60.0
      target_throughput_rps: 50.0
      requests_per_second: 15.0
    
  # Future exchanges can be added here without code changes
  binance_spot:
    api_key: "${BINANCE_API_KEY}"
    secret_key: "${BINANCE_SECRET_KEY}"
    base_url: "https://api.binance.com"
    websocket_url: "wss://stream.binance.com:9443/ws"
    enabled: false  # Disabled until implementation ready
```

### Dynamic Exchange Addition Process
1. **Add to YAML Configuration** - No code changes required
2. **Set Environment Variables** - Add API credentials to .env
3. **Register in Factory** - Add exchange class to factory mapping
4. **Configuration Validation** - System validates new exchange automatically

## Utility Functions

### Safe Configuration Value Extraction
```python
def _safe_get_config_value(self, config: Dict[str, Any], key: str, default: Any, value_type: type, config_name: str) -> Any:
    """Safely extract and validate configuration value with type checking."""
    try:
        value = config.get(key, default)
        if value_type == float:
            return float(value)
        elif value_type == int:
            return int(value)
        elif value_type == bool:
            return bool(value)
        elif value_type == str:
            return str(value)
        else:
            return value_type(value)
    except (ValueError, TypeError) as e:
        raise ConfigurationError(
            f"Invalid value for {config_name}.{key}: {config.get(key)} (expected {value_type.__name__})",
            f"{config_name}.{key}"
        ) from e
```

---

*This Exchange Configuration specification provides comprehensive management for all exchange-specific settings while supporting separated domain architecture and dynamic exchange scaling without code changes.*