# Configuration System Usage Guide

This document explains how to use the centralized configuration system for the HFT CEX Arbitrage Engine.

## Quick Start

1. **Copy the example configuration:**
   ```bash
   cp .env.example .env
   ```

2. **Edit .env file with your settings:**
   ```bash
   # Environment
   ENVIRONMENT=dev
   DEBUG=true
   
   # MEXC API Credentials
   MEXC_API_KEY=your_actual_mexc_api_key
   MEXC_SECRET_KEY=your_actual_mexc_secret_key
   
   # Trading Parameters
   ENABLED_TRADING_PAIRS=BTCUSDT,ETHUSDT,BNBUSDT
   MAX_POSITION_SIZE=1000.0
   ```

3. **Use in your code:**
   ```python
   from common.config import config
   from exchanges.mexc.mexc_private import MexcPrivateExchange
   
   # API credentials automatically loaded from config
   exchange = MexcPrivateExchange()
   
   # Access configuration values
   timeout = config.REQUEST_TIMEOUT
   debug = config.DEBUG_MODE
   ```

## Configuration Categories

### Environment Settings
- `ENVIRONMENT`: Environment type (`dev`, `prod`, `test`)
- `DEBUG`: Enable debug mode (`true`/`false`)
- `LOG_LEVEL`: Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`)

### Exchange API Credentials
- `MEXC_API_KEY` / `MEXC_SECRET_KEY`: MEXC exchange credentials
- `BINANCE_API_KEY` / `BINANCE_SECRET_KEY`: Binance credentials (future)
- `COINBASE_API_KEY` / `COINBASE_SECRET_KEY`: Coinbase credentials (future)

### Performance Settings
- `REQUEST_TIMEOUT`: HTTP request timeout (seconds)
- `MAX_CONNECTIONS`: Maximum HTTP connections
- `MEXC_RATE_LIMIT_PER_SECOND`: MEXC API rate limit
- `WS_CONNECT_TIMEOUT`: WebSocket connection timeout

### Trading Parameters
- `MAX_POSITION_SIZE`: Maximum position size (USD)
- `MAX_ORDER_SIZE`: Maximum order size (USD)
- `MIN_PROFIT_THRESHOLD`: Minimum profit threshold (0.001 = 0.1%)
- `ENABLED_TRADING_PAIRS`: Comma-separated list of trading pairs

## Usage Examples

### Basic Exchange Usage
```python
from common.config import config
from exchanges.mexc.mexc_private import MexcPrivateExchange
from exchanges.mexc.mexc_public import MexcPublicExchange

# Private exchange (requires API credentials)
private_exchange = MexcPrivateExchange()

# Public exchange (no credentials required)
public_exchange = MexcPublicExchange()
```

### Configuration Validation
```python
from common.config import validate_environment, ConfigurationError

try:
    validate_environment()
    print("Configuration is valid!")
except ConfigurationError as e:
    print(f"Configuration error: {e}")
```

### Accessing Configuration Values
```python
from common.config import config

# Check environment
if config.ENVIRONMENT == 'prod':
    print("Running in production")

# Get exchange-specific settings
mexc_config = config.get_exchange_config('MEXC')
print(f"MEXC rate limit: {mexc_config['rate_limit_per_second']}")

# Check if credentials are available
if config.has_exchange_credentials('MEXC'):
    print("MEXC credentials are configured")
```

### Using Configuration in Custom Code
```python
from common.config import config, get_exchange_credentials

# Get API credentials for an exchange
credentials = get_exchange_credentials('MEXC')
api_key = credentials['api_key']
secret_key = credentials['secret_key']

# Create REST configuration for specific use cases
rest_config = config.create_rest_config('MEXC', 'order')  # Optimized for order placement
```

## Environment-Specific Configuration

### Development Environment
```bash
ENVIRONMENT=dev
DEBUG=true
LOG_LEVEL=DEBUG
MAX_POSITION_SIZE=100.0  # Small positions for testing
```

### Production Environment
```bash
ENVIRONMENT=prod
DEBUG=false
LOG_LEVEL=INFO
MAX_POSITION_SIZE=10000.0  # Real position sizes
REQUEST_TIMEOUT=5.0  # Faster timeouts for production
```

### Testing Environment
```bash
ENVIRONMENT=test
DEBUG=true
LOG_LEVEL=DEBUG
# No API keys needed for testing
```

## Security Best Practices

### API Key Management
- **Never commit API keys to version control**
- Use environment variables or secure secrets management
- Regularly rotate API keys
- Use IP whitelisting where supported
- Enable 2FA on exchange accounts

### Configuration Security
```python
# The configuration system never logs sensitive data
from common.config import config

# This is safe - no API keys are exposed
safe_summary = config.get_safe_config_summary()
print(safe_summary)  # Only shows non-sensitive configuration
```

### Production Security
- Set restrictive file permissions on `.env` file:
  ```bash
  chmod 600 .env
  ```
- Use secure secrets management in production
- Monitor API usage and set up alerts
- Regular security audits of API permissions

## Error Handling

### Configuration Errors
```python
from common.config import config, ConfigurationError

try:
    # Configuration validation happens automatically
    exchange = MexcPrivateExchange()
except ConfigurationError as e:
    print(f"Configuration error: {e}")
    if e.setting_name:
        print(f"Problem with setting: {e.setting_name}")
```

### Missing Credentials
```python
from common.config import config

# Check before creating exchange instances
if not config.has_exchange_credentials('MEXC'):
    print("MEXC credentials not configured")
    print("Please set MEXC_API_KEY and MEXC_SECRET_KEY in .env file")
```

## Advanced Usage

### Custom RestConfig Creation
```python
from common.config import config

# Create optimized configuration for different endpoint types
order_config = config.create_rest_config('MEXC', 'order')      # Ultra-fast for orders
market_config = config.create_rest_config('MEXC', 'market_data')  # Optimized for market data
history_config = config.create_rest_config('MEXC', 'history')     # Longer timeout for historical data
```

### Runtime Configuration Changes
```python
from common.config import config

# Configuration is loaded once at startup for performance
# Runtime changes require application restart
print(f"Current environment: {config.ENVIRONMENT}")
```

### Multi-Exchange Setup
```python
from common.config import config

# Get all enabled exchanges
enabled_exchanges = config.get_enabled_exchanges()
print(f"Enabled exchanges: {enabled_exchanges}")

# Create exchanges for each enabled exchange
for exchange_name in enabled_exchanges:
    if exchange_name == 'MEXC':
        mexc_exchange = MexcPrivateExchange()
        # ... use exchange
```

## Performance Considerations

The configuration system is designed for zero runtime overhead:

- **Singleton pattern**: Configuration loaded once at startup
- **Lazy validation**: Validation happens during initialization
- **Type safety**: Full type hints for IDE support and runtime safety
- **Memory efficient**: O(1) memory usage, no runtime allocations
- **Thread safe**: Safe for concurrent access in async environments

## Troubleshooting

### Common Issues

1. **"Configuration Error: MEXC_API_KEY appears to be too short"**
   - Check that your API key is correctly set in .env file
   - Ensure no extra spaces or quotes around the API key

2. **"No exchanges configured with valid credentials"**
   - At least one exchange needs both API key and secret key
   - Check that both `MEXC_API_KEY` and `MEXC_SECRET_KEY` are set

3. **"Invalid environment: xyz"**
   - `ENVIRONMENT` must be one of: `dev`, `prod`, `test`

### Debug Information
```python
from common.config import config

# Get safe configuration summary for debugging
debug_info = config.get_safe_config_summary()
for key, value in debug_info.items():
    print(f"{key}: {value}")
```

### Validation Script
```python
# Run configuration validation
from common.config import validate_environment

try:
    validate_environment()
    print("✅ Configuration validation passed")
except Exception as e:
    print(f"❌ Configuration validation failed: {e}")
```

## Migration from Hardcoded Values

If you have existing code with hardcoded API keys or timeouts:

### Before (Old Pattern)
```python
# DON'T DO THIS - hardcoded values
exchange = MexcPrivateExchange(
    api_key="hardcoded_key",
    secret_key="hardcoded_secret"
)

config = RestConfig(timeout=10.0, max_retries=3)
```

### After (New Pattern)
```python
# DO THIS - use centralized configuration
from common.config import config

# Credentials automatically loaded from .env
exchange = MexcPrivateExchange()

# Configuration automatically optimized
rest_config = config.create_rest_config('MEXC', 'order')
```

## Support

For configuration issues:
1. Check this documentation
2. Validate your .env file against .env.example
3. Run the validation script to identify specific issues
4. Check the application logs for configuration error messages