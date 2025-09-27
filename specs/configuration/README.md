# Configuration System Specifications

Complete specifications for the CEX Arbitrage Engine's unified configuration system, designed for HFT performance with separated domain architecture support.

## Architecture Overview

The configuration system provides **comprehensive management** for all system components including exchanges, networking, logging, database operations, and arbitrage engine settings. Built with **HFT performance requirements** and **separated domain architecture** principles.

### Core Design Principles

1. **Unified Dictionary Pattern** - Single `exchanges:` configuration supports all exchange types
2. **Environment Variable Integration** - Secure credential management via `${VAR_NAME}` substitution
3. **HFT Performance Compliance** - Sub-50ms configuration loading with validation
4. **Separated Domain Support** - Configuration supports both public (market data) and private (trading) operations
5. **Dynamic Exchange Scaling** - New exchanges require only YAML configuration, no code changes
6. **Type-Safe Access** - msgspec.Struct-based configuration with comprehensive validation

## Configuration Specifications

### [Core Configuration Manager](core-configuration-manager-spec.md)
**Primary configuration orchestrator with specialized manager delegation**
- HftConfig singleton with performance monitoring (sub-50ms loading)
- Environment variable substitution with security validation
- Specialized manager initialization (database, exchange, logging)
- YAML loading with comprehensive error handling
- Configuration validation and HFT compliance checking

### [Exchange Configuration](exchange-configuration-spec.md) 
**Exchange-specific configuration management supporting separated domains**
- ExchangeConfigManager with dynamic exchange support
- Unified credential management from environment variables
- WebSocket and REST transport configuration
- Rate limiting and performance optimization settings
- Exchange validation with HFT requirement enforcement

### [Database Configuration](database-configuration-spec.md)
**Database connection and data collection configuration**
- DatabaseConfigManager with connection pool optimization
- DataCollectorConfig with analytics integration
- Performance-tuned settings for HFT operations
- Connection validation and monitoring capabilities
- Symbol and exchange configuration integration

### [Logging Configuration](logging-configuration-spec.md)
**HFT logging system configuration integration**
- LoggingConfigManager with backend routing
- Environment-specific logging configurations
- HFT performance optimization settings
- Multi-backend support (console, file, Prometheus, audit)
- Factory-based logger injection throughout codebase

### [Network Configuration](network-configuration-spec.md)
**Network and transport layer configuration**
- NetworkConfig struct with timeout and retry settings
- WebSocketConfig with connection management
- RestTransportConfig for the new transport system
- Performance optimization for sub-millisecond operations
- Exchange-specific transport tuning

## Configuration Structure Hierarchy

```yaml
# Complete configuration.yaml structure
environment:
  name: dev  # dev, prod, test
  debug: true

exchanges:
  # Unified exchange configuration supporting all exchange types
  mexc_spot:
    api_key: "${MEXC_API_KEY}"
    secret_key: "${MEXC_SECRET_KEY}"
    base_url: "https://api.mexc.com"
    websocket_url: "wss://wbs-api.mexc.com/ws"
    enabled: true
    transport: { ... }  # REST transport configuration
    websocket_config: { ... }  # WebSocket configuration
    
  gateio_spot:
    api_key: "${GATEIO_API_KEY}"
    secret_key: "${GATEIO_SECRET_KEY}"
    base_url: "https://api.gateio.ws/api/v4"
    websocket_url: "wss://api.gateio.ws/ws/v4/"
    enabled: true
    transport: { ... }
    websocket_config: { ... }

network:
  request_timeout: 10.0
  connect_timeout: 5.0
  max_retries: 3
  retry_delay: 1.0

ws:  # Global WebSocket template
  connect_timeout: 10.0
  ping_interval: 20.0
  max_reconnect_attempts: 10
  enable_compression: true

database:
  host: "${DB_HOST:localhost}"
  port: 5432
  database: "${DB_NAME:arbitrage}"
  username: "${DB_USER:postgres}"
  password: "${DB_PASSWORD}"
  pool: { ... }
  performance: { ... }

logging:
  backends:
    console: { ... }
    file: { ... }
    prometheus: { ... }
    audit: { ... }
  hft_settings:
    ring_buffer_size: 10000
    batch_size: 50

arbitrage:
  enabled_exchanges:
    - "MEXC_SPOT"
    - "GATEIO_SPOT"
  risk_limits: { ... }
  arbitrage_pairs: [ ... ]

data_collector:
  enabled: true
  snapshot_interval: 0.5
  exchanges: ["mexc", "gateio"]
  analytics: { ... }
```

## Separated Domain Architecture Support

### Public Domain Configuration
**Market data operations - no authentication required**
- Symbol information and trading rules access
- Orderbook and market data streaming configuration
- Public REST API endpoint configuration
- Public WebSocket connection settings

### Private Domain Configuration  
**Trading operations - authentication required**
- API credentials and authentication configuration
- Private REST API endpoint configuration
- Private WebSocket connection settings with authentication
- Trading-specific rate limiting and performance settings

### Configuration Sharing Policy
**Minimal shared configuration between domains**
- **PERMITTED**: Static configuration (symbol_info, exchange URLs, trading rules)
- **PROHIBITED**: Real-time data caching (balances, orders, positions, orderbooks)
- **RATIONALE**: Maintains HFT caching policy compliance and domain separation

## Performance Specifications

### HFT Compliance Requirements
- **Configuration Loading**: <50ms total (YAML load + validation + manager initialization)
- **Environment Variable Substitution**: <2ms for typical configuration
- **Configuration Access**: <1μs for cached configuration objects
- **Memory Footprint**: <1MB for complete configuration cache
- **Startup Impact**: Zero blocking operations during trading initialization

### Performance Monitoring
- ConfigLoadingMetrics struct with sub-component timing
- HFT compliance validation methods
- Performance reporting and debugging capabilities
- Benchmarking and optimization tracking

## Integration Patterns

### Factory Integration
```python
# ExchangeFactory integration
config = HftConfig()
exchange_config = config.get_exchange_config('mexc_spot')
mexc_exchange = factory.create_exchange('mexc_spot', exchange_config)

# Separated domain creation
public_config = config.get_exchange_config('mexc_spot')  # Market data only
private_config = config.get_exchange_config('mexc_spot')  # Trading operations
```

### Manager Integration
```python
# Specialized manager access
database_config = config.get_database_config()
logging_config = config.get_logging_config()
network_config = config.get_network_config()

# Exchange manager integration
exchange_manager = config._exchange_manager
all_exchanges = exchange_manager.get_all_exchange_configs()
```

## Security Considerations

### Credential Protection
- **Environment Variable Only** - Never store credentials in YAML directly
- **Format Validation** - Validate credential format without exposing values
- **Secure Logging** - Log credential status without showing keys
- **Production Safeguards** - Validate credential availability in production

### Configuration Validation
- **Paired Credentials** - API key and secret must both be present or both empty
- **URL Validation** - Validate REST and WebSocket URL formats
- **Range Validation** - Validate numeric parameters within acceptable ranges
- **Environment Validation** - Ensure valid environment names (dev, prod, test)

## Usage Examples

### Basic Configuration Access
```python
from src.config.config_manager import get_config

# Get configuration instance
config = get_config()

# Exchange configuration
mexc_config = config.get_exchange_config('mexc_spot')
if mexc_config.has_credentials():
    # Trading mode
    private_exchange = factory.create_private_exchange('mexc_spot', mexc_config)
else:
    # Public-only mode
    public_exchange = factory.create_public_exchange('mexc_spot', mexc_config)

# Network and transport configuration
network_config = config.get_network_config()
transport_config = mexc_config.get_transport_config(is_private=True)

# Database and logging configuration
database_config = config.get_database_config()
logging_config = config.get_logging_config()
```

### Configuration Validation
```python
# Comprehensive validation
config.validate_configuration()

# Performance compliance checking
if not config.validate_hft_compliance():
    logger.warning("Configuration loading exceeds HFT requirements")

# Get performance report
performance_report = config.get_performance_report()
logger.info(performance_report)
```

---

## Next Steps

1. **Review individual component specifications** for detailed implementation guidance
2. **Implement configuration changes** following the structured approach
3. **Validate HFT performance compliance** during configuration loading
4. **Test separated domain architecture** with public/private exchange creation
5. **Monitor configuration performance** in production environments

*This configuration system provides the foundation for scalable, high-performance trading operations while maintaining security, flexibility, and separated domain architecture compliance.*