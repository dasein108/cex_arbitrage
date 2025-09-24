# Comprehensive Flexible Logging Implementation Plan

## Overview

Implementation plan for a simple but highly extendable logging system that supports multiple backends (file, Prometheus, third-party services) with factory pattern injection and zero-overhead hot paths.

## Core Requirements

### 1. Simple Interface
- Use as `self.logger` throughout codebase
- Drop-in replacement for Python's logging
- Zero changes to existing logging calls
- Factory pattern injection into all base classes

### 2. Selective Routing
- **Metrics/Latency** → Prometheus (structured data)
- **Warnings/Errors** → File logging (with context)
- **Debug/Info** → Console (DEV only)
- **Audit Events** → Multiple destinations (file + Elasticsearch)

### 3. Performance Requirements
- **Zero formatting overhead** in hot paths
- **Async dispatch** - no blocking
- **Lazy evaluation** - format only when needed
- **Sub-millisecond** log call latency
- **Backwards compatible** with existing Python logging

### 4. Extensibility
- **Pluggable backends** - easy to add new destinations
- **Configurable routing** - rules-based message routing
- **Environment-aware** - different configs for DEV/PROD
- **Context preservation** - correlation IDs, exchange info

## Implementation Phases

### Phase 1: Core Infrastructure (Week 3)

#### 1.1 Base Interfaces (`src/core/logging/interfaces.py`)
```python
class HFTLoggerInterface(ABC):
    """Ultra-lightweight logger interface for injection"""
    
    # Standard logging methods (same API as Python logging)
    def debug(self, msg: str, **context) -> None
    def info(self, msg: str, **context) -> None  
    def warning(self, msg: str, **context) -> None
    def error(self, msg: str, **context) -> None
    def critical(self, msg: str, **context) -> None
    
    # HFT-specific methods
    def metric(self, name: str, value: float, **tags) -> None
    def latency(self, operation: str, duration_ms: float, **tags) -> None
    def audit(self, event: str, **context) -> None
    
    # Context management
    def set_context(self, **context) -> None
    async def flush(self) -> None

class LogBackend(ABC):
    """Abstract backend for pluggable destinations"""
    def should_handle(self, record: LogRecord) -> bool  # Fast filter
    async def write(self, record: LogRecord) -> None    # Format here
    async def flush(self) -> None
```

#### 1.2 Core Logger Implementation (`src/core/logging/hft_logger.py`)
```python
class HFTLogger(HFTLoggerInterface):
    """
    Main logger implementation with async dispatch.
    
    ZERO FORMATTING in hot path - all formatting in backends.
    """
    
    def __init__(self, name: str, backends: List[LogBackend], router: LogRouter):
        self.name = name
        self.backends = backends
        self.router = router
        self.context = {}  # Persistent context
        self._queue = asyncio.Queue(maxsize=10000)
        self._task = asyncio.create_task(self._dispatch_loop())
    
    def debug(self, msg: str, **context):
        # Ultra-fast: create record and queue it
        record = LogRecord(
            timestamp=time.time(),
            level=LogLevel.DEBUG,
            log_type=LogType.TEXT,
            logger_name=self.name,
            message=msg,
            context={**self.context, **context}
        )
        self._queue.put_nowait(record)  # Non-blocking
    
    def metric(self, name: str, value: float, **tags):
        # Direct to metrics backends
        record = LogRecord(
            timestamp=time.time(),
            level=LogLevel.INFO,
            log_type=LogType.METRIC,
            logger_name=self.name,
            message="",
            context=self.context,
            metric_name=name,
            metric_value=value,
            metric_tags=tags
        )
        self._queue.put_nowait(record)
    
    async def _dispatch_loop(self):
        """Background task to process log queue"""
        while True:
            record = await self._queue.get()
            backends = self.router.get_backends(record)
            
            # Dispatch to all matching backends concurrently
            if backends:
                await asyncio.gather(
                    *[backend.write(record) for backend in backends],
                    return_exceptions=True
                )
```

#### 1.3 Essential Backends (`src/core/logging/backends/`)
- **ConsoleBackend** - DEV environment, Python logging compatibility
- **FileBackend** - Warnings/errors with text formatting
- **PrometheusBackend** - Metrics with batching

### Phase 2: Backend Implementations (Week 3)

#### 2.1 File Backend (`src/core/logging/backends/file.py`)
```python
class FileBackend(LogBackend):
    """
    High-performance file logging with rotation.
    Handles text formatting only when writing.
    """
    
    def should_handle(self, record: LogRecord) -> bool:
        return (record.level >= LogLevel.WARNING and 
                record.log_type in [LogType.TEXT, LogType.AUDIT])
    
    async def write(self, record: LogRecord) -> None:
        # Format ONLY when writing (not in hot path)
        if self.format_type == 'json':
            formatted = self._format_json(record)
        else:
            formatted = self._format_text(record)
        
        async with aiofiles.open(self.file_path, 'a') as f:
            await f.write(formatted + '\n')
    
    def _format_text(self, record: LogRecord) -> str:
        # Human-readable format with context
        dt = datetime.fromtimestamp(record.timestamp)
        return f"{dt} {record.level.name} {record.logger_name}: {record.message} | {record.context}"
```

#### 2.2 Prometheus Backend (`src/core/logging/backends/prometheus.py`)
```python
class PrometheusBackend(LogBackend):
    """
    Batched metrics to Prometheus push gateway.
    Zero formatting overhead - direct metric push.
    """
    
    def should_handle(self, record: LogRecord) -> bool:
        return record.log_type == LogType.METRIC
    
    async def write(self, record: LogRecord) -> None:
        # Buffer for batching - no formatting overhead
        self._buffer.append({
            'name': f"hft_{record.metric_name}",
            'value': record.metric_value,
            'labels': {
                'exchange': record.exchange,
                'symbol': record.symbol,
                **record.metric_tags
            },
            'timestamp': record.timestamp
        })
        
        if len(self._buffer) >= self.batch_size:
            await self.flush()
    
    async def flush(self) -> None:
        # Push all buffered metrics to Prometheus
        await self._push_to_prometheus(self._buffer)
        self._buffer.clear()
```

#### 2.3 Console Backend (`src/core/logging/backends/console.py`)
```python
class ConsoleBackend(LogBackend):
    """
    DEV environment console output using Python logging.
    Maintains full backwards compatibility.
    """
    
    def __init__(self, config):
        self.enabled = config.get('environment') == 'dev'
    
    def should_handle(self, record: LogRecord) -> bool:
        return self.enabled and record.log_type == LogType.TEXT
    
    async def write(self, record: LogRecord) -> None:
        # Use existing Python logger for compatibility
        py_logger = logging.getLogger(record.logger_name)
        py_level = self._convert_level(record.level)
        
        # Keep existing format exactly
        message = record.message
        if record.context:
            message += f" | {record.context}"
        
        py_logger.log(py_level, message)
```

### Phase 3: Factory Integration (Week 3)

#### 3.1 Logger Factory (`src/core/logging/factory.py`)
```python
class LoggerFactory:
    """
    Creates and configures loggers for injection into base classes.
    Handles environment-specific configurations.
    """
    
    @staticmethod
    def create_logger(name: str, config: LogConfig = None) -> HFTLoggerInterface:
        config = config or LoggerFactory._get_default_config()
        
        # Create backends based on environment
        backends = LoggerFactory._create_backends(config)
        
        # Create router
        router = LoggerFactory._create_router(config, backends)
        
        # Return configured logger
        return HFTLogger(name, backends, router)
    
    @staticmethod
    def _get_default_config() -> LogConfig:
        env = os.getenv('ENVIRONMENT', 'dev')
        
        if env == 'dev':
            return LogConfig(
                backends={
                    'console': ConsoleConfig(enabled=True),
                    'file': FileConfig(file_path='logs/dev.log'),
                    'prometheus': PrometheusConfig(enabled=False)
                },
                routing_rules=DEVELOPMENT_ROUTING_RULES
            )
        else:
            return LogConfig(
                backends={
                    'file': FileConfig(file_path='logs/prod.log'),
                    'prometheus': PrometheusConfig(
                        push_gateway='prometheus-gateway:9091'
                    ),
                    'datadog': DatadogConfig(api_key=os.getenv('DATADOG_API_KEY'))
                },
                routing_rules=PRODUCTION_ROUTING_RULES
            )
```

#### 3.2 Base Class Integration (`src/core/transport/websocket/strategies/enhanced_message_parser.py`)
```python
class EnhancedBaseMessageParser(ABC):
    """Enhanced base with injected logger"""
    
    def __init__(self, mapper: BaseExchangeMapper, exchange_name: str, logger: HFTLoggerInterface = None):
        self.mapper = mapper
        self.exchange_name = exchange_name
        
        # Use injected logger or create default
        self.logger = logger or LoggerFactory.create_logger(
            f"parser.{exchange_name}",
            LogConfig.for_component("message_parser")
        )
        
        # Set persistent context
        self.logger.set_context(
            exchange=exchange_name,
            component="message_parser"
        )
    
    async def parse_message(self, msg):
        start = time.perf_counter()
        try:
            result = await self._parse(msg)
            
            # Latency metric - goes to Prometheus
            self.logger.latency(
                "parse_message", 
                (time.perf_counter() - start) * 1000,
                message_type=result.message_type.name if result else "unknown"
            )
            return result
            
        except Exception as e:
            # Error with context - goes to file
            self.logger.error(f"Parse failed: {e}", 
                            message_preview=str(msg)[:100],
                            error_type=type(e).__name__)
            raise
```

#### 3.3 Factory Pattern Update (`src/cex/factories/exchange_factory.py`)
```python
class ExchangeFactory:
    """Enhanced factory with logger injection"""
    
    @staticmethod
    def create_public_exchange(exchange_enum, symbols, config=None):
        # Create exchange-specific logger
        logger = LoggerFactory.create_logger(
            f"exchange.{exchange_enum.value}.public",
            config.logging_config if config else None
        )
        
        # Create exchange with injected logger
        if exchange_enum == ExchangeEnum.MEXC:
            mapper = MexcUnifiedMappings()
            parser = MexcPublicMessageParser(mapper, logger=logger)
            exchange = MexcPublicExchange(parser=parser, logger=logger)
        
        elif exchange_enum == ExchangeEnum.GATEIO:
            mapper = GateioUnifiedMappings() 
            parser = GateioPublicMessageParser(mapper, logger=logger)
            exchange = GateioPublicExchange(parser=parser, logger=logger)
        
        return exchange
```

### Phase 4: Configuration System (Week 4)

#### 4.1 Configuration Structure (`src/core/logging/config.py`)
```python
@dataclass
class LogConfig:
    """Complete logging configuration"""
    environment: str = "dev"
    backends: Dict[str, BackendConfig] = field(default_factory=dict)
    routing_rules: List[Dict[str, Any]] = field(default_factory=list)
    global_context: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_yaml(cls, yaml_file: str) -> 'LogConfig':
        """Load configuration from YAML file"""
        pass
    
    @classmethod  
    def for_component(cls, component_name: str) -> 'LogConfig':
        """Get component-specific configuration"""
        pass

@dataclass
class BackendConfig:
    enabled: bool = True
    min_level: str = "DEBUG"
    config: Dict[str, Any] = field(default_factory=dict)

@dataclass
class FileConfig(BackendConfig):
    file_path: str = "logs/app.log"
    format: str = "text"  # 'text' or 'json'
    rotation: bool = True
    max_size_mb: int = 100

@dataclass
class PrometheusConfig(BackendConfig):
    push_gateway: str = None
    job_name: str = "hft_arbitrage"
    prefix: str = "hft_"
    batch_size: int = 100
    flush_interval: float = 5.0

@dataclass
class DatadogConfig(BackendConfig):
    api_key: str = None
    service: str = "hft-arbitrage"
    tags: List[str] = field(default_factory=list)
```

#### 4.2 YAML Configuration Example (`config/logging.yaml`)
```yaml
logging:
  environment: "dev"
  
  backends:
    console:
      enabled: true
      min_level: "DEBUG"
      config:
        color: true
    
    file:
      enabled: true
      min_level: "WARNING"
      config:
        file_path: "logs/hft.log"
        format: "text"
        rotation: true
        max_size_mb: 100
    
    prometheus:
      enabled: true
      min_level: "INFO"
      config:
        push_gateway: "localhost:9091"
        job_name: "hft_arbitrage"
        prefix: "hft_"
        batch_size: 50
        flush_interval: 3.0
    
    datadog:
      enabled: false
      config:
        api_key: "${DATADOG_API_KEY}"
        service: "hft-arbitrage"
        tags: ["env:dev", "version:1.0"]
  
  routing_rules:
    - name: "metrics_to_prometheus"
      log_types: ["METRIC"]
      backends: ["prometheus"]
    
    - name: "errors_to_file_and_console"
      min_level: "WARNING"
      backends: ["file", "console"]
    
    - name: "debug_to_console_dev_only"
      max_level: "INFO"
      environments: ["dev"]
      backends: ["console"]
  
  global_context:
    service: "hft-arbitrage"
    version: "1.0.0"
```

### Phase 5: Advanced Features (Week 4)

#### 5.1 Third-Party Backend Examples
```python
class SlackBackend(LogBackend):
    """Send critical errors to Slack"""
    def should_handle(self, record):
        return record.level >= LogLevel.CRITICAL

class ElasticsearchBackend(LogBackend):
    """Structured logs for analysis"""
    def should_handle(self, record):
        return record.log_type == LogType.AUDIT

class CustomWebhookBackend(LogBackend):
    """Send to custom API endpoint"""
    def should_handle(self, record):
        return 'alert' in record.context
```

#### 5.2 Performance Monitoring Integration
```python
class PerformanceLogger:
    """HFT-specific performance logging"""
    
    def __init__(self, logger: HFTLoggerInterface):
        self.logger = logger
    
    @contextmanager
    def time_operation(self, operation: str, **tags):
        start = time.perf_counter()
        try:
            yield
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            self.logger.latency(operation, duration_ms, **tags)
    
    def log_trade_execution(self, order_id: str, latency_ms: float, **context):
        self.logger.audit("trade_executed", 
                         order_id=order_id,
                         latency_ms=latency_ms,
                         **context)
        
        self.logger.metric("trade_execution_latency", latency_ms,
                          exchange=context.get('exchange'),
                          symbol=context.get('symbol'))
```

## Integration Examples

### Example 1: Message Parser Usage
```python
class MexcPublicMessageParser(EnhancedBaseMessageParser):
    async def parse_message(self, msg):
        # Debug logging (goes to console in DEV)
        self.logger.debug(f"Parsing message: {msg[:100]}")
        
        try:
            with PerformanceLogger(self.logger).time_operation("parse_orderbook"):
                result = self._parse_orderbook(msg)
            
            # Metrics (go to Prometheus)
            self.logger.metric("orderbook_depth", len(result.bids))
            self.logger.counter("messages_parsed", tags={"type": "orderbook"})
            
            return result
            
        except Exception as e:
            # Error logging (goes to file + console)
            self.logger.error(f"Parse failed: {e}",
                            message_size=len(msg),
                            exchange="mexc",
                            error_type=type(e).__name__)
            raise
```

### Example 2: WebSocket Manager Usage  
```python
class WebSocketManager:
    def __init__(self, logger=None):
        # Backwards compatible - existing logs still work
        self.logger = logger or LoggerFactory.create_logger("websocket")
    
    async def connect(self):
        try:
            # Existing Python logging calls work unchanged
            self.logger.info(f"Connection state: {old} → {new}")
            self.logger.warning(f"Connection error: {error}")
            
            # New HFT features available
            self.logger.latency("websocket_connect", elapsed_ms)
            self.logger.audit("connection_established", endpoint=self.url)
            
        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
```

### Example 3: Arbitrage Engine Usage
```python
class ArbitrageEngine:
    def __init__(self, logger=None):
        self.logger = logger or LoggerFactory.create_logger("arbitrage")
    
    async def execute_arbitrage(self, opportunity):
        # Audit trail
        self.logger.audit("arbitrage_opportunity_detected",
                         profit_bps=opportunity.profit_bps,
                         volume_usd=opportunity.volume)
        
        with PerformanceLogger(self.logger).time_operation("arbitrage_execution"):
            try:
                result = await self._execute(opportunity)
                
                # Success metrics
                self.logger.metric("arbitrage_profit_usd", result.profit)
                self.logger.metric("arbitrage_success", 1)
                
                return result
                
            except Exception as e:
                # Error tracking
                self.logger.error(f"Arbitrage failed: {e}",
                                opportunity_id=opportunity.id,
                                exchanges=opportunity.exchanges)
                
                self.logger.metric("arbitrage_failure", 1, 
                                 error_type=type(e).__name__)
                raise
```

## Migration Strategy

### Phase 1: Zero-Impact Introduction
1. Create logging infrastructure alongside existing system
2. Factory injection in new components only
3. Existing Python logging continues unchanged
4. Test with DEV environment

### Phase 2: Gradual Migration  
1. Update base classes to accept optional logger parameter
2. Migrate high-value components (parsers, engines)
3. Add performance metrics to critical paths
4. Validate routing rules work correctly

### Phase 3: Full Adoption
1. Update all factory methods to inject loggers
2. Add HFT-specific logging (metrics, audit trails)
3. Configure production backends (Prometheus, Datadog)
4. Remove redundant Python logging where appropriate

### Phase 4: Optimization
1. Profile logging performance
2. Optimize hot paths
3. Add advanced features (alerting, dashboards)
4. Create logging best practices documentation

## Success Metrics

### Performance
- **Log call latency**: <100μs in hot paths
- **Async dispatch**: No blocking on log calls
- **Memory usage**: <10MB for log buffers
- **Throughput**: Handle >10k logs/second

### Functionality
- **Backend flexibility**: Add new backend in <50 lines
- **Environment parity**: DEV/PROD configs work seamlessly
- **Backwards compatibility**: 100% existing log calls work
- **Context preservation**: Correlation tracking across all logs

### Operational
- **Zero downtime**: Logging failures don't affect trading
- **Observable**: Easy to debug logging issues
- **Configurable**: Change routing without code changes
- **Scalable**: Handle production log volumes

This plan provides a simple interface with maximum extensibility, zero performance impact on hot paths, and seamless integration with the existing factory pattern architecture.