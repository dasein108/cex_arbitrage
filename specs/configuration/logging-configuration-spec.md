# Logging Configuration Specification

Complete specification for the LoggingConfigManager that integrates with the HFT logging system and provides environment-specific configuration for ultra-high-performance logging operations.

## Overview

The **LoggingConfigManager** provides specialized configuration management for the HFT logging system, supporting multiple backends, environment-specific settings, and factory-based logger injection throughout the codebase. Designed for sub-microsecond logging operations with comprehensive backend routing.

## Architecture

### Core Design Principles

1. **HFT Performance Compliance** - Sub-microsecond logging with ring buffer architecture
2. **Multi-Backend Support** - Console, file, Prometheus, audit, and Python logging bridge
3. **Environment-Specific Configuration** - Development vs production logging optimization
4. **Factory-Based Injection** - Hierarchical logger creation throughout codebase
5. **Intelligent Routing** - Message routing based on content, level, and environment
6. **Minimal Configuration Overhead** - Simple, trust-based configuration parsing

### Integration with HFT Logging System
```
LoggingConfigManager → HFTLogger Configuration → Backend Router → Output Targets
        ↓                      ↓                      ↓              ↓
Config Parsing → Ring Buffer Setup → Message Routing → Environment Output
```

## LoggingConfigManager Class Specification

### Class Definition
```python
class LoggingConfigManager:
    """
    Simple logging configuration manager.
    
    Provides specialized configuration management for:
    - HFT logging system integration
    - Environment-specific backend configuration
    - Performance optimization settings
    - Factory-based logger injection support
    - Multi-backend routing and output
    """
    
    def __init__(self, config_data: Dict[str, Any]):
        self.config_data = config_data
```

### Configuration Access Methods

#### Primary Configuration Access
```python
def get_logging_config(self) -> Dict[str, Any]:
    """
    Get logging configuration from config.yaml. Trust config, fail fast.
    
    Returns:
        Dictionary with logging configuration settings including:
        - backends: Backend-specific configuration (console, file, prometheus, audit)
        - hft_settings: Performance optimization settings
        - environment: Environment-specific overrides
    """
    return self.config_data.get('logging', self._get_default_config())

def _get_default_config(self) -> Dict[str, Any]:
    """
    Simple default configuration for development environments.
    
    Returns:
        Default logging configuration with console and file backends
    """
    return {
        'backends': {
            'console': {
                'enabled': True,
                'level': 'DEBUG',
                'colored_output': True
            },
            'file': {
                'enabled': True,
                'level': 'INFO',
                'file_path': 'logs/hft.log'
            }
        },
        'hft_settings': {
            'ring_buffer_size': 10000,
            'batch_size': 50
        }
    }
```

## HFT Logging System Integration

### Backend Configuration Structure

#### Console Backend Configuration
```yaml
backends:
  console:
    enabled: true
    level: DEBUG  # DEBUG, INFO, WARNING, ERROR
    colored_output: true
    structured: true  # Include structured data in output
    timestamp_format: "%Y-%m-%d %H:%M:%S.%f"
    include_tags: true
    max_message_length: 1000
```

#### File Backend Configuration
```yaml
backends:
  file:
    enabled: true
    level: INFO
    file_path: "logs/hft.log"
    format: "text"  # text, json
    rotation: "daily"  # daily, size, none
    max_file_size: "100MB"
    backup_count: 7
    compression: true
```

#### Prometheus Backend Configuration
```yaml
backends:
  prometheus:
    enabled: true
    push_gateway_url: "http://monitoring:9091"
    job_name: "hft_arbitrage"
    push_interval: 10  # seconds
    histogram_buckets: [0.001, 0.01, 0.1, 1.0, 10.0]  # milliseconds
    include_exchange_labels: true
```

#### Audit Backend Configuration
```yaml
backends:
  audit:
    enabled: true
    level: INFO
    file_path: "logs/audit.log"
    format: "json"
    include_compliance_fields: true
    retention_days: 365
    encryption: true
```

### HFT Performance Settings

#### Performance Optimization Configuration
```yaml
hft_settings:
  # Ring buffer settings
  ring_buffer_size: 10000  # Number of messages in ring buffer
  batch_size: 50  # Messages per batch processing
  flush_interval_ms: 10  # Milliseconds between flushes
  
  # Performance thresholds
  max_latency_us: 1000  # Maximum logging latency in microseconds
  warning_threshold_us: 500  # Warning threshold for slow logging
  
  # Memory management
  max_memory_mb: 100  # Maximum memory usage for logging
  gc_threshold: 0.8  # Garbage collection threshold
  
  # Error handling
  enable_failover: true  # Enable backend failover
  max_retry_attempts: 3  # Maximum retry attempts for failed operations
```

## Environment-Specific Configuration

### Development Environment Configuration
```yaml
logging:
  backends:
    console:
      enabled: true
      level: DEBUG
      colored_output: true
      structured: true
      include_tags: true
      
    file:
      enabled: true
      level: INFO
      file_path: "logs/dev.log"
      format: "text"
      rotation: "none"
      
    prometheus:
      enabled: true
      push_gateway_url: null  # Pull-based in development
      
  hft_settings:
    ring_buffer_size: 5000
    batch_size: 100
    flush_interval_ms: 100
    max_latency_us: 5000  # More relaxed in development
```

### Production Environment Configuration
```yaml
logging:
  backends:
    console:
      enabled: false  # Disable console in production
      
    file:
      enabled: true
      level: WARNING  # Only warnings and errors
      file_path: "logs/prod.log"
      format: "json"
      rotation: "daily"
      max_file_size: "500MB"
      backup_count: 30
      compression: true
      
    audit:
      enabled: true
      level: INFO
      file_path: "logs/audit.log"
      format: "json"
      include_compliance_fields: true
      retention_days: 2555  # 7 years for compliance
      
    prometheus:
      enabled: true
      push_gateway_url: "http://monitoring:9091"
      job_name: "hft_arbitrage_prod"
      push_interval: 5  # More frequent in production
      histogram_buckets: [0.0001, 0.001, 0.01, 0.1, 1.0]  # Microsecond precision
      
  hft_settings:
    ring_buffer_size: 20000  # Larger buffer for production
    batch_size: 200
    flush_interval_ms: 5  # Faster flushing in production
    max_latency_us: 1000  # Strict latency requirements
    warning_threshold_us: 500
```

### Test Environment Configuration
```yaml
logging:
  backends:
    console:
      enabled: true
      level: ERROR  # Only errors in tests
      colored_output: false  # No colors for test output
      
    file:
      enabled: false  # No file logging in tests
      
    prometheus:
      enabled: false  # No metrics in tests
      
  hft_settings:
    ring_buffer_size: 1000  # Small buffer for tests
    batch_size: 10
    flush_interval_ms: 1000  # Slow flushing in tests
    max_latency_us: 10000  # Relaxed latency in tests
```

## Factory-Based Logger Integration

### Hierarchical Logger Creation

#### Exchange Logger Factory Integration
```python
# Exchange-level logger creation
def get_exchange_logger(exchange_name: str, component_type: str) -> HFTLoggerInterface:
    """
    Create logger for exchange-level components using logging configuration.
    
    Uses logging configuration to determine:
    - Backend routing rules
    - Performance settings
    - Environment-specific behavior
    """
    logging_config = get_logging_config()
    
    return create_hft_logger(
        name=f"exchange.{exchange_name}.{component_type}",
        tags=[exchange_name, component_type],
        config=logging_config
    )

# Strategy-level logger creation  
def get_strategy_logger(strategy_path: str, tags: List[str]) -> HFTLoggerInterface:
    """
    Create logger for strategy components with hierarchical tags.
    
    Applies logging configuration for:
    - Backend selection based on strategy type
    - Performance optimization based on exchange
    - Tag-based routing rules
    """
    logging_config = get_logging_config()
    
    return create_hft_logger(
        name=f"strategy.{strategy_path}",
        tags=tags,
        config=logging_config
    )
```

### Configuration-Driven Logger Behavior

#### Backend Selection Based on Configuration
```python
def create_hft_logger(name: str, tags: List[str], config: Dict[str, Any]) -> HFTLoggerInterface:
    """
    Create HFT logger with configuration-driven backend selection.
    
    Args:
        name: Logger name
        tags: Hierarchical tags for routing
        config: Logging configuration from LoggingConfigManager
        
    Returns:
        HFTLoggerInterface with configured backends
    """
    # Extract backend configuration
    backends_config = config.get('backends', {})
    hft_settings = config.get('hft_settings', {})
    
    # Create logger with configuration
    logger = HFTLogger(
        name=name,
        tags=tags,
        ring_buffer_size=hft_settings.get('ring_buffer_size', 10000),
        batch_size=hft_settings.get('batch_size', 50),
        max_latency_us=hft_settings.get('max_latency_us', 1000)
    )
    
    # Configure backends based on configuration
    for backend_name, backend_config in backends_config.items():
        if backend_config.get('enabled', False):
            backend = create_backend(backend_name, backend_config)
            logger.add_backend(backend)
    
    return logger
```

## Message Routing Configuration

### Intelligent Message Routing Rules

#### Route Configuration
```yaml
routing:
  rules:
    # Console routing (development only)
    - match:
        level: [DEBUG, INFO, WARNING, ERROR]
        environment: development
      backends: [console]
      
    # File routing (warnings and errors)
    - match:
        level: [WARNING, ERROR]
      backends: [file]
      
    # Audit routing (trading events)
    - match:
        tags: [trading, order, balance]
        level: [INFO, WARNING, ERROR]
      backends: [audit]
      
    # Prometheus routing (metrics only)
    - match:
        type: metric
      backends: [prometheus]
      
    # Error routing (multiple backends)
    - match:
        level: ERROR
      backends: [file, audit, console]
```

#### Dynamic Routing Based on Tags
```python
class ConfigurableMessageRouter:
    """Message router that uses configuration to determine backend routing."""
    
    def __init__(self, routing_config: Dict[str, Any]):
        self.routing_rules = routing_config.get('rules', [])
        self.default_backends = routing_config.get('default_backends', ['console'])
    
    def route_message(self, message: LogMessage) -> List[str]:
        """Determine which backends should receive this message based on configuration."""
        backends = set()
        
        # Apply routing rules from configuration
        for rule in self.routing_rules:
            if self._message_matches_rule(message, rule['match']):
                backends.update(rule['backends'])
        
        # Use default backends if no rules matched
        if not backends:
            backends.update(self.default_backends)
        
        return list(backends)
```

## Performance Integration

### HFT Performance Monitoring Configuration

#### Performance Metrics Configuration
```yaml
performance:
  metrics:
    # Latency tracking
    track_latency: true
    latency_percentiles: [50, 95, 99, 99.9]
    latency_bucket_size_us: 100  # Microseconds per bucket
    
    # Throughput tracking
    track_throughput: true
    throughput_window_ms: 1000  # 1 second window
    
    # Memory tracking
    track_memory: true
    memory_check_interval_ms: 5000
    
    # Error tracking
    track_errors: true
    error_categorization: true
```

#### Performance Threshold Configuration
```yaml
performance:
  thresholds:
    # Latency thresholds
    max_logging_latency_us: 1000  # 1ms maximum
    warning_latency_us: 500  # 500μs warning
    critical_latency_us: 2000  # 2ms critical
    
    # Throughput thresholds
    min_throughput_msgs_per_sec: 100000  # 100K msgs/sec minimum
    warning_throughput_msgs_per_sec: 50000  # 50K msgs/sec warning
    
    # Memory thresholds
    max_memory_usage_mb: 100  # 100MB maximum
    warning_memory_usage_mb: 75  # 75MB warning
    
    # Error thresholds
    max_error_rate_percent: 1.0  # 1% maximum error rate
    warning_error_rate_percent: 0.5  # 0.5% warning error rate
```

## Configuration Examples

### Complete Logging Configuration
```yaml
logging:
  # Backend configuration
  backends:
    console:
      enabled: true
      level: DEBUG
      colored_output: true
      structured: true
      timestamp_format: "%Y-%m-%d %H:%M:%S.%f"
      include_tags: true
      max_message_length: 1000
      
    file:
      enabled: true
      level: INFO
      file_path: "logs/hft.log"
      format: "json"
      rotation: "daily"
      max_file_size: "100MB"
      backup_count: 7
      compression: true
      
    prometheus:
      enabled: true
      push_gateway_url: "http://monitoring:9091"
      job_name: "hft_arbitrage"
      push_interval: 10
      histogram_buckets: [0.001, 0.01, 0.1, 1.0, 10.0]
      include_exchange_labels: true
      
    audit:
      enabled: true
      level: INFO
      file_path: "logs/audit.log"
      format: "json"
      include_compliance_fields: true
      retention_days: 365
      encryption: true
  
  # HFT performance settings
  hft_settings:
    ring_buffer_size: 10000
    batch_size: 50
    flush_interval_ms: 10
    max_latency_us: 1000
    warning_threshold_us: 500
    max_memory_mb: 100
    gc_threshold: 0.8
    enable_failover: true
    max_retry_attempts: 3
  
  # Message routing configuration
  routing:
    rules:
      - match:
          level: [DEBUG, INFO, WARNING, ERROR]
          environment: development
        backends: [console]
        
      - match:
          level: [WARNING, ERROR]
        backends: [file]
        
      - match:
          tags: [trading, order, balance]
          level: [INFO, WARNING, ERROR]
        backends: [audit]
        
      - match:
          type: metric
        backends: [prometheus]
        
      - match:
          level: ERROR
        backends: [file, audit, console]
    
    default_backends: [console]
  
  # Performance monitoring
  performance:
    metrics:
      track_latency: true
      latency_percentiles: [50, 95, 99, 99.9]
      track_throughput: true
      track_memory: true
      track_errors: true
      
    thresholds:
      max_logging_latency_us: 1000
      warning_latency_us: 500
      min_throughput_msgs_per_sec: 100000
      max_memory_usage_mb: 100
      max_error_rate_percent: 1.0
```

## Usage Examples

### Basic Logging Configuration Access
```python
from src.config.config_manager import get_config

# Get configuration instance
config = get_config()

# Logging configuration
logging_config = config.get_logging_config()

# Setup HFT logging system with configuration
setup_hft_logging(logging_config)

# Create loggers using factory functions with configuration
exchange_logger = get_exchange_logger('mexc', 'unified_exchange')
strategy_logger = get_strategy_logger('ws.connection.mexc.private', ['mexc', 'private', 'ws', 'connection'])
```

### Environment-Specific Logging Setup
```python
def setup_logging_for_environment(environment: str) -> None:
    """Setup logging based on environment configuration."""
    config = get_config()
    logging_config = config.get_logging_config()
    
    if environment == 'production':
        # Production: File + Audit + Prometheus
        configure_production_logging(logging_config)
    elif environment == 'development':
        # Development: Console + File + Prometheus
        configure_development_logging(logging_config)
    elif environment == 'test':
        # Test: Console errors only
        configure_test_logging(logging_config)

def configure_production_logging(config: Dict[str, Any]) -> None:
    """Configure logging for production environment."""
    # Disable console, enable file/audit/prometheus
    backends = config['backends']
    backends['console']['enabled'] = False
    backends['file']['level'] = 'WARNING'
    backends['audit']['enabled'] = True
    backends['prometheus']['enabled'] = True
    
    # Optimize HFT settings for production
    hft_settings = config['hft_settings']
    hft_settings['ring_buffer_size'] = 20000
    hft_settings['batch_size'] = 200
    hft_settings['flush_interval_ms'] = 5
```

### Performance Monitoring Integration
```python
class LoggingPerformanceMonitor:
    """Monitor logging performance using configuration thresholds."""
    
    def __init__(self, logging_config: Dict[str, Any]):
        self.config = logging_config
        self.performance_config = logging_config.get('performance', {})
        self.thresholds = self.performance_config.get('thresholds', {})
    
    def check_performance_compliance(self, metrics: LoggingMetrics) -> bool:
        """Check if logging performance meets configured thresholds."""
        max_latency = self.thresholds.get('max_logging_latency_us', 1000)
        min_throughput = self.thresholds.get('min_throughput_msgs_per_sec', 100000)
        max_memory = self.thresholds.get('max_memory_usage_mb', 100)
        
        if metrics.avg_latency_us > max_latency:
            logger.warning(f"Logging latency {metrics.avg_latency_us}μs exceeds threshold {max_latency}μs")
            return False
            
        if metrics.throughput_msgs_per_sec < min_throughput:
            logger.warning(f"Logging throughput {metrics.throughput_msgs_per_sec} below threshold {min_throughput}")
            return False
            
        if metrics.memory_usage_mb > max_memory:
            logger.warning(f"Logging memory {metrics.memory_usage_mb}MB exceeds threshold {max_memory}MB")
            return False
        
        return True
```

## Integration Patterns

### Factory Integration with Configuration
```python
# Exchange factory integration
class ExchangeFactory:
    """Exchange factory with logging configuration integration."""
    
    def __init__(self, config: HftConfig):
        self.config = config
        self.logging_config = config.get_logging_config()
    
    def create_exchange(self, exchange_name: str) -> BaseExchange:
        """Create exchange with properly configured logger."""
        # Create logger using configuration
        logger = get_exchange_logger(exchange_name, 'unified_exchange')
        
        # Configure logger performance based on logging config
        hft_settings = self.logging_config.get('hft_settings', {})
        logger.configure_performance(
            max_latency_us=hft_settings.get('max_latency_us', 1000),
            ring_buffer_size=hft_settings.get('ring_buffer_size', 10000)
        )
        
        return ExchangeClass(logger=logger)
```

### Audit Trail Integration
```python
class AuditLogger:
    """Audit logger that uses configuration for compliance settings."""
    
    def __init__(self, logging_config: Dict[str, Any]):
        self.audit_config = logging_config['backends']['audit']
        self.logger = get_logger('audit.compliance')
    
    def log_trading_event(self, event_data: Dict[str, Any]) -> None:
        """Log trading event with compliance fields from configuration."""
        if self.audit_config.get('include_compliance_fields', False):
            event_data.update({
                'compliance_timestamp': time.time(),
                'system_version': VERSION,
                'environment': ENVIRONMENT
            })
        
        self.logger.audit('trading_event', event_data)
```

---

*This Logging Configuration specification provides comprehensive integration with the HFT logging system while supporting environment-specific optimization and factory-based logger injection throughout the codebase.*