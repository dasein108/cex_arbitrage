# Strategy Logger Injection Plan - HFT Hierarchical Tagging System

Comprehensive plan for migrating all strategy components from Python logging to HFT logging with hierarchical tag-based logger injection.

## Current Logging Patterns Found

### 1. Core Transport Strategy Set
```python
# src/core/transport/rest/strategies/strategy_set.py:44
self.logger = logging.getLogger(__name__)
```

### 2. Exchange-Specific Strategy Implementations
```python
# src/exchanges/mexc/ws/strategies/public/connection.py:19
self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
```

### 3. Strategy Factory (Import Only)
```python
# src/core/transport/rest/strategies/factory.py:10
import logging  # No logger instantiation found
```

## Proposed Hierarchical Tagging System

### Tag Hierarchy Design
```python
# Multi-dimensional tagging: [exchange, api_type, transport, strategy_type]
tags = ['mexc', 'private', 'rest', 'auth']           # MEXC private REST auth strategy
tags = ['gateio', 'public', 'ws', 'connection']     # Gate.io public WebSocket connection strategy  
tags = ['mexc', 'private', 'ws', 'message_parser']  # MEXC private WebSocket message parser
```

### Logger Naming Convention
```python
# Base logger naming: transport.strategy_type.exchange.api_type
logger_name = 'rest.auth.mexc.private'      # REST auth strategy for MEXC private
logger_name = 'ws.connection.gateio.public' # WebSocket connection for Gate.io public
logger_name = 'rest.strategy_set.core'      # Core REST strategy set
```

## Factory-Based Logger Injection Architecture

### 1. Strategy Factory Logger Injection

#### REST Strategy Factory Enhancement
```python
# src/core/transport/rest/strategies/factory.py

# HFT Logger Integration
from src.core.logging import get_logger, get_strategy_logger, LoggingTimer

class RestStrategyFactory(BaseCompositeFactory[RestStrategySet]):
    
    @classmethod
    def _assemble_components(cls, exchange: ExchangeEnum, strategy_config: Dict[str, type], **kwargs) -> RestStrategySet:
        config = kwargs.get('config')
        is_private = kwargs.get('is_private', False)
        
        # Create strategy-specific loggers with hierarchical tags
        api_type = 'private' if is_private else 'public'
        base_tags = [exchange.value, api_type, 'rest']
        
        # Create strategies with injected loggers
        request_strategy = cls._create_component_with_logger(
            strategy_config['request'], 
            exchange.value,
            logger=get_strategy_logger('rest.request', base_tags + ['request']),
            config=config
        )
        
        # Inject HFT logger into strategy set
        strategy_set_logger = get_strategy_logger('rest.strategy_set', base_tags)
        
        return RestStrategySet(
            request_strategy=request_strategy,
            rate_limit_strategy=rate_limit_strategy,
            retry_strategy=retry_strategy,
            auth_strategy=auth_strategy,
            exception_handler_strategy=exception_handler_strategy,
            logger=strategy_set_logger  # Inject HFT logger
        )
```

#### WebSocket Strategy Factory Enhancement
```python
# src/core/transport/ws/strategies/factory.py

class WebSocketStrategyFactory(BaseCompositeFactory[WebSocketStrategySet]):
    
    @classmethod
    def inject(cls, exchange: ExchangeEnum, is_private: bool, config: ExchangeConfig = None, **kwargs) -> WebSocketStrategySet:
        # Create hierarchical tags
        api_type = 'private' if is_private else 'public'
        base_tags = [exchange.value, api_type, 'ws']
        
        # Get strategy configuration
        strategy_config = cls._implementations[(exchange, is_private)]
        
        # Create strategies with injected loggers
        connection_strategy = strategy_config['connection'](
            config=config,
            logger=get_strategy_logger('ws.connection', base_tags + ['connection'])
        )
        
        return WebSocketStrategySet(
            connection_strategy=connection_strategy,
            subscription_strategy=subscription_strategy,
            message_parser=message_parser,
            logger=get_strategy_logger('ws.strategy_set', base_tags)
        )
```

### 2. Strategy Base Class Logger Injection

#### REST Strategy Base Classes
```python
# src/core/transport/rest/strategies/request.py
class RequestStrategy(ABC):
    def __init__(self, base_url: str, logger=None, **kwargs):
        self.base_url = base_url
        self.logger = logger or get_logger('strategy.request.composite')
```

#### WebSocket Strategy Base Classes  
```python
# src/core/exchanges/ws/strategies/connection.py
class ConnectionStrategy(ABC):
    def __init__(self, config: ExchangeConfig, logger=None):
        self.config = config
        self.logger = logger or get_logger('strategy.connection.composite')
```

### 3. Exchange-Specific Strategy Implementation

#### Pattern for Exchange Strategy Constructors
```python
# Current Pattern (to be migrated):
class MexcPublicConnectionStrategy(ConnectionStrategy):
    def __init__(self, config: ExchangeConfig):
        super().__init__(config)
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

# New HFT Pattern:
class MexcPublicConnectionStrategy(ConnectionStrategy):
    def __init__(self, config: ExchangeConfig, logger=None):
        # Create hierarchical tags if no logger provided
        if logger is None:
            tags = ['mexc', 'public', 'ws', 'connection']
            logger = get_strategy_logger('ws.connection.mexc.public', tags)
        
        super().__init__(config, logger=logger)
        
        # Strategy-specific initialization with metrics
        self.logger.info("MEXC public connection strategy initialized",
                        websocket_url=config.websocket_url,
                        ping_interval=self.ping_interval)
```

## HFT Logger Integration Functions

### New Strategy Logger Functions
```python
# src/core/logging/__init__.py

def get_strategy_logger(strategy_path: str, tags: List[str]) -> HFTLogger:
    """
    Create strategy-specific logger with hierarchical tags.
    
    Args:
        strategy_path: Dot-separated strategy path (e.g., 'rest.auth.mexc.private')
        tags: Hierarchical tags [exchange, api_type, transport, strategy_type]
        
    Returns:
        HFTLogger with strategy-specific configuration
    """
    logger = HFTLogger(strategy_path)
    logger.add_default_tags({
        "exchange": tags[0],
        "api_type": tags[1], 
        "transport": tags[2],
        "strategy_type": tags[3] if len(tags) > 3 else 'core',
        "component": "strategy"
    })
    return logger

def get_strategy_metrics_logger(exchange: str, api_type: str, transport: str) -> HFTLogger:
    """Create strategy metrics logger for performance tracking."""
    return get_strategy_logger(f'{transport}.metrics.{exchange}.{api_type}', 
                              [exchange, api_type, transport, 'metrics'])
```

## Migration Strategy by Component Type

### Phase 1: Core Strategy Infrastructure

#### 1.1 REST Strategy Set Migration
```python
# src/core/transport/rest/strategies/strategy_set.py

# Before:
self.logger = logging.getLogger(__name__)

# After:
def __init__(self, request_strategy, rate_limit_strategy, retry_strategy, 
             auth_strategy=None, exception_handler_strategy=None, logger=None):
    # ... existing initialization ...
    
    # Initialize HFT logger with optional injection
    self.logger = logger or get_logger('rest.strategy_set.core')
    
    # Track strategy set creation metrics
    self.logger.info("REST strategy set created",
                    has_auth=auth_strategy is not None,
                    has_exception_handler=exception_handler_strategy is not None)
    
    self.logger.metric("rest_strategy_sets_created", 1,
                      tags={"type": "core"})
```

#### 1.2 WebSocket Strategy Set Migration
```python
# Similar pattern for WebSocket strategy sets with ws.strategy_set.core logger
```

### Phase 2: Exchange Strategy Implementations

#### 2.1 REST Strategy Implementations
```python
# Pattern for all REST strategies (auth, request, retry, rate_limit, exception_handler)

# Before:
class MexcAuthStrategy(AuthStrategy):
    def __init__(self, exchange_config: ExchangeConfig):
        # No logger currently

# After:
class MexcAuthStrategy(AuthStrategy):
    def __init__(self, exchange_config: ExchangeConfig, logger=None):
        if logger is None:
            tags = ['mexc', 'private', 'rest', 'auth']  # Assume private for auth
            logger = get_strategy_logger('rest.auth.mexc.private', tags)
            
        self.logger = logger
        # ... existing initialization ...
        
        self.logger.info("MEXC auth strategy initialized",
                        api_key_configured=bool(exchange_config.credentials.api_key))
```

#### 2.2 WebSocket Strategy Implementations  
```python
# Before:
class MexcPublicConnectionStrategy(ConnectionStrategy):
    def __init__(self, config: ExchangeConfig):
        super().__init__(config)
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

# After:
class MexcPublicConnectionStrategy(ConnectionStrategy):
    def __init__(self, config: ExchangeConfig, logger=None):
        if logger is None:
            tags = ['mexc', 'public', 'ws', 'connection']
            logger = get_strategy_logger('ws.connection.mexc.public', tags)
            
        super().__init__(config, logger=logger)
        
        # Strategy-specific metrics and logging
        self.logger.info("MEXC public connection strategy initialized",
                        websocket_url=config.websocket_url,
                        ping_interval=self.ping_interval)
        
        self.logger.metric("ws_connection_strategies_created", 1,
                          tags={"exchange": "mexc", "type": "public"})
```

## Comprehensive Metrics Strategy

### Strategy-Level Performance Metrics

#### REST Strategy Metrics
```python
# In strategy implementations:
self.logger.metric("rest_auth_signatures_generated", 1,
                  tags={"exchange": "mexc", "endpoint": endpoint})
                  
self.logger.metric("rest_retry_attempts", attempt,
                  tags={"exchange": "mexc", "error_type": error_type})
                  
self.logger.metric("rest_rate_limit_delays", delay_seconds,
                  tags={"exchange": "mexc", "limit_type": "weight"})
```

#### WebSocket Strategy Metrics  
```python
# In strategy implementations:
self.logger.metric("ws_connections_established", 1,
                  tags={"exchange": "mexc", "type": "public"})
                  
self.logger.metric("ws_subscription_messages_sent", len(messages),
                  tags={"exchange": "mexc", "channels": len(channels)})
                  
self.logger.metric("ws_message_parsing_time_us", parsing_time_us,
                  tags={"exchange": "mexc", "message_type": message.type})
```

### Factory-Level Metrics
```python
# In strategy factories:
self.logger.metric("strategy_sets_created", 1,
                  tags={"exchange": exchange.value, "type": api_type, "transport": "rest"})
                  
self.logger.metric("strategy_creation_time_ms", timer.elapsed_ms,
                  tags={"exchange": exchange.value, "strategy": "auth"})
```

## Implementation Priority Order

### Week 1: Core Strategy Infrastructure
1. **Strategy Set Classes**: `RestStrategySet`, `WebSocketStrategySet`
2. **Strategy Factory Classes**: `RestStrategyFactory`, `WebSocketStrategyFactory`  
3. **Base Strategy Interfaces**: Add logger injection support

### Week 2: REST Strategy Implementations
1. **MEXC REST Strategies**: auth, request, retry, rate_limit, exception_handler
2. **Gate.io REST Strategies**: Same strategy types
3. **Strategy Performance Metrics**: Comprehensive tracking

### Week 3: WebSocket Strategy Implementations  
1. **MEXC WebSocket Strategies**: connection, subscription, message_parser
2. **Gate.io WebSocket Strategies**: Same strategy types
3. **Real-time Performance Metrics**: Message processing, connection health

### Week 4: Integration and Optimization
1. **Factory Integration**: Seamless logger injection via factories
2. **Performance Validation**: Ensure <1μs logging overhead
3. **Metrics Dashboard**: Prometheus integration for strategy monitoring

## Benefits of Hierarchical Tag Strategy

### 1. Operational Excellence
- **Unified Monitoring**: All strategies report to same metrics system
- **Hierarchical Filtering**: Query by exchange, API type, transport, strategy
- **Correlation Analysis**: Link strategy performance to exchange health

### 2. Development Benefits  
- **Consistent Patterns**: Same logger injection pattern across all strategies
- **Easy Debugging**: Rich context with exchange/API type/strategy info
- **Factory Integration**: Automatic logger injection via existing factories

### 3. Performance Benefits
- **<1μs Overhead**: HFT-compliant logging performance
- **Selective Routing**: Metrics→Prometheus, errors→file, debug→console
- **Strategy-Specific Optimization**: Per-strategy performance tuning

### 4. Production Benefits
- **Real-time Monitoring**: Live strategy performance dashboards
- **Automated Alerting**: Strategy-specific error rate alerts  
- **Audit Compliance**: Complete strategy execution audit trail
- **Exchange Health Correlation**: Link strategy issues to exchange status

This comprehensive strategy logger injection plan will provide unprecedented visibility into strategy-level performance while maintaining HFT-compliant <1μs logging latency across all strategy components.