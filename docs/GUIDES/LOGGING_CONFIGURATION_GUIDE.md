# HFT Logging System Configuration Guide

## Overview

The HFT Arbitrage Engine uses a high-performance logging system designed for sub-millisecond trading operations. The system provides:

- **<1ms latency** per log operation (HFT compliant)
- **170,000+ messages/second** sustained throughput
- **Factory-based logger injection** across all components
- **Hierarchical tagging system** for precise metrics routing
- **Multi-backend support** (Console, File, Prometheus, Audit)
- **Automatic configuration** from `config.yaml`

## Quick Start

No configuration needed! Logging works out of the box:

```python
from core.logging import get_logger

logger = get_logger('my_component')
logger.info('Application started')
logger.debug('Debug information') 
logger.error('An error occurred')
```

## Configuration Overview

All logging settings are controlled via `config.yaml`. The system supports multiple configuration levels with a clear override hierarchy:

1. **Global Configuration** - Base environment-level settings
2. **Environment-Specific Overrides** - Per-environment (dev/prod/test) customization
3. **Backend Configuration** - Per-backend (console, file, prometheus) settings  
4. **Module-Specific Configuration** - Component-level runtime overrides
5. **Tag-Based Configuration** - Hierarchical tag filtering

### Configuration Override Hierarchy

The system follows this precedence order (highest to lowest):

```
Module-Specific Runtime Config → Environment Variables → Environment-Specific Config → Backend Config → Global Config
```

### Basic Configuration Structure

```yaml
# Global environment settings
environment:
  name: dev                          # dev, prod, test
  debug: true
  log_level: DEBUG                   # Global minimum log level

logging:
  # Console output (enabled by default)
  console:
    enabled: true                    # Show logs in console
    color: true                      # Colored output
    include_context: true            # Include context data
    min_level: DEBUG                 # Console-specific log level
    
  # File output
  file:
    enabled: true                    # Log to file
    path: logs/hft.log              # Log file path
    format: text                     # text or json
    min_level: INFO                  # File-specific log level
    max_size_mb: 100                 # Max file size
    backup_count: 5                  # Backup files to keep
    
  # Prometheus metrics (optional)
  prometheus:
    enabled: false                   # Disabled by default
    push_gateway_url: http://localhost:9091
    job_name: hft_arbitrage
    batch_size: 100                  # Metrics per batch
    flush_interval: 5.0              # Seconds between flushes
    
  # Performance tuning
  performance:
    buffer_size: 10000               # Async buffer size
    batch_size: 50                   # Batch dispatch size
    correlation_tracking: true       # Track correlation IDs
    performance_tracking: true       # Track performance metrics
```

## Environment-Specific Configuration Overrides

The HFT logging system supports multiple ways to override configuration for different environments (dev, prod, test) and specific modules.

### 1. Environment Variables Override

Use environment variables to override any configuration setting without modifying `config.yaml`:

#### Setting Environment Name

```bash
# Override environment name
export ENVIRONMENT=prod
export HFT_LOG_LEVEL=ERROR
export HFT_CONSOLE_ENABLED=false

# Start application - will use production settings
python main.py
```

#### Environment Variable Patterns

```bash
# Global settings
export HFT_LOG_LEVEL=INFO                    # Override environment.log_level
export HFT_DEBUG=false                       # Override environment.debug

# Console backend overrides
export HFT_CONSOLE_ENABLED=true              # Override logging.console.enabled
export HFT_CONSOLE_MIN_LEVEL=WARNING         # Override logging.console.min_level
export HFT_CONSOLE_COLOR=false               # Override logging.console.color

# File backend overrides  
export HFT_FILE_ENABLED=true                 # Override logging.file.enabled
export HFT_FILE_PATH=/var/log/hft/app.log    # Override logging.file.path
export HFT_FILE_MIN_LEVEL=ERROR              # Override logging.file.min_level
export HFT_FILE_FORMAT=json                  # Override logging.file.format

# Prometheus overrides
export HFT_PROMETHEUS_ENABLED=true           # Override logging.prometheus.enabled
export HFT_PROMETHEUS_URL=http://prod-gateway:9091  # Override push_gateway_url
export HFT_PROMETHEUS_JOB=hft_prod           # Override job_name

# Performance overrides
export HFT_BUFFER_SIZE=20000                 # Override logging.performance.buffer_size
export HFT_BATCH_SIZE=100                    # Override logging.performance.batch_size
```

### 2. Multiple Configuration Files per Environment

#### Option A: Separate Config Files

```bash
# Project structure
config/
├── config.yaml              # Base configuration
├── config.dev.yaml         # Development overrides
├── config.prod.yaml        # Production overrides
└── config.test.yaml        # Testing overrides
```

**config.yaml** (base configuration):
```yaml
environment:
  name: dev
  debug: true
  log_level: DEBUG

logging:
  console:
    enabled: true
    color: true
    min_level: DEBUG
  file:
    enabled: true
    path: logs/hft.log
    min_level: INFO
  prometheus:
    enabled: false
```

**config.prod.yaml** (production overrides):
```yaml
environment:
  name: prod
  debug: false
  log_level: WARNING

logging:
  console:
    enabled: false              # No console in production
  file:
    path: /var/log/hft/prod.log
    format: json               # Structured logging
    min_level: ERROR           # Only errors and critical
    max_size_mb: 500
  prometheus:
    enabled: true              # Enable metrics in production
    push_gateway_url: http://monitoring:9091
    job_name: hft_arbitrage_prod
```

**config.test.yaml** (testing overrides):
```yaml
environment:
  name: test
  debug: false
  log_level: WARNING

logging:
  console:
    color: false               # No colors for CI/CD
    min_level: WARNING         # Reduce test noise
  file:
    enabled: false             # No files in tests
  prometheus:
    enabled: false             # No metrics in tests
```

#### Load Environment-Specific Config

```python
import os
from core.config.config_manager import HftConfig

# Method 1: Environment-based config file selection
env = os.getenv('ENVIRONMENT', 'dev')
config_file = f'config.{env}.yaml'

config = HftConfig(config_file=config_file)

# Method 2: Automatic environment detection
config = HftConfig()  # Automatically loads config.{ENVIRONMENT}.yaml if exists
```

#### Option B: Single File with Environment Sections

```yaml
# config.yaml with environment-specific sections
defaults: &defaults
  logging:
    performance:
      buffer_size: 10000
      batch_size: 50

development:
  <<: *defaults
  environment:
    name: dev
    debug: true
    log_level: DEBUG
  logging:
    console:
      enabled: true
      color: true
      min_level: DEBUG
    file:
      enabled: true
      min_level: INFO
    prometheus:
      enabled: false

production:
  <<: *defaults
  environment:
    name: prod
    debug: false
    log_level: ERROR
  logging:
    console:
      enabled: false
    file:
      enabled: true
      path: /var/log/hft/prod.log
      format: json
      min_level: ERROR
      max_size_mb: 500
    prometheus:
      enabled: true
      push_gateway_url: http://monitoring:9091
      job_name: hft_arbitrage_prod
      batch_size: 200

testing:
  <<: *defaults
  environment:
    name: test
    debug: false
    log_level: WARNING
  logging:
    console:
      enabled: true
      color: false
      min_level: WARNING
    file:
      enabled: false
    prometheus:
      enabled: false
```

### 3. Runtime Environment Configuration

#### Programmatic Environment Override

```python
from core.logging import LoggerFactory, configure_logging

# Override configuration at runtime
def configure_for_environment(env_name: str):
    if env_name == 'prod':
        config = {
            'environment': 'prod',
            'console': {'enabled': False},
            'file': {
                'enabled': True,
                'path': '/var/log/hft/prod.log',
                'format': 'json',
                'min_level': 'ERROR'
            },
            'prometheus': {
                'enabled': True,
                'push_gateway_url': 'http://monitoring:9091',
                'job_name': 'hft_arbitrage_prod'
            }
        }
    elif env_name == 'test':
        config = {
            'environment': 'test',
            'console': {'enabled': True, 'color': False, 'min_level': 'WARNING'},
            'file': {'enabled': False},
            'prometheus': {'enabled': False}
        }
    else:  # dev
        config = {
            'environment': 'dev',
            'console': {'enabled': True, 'color': True, 'min_level': 'DEBUG'},
            'file': {'enabled': True, 'min_level': 'INFO'},
            'prometheus': {'enabled': False}
        }
    
    # Apply configuration
    configure_logging(config)

# Usage
import os
env = os.getenv('ENVIRONMENT', 'dev')
configure_for_environment(env)
```

#### Environment Detection and Auto-Configuration

```python
import os
from core.logging import LoggerFactory

class EnvironmentAwareLogging:
    @staticmethod
    def setup():
        env = os.getenv('ENVIRONMENT', 'dev').lower()
        
        if env == 'production' or env == 'prod':
            EnvironmentAwareLogging._setup_production()
        elif env == 'testing' or env == 'test':
            EnvironmentAwareLogging._setup_testing()
        else:
            EnvironmentAwareLogging._setup_development()
    
    @staticmethod
    def _setup_production():
        LoggerFactory.configure_defaults({
            'environment': 'prod',
            'backends': {
                'console': {'enabled': False},
                'file': {
                    'enabled': True,
                    'path': '/var/log/hft/prod.log',
                    'format': 'json',
                    'min_level': 'ERROR'
                },
                'prometheus': {
                    'enabled': True,
                    'push_gateway_url': os.getenv('PROMETHEUS_GATEWAY', 'http://monitoring:9091'),
                    'job_name': 'hft_arbitrage_prod'
                }
            }
        })
    
    @staticmethod
    def _setup_testing():
        LoggerFactory.configure_defaults({
            'environment': 'test',
            'backends': {
                'console': {'enabled': True, 'color': False, 'min_level': 'WARNING'},
                'file': {'enabled': False},
                'prometheus': {'enabled': False}
            }
        })
    
    @staticmethod
    def _setup_development():
        LoggerFactory.configure_defaults({
            'environment': 'dev',
            'backends': {
                'console': {'enabled': True, 'color': True, 'min_level': 'DEBUG'},
                'file': {'enabled': True, 'min_level': 'INFO'},
                'prometheus': {'enabled': False}
            }
        })

# Auto-setup on import
EnvironmentAwareLogging.setup()
```

## Log Level Configuration

### 1. Global Log Level Configuration

Set the baseline log level for the entire application:

```yaml
# config.yaml
environment:
  log_level: INFO    # CRITICAL, ERROR, WARNING, INFO, DEBUG
```

This affects all loggers unless overridden by specific backend or module configurations.

### 2. Backend-Specific Log Levels

Configure different log levels for each output backend:

```yaml
logging:
  console:
    min_level: DEBUG     # Show everything in console during development
  file:
    min_level: WARNING   # Only important messages in log files
  prometheus:
    enabled: true
    # Prometheus automatically captures metrics regardless of log level
```

### 3. Module-Specific Log Level Configuration

Configure specific log levels for individual modules or components:

```python
# Method 1: Via factory configuration
from core.logging import get_logger

# Create logger with specific minimum level
config = {
    'logger_config': {
        'min_level': 'ERROR'  # Only log errors and critical for this component
    }
}
logger = get_logger('mexc.websocket.private', config)

# Method 2: Using specialized factory functions
from core.logging import get_exchange_logger, get_strategy_logger

# Exchange-specific logger with default exchange context
logger = get_exchange_logger('mexc', 'websocket.private')

# Strategy logger with hierarchical tags
tags = ['mexc', 'private', 'ws', 'connection']
logger = get_strategy_logger('ws.connection.mexc.private', tags)
```

## Module-Specific Configuration Overrides

The system allows fine-grained configuration overrides for specific modules, components, or even individual logger instances.

### 1. Runtime Module Configuration

#### Per-Module Logger Configuration

```python
from core.logging import get_logger, LoggerFactory

# Configure specific module with custom settings
def create_mexc_websocket_logger():
    config = {
        'logger_config': {
            'min_level': 'DEBUG',           # Override global log level
            'file_path': 'logs/mexc_ws.log', # Module-specific log file
            'include_context': True,        # Include full context
            'buffer_size': 5000,           # Custom buffer size
            'batch_size': 25               # Custom batch size
        },
        'default_context': {
            'exchange': 'mexc',
            'transport': 'websocket',
            'component': 'connection'
        }
    }
    return get_logger('mexc.websocket.connection', config)

# Configure trading module with different settings
def create_trading_logger():
    config = {
        'logger_config': {
            'min_level': 'INFO',           # Less verbose for trading
            'file_path': 'logs/trading.log',
            'performance_tracking': True,   # Enable performance metrics
            'correlation_tracking': True   # Enable correlation tracking
        },
        'default_context': {
            'component': 'trading',
            'module': 'order_execution'
        }
    }
    return get_logger('trading.order_execution', config)

# Usage
mexc_logger = create_mexc_websocket_logger()
trading_logger = create_trading_logger()
```

#### Component-Specific Configuration Classes

```python
from core.logging import LoggerFactory, get_logger
from typing import Dict, Any

class ComponentLoggerConfig:
    """Base class for component-specific logger configurations."""
    
    @staticmethod
    def get_base_config() -> Dict[str, Any]:
        return {
            'logger_config': {
                'buffer_size': 10000,
                'batch_size': 50,
                'include_context': True
            }
        }

class ExchangeLoggerConfig(ComponentLoggerConfig):
    """Configuration for exchange-related loggers."""
    
    @staticmethod
    def mexc_websocket_config() -> Dict[str, Any]:
        config = ComponentLoggerConfig.get_base_config()
        config.update({
            'logger_config': {
                **config['logger_config'],
                'min_level': 'DEBUG',
                'file_path': 'logs/mexc_websocket.log',
                'performance_tracking': True
            },
            'default_context': {
                'exchange': 'mexc',
                'transport': 'websocket'
            }
        })
        return config
    
    @staticmethod
    def gateio_rest_config() -> Dict[str, Any]:
        config = ComponentLoggerConfig.get_base_config()
        config.update({
            'logger_config': {
                **config['logger_config'],
                'min_level': 'INFO',
                'file_path': 'logs/gateio_rest.log',
                'correlation_tracking': True
            },
            'default_context': {
                'exchange': 'gateio',
                'transport': 'rest'
            }
        })
        return config

class ArbitrageLoggerConfig(ComponentLoggerConfig):
    """Configuration for arbitrage-related loggers."""
    
    @staticmethod
    def detector_config() -> Dict[str, Any]:
        config = ComponentLoggerConfig.get_base_config()
        config.update({
            'logger_config': {
                **config['logger_config'],
                'min_level': 'INFO',
                'file_path': 'logs/arbitrage_detector.log',
                'performance_tracking': True,
                'correlation_tracking': True
            },
            'default_context': {
                'component': 'arbitrage',
                'subcomponent': 'detector'
            }
        })
        return config

# Usage
mexc_ws_logger = get_logger('mexc.websocket', ExchangeLoggerConfig.mexc_websocket_config())
gateio_rest_logger = get_logger('gateio.rest', ExchangeLoggerConfig.gateio_rest_config())
arbitrage_logger = get_logger('arbitrage.detector', ArbitrageLoggerConfig.detector_config())
```

### 2. Configuration via Environment Variables for Specific Modules

#### Module-Specific Environment Variables

```bash
# Set log levels for specific modules
export HFT_MODULE_MEXC_WEBSOCKET_LEVEL=DEBUG
export HFT_MODULE_GATEIO_REST_LEVEL=INFO
export HFT_MODULE_ARBITRAGE_DETECTOR_LEVEL=WARNING

# Set file paths for specific modules
export HFT_MODULE_MEXC_WEBSOCKET_FILE=logs/mexc_ws.log
export HFT_MODULE_TRADING_FILE=logs/trading.log
export HFT_MODULE_ARBITRAGE_FILE=logs/arbitrage.log

# Enable/disable features for specific modules
export HFT_MODULE_TRADING_PERFORMANCE_TRACKING=true
export HFT_MODULE_WEBSOCKET_CORRELATION_TRACKING=false
```

#### Environment-Based Module Configuration

```python
import os
from core.logging import get_logger

def get_module_logger(module_name: str, default_config: Dict[str, Any] = None):
    """Get logger with environment-based module configuration."""
    
    # Base configuration
    config = default_config or {}
    
    # Environment variable overrides
    env_prefix = f"HFT_MODULE_{module_name.upper().replace('.', '_')}"
    
    # Override log level
    env_level = os.getenv(f"{env_prefix}_LEVEL")
    if env_level:
        config.setdefault('logger_config', {})['min_level'] = env_level
    
    # Override file path
    env_file = os.getenv(f"{env_prefix}_FILE")
    if env_file:
        config.setdefault('logger_config', {})['file_path'] = env_file
    
    # Override performance tracking
    env_perf = os.getenv(f"{env_prefix}_PERFORMANCE_TRACKING")
    if env_perf:
        config.setdefault('logger_config', {})['performance_tracking'] = env_perf.lower() == 'true'
    
    # Override correlation tracking
    env_corr = os.getenv(f"{env_prefix}_CORRELATION_TRACKING")
    if env_corr:
        config.setdefault('logger_config', {})['correlation_tracking'] = env_corr.lower() == 'true'
    
    return get_logger(module_name, config)

# Usage
mexc_logger = get_module_logger('mexc.websocket')
trading_logger = get_module_logger('trading.orders')
arbitrage_logger = get_module_logger('arbitrage.detector')
```

### 3. Configuration Files for Specific Modules

#### Module-Specific Configuration Files

```bash
# Project structure
config/
├── config.yaml                    # Base configuration
├── modules/
│   ├── mexc_websocket.yaml       # MEXC WebSocket specific config
│   ├── gateio_rest.yaml          # Gate.io REST specific config
│   ├── trading.yaml              # Trading module specific config
│   └── arbitrage.yaml            # Arbitrage module specific config
```

**config/modules/mexc_websocket.yaml**:
```yaml
logger_config:
  min_level: DEBUG
  file_path: logs/mexc_websocket.log
  buffer_size: 5000
  batch_size: 25
  performance_tracking: true
  correlation_tracking: true

default_context:
  exchange: mexc
  transport: websocket
  api_type: public

backends:
  console:
    enabled: true
    min_level: DEBUG
  file:
    enabled: true
    format: json
  prometheus:
    enabled: true
    tags: ["mexc", "websocket"]
```

**config/modules/trading.yaml**:
```yaml
logger_config:
  min_level: INFO
  file_path: logs/trading.log
  buffer_size: 20000
  batch_size: 100
  performance_tracking: true
  correlation_tracking: true

default_context:
  component: trading
  criticality: high

backends:
  console:
    enabled: true
    min_level: INFO
  file:
    enabled: true
    format: json
    min_level: INFO
  prometheus:
    enabled: true
    tags: ["trading", "orders"]
```

#### Load Module-Specific Configuration

```python
import yaml
from pathlib import Path
from core.logging import get_logger

def load_module_config(module_name: str) -> Dict[str, Any]:
    """Load module-specific configuration from file."""
    
    config_file = Path(f"config/modules/{module_name.replace('.', '_')}.yaml")
    
    if config_file.exists():
        with open(config_file, 'r') as f:
            return yaml.safe_load(f)
    
    return {}

def get_configured_module_logger(module_name: str):
    """Get logger with module-specific configuration."""
    
    # Load module-specific config
    module_config = load_module_config(module_name)
    
    # Create logger with module config
    return get_logger(module_name, module_config)

# Usage
mexc_logger = get_configured_module_logger('mexc.websocket')
trading_logger = get_configured_module_logger('trading.orders')
arbitrage_logger = get_configured_module_logger('arbitrage.detector')
```

### 4. Dynamic Configuration Updates

#### Runtime Configuration Updates

```python
from core.logging import LoggerFactory

class DynamicLoggerConfiguration:
    """Manage dynamic logger configuration updates."""
    
    @staticmethod
    def update_module_log_level(module_name: str, new_level: str):
        """Update log level for specific module at runtime."""
        
        # Get current configuration
        current_config = LoggerFactory._default_config.copy()
        
        # Update module-specific configuration
        module_config = {
            'logger_config': {
                'min_level': new_level
            }
        }
        
        # Apply update
        LoggerFactory.configure_defaults({
            f'module_overrides.{module_name}': module_config
        })
        
        # Clear cache to force reconfiguration
        LoggerFactory.clear_cache()
    
    @staticmethod
    def enable_debug_for_module(module_name: str):
        """Enable debug logging for specific module."""
        DynamicLoggerConfiguration.update_module_log_level(module_name, 'DEBUG')
    
    @staticmethod
    def disable_verbose_logging_for_module(module_name: str):
        """Reduce logging verbosity for specific module."""
        DynamicLoggerConfiguration.update_module_log_level(module_name, 'WARNING')

# Usage - can be called at runtime
DynamicLoggerConfiguration.enable_debug_for_module('mexc.websocket')
DynamicLoggerConfiguration.disable_verbose_logging_for_module('arbitrage.detector')
```

#### Configuration Hot-Reload

```python
import os
import yaml
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from core.logging import LoggerFactory

class ConfigFileHandler(FileSystemEventHandler):
    """Handle configuration file changes."""
    
    def on_modified(self, event):
        if event.src_path.endswith('.yaml') and 'config' in event.src_path:
            print(f"Configuration file changed: {event.src_path}")
            self.reload_configuration()
    
    def reload_configuration(self):
        """Reload configuration from files."""
        try:
            # Reload main config
            with open('config.yaml', 'r') as f:
                config = yaml.safe_load(f)
            
            # Apply new configuration
            LoggerFactory.configure_defaults(config.get('logging', {}))
            LoggerFactory.clear_cache()
            
            print("Configuration reloaded successfully")
        except Exception as e:
            print(f"Error reloading configuration: {e}")

# Enable configuration hot-reload
def enable_config_hot_reload():
    event_handler = ConfigFileHandler()
    observer = Observer()
    observer.schedule(event_handler, path='config/', recursive=True)
    observer.start()
    return observer

# Usage
# observer = enable_config_hot_reload()
```

## Practical Configuration Override Examples

### Real-World Deployment Scenarios

#### Scenario 1: Production Deployment with Module-Specific Logging

```bash
# Production environment variables
export ENVIRONMENT=prod
export HFT_CONSOLE_ENABLED=false
export HFT_FILE_PATH=/var/log/hft/prod.log
export HFT_FILE_FORMAT=json
export HFT_PROMETHEUS_ENABLED=true

# Module-specific overrides for troubleshooting
export HFT_MODULE_MEXC_WEBSOCKET_LEVEL=INFO          # Normal level for WebSocket
export HFT_MODULE_TRADING_ORDERS_LEVEL=DEBUG         # Debug trading issues
export HFT_MODULE_ARBITRAGE_DETECTOR_LEVEL=ERROR     # Reduce noise from detector

# Start application
python main.py
```

#### Scenario 2: Development with Exchange-Specific Debugging

```bash
# Development with specific exchange debugging
export ENVIRONMENT=dev
export HFT_CONSOLE_ENABLED=true
export HFT_CONSOLE_COLOR=true

# Enable verbose logging for MEXC issues
export HFT_MODULE_MEXC_WEBSOCKET_LEVEL=DEBUG
export HFT_MODULE_MEXC_REST_LEVEL=DEBUG
export HFT_MODULE_MEXC_WEBSOCKET_FILE=logs/mexc_debug.log

# Normal logging for other exchanges
export HFT_MODULE_GATEIO_WEBSOCKET_LEVEL=INFO
export HFT_MODULE_GATEIO_REST_LEVEL=INFO

python main.py
```

#### Scenario 3: Testing with Minimal Logging

```bash
# Testing environment - minimal logging
export ENVIRONMENT=test
export HFT_CONSOLE_ENABLED=true
export HFT_CONSOLE_COLOR=false
export HFT_FILE_ENABLED=false
export HFT_PROMETHEUS_ENABLED=false

# Only show warnings and errors
export HFT_CONSOLE_MIN_LEVEL=WARNING

pytest tests/
```

### Advanced Configuration Patterns

#### Pattern 1: Exchange-Specific Log Files

```python
from core.logging import get_logger

class ExchangeLoggerManager:
    """Manage exchange-specific logging configurations."""
    
    @staticmethod
    def setup_exchange_loggers():
        """Setup separate log files for each exchange."""
        
        # MEXC loggers
        mexc_ws_config = {
            'logger_config': {
                'file_path': 'logs/mexc_websocket.log',
                'min_level': 'DEBUG'
            },
            'default_context': {'exchange': 'mexc', 'transport': 'ws'}
        }
        
        mexc_rest_config = {
            'logger_config': {
                'file_path': 'logs/mexc_rest.log', 
                'min_level': 'INFO'
            },
            'default_context': {'exchange': 'mexc', 'transport': 'rest'}
        }
        
        # Gate.io loggers
        gateio_ws_config = {
            'logger_config': {
                'file_path': 'logs/gateio_websocket.log',
                'min_level': 'DEBUG'
            },
            'default_context': {'exchange': 'gateio', 'transport': 'ws'}
        }
        
        gateio_rest_config = {
            'logger_config': {
                'file_path': 'logs/gateio_rest.log',
                'min_level': 'INFO'
            },
            'default_context': {'exchange': 'gateio', 'transport': 'rest'}
        }
        
        return {
            'mexc_ws': get_logger('mexc.websocket', mexc_ws_config),
            'mexc_rest': get_logger('mexc.rest', mexc_rest_config),
            'gateio_ws': get_logger('gateio.websocket', gateio_ws_config),
            'gateio_rest': get_logger('gateio.rest', gateio_rest_config)
        }

# Usage
loggers = ExchangeLoggerManager.setup_exchange_loggers()
mexc_ws_logger = loggers['mexc_ws']
gateio_rest_logger = loggers['gateio_rest']
```

#### Pattern 2: Component-Specific Configuration Classes

```python
from typing import Dict, Any
from core.logging import get_logger

class ComponentConfigs:
    """Centralized component configuration definitions."""
    
    WEBSOCKET_CONFIG = {
        'logger_config': {
            'buffer_size': 5000,
            'batch_size': 25,
            'performance_tracking': True,
            'correlation_tracking': True
        }
    }
    
    REST_CONFIG = {
        'logger_config': {
            'buffer_size': 10000,
            'batch_size': 50,
            'performance_tracking': True,
            'correlation_tracking': False
        }
    }
    
    TRADING_CONFIG = {
        'logger_config': {
            'buffer_size': 20000,
            'batch_size': 100,
            'performance_tracking': True,
            'correlation_tracking': True,
            'file_path': 'logs/trading.log'
        }
    }
    
    ARBITRAGE_CONFIG = {
        'logger_config': {
            'buffer_size': 15000,
            'batch_size': 75,
            'performance_tracking': True,
            'correlation_tracking': True,
            'file_path': 'logs/arbitrage.log'
        }
    }

class SmartLoggerFactory:
    """Smart logger factory with component-aware configuration."""
    
    @staticmethod
    def get_websocket_logger(exchange: str, api_type: str = 'public'):
        config = ComponentConfigs.WEBSOCKET_CONFIG.copy()
        config['logger_config']['file_path'] = f'logs/{exchange}_websocket.log'
        config['default_context'] = {
            'exchange': exchange,
            'transport': 'websocket',
            'api_type': api_type
        }
        return get_logger(f'{exchange}.websocket.{api_type}', config)
    
    @staticmethod
    def get_rest_logger(exchange: str, api_type: str = 'public'):
        config = ComponentConfigs.REST_CONFIG.copy()
        config['logger_config']['file_path'] = f'logs/{exchange}_rest.log'
        config['default_context'] = {
            'exchange': exchange,
            'transport': 'rest',
            'api_type': api_type
        }
        return get_logger(f'{exchange}.rest.{api_type}', config)
    
    @staticmethod
    def get_trading_logger(component: str = 'orders'):
        config = ComponentConfigs.TRADING_CONFIG.copy()
        config['default_context'] = {
            'component': 'trading',
            'subcomponent': component
        }
        return get_logger(f'trading.{component}', config)
    
    @staticmethod
    def get_arbitrage_logger(strategy: str = 'detector'):
        config = ComponentConfigs.ARBITRAGE_CONFIG.copy()
        config['default_context'] = {
            'component': 'arbitrage',
            'strategy': strategy
        }
        return get_logger(f'arbitrage.{strategy}', config)

# Usage
mexc_ws_logger = SmartLoggerFactory.get_websocket_logger('mexc', 'public')
gateio_rest_logger = SmartLoggerFactory.get_rest_logger('gateio', 'private')
trading_logger = SmartLoggerFactory.get_trading_logger('execution')
arbitrage_logger = SmartLoggerFactory.get_arbitrage_logger('opportunity_detector')
```

#### Pattern 3: Environment-Aware Configuration with Fallbacks

```python
import os
from typing import Dict, Any
from core.logging import get_logger, LoggerFactory

class EnvironmentConfigManager:
    """Manage environment-aware configuration with intelligent fallbacks."""
    
    # Environment-specific base configurations
    ENV_CONFIGS = {
        'dev': {
            'console': {'enabled': True, 'color': True, 'min_level': 'DEBUG'},
            'file': {'enabled': True, 'min_level': 'INFO'},
            'prometheus': {'enabled': False}
        },
        'prod': {
            'console': {'enabled': False},
            'file': {'enabled': True, 'format': 'json', 'min_level': 'WARNING'},
            'prometheus': {'enabled': True}
        },
        'test': {
            'console': {'enabled': True, 'color': False, 'min_level': 'WARNING'},
            'file': {'enabled': False},
            'prometheus': {'enabled': False}
        }
    }
    
    @classmethod
    def get_environment_config(cls) -> Dict[str, Any]:
        """Get configuration for current environment with fallbacks."""
        env = os.getenv('ENVIRONMENT', 'dev').lower()
        
        # Get base environment config
        base_config = cls.ENV_CONFIGS.get(env, cls.ENV_CONFIGS['dev'])
        
        # Apply environment variable overrides
        config = cls._apply_env_overrides(base_config.copy())
        
        return config
    
    @classmethod
    def _apply_env_overrides(cls, config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply environment variable overrides to configuration."""
        
        # Console overrides
        if os.getenv('HFT_CONSOLE_ENABLED'):
            config['console']['enabled'] = os.getenv('HFT_CONSOLE_ENABLED').lower() == 'true'
        if os.getenv('HFT_CONSOLE_MIN_LEVEL'):
            config['console']['min_level'] = os.getenv('HFT_CONSOLE_MIN_LEVEL')
        if os.getenv('HFT_CONSOLE_COLOR'):
            config['console']['color'] = os.getenv('HFT_CONSOLE_COLOR').lower() == 'true'
        
        # File overrides
        if os.getenv('HFT_FILE_ENABLED'):
            config['file']['enabled'] = os.getenv('HFT_FILE_ENABLED').lower() == 'true'
        if os.getenv('HFT_FILE_PATH'):
            config['file']['path'] = os.getenv('HFT_FILE_PATH')
        if os.getenv('HFT_FILE_MIN_LEVEL'):
            config['file']['min_level'] = os.getenv('HFT_FILE_MIN_LEVEL')
        
        # Prometheus overrides
        if os.getenv('HFT_PROMETHEUS_ENABLED'):
            config['prometheus']['enabled'] = os.getenv('HFT_PROMETHEUS_ENABLED').lower() == 'true'
        
        return config
    
    @classmethod
    def setup_logging(cls):
        """Setup logging with environment-aware configuration."""
        config = cls.get_environment_config()
        LoggerFactory.configure_defaults(config)
    
    @classmethod
    def get_module_logger(cls, module_name: str, module_overrides: Dict[str, Any] = None):
        """Get logger with environment and module-specific configuration."""
        
        # Start with environment config
        base_config = cls.get_environment_config()
        
        # Apply module-specific overrides
        if module_overrides:
            # Merge module overrides into base config
            config = {**base_config, 'logger_config': module_overrides}
        else:
            config = base_config
        
        # Check for module-specific environment variables
        env_prefix = f"HFT_MODULE_{module_name.upper().replace('.', '_')}"
        
        if os.getenv(f"{env_prefix}_LEVEL"):
            config.setdefault('logger_config', {})['min_level'] = os.getenv(f"{env_prefix}_LEVEL")
        
        if os.getenv(f"{env_prefix}_FILE"):
            config.setdefault('logger_config', {})['file_path'] = os.getenv(f"{env_prefix}_FILE")
        
        return get_logger(module_name, config)

# Auto-setup on import
EnvironmentConfigManager.setup_logging()

# Usage examples
mexc_logger = EnvironmentConfigManager.get_module_logger(
    'mexc.websocket',
    {'min_level': 'DEBUG', 'file_path': 'logs/mexc_ws.log'}
)

trading_logger = EnvironmentConfigManager.get_module_logger(
    'trading.orders',
    {'performance_tracking': True, 'correlation_tracking': True}
)
```

### Quick Configuration Commands

#### Development Quick Setup

```bash
# Quick development setup with debug logging
export ENVIRONMENT=dev
export HFT_CONSOLE_ENABLED=true
export HFT_CONSOLE_COLOR=true  
export HFT_CONSOLE_MIN_LEVEL=DEBUG
export HFT_FILE_ENABLED=true
export HFT_FILE_MIN_LEVEL=INFO
```

#### Production Quick Setup

```bash
# Quick production setup with minimal logging
export ENVIRONMENT=prod
export HFT_CONSOLE_ENABLED=false
export HFT_FILE_ENABLED=true
export HFT_FILE_PATH=/var/log/hft/prod.log
export HFT_FILE_FORMAT=json
export HFT_FILE_MIN_LEVEL=WARNING
export HFT_PROMETHEUS_ENABLED=true
export HFT_PROMETHEUS_URL=http://monitoring:9091
```

#### Testing Quick Setup

```bash
# Quick testing setup with minimal noise
export ENVIRONMENT=test
export HFT_CONSOLE_ENABLED=true
export HFT_CONSOLE_COLOR=false
export HFT_CONSOLE_MIN_LEVEL=WARNING
export HFT_FILE_ENABLED=false
export HFT_PROMETHEUS_ENABLED=false
```

#### Module-Specific Debugging

```bash
# Debug specific exchange issues
export HFT_MODULE_MEXC_WEBSOCKET_LEVEL=DEBUG
export HFT_MODULE_MEXC_WEBSOCKET_FILE=logs/mexc_debug.log

# Debug trading execution
export HFT_MODULE_TRADING_ORDERS_LEVEL=DEBUG
export HFT_MODULE_TRADING_ORDERS_FILE=logs/trading_debug.log

# Reduce arbitrage detector noise
export HFT_MODULE_ARBITRAGE_DETECTOR_LEVEL=ERROR
```

### 4. Tag-Based Log Level Configuration  

Configure log levels based on hierarchical tags for fine-grained control:

```python
# Hierarchical tag structure: [exchange, api_type, transport, strategy_type]
from core.logging import get_strategy_logger

# Create loggers with different tag combinations
mexc_ws_logger = get_strategy_logger('ws.mexc.public', ['mexc', 'public', 'ws', 'market_data'])
gateio_rest_logger = get_strategy_logger('rest.gateio.private', ['gateio', 'private', 'rest', 'trading'])
arbitrage_logger = get_strategy_logger('arbitrage.detector', ['core', 'arbitrage', 'engine', 'detector'])

# Tags enable precise routing and filtering
mexc_ws_logger.info("WebSocket connection established", symbol="BTC/USDT")
arbitrage_logger.info("Opportunity detected", exchange_pair="mexc-gateio", spread=0.025)
```

## File Logging Configuration

### Basic File Logging Setup

```yaml
logging:
  file:
    enabled: true                    # Enable file logging
    path: logs/hft.log              # Log file location
    format: text                     # text or json format
    min_level: INFO                  # Minimum level for file output
    max_size_mb: 100                 # File size before rotation
    backup_count: 5                  # Number of backup files to keep
```

## Metrics Logging Configuration

The HFT system provides built-in metrics collection through Prometheus integration, enabling real-time monitoring of trading performance, system health, and operational metrics.

### Basic Metrics Setup via config.yaml

```yaml
logging:
  # Prometheus metrics collection
  prometheus:
    enabled: true                    # Enable metrics collection
    push_gateway_url: http://localhost:9091  # Prometheus pushgateway URL
    job_name: hft_arbitrage         # Job identifier in Prometheus
    batch_size: 100                 # Metrics per batch
    flush_interval: 5.0             # Seconds between metric flushes
    
    # Metric filtering and routing
    include_tags: true              # Include hierarchical tags in metrics
    metric_prefix: hft_arbitrage    # Prefix for all metrics
    
    # Performance optimization
    buffer_size: 5000               # Metrics buffer size
    compression: gzip               # Compress metrics data
    timeout_seconds: 10             # Request timeout
```

### Advanced Metrics Configuration

```yaml
logging:
  prometheus:
    enabled: true
    push_gateway_url: http://prometheus-gateway:9091
    job_name: hft_arbitrage_prod
    
    # Batch processing configuration
    batch_size: 200                 # Larger batches for production
    flush_interval: 10.0            # Less frequent flushes
    max_retries: 3                  # Retry failed pushes
    
    # Metric categorization
    metric_categories:
      trading:
        enabled: true
        prefix: trading              # trading_orders_placed_total
        tags: ["exchange", "symbol", "order_type"]
        
      performance:
        enabled: true
        prefix: perf                 # perf_latency_seconds
        tags: ["component", "operation"]
        
      system:
        enabled: true
        prefix: sys                  # sys_memory_usage_bytes
        tags: ["component", "resource_type"]
        
      arbitrage:
        enabled: true
        prefix: arb                  # arb_opportunities_detected_total
        tags: ["exchange_pair", "symbol"]
    
    # Histogram configuration for latency tracking
    histograms:
      enabled: true
      buckets: [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
      
    # Health check metrics
    health_metrics:
      enabled: true
      interval_seconds: 30          # Health metrics frequency
      include_system_metrics: true  # CPU, memory, disk usage
```

### Environment-Specific Metrics Configuration

#### Development Environment
```yaml
# config.yaml for development
logging:
  prometheus:
    enabled: true                   # Enable for testing
    push_gateway_url: http://localhost:9091
    job_name: hft_arbitrage_dev
    batch_size: 50                  # Smaller batches
    flush_interval: 2.0             # More frequent flushes for debugging
    metric_categories:
      trading:
        enabled: true
      performance:
        enabled: true               # Full performance tracking in dev
      system:
        enabled: false              # Disable system metrics in dev
```

#### Production Environment  
```yaml
# config.yaml for production
logging:
  prometheus:
    enabled: true
    push_gateway_url: http://monitoring-gateway:9091
    job_name: hft_arbitrage_prod
    batch_size: 500                 # Large batches for efficiency
    flush_interval: 30.0            # Less frequent flushes
    
    # Production-optimized settings
    compression: gzip
    timeout_seconds: 15
    max_retries: 5
    
    metric_categories:
      trading:
        enabled: true               # Critical for trading monitoring
      performance:
        enabled: true               # Performance tracking essential
      system:
        enabled: true               # System health monitoring
      arbitrage:
        enabled: true               # Business logic monitoring
    
    histograms:
      enabled: true
      # Production-tuned buckets for sub-millisecond tracking
      buckets: [0.0001, 0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.5, 1.0]
```

#### Testing Environment
```yaml
# config.yaml for testing
logging:
  prometheus:
    enabled: false                  # Usually disabled in tests
    # Or minimal configuration for integration tests:
    # enabled: true
    # push_gateway_url: http://test-prometheus:9091
    # job_name: hft_arbitrage_test
    # batch_size: 10
    # flush_interval: 1.0
```

### Metrics Usage Examples

#### Basic Metrics Logging

```python
from core.logging import get_logger

# Create logger with metrics capability
logger = get_logger('trading.orders')

# Counter metrics - track counts
logger.counter('orders_placed_total', 1, 
              exchange='mexc', 
              symbol='BTC/USDT', 
              order_type='limit')

logger.counter('errors_total', 1,
              component='websocket',
              error_type='connection_lost')

# Gauge metrics - track current values
logger.gauge('account_balance_usd', 50000.0,
            exchange='mexc',
            currency='USDT')

logger.gauge('open_positions_count', 5,
            exchange='gateio')

# Histogram metrics - track distributions
logger.histogram('order_execution_time_seconds', 0.045,
                exchange='mexc',
                order_type='market')

logger.histogram('api_response_time_seconds', 0.023,
                endpoint='/api/v3/order',
                method='POST')

# Direct metric logging
logger.metric('latency_ms', 12.5,
             operation='place_order',
             exchange='mexc')
```

#### Advanced Metrics with Tags

```python
from core.logging import get_strategy_logger

# Create strategy logger with hierarchical tags
tags = ['mexc', 'private', 'ws', 'trading']
logger = get_strategy_logger('ws.trading.mexc.private', tags)

# Metrics automatically include tag context
logger.counter('websocket_messages_received_total', 1,
              message_type='orderbook_update',
              symbol='BTC/USDT')

logger.histogram('message_processing_time_seconds', 0.002,
                message_type='trade_update',
                symbol='ETH/USDT')

# Business logic metrics
arbitrage_logger = get_logger('arbitrage.detector')
arbitrage_logger.counter('opportunities_detected_total', 1,
                        exchange_pair='mexc-gateio',
                        symbol='BTC/USDT',
                        profit_bps=125)

arbitrage_logger.gauge('current_spread_bps', 85,
                      exchange_pair='mexc-gateio',
                      symbol='BTC/USDT')
```

#### Performance Metrics with Timing

```python
from core.logging import get_logger, LoggingTimer
import time

logger = get_logger('performance.trading')

# Automatic timing with context manager
with LoggingTimer(logger, "complete_arbitrage_cycle") as timer:
    # Perform arbitrage operations
    await detect_opportunity()
    await place_orders()
    await monitor_execution()
    
    # Timer automatically creates histogram metric:
    # complete_arbitrage_cycle_seconds{component="performance.trading"}

# Manual timing for complex scenarios
start_time = time.time()

# Perform operation
result = await execute_trading_strategy()

# Log timing manually
duration_seconds = time.time() - start_time
logger.histogram('trading_strategy_execution_seconds', duration_seconds,
                strategy_type='arbitrage',
                success=str(result.success),
                exchange_count=result.exchanges_used)

# High-frequency metrics (use sparingly)
logger.metric('tick_processing_latency_us', 247,  # microseconds
             exchange='mexc',
             data_type='orderbook')
```

#### System Health Metrics

```python
import psutil
from core.logging import get_logger

health_logger = get_logger('system.health')

# System resource metrics
health_logger.gauge('cpu_usage_percent', psutil.cpu_percent())
health_logger.gauge('memory_usage_bytes', psutil.virtual_memory().used)
health_logger.gauge('disk_usage_percent', psutil.disk_usage('/').percent)

# Application-specific health metrics
health_logger.gauge('active_websocket_connections', connection_count,
                   component='websocket_manager')

health_logger.gauge('message_queue_size', queue_size,
                   queue_type='orderbook_updates')

health_logger.counter('circuit_breaker_triggered_total', 1,
                     component='risk_manager',
                     reason='max_loss_exceeded')
```

### Metrics Best Practices

#### 1. Choose Appropriate Metric Types

```python
# COUNTER: Always increasing values
logger.counter('orders_placed_total', 1)        # ✓ Good
logger.counter('current_price', 50000)          # ✗ Bad - use gauge

# GAUGE: Current state/level
logger.gauge('account_balance_usd', 25000)      # ✓ Good
logger.gauge('orders_processed_today', count)   # ✗ Bad - use counter

# HISTOGRAM: Distributions and timing
logger.histogram('latency_seconds', 0.045)     # ✓ Good
logger.histogram('account_id', 12345)          # ✗ Bad - not a distribution
```

#### 2. Use Meaningful Tags

```python
# Good: Descriptive tags that enable filtering
logger.counter('api_requests_total', 1,
              exchange='mexc',
              endpoint='/api/v3/order',
              method='POST',
              status_code='200')

# Bad: Too many tags (high cardinality)
logger.counter('requests_total', 1,
              user_id='12345',           # ✗ High cardinality
              request_id='abc-123',      # ✗ Unique per request
              timestamp='1640995200')    # ✗ Always different

# Bad: Meaningless tags
logger.counter('events_total', 1,
              tag1='value1',             # ✗ Generic
              tag2='value2')             # ✗ Generic
```

#### 3. Optimize for HFT Performance

```python
# Good: Minimal metrics in hot paths
def process_orderbook_update(data):
    # Hot path - no logging, minimal metrics
    process_data(data)
    
    # Single metric at the end
    logger.counter('orderbook_updates_processed_total', 1,
                  exchange=data.exchange)

# Bad: Excessive metrics in hot paths
def process_orderbook_update_bad(data):
    logger.metric('processing_start_timestamp', time.time())  # ✗ Hot path
    logger.counter('function_called_total', 1)               # ✗ Unnecessary
    
    for item in data.items:
        logger.counter('item_processed', 1)                  # ✗ Loop metrics
    
    logger.metric('processing_end_timestamp', time.time())   # ✗ Hot path
```

#### 4. Use Batch Metrics for High-Frequency Operations

```python
# Good: Batch high-frequency operations
def process_message_batch(messages):
    start_time = time.time()
    processed_count = 0
    error_count = 0
    
    for message in messages:
        try:
            process_message(message)  # No metrics here
            processed_count += 1
        except Exception:
            error_count += 1
    
    # Single batch metric
    duration = time.time() - start_time
    logger.counter('messages_processed_total', processed_count)
    logger.counter('messages_failed_total', error_count)
    logger.histogram('batch_processing_seconds', duration,
                    batch_size=len(messages))

# Bad: Individual metrics per message
def process_message_batch_bad(messages):
    for message in messages:
        start = time.time()                               # ✗ Per-message timing
        process_message(message)
        logger.histogram('message_time', time.time() - start)  # ✗ High frequency
```

### Prometheus Stack Setup

#### 1. Start Prometheus Infrastructure

```bash
# Start Prometheus + Grafana stack
docker-compose -f docker/docker-compose.prometheus.yml up -d

# Verify services
docker ps | grep -E "(prometheus|grafana|pushgateway)"
```

#### 2. Configure Pushgateway

```yaml
# docker/docker-compose.prometheus.yml
version: '3.8'
services:
  pushgateway:
    image: prom/pushgateway:latest
    ports:
      - "9091:9091"
    command:
      - '--web.listen-address=0.0.0.0:9091'
      - '--persistence.file=/data/pushgateway.data'
      - '--persistence.interval=5m'
    volumes:
      - pushgateway_data:/data

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
```

#### 3. Access Monitoring Dashboards

```bash
# Prometheus UI
open http://localhost:9090

# Grafana dashboards
open http://localhost:3000
# Login: admin/admin

# Pushgateway metrics
open http://localhost:9091
```

#### 4. Query Examples

```promql
# Prometheus queries for HFT metrics

# Order execution rate
rate(trading_orders_placed_total[1m])

# Average latency over 5 minutes
rate(perf_latency_seconds_sum[5m]) / rate(perf_latency_seconds_count[5m])

# Error rate by exchange
rate(errors_total[1m]) by (exchange)

# 95th percentile latency
histogram_quantile(0.95, rate(api_response_time_seconds_bucket[5m]))

# Active arbitrage opportunities
arb_opportunities_detected_total - arb_opportunities_executed_total
```

### Advanced File Logging Configuration

```yaml
logging:
  file:
    enabled: true
    path: logs/hft.log
    format: json                     # Use JSON for structured logging
    min_level: WARNING               # Only log warnings and above to file
    max_size_mb: 50                  # Smaller files for easier management
    backup_count: 10                 # Keep more backup files
    
    # Additional file backends for specific components
    audit:
      enabled: true
      path: logs/audit.log          # Separate audit trail
      format: json
      min_level: INFO
      
    errors:
      enabled: true  
      path: logs/errors.log         # Separate error log
      format: text
      min_level: ERROR
```

### Component-Specific File Logging

Configure different log files for different components:

```python
# Create loggers that write to specific files
from core.logging import get_logger

# Trading operations logger - writes to trading.log
trading_config = {
    'logger_config': {
        'file_path': 'logs/trading.log',
        'min_level': 'INFO'
    }
}
trading_logger = get_logger('trading.operations', trading_config)

# WebSocket logger - writes to websocket.log  
ws_config = {
    'logger_config': {
        'file_path': 'logs/websocket.log',
        'min_level': 'DEBUG'
    }
}
ws_logger = get_logger('websocket.manager', ws_config)

# Error logger - writes to errors.log
error_config = {
    'logger_config': {
        'file_path': 'logs/errors.log', 
        'min_level': 'ERROR'
    }
}
error_logger = get_logger('error.handler', error_config)
```

## Key Features

### 1. Factory-Based Logger Injection
- **Automatic dependency injection** across all components
- **Hierarchical tagging system** for precise metrics routing
- **Type-safe logger creation** via factory patterns

### 2. Performance Optimized
- **<1ms logging latency** (HFT compliant)
- **170,000+ messages/second** sustained throughput  
- **Async dispatch** for non-blocking operation
- **Ring buffer** with configurable size for memory efficiency

### 3. Multi-Backend Architecture
- **Console**: Colored output for development
- **File**: Rotating file logs with size limits
- **Prometheus**: Metrics collection and monitoring
- **Audit**: Compliance and trading operation tracking

### 4. Flexible Configuration
- **YAML-based configuration** - no code changes needed
- **Environment-specific settings** (dev, prod, test)
- **Runtime configuration updates** via factory methods

## Usage Examples

### Basic Logging

```python
from core.logging import get_logger

logger = get_logger('my.component')

# Standard log levels
logger.debug('Debug information')
logger.info('Information message')
logger.warning('Warning message')
logger.error('Error occurred')
logger.critical('Critical issue')

# With context data
logger.info('Order placed', order_id=123, exchange='mexc')
```

### Performance Metrics

```python
# Log metrics (sent to Prometheus if enabled)
logger.metric('latency_ms', 1.23, operation='place_order')
logger.counter('orders_placed', 1, exchange='mexc')

# Timing operations
with logger.timer('database_query'):
    # Code to time
    pass
```

### Component-Specific Loggers

```python
# Exchange logger
from core.logging import get_exchange_logger
logger = get_exchange_logger('mexc', 'websocket')

# Arbitrage logger  
from core.logging import get_arbitrage_logger
logger = get_arbitrage_logger('strategy_1')
```

## Environment-Specific Configuration

### Development Environment (default)

Optimized for development with maximum visibility:

```yaml
# config.yaml for development
environment:
  name: dev
  debug: true
  log_level: DEBUG

logging:
  console:
    enabled: true
    color: true                      # Colored output for readability
    include_context: true            # Show all context data
    min_level: DEBUG                 # Show everything in console
    
  file:
    enabled: true
    path: logs/dev.log
    format: text                     # Human-readable format
    min_level: INFO                  # File logs start at INFO
    max_size_mb: 50
    backup_count: 3
    
  prometheus:
    enabled: false                   # Usually disabled in dev
    
  performance:
    buffer_size: 5000                # Smaller buffer for responsiveness
    batch_size: 25
```

### Production Environment

Optimized for performance and storage efficiency:

```yaml
# config.yaml for production
environment:
  name: prod
  debug: false
  log_level: INFO

logging:
  console:
    enabled: false                   # No console output in production
    
  file:
    enabled: true
    path: /var/log/hft/prod.log     # System log directory
    format: json                     # Structured logging for parsing
    min_level: WARNING               # Only important messages
    max_size_mb: 200                 # Larger files
    backup_count: 10                 # More backups
    
  prometheus:
    enabled: true                    # Enable metrics collection
    push_gateway_url: http://prometheus:9091
    job_name: hft_arbitrage_prod
    batch_size: 200                  # Larger batches for efficiency
    flush_interval: 10.0
    
  performance:
    buffer_size: 20000               # Larger buffer for throughput
    batch_size: 100
    correlation_tracking: true
    performance_tracking: true
```

### Testing Environment

Optimized for CI/CD and automated testing:

```yaml
# config.yaml for testing
environment:
  name: test
  debug: false
  log_level: WARNING

logging:
  console:
    enabled: true
    color: false                     # No colors for CI/CD logs
    include_context: false           # Minimal context for clean output
    min_level: WARNING               # Reduce noise in test output
    
  file:
    enabled: false                   # Usually disabled in tests
    
  prometheus:
    enabled: false                   # Disabled in tests
    
  performance:
    buffer_size: 1000                # Small buffer for tests
    batch_size: 10
```

## Real-World Configuration Examples

### High-Frequency Trading Production Setup

```yaml
# Production HFT configuration
environment:
  name: prod
  log_level: ERROR                   # Minimal logging for maximum performance

logging:
  console:
    enabled: false                   # No console in HFT prod
    
  file:
    enabled: true
    path: /var/log/hft/trading.log
    format: json
    min_level: ERROR                 # Only errors and critical
    max_size_mb: 500                 # Large files for burst logging
    backup_count: 20
    
  prometheus:
    enabled: true
    push_gateway_url: http://monitoring:9091
    job_name: hft_trading
    batch_size: 500                  # Large batches
    flush_interval: 30.0             # Less frequent flushes
    
  performance:
    buffer_size: 50000               # Very large buffer
    batch_size: 200
    correlation_tracking: false      # Disable for max performance
    performance_tracking: true       # Keep metrics only
```

### Development with Debugging Setup

```yaml
# Development with enhanced debugging
environment:
  name: dev
  debug: true
  log_level: DEBUG

logging:
  console:
    enabled: true
    color: true
    include_context: true
    min_level: DEBUG
    
  file:
    enabled: true
    path: logs/debug.log
    format: text
    min_level: DEBUG                 # Log everything to file
    max_size_mb: 100
    backup_count: 5
    
  # Additional file for specific components
  audit:
    enabled: true
    path: logs/trading_audit.log
    format: json
    min_level: INFO
    
  performance:
    buffer_size: 10000
    batch_size: 50
    correlation_tracking: true       # Full tracking in dev
    performance_tracking: true
```

## Prometheus Integration

To enable metrics collection:

1. Enable in config.yaml:
```yaml
logging:
  prometheus:
    enabled: true
```

2. Start Prometheus stack:
```bash
docker-compose -f docker/docker-compose.prometheus.yml up -d
```

3. Access dashboards:
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000

## Troubleshooting

### No Console Output

1. Check that console is enabled in config.yaml:
```yaml
logging:
  console:
    enabled: true
    min_level: DEBUG  # Ensure level is appropriate
```

2. Verify environment log level:
```yaml
environment:
  log_level: DEBUG    # Must be at or below console min_level
```

3. Check if messages are being filtered by level:
```python
# Test with different log levels
logger.critical("This should always appear")
logger.error("This appears if min_level <= ERROR")
logger.info("This appears if min_level <= INFO")
```

### Log Files Not Created

1. Verify file backend configuration:
```yaml
logging:
  file:
    enabled: true
    path: logs/hft.log  # Check path exists and is writable
```

2. Ensure directory exists:
```bash
mkdir -p logs
chmod 755 logs
```

3. Check file permissions and disk space:
```bash
df -h                           # Check disk space
ls -la logs/                   # Check permissions
```

### High Memory Usage

1. Adjust performance settings:
```yaml
logging:
  performance:
    buffer_size: 5000  # Reduce buffer size
    batch_size: 25     # Smaller batches
```

2. Disable unnecessary features:
```yaml
logging:
  performance:
    correlation_tracking: false  # Disable if not needed
    performance_tracking: false  # Disable if not needed
```

3. Increase flush frequency:
```yaml
logging:
  prometheus:
    flush_interval: 1.0          # Flush more frequently
```

### Log Messages Not Appearing in Files

1. Check log level hierarchy:
```yaml
# These must be compatible:
environment:
  log_level: INFO     # Global minimum
logging:
  file:
    min_level: DEBUG  # Backend minimum (should be >= global)
```

2. Verify component-specific configuration:
```python
# Check if component has its own min_level override
config = {
    'logger_config': {
        'min_level': 'WARNING'  # This overrides global settings
    }
}
logger = get_logger('component', config)
```

### Performance Issues

1. Check if async dispatch is working:
```python
# Verify logger is using async backend
from core.logging import get_logger
logger = get_logger('performance.test')

# This should be fast (<1ms)
import time
start = time.time()
logger.info("Performance test message")
duration = time.time() - start
print(f"Log operation took: {duration*1000:.3f}ms")
```

2. Monitor buffer overflow:
```yaml
logging:
  performance:
    buffer_size: 20000  # Increase if messages are being dropped
```

## Best Practices

### 1. Use Structured Logging
Always include context as keyword arguments rather than string formatting:

```python
# Good: Structured logging
logger.info('Order executed', 
           order_id=123, 
           price=50000, 
           exchange='mexc',
           symbol='BTC/USDT',
           execution_time_ms=45.2)

# Bad: String formatting
logger.info(f'Order {123} executed at price {50000} on mexc')
```

### 2. Choose Appropriate Log Levels

Follow this hierarchy for consistent logging:

```python
# CRITICAL: System failures, trading halts
logger.critical('Exchange connection lost', exchange='mexc', retry_count=5)

# ERROR: Errors that need immediate attention  
logger.error('Order placement failed', order_id=123, error_code='INSUFFICIENT_BALANCE')

# WARNING: Important warnings, degraded performance
logger.warning('High latency detected', latency_ms=150, threshold_ms=100)

# INFO: General information, successful operations
logger.info('Order executed successfully', order_id=123, filled_quantity=1.5)

# DEBUG: Detailed debugging, development only
logger.debug('WebSocket message received', message_type='orderbook', symbol='BTC/USDT')
```

### 3. Use Hierarchical Component Naming

Organize loggers in a clear hierarchy:

```python
# Exchange components
mexc_ws_logger = get_logger('exchanges.mexc.websocket.public')
gateio_rest_logger = get_logger('exchanges.gateio.rest.private')

# Arbitrage components  
detector_logger = get_logger('arbitrage.detector.opportunity')
executor_logger = get_logger('arbitrage.executor.orders')

# Core system components
config_logger = get_logger('core.config.manager')
database_logger = get_logger('core.database.connection')
```

### 4. Optimize for HFT Performance

Avoid logging in hot paths - use metrics instead:

```python
# Bad: Logging in tight loop (kills performance)
for order in orders:
    logger.debug(f'Processing order {order.id}')  # NEVER do this

# Good: Aggregate logging and use metrics
start_time = time.time()
processed_count = 0

for order in orders:
    # Process order (no logging here)
    processed_count += 1

# Log summary after loop
duration_ms = (time.time() - start_time) * 1000
logger.info('Order batch processed', 
           count=processed_count, 
           duration_ms=duration_ms)

# Use metrics for high-frequency data
logger.metric('orders_processed_per_second', processed_count / (duration_ms / 1000))
```

### 5. Use Factory Pattern Correctly

Always use the factory pattern for logger creation:

```python
# Correct: Factory pattern with dependency injection
class MexcWebSocketClient:
    def __init__(self, config, logger=None):
        # Factory injection pattern
        if logger is None:
            tags = ['mexc', 'public', 'ws', 'connection']
            logger = get_strategy_logger('ws.connection.mexc.public', tags)
        self.logger = logger

# Incorrect: Direct logger creation
class BadExample:
    def __init__(self):
        self.logger = get_logger('some.component')  # No factory injection
```

### 6. Environment-Specific Configuration

Configure logging appropriately for each environment:

```python
# Development: Maximum visibility
if environment == 'dev':
    - console.min_level = DEBUG
    - file.min_level = INFO  
    - include all context data

# Production: Performance optimized
if environment == 'prod':
    - console.enabled = false
    - file.min_level = WARNING
    - large buffer sizes
    - prometheus enabled

# Testing: Minimal noise
if environment == 'test':
    - console.min_level = WARNING
    - no file logging
    - no colors for CI/CD
```

### 7. Use Performance Tracking

Leverage built-in performance tracking:

```python
from core.logging import LoggingTimer

# Automatic timing with context manager
with LoggingTimer(logger, "database_query") as timer:
    result = await database.execute_query(sql)
    # Automatically logs query duration

# Manual timing for complex operations
logger.performance_start("arbitrage_cycle", correlation_id="abc123")
# ... perform arbitrage operations ...
logger.performance_end("arbitrage_cycle", 
                      correlation_id="abc123",
                      profit_usd=45.67,
                      exchanges_used=2)
```

### 8. Handle Errors Properly

Always include relevant context when logging errors:

```python
try:
    await exchange.place_order(order)
except Exception as e:
    logger.error('Order placement failed',
                exchange='mexc',
                order_id=order.id,
                symbol=order.symbol,
                error_type=type(e).__name__,
                error_message=str(e),
                stack_trace=traceback.format_exc())
```

## Migration from Standard Logging

If migrating from Python's standard logging:

```python
# Old
import logging
logger = logging.getLogger(__name__)

# New  
from core.logging import get_logger
logger = get_logger(__name__)
```

All method signatures remain the same (`debug`, `info`, `warning`, `error`, `critical`).