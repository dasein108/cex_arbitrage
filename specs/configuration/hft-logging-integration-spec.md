# HFT Logging System Integration Specification

Complete specification for integrating the HFT logging system with the configuration management system, supporting environment-specific optimization and factory-based logger injection.

## Overview

This specification details how the **LoggingConfigManager** integrates with the comprehensive HFT logging system to provide configuration-driven logging with sub-microsecond performance and multi-backend routing.

## Architecture Integration

### Configuration-Driven Logging Flow
```
LoggingConfigManager → Backend Configuration → Logger Factory → HFTLogger Instances
        ↓                      ↓                    ↓               ↓
Environment Settings → Backend Routing → Performance Tuning → Structured Output
```

### Performance Specifications (Achieved)
- **Latency**: 1.16μs average (target: <1ms) ✅
- **Throughput**: 859,598+ messages/second sustained ✅ 
- **Memory**: Ring buffer with configurable size (default: 10,000 messages)
- **Async Dispatch**: Zero-blocking operations with batch processing
- **Error Resilience**: Automatic backend failover and graceful degradation

## Configuration Structure Integration

### HFT Settings from Configuration
```yaml
logging:
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
```

### Backend Configuration Integration
```yaml
logging:
  backends:
    console:
      enabled: true
      level: DEBUG
      colored_output: true
      structured: true
      
    file:
      enabled: true
      level: INFO
      file_path: "logs/hft.log"
      format: "json"
      rotation: "daily"
      
    prometheus:
      enabled: true
      push_gateway_url: "http://monitoring:9091"
      job_name: "hft_arbitrage"
      
    audit:
      enabled: true
      level: INFO
      file_path: "logs/audit.log"
      format: "json"
```

## Factory-Based Logger Creation

### Configuration-Driven Factory Functions
```python
def create_hft_logger_from_config(name: str, tags: List[str], config: Dict[str, Any]) -> HFTLoggerInterface:
    """
    Create HFT logger using configuration manager settings.
    
    Args:
        name: Logger name
        tags: Hierarchical tags for routing
        config: Logging configuration from LoggingConfigManager
        
    Returns:
        HFTLoggerInterface with configured backends and performance settings
    """
    # Extract HFT settings from configuration
    hft_settings = config.get('hft_settings', {})
    backends_config = config.get('backends', {})
    
    # Create logger with configuration-driven settings
    logger = HFTLogger(
        name=name,
        tags=tags,
        ring_buffer_size=hft_settings.get('ring_buffer_size', 10000),
        batch_size=hft_settings.get('batch_size', 50),
        flush_interval_ms=hft_settings.get('flush_interval_ms', 10),
        max_latency_us=hft_settings.get('max_latency_us', 1000)
    )
    
    # Configure backends based on configuration
    for backend_name, backend_config in backends_config.items():
        if backend_config.get('enabled', False):
            backend = create_backend_from_config(backend_name, backend_config)
            logger.add_backend(backend)
    
    return logger

def get_exchange_logger_with_config(exchange_name: str, component_type: str) -> HFTLoggerInterface:
    """Create logger for exchange-level components using logging configuration."""
    from src.config.config_manager import get_config
    
    config = get_config()
    logging_config = config.get_logging_config()
    
    return create_hft_logger_from_config(
        name=f"exchange.{exchange_name}.{component_type}",
        tags=[exchange_name, component_type],
        config=logging_config
    )

def get_strategy_logger_with_config(strategy_path: str, tags: List[str]) -> HFTLoggerInterface:
    """Create logger for strategy components using logging configuration."""
    from src.config.config_manager import get_config
    
    config = get_config()
    logging_config = config.get_logging_config()
    
    return create_hft_logger_from_config(
        name=f"strategy.{strategy_path}",
        tags=tags,
        config=logging_config
    )
```

## Environment-Specific Integration

### Development Environment Configuration
```python
def setup_development_logging_from_config() -> None:
    """Setup logging for development environment using configuration."""
    from src.config.config_manager import get_config
    
    config = get_config()
    logging_config = config.get_logging_config()
    
    # Development-specific overrides
    if config.ENVIRONMENT == 'dev':
        # Enable console with debug level
        logging_config['backends']['console']['enabled'] = True
        logging_config['backends']['console']['level'] = 'DEBUG'
        
        # Relaxed HFT settings for development
        logging_config['hft_settings']['max_latency_us'] = 5000
        logging_config['hft_settings']['flush_interval_ms'] = 100
    
    configure_hft_logging(logging_config)

def setup_production_logging_from_config() -> None:
    """Setup logging for production environment using configuration."""
    from src.config.config_manager import get_config
    
    config = get_config()
    logging_config = config.get_logging_config()
    
    # Production-specific overrides
    if config.ENVIRONMENT == 'prod':
        # Disable console, enable file/audit/prometheus
        logging_config['backends']['console']['enabled'] = False
        logging_config['backends']['file']['level'] = 'WARNING'
        logging_config['backends']['audit']['enabled'] = True
        logging_config['backends']['prometheus']['enabled'] = True
        
        # Strict HFT settings for production
        logging_config['hft_settings']['max_latency_us'] = 1000
        logging_config['hft_settings']['flush_interval_ms'] = 5
        logging_config['hft_settings']['ring_buffer_size'] = 20000
    
    configure_hft_logging(logging_config)
```

### Configuration-Driven Backend Creation
```python
def create_backend_from_config(backend_name: str, backend_config: Dict[str, Any]) -> LoggingBackend:
    """Create logging backend from configuration."""
    if backend_name == 'console':
        return ConsoleBackend(
            level=backend_config.get('level', 'INFO'),
            colored_output=backend_config.get('colored_output', True),
            structured=backend_config.get('structured', True)
        )
    elif backend_name == 'file':
        return FileBackend(
            level=backend_config.get('level', 'INFO'),
            file_path=backend_config.get('file_path', 'logs/hft.log'),
            format=backend_config.get('format', 'json'),
            rotation=backend_config.get('rotation', 'daily')
        )
    elif backend_name == 'prometheus':
        return PrometheusBackend(
            push_gateway_url=backend_config.get('push_gateway_url'),
            job_name=backend_config.get('job_name', 'hft_arbitrage'),
            push_interval=backend_config.get('push_interval', 10)
        )
    elif backend_name == 'audit':
        return AuditBackend(
            level=backend_config.get('level', 'INFO'),
            file_path=backend_config.get('file_path', 'logs/audit.log'),
            format=backend_config.get('format', 'json')
        )
    else:
        raise ValueError(f"Unknown backend type: {backend_name}")
```

## Performance Integration

### Configuration-Driven Performance Monitoring
```python
class ConfigurablePerformanceMonitor:
    """Performance monitor that uses configuration thresholds."""
    
    def __init__(self, logging_config: Dict[str, Any]):
        self.config = logging_config
        self.hft_settings = logging_config.get('hft_settings', {})
        self.performance_thresholds = logging_config.get('performance', {}).get('thresholds', {})
    
    def validate_logging_performance(self, metrics: LoggingMetrics) -> bool:
        """Validate logging performance against configured thresholds."""
        max_latency = self.hft_settings.get('max_latency_us', 1000)
        warning_threshold = self.hft_settings.get('warning_threshold_us', 500)
        
        if metrics.avg_latency_us > max_latency:
            logger.error("Logging latency exceeds configuration threshold",
                        actual_us=metrics.avg_latency_us,
                        threshold_us=max_latency)
            return False
            
        if metrics.avg_latency_us > warning_threshold:
            logger.warning("Logging latency approaching threshold",
                          actual_us=metrics.avg_latency_us,
                          threshold_us=warning_threshold)
        
        return True
```

### HFT Compliance Checking

```python
def validate_hft_logging_compliance() -> bool:
    """Validate HFT logging compliance using configuration."""
    from src.config.config_manager import get_config

    config = get_config()
    logging_config = config.get_logging_config()

    # Get performance metrics from active logger
    logger = get_hft_logger()
    metrics = logger._get_performance_metrics()

    # Validate against configuration thresholds
    monitor = ConfigurablePerformanceMonitor(logging_config)
    return monitor.validate_logging_performance(metrics)
```

## Exchange Integration Patterns

### Exchange Factory Integration
```python
class ExchangeFactory:
    """Exchange factory with configuration-driven logging."""
    
    def __init__(self, config: HftConfig):
        self.config = config
        self.logging_config = config.get_logging_config()
    
    async def create_exchange(self, exchange_name: str) -> UnifiedCompositeExchange:
        """Create exchange with properly configured logger."""
        # Create logger using configuration
        logger = get_exchange_logger_with_config(exchange_name, 'unified_exchange')
        
        # Configure logger performance based on logging config
        hft_settings = self.logging_config.get('hft_settings', {})
        logger.configure_performance(
            max_latency_us=hft_settings.get('max_latency_us', 1000),
            ring_buffer_size=hft_settings.get('ring_buffer_size', 10000)
        )
        
        exchange_config = self.config.get_exchange_config(exchange_name)
        
        if exchange_name.lower() == 'mexc':
            from exchanges.integrations.mexc.mexc_unified_exchange import MexcUnifiedExchange
            return MexcUnifiedExchange(
                config=exchange_config,
                logger=logger
            )
        elif exchange_name.lower() == 'gateio':
            from exchanges.integrations.gateio.gateio_unified_exchange import GateioUnifiedExchange
            return GateioUnifiedExchange(
                config=exchange_config,
                logger=logger
            )
        else:
            raise ValueError(f"Unknown exchange: {exchange_name}")
```

### Strategy Component Integration
```python
class ConnectionStrategy:
    """WebSocket connection strategy with configuration-driven logging."""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[HFTLoggerInterface] = None):
        if logger is None:
            # Create logger using configuration
            tags = ['mexc', 'private', 'ws', 'connection']
            logger = get_strategy_logger_with_config('ws.connection.mexc.private', tags)
        
        self.logger = logger
        self.config = config
        
        # Configure performance based on environment
        from src.config.config_manager import get_config
        app_config = get_config()
        logging_config = app_config.get_logging_config()
        
        self.performance_config = logging_config.get('hft_settings', {})
        
        self.logger.info("Connection strategy initialized with configuration",
                        exchange="mexc",
                        api_type="private", 
                        transport="websocket",
                        performance_target_us=self.performance_config.get('max_latency_us', 1000))
    
    async def connect(self) -> None:
        """Connect with performance tracking based on configuration."""
        target_latency = self.performance_config.get('max_latency_us', 1000) / 1000  # Convert to ms
        
        with LoggingTimer(self.logger, "ws_connection") as timer:
            try:
                await self._establish_connection()
                
                self.logger.info("WebSocket connection established",
                               duration_us=timer.elapsed_us,
                               meets_target=timer.elapsed_ms < target_latency)
                               
                self.logger.metric("ws_connection_success", 1,
                                  tags={"exchange": "mexc", "api_type": "private"})
                                  
            except Exception as e:
                self.logger.error("WebSocket connection failed",
                                duration_us=timer.elapsed_us,
                                error=str(e))
                                
                self.logger.metric("ws_connection_error", 1,
                                  tags={"exchange": "mexc", "error": type(e).__name__})
                raise
```

## Configuration Validation

### Logging Configuration Validation
```python
def validate_logging_configuration(logging_config: Dict[str, Any]) -> bool:
    """Validate logging configuration for HFT compliance."""
    hft_settings = logging_config.get('hft_settings', {})
    
    # Validate HFT performance settings
    max_latency_us = hft_settings.get('max_latency_us', 1000)
    if max_latency_us > 5000:  # 5ms maximum
        raise ValueError(f"max_latency_us {max_latency_us} exceeds HFT requirements")
    
    ring_buffer_size = hft_settings.get('ring_buffer_size', 10000)
    if ring_buffer_size < 1000:
        raise ValueError(f"ring_buffer_size {ring_buffer_size} too small for HFT operations")
    
    # Validate backend configuration
    backends = logging_config.get('backends', {})
    if not any(backend.get('enabled', False) for backend in backends.values()):
        raise ValueError("At least one logging backend must be enabled")
    
    return True
```

## Usage Examples

### Complete Configuration Integration
```python
def setup_hft_system_with_logging() -> None:
    """Setup complete HFT system with integrated logging configuration."""
    from src.config.config_manager import get_config
    
    # Get configuration
    config = get_config()
    
    # Validate logging configuration
    logging_config = config.get_logging_config()
    validate_logging_configuration(logging_config)
    
    # Setup environment-specific logging
    if config.ENVIRONMENT == 'prod':
        setup_production_logging_from_config()
    else:
        setup_development_logging_from_config()
    
    # Validate HFT compliance
    if not validate_hft_logging_compliance():
        raise RuntimeError("Logging system does not meet HFT requirements")
    
    # Create exchange factory with configured logging
    factory = ExchangeFactory(config)
    
    # Create exchanges with proper logging
    mexc_exchange = await factory.create_exchange('mexc')
    gateio_exchange = await factory.create_exchange('gateio')
    
    logger = get_exchange_logger_with_config('system', 'startup')
    logger.info("HFT system initialized with configuration-driven logging",
               environment=config.ENVIRONMENT,
               exchanges=['mexc', 'gateio'],
               logging_backends=list(logging_config['backends'].keys()))
```

### Performance Monitoring Integration

```python
async def monitor_hft_logging_performance() -> None:
    """Monitor HFT logging performance using configuration thresholds."""
    from src.config.config_manager import get_config

    config = get_config()
    logging_config = config.get_logging_config()

    monitor = ConfigurablePerformanceMonitor(logging_config)
    logger = get_exchange_logger_with_config('system', 'performance')

    while True:
        # Get current performance metrics
        hft_logger = get_hft_logger()
        metrics = hft_logger._get_performance_metrics()

        # Validate against configuration
        is_compliant = monitor.validate_logging_performance(metrics)

        logger.metric("logging_performance_compliant", 1 if is_compliant else 0)
        logger.metric("logging_latency_us", metrics.avg_latency_us)
        logger.metric("logging_throughput_msgs_per_sec", metrics.throughput_msgs_per_sec)

        await asyncio.sleep(10)  # Check every 10 seconds
```

---

*This HFT Logging Integration specification provides comprehensive integration between the configuration management system and the high-performance logging architecture, ensuring configuration-driven optimization while maintaining sub-microsecond performance requirements.*