# HFT Logger Injection Plan - COMPLETE MIGRATION STRATEGY

Complete migration strategy to replace Python logging with factory-based HFT logger injection across the entire codebase.

## Executive Summary

**Current State**: Found **108 files** with `logging.getLogger()` usage across the entire codebase  
**Target State**: Complete replacement with HFT logging system using factory pattern injection  
**Estimated Effort**: ~178 hours across 7 phases with dependencies  
**Status**: 15 files migrated (✅), 93 files remaining  

Replace all `import logging` and `logging.getLogger()` calls with our HFT logging system using factory pattern injection. This will enable selective routing (metrics→Prometheus, warnings→file, debug→console) with <1ms performance and correlation tracking.

## Current Implementation Status ✅

We have successfully implemented:
1. ✅ **HFT logging system** with factory pattern (`src/core/logging/`)
2. ✅ **Strategy logger injection** with hierarchical tagging (`get_strategy_logger()`)
3. ✅ **REST factories** with HFT logging (`src/core/factories/rest/`)
4. ✅ **WebSocket manager** with HFT logging (`src/core/transport/websocket/ws_manager.py`)
5. ✅ **Base exchange WebSocket interface** (`src/core/exchanges/websocket/ws_base.py`)
6. ✅ **REST strategy set** with logger injection (`src/core/transport/rest/strategies/strategy_set.py`)
7. ✅ **Sample strategy implementations** (MEXC auth, request, retry, connection strategies)

## Complete Inventory Analysis

### Component Categories Found

| Category | Files | Complexity | Priority | Status |
|----------|-------|------------|----------|---------|
| **Core Base Classes** | 12 | High | Critical | 🔄 4/12 |
| **Exchange Implementations** | 28 | Medium | Critical | 🔄 4/28 |
| **Arbitrage Engine** | 23 | Medium | High | ⏳ 0/23 |
| **Message Parsers & Strategies** | 15 | Medium | High | 🔄 3/15 |
| **Transport Layer** | 8 | Medium | High | 🔄 2/8 |
| **Factory Classes** | 6 | Low | Medium | 🔄 2/6 |
| **Tools & Examples** | 12 | Low | Low | ⏳ 0/12 |
| **Analytics & DB** | 4 | Low | Low | ⏳ 0/4 |
| **TOTAL** | **108** | **-** | **-** | **15/108** |

### Current Logging Patterns Identified

**Pattern 1 - Module-level Logger (68 files)**:
```python
logger = logging.getLogger(__name__)
```

**Pattern 2 - Class-level Logger with Class Name (28 files)**:
```python
self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
```

**Pattern 3 - Dynamic Exchange Logger (8 files)**:
```python
self.logger = logging.getLogger(f"{__name__}.{exchange_name}")
```

**Pattern 4 - HFT Bridge Usage (4 files)** [Already compliant]:
```python
# In src/core/logging/backends/*.py - these are part of HFT system
```

## DETAILED COMPONENT CLASSIFICATION

### Critical Path Components (Must migrate first)

**Core Base Classes** (12 files, blocks everything else):

| File | Current Pattern | Target Pattern | Dependencies |
|------|----------------|----------------|--------------|
| `/src/core/exchanges/rest/base_rest.py` | `logging.getLogger(f"{__name__}.{self.exchange_tag}")` | `get_exchange_logger(exchange_tag, 'rest.base')` | None |
| `/src/core/exchanges/websocket/spot/base_ws_public.py` | `logging.getLogger(f"{__name__}.{exchange}_public")` | `get_exchange_logger(exchange, 'ws.public')` | None |
| `/src/core/transport/websocket/strategies/enhanced_message_parser.py` | `logging.getLogger(f"{module}.{class}")` | `get_strategy_logger('ws.message_parser', tags)` | None |
| `/src/core/transport/websocket/error_handling.py` | `logging.getLogger(f"{__name__}.{exchange}")` | `get_exchange_logger(exchange, 'ws.error')` | None |
| `/src/core/transport/websocket/ws_client.py` | `logging.getLogger(f"{__name__}.{url}")` | `get_logger('ws.client')` | None |
| `/src/core/transport/websocket/strategies/connection.py` | `logging.getLogger(f"{__name__}.{class}")` | `get_strategy_logger('ws.connection', tags)` | None |

**Exchange Implementations** (28 files, critical for production):

| Exchange | Component | Files | Migration Type |
|----------|-----------|-------|----------------|
| **MEXC** | WebSocket Strategies | 4 | Strategy logger injection |
| **MEXC** | REST Strategies | 3 | Strategy logger injection |
| **MEXC** | Exchange Classes | 2 | Exchange logger injection |
| **Gate.io** | WebSocket Strategies | 9 | Strategy logger injection |
| **Gate.io** | REST Strategies | 4 | Exchange logger injection |
| **Gate.io** | Exchange Classes | 4 | Exchange logger injection |
| **Factories** | Exchange Creation | 2 | Factory logger injection |

### High Impact Components

**Arbitrage Engine** (23 files in `/src/arbitrage/`):
- All use module-level `logging.getLogger(__name__)` pattern
- Can be migrated in parallel (low dependencies)
- Each needs `get_arbitrage_logger('component_name')` pattern

**Message Parsers & Strategies** (15 files):
- WebSocket message parsers (6 files)
- REST strategies (4 files) - ✅ **SOME DONE**
- Connection strategies (5 files) - ✅ **SOME DONE**

## MIGRATION PATTERNS BY COMPONENT TYPE

### Pattern 1: Base Class Logger Injection

**Current**:
```python
# src/core/exchanges/rest/rest_base.py
self.logger = logging.getLogger(f"{__name__}.{self.exchange_tag}")
```

**Target**:
```python
def __init__(self, exchange_tag: str, logger: HFTLoggerInterface = None):
    if logger is None:
        logger = get_exchange_logger(exchange_tag.lower(), 'rest.composite')
    self.logger = logger
```

### Pattern 2: Strategy Logger Injection (Hierarchical Tags)

**Current**:
```python
# Strategy classes
self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
```

**Target**:
```python
def __init__(self, mapper, logger: HFTLoggerInterface = None):
    if logger is None:
        # Extract exchange from class name: MexcPublicConnectionStrategy -> mexc
        exchange = self.__class__.__name__.lower()[:4]  # mexc, gate, etc.
        api_type = 'private' if 'private' in self.__class__.__name__.lower() else 'public'
        transport = 'ws' if 'ws' in self.__module__ else 'rest'
        strategy_type = self._extract_strategy_type()  # connection, auth, etc.
        
        tags = [exchange, api_type, transport, strategy_type]
        strategy_path = f'{transport}.{strategy_type}.{exchange}.{api_type}'
        logger = get_strategy_logger(strategy_path, tags)
    
    self.logger = logger
    
    # Log strategy initialization with metrics
    self.logger.info(f"{self.__class__.__name__} strategy initialized",
                    strategy_type=strategy_type,
                    exchange=exchange,
                    api_type=api_type)
    
    self.logger.metric("strategy_instances_created", 1,
                      tags={"exchange": exchange, "type": strategy_type})
```

### Pattern 3: Exchange Implementation Logger Injection

**Current**:
```python
# Exchange classes
self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
```

**Target**:
```python
def __init__(self, config: ExchangeConfig, logger: HFTLoggerInterface = None):
    if logger is None:
        component_type = 'private_exchange' if 'Private' in self.__class__.__name__ else 'public_exchange'
        logger = get_exchange_logger(config.name.lower(), component_type)
    
    self.logger = logger
    
    # Enhanced initialization logging
    self.logger.info("Exchange instance created",
                    exchange=config.name,
                    component_type=component_type,
                    base_url=config.base_url)
    
    self.logger.metric("exchange_instances_created", 1,
                      tags={"exchange": config.name, "type": component_type})
```

### Pattern 4: Arbitrage Component Logger Injection

**Current**:
```python
# Arbitrage modules
logger = logging.getLogger(__name__)
```

**Target**:
```python
# Module-level
from src.core.logging import get_arbitrage_logger
logger = get_arbitrage_logger('component_name')

# Enhanced logging with correlation tracking
def execute_arbitrage_operation(opportunity):
    correlation_id = generate_correlation_id()
    
    logger.info("Arbitrage operation started",
               correlation_id=correlation_id,
               opportunity_id=opportunity.id,
               profit_estimate=opportunity.profit)
    
    with LoggingTimer(logger, "arbitrage_execution") as timer:
        result = _execute_operation(opportunity)
    
    logger.metric("arbitrage_operations_completed", 1,
                 tags={"status": "success", "component": "component_name"})
    
    logger.audit("Arbitrage operation completed",
                correlation_id=correlation_id,
                profit_realized=result.profit,
                execution_time_ms=timer.elapsed_ms)
```

## DETAILED MIGRATION PHASES

### Phase 1: Core Infrastructure (Week 1) - CRITICAL PATH

**Files to migrate** (blocks all other migration):
1. `src/core/exchanges/rest/base_rest.py` - REST base class
2. `src/core/exchanges/websocket/spot/base_ws_public.py` - WebSocket base class  
3. `src/core/transport/websocket/strategies/enhanced_message_parser.py` - Message parser base
4. `src/core/transport/websocket/error_handling.py` - Error handling
5. `src/core/transport/websocket/ws_client.py` - WebSocket client
6. `src/core/transport/websocket/strategies/connection.py` - Connection strategy base
7. `src/core/transport/websocket/strategies/factory.py` - WebSocket strategy factory
8. `src/core/transport/rest/rest_transport_manager.py` - REST transport manager

**Success Criteria**:
- All base classes accept logger injection
- No `logging.getLogger()` in critical path components
- Performance tests pass (<1ms logging latency)

### Phase 2: Factory Layer (Week 2) - HIGH PRIORITY

**Files to migrate**:
1. `src/exchanges/factories/exchange_factory.py` - Main exchange factory
2. `src/core/factories/base_exchange_factory.py` - Factory base class
3. `src/core/factories/base_composite_factory.py` - Composite factory base
4. `src/core/exchanges/services/symbol_mapper/factory.py` - Symbol mapper factory

**Factory Integration Pattern**:
```python
# Enhanced factory with logger injection
class ExchangeFactory:
    @classmethod
    def create_private_exchange(cls, exchange: ExchangeEnum, config: ExchangeConfig):
        # Create exchange-specific logger
        logger = get_exchange_logger(config.name.lower(), 'private_exchange')
        
        # Track factory metrics
        with LoggingTimer(logger, "exchange_creation") as timer:
            if exchange == ExchangeEnum.MEXC:
                instance = MexcPrivateExchange(config=config, logger=logger)
            # ... other exchanges
        
        logger.metric("exchange_creations", 1,
                     tags={"exchange": config.name, "type": "private"})
        
        return instance
```

### Phase 3: Exchange Strategy Implementations (Week 3-4) - CRITICAL

**MEXC Strategies** (7 files):
- `src/exchanges/mexc/ws/strategies/private/message_parser.py`
- `src/exchanges/mexc/ws/strategies/private/connection.py` 
- `src/exchanges/mexc/ws/strategies/private/subscription.py`
- `src/exchanges/mexc/ws/strategies/public/subscription.py`
- `src/exchanges/mexc/rest/strategies/rate_limit.py`
- `src/exchanges/mexc/rest/strategies/exception_handler.py`
- `src/exchanges/mexc/private_exchange.py`

**Gate.io Strategies** (17 files):
- All WebSocket strategies (9 files)
- All REST strategies (4 files)
- All exchange classes (4 files)

**Implementation Example**:
```python
# MEXC WebSocket Subscription Strategy
class MexcPublicSubscriptionStrategy:
    def __init__(self, mapper, logger=None):
        if logger is None:
            tags = ['mexc', 'public', 'ws', 'subscription']
            logger = get_strategy_logger('ws.subscription.mexc.public', tags)
        
        self.logger = logger
        self.mapper = mapper
        
        self.logger.info("MEXC public subscription strategy initialized")
        self.logger.metric("ws_subscription_strategies_created", 1,
                          tags={"exchange": "mexc", "type": "public"})
    
    async def create_subscription_messages(self, action, symbols, channels):
        with LoggingTimer(self.logger, "subscription_message_creation") as timer:
            messages = self._build_messages(action, symbols, channels)
        
        self.logger.debug("Subscription messages created",
                         action=action.value,
                         symbols_count=len(symbols),
                         channels_count=len(channels),
                         messages_count=len(messages))
        
        self.logger.metric("ws_subscription_messages_created", len(messages),
                          tags={"exchange": "mexc", "action": action.value})
        
        return messages
```

### Phase 4: Arbitrage Engine (Week 5) - HIGH PRIORITY

**All 23 arbitrage files** can be migrated in parallel:

| Component | File | Migration Type |
|-----------|------|----------------|
| Engine Core | `engine.py`, `simple_engine.py` | Arbitrage logger |
| Detection | `detector.py`, `opportunity_processor.py` | Arbitrage logger |
| Execution | `controller.py`, `aggregator.py` | Arbitrage logger |
| Risk Management | `risk.py`, `position.py`, `balance.py` | Arbitrage logger |
| Infrastructure | `orchestrator.py`, `configuration_manager.py` | Arbitrage logger |

**Arbitrage Component Pattern**:
```python
# src/arbitrage/detector.py
from src.core.logging import get_arbitrage_logger, LoggingTimer

class ArbitrageDetector:
    def __init__(self, strategy_name: str, logger=None):
        if logger is None:
            logger = get_arbitrage_logger(f'detector.{strategy_name}')
        
        self.logger = logger
        self.strategy_name = strategy_name
        
        self.logger.info("Arbitrage detector initialized",
                        strategy=strategy_name)
    
    async def detect_opportunities(self, market_data):
        correlation_id = self._generate_correlation_id()
        
        with LoggingTimer(self.logger, "opportunity_detection") as timer:
            opportunities = await self._analyze_markets(market_data, correlation_id)
        
        self.logger.info("Opportunity detection completed",
                        correlation_id=correlation_id,
                        opportunities_found=len(opportunities),
                        analysis_time_ms=timer.elapsed_ms)
        
        self.logger.metric("arbitrage_opportunities_detected", len(opportunities),
                          tags={"strategy": self.strategy_name})
        
        if opportunities:
            for opp in opportunities:
                self.logger.audit("Arbitrage opportunity detected",
                                correlation_id=correlation_id,
                                opportunity_id=opp.id,
                                profit_estimate=opp.profit,
                                confidence=opp.confidence)
        
        return opportunities
```

### Phase 5: Supporting Components (Week 6) - MEDIUM PRIORITY

**Transport Layer** (6 remaining files):
- `src/core/transport/rest/rest_client_legacy.py`
- `src/core/config/config_manager.py`
- `src/core/registry/exchange_registry.py`
- `src/core/registry/factory_registry.py`

**Tools & Examples** (12 files):
- All `/src/tools/` scripts
- All `/src/examples/` demonstration files
- All `/src/analysis/` components

### Phase 6: Final Cleanup (Week 7) - LOW PRIORITY

**Database & Analytics** (4 files):
- `/src/db/` database operations
- `/src/analysis/` analytics components

## SUCCESS METRICS & VALIDATION

### Performance Validation Checkpoints

**After Each Phase**:
1. **Latency Test**: All logging operations must remain <1ms
2. **Throughput Test**: Must maintain 170K+ messages/second
3. **Memory Test**: No memory leaks in logger injection
4. **Integration Test**: End-to-end arbitrage cycle timing

**Final Success Criteria**:
- ✅ Zero `logging.getLogger()` calls remain in codebase
- ✅ All components use HFT logger injection  
- ✅ Hierarchical tagging implemented for all strategies
- ✅ Performance benchmarks maintained
- ✅ Prometheus metrics integration working
- ✅ Correlation tracking functional across all components

## IMPLEMENTATION TIMELINE

| Week | Phase | Components | Files | Dependencies |
|------|-------|------------|-------|--------------|
| **1** | Core Infrastructure | Base classes, transport | 8 | None |
| **2** | Factory Layer | Factories, registries | 4 | Phase 1 |
| **3** | Exchange Strategies (MEXC) | WebSocket/REST strategies | 7 | Phase 1-2 |
| **4** | Exchange Strategies (Gate.io) | WebSocket/REST strategies | 17 | Phase 1-2 |
| **5** | Arbitrage Engine | All arbitrage components | 23 | Minimal |
| **6** | Supporting Components | Tools, examples, config | 16 | Minimal |
| **7** | Final Cleanup | Database, analytics | 4 | None |

**Total**: 7 weeks, 79 files, complete HFT logging migration

This comprehensive plan provides a systematic approach to eliminate ALL `logging.getLogger()` usage while maintaining HFT performance requirements.

### 1.2 WebSocket Factory Integration

**Targets**: 
- `src/core/factories/websocket/public_websocket_factory.py`
- `src/core/factories/websocket/private_websocket_factory.py`

**Implementation Strategy**:

```python
# Before: Standard Python logging
import logging
logger = logging.getLogger(__name__)

# After: HFT factory injection
from src.core.logging import get_logger
logger = get_logger('ws.factory.public')

class PublicWebSocketExchangeFactory(BaseExchangeFactory):
    @classmethod
    def inject(cls, exchange, config, **kwargs):
        # Create exchange-specific logger
        exchange_logger = get_exchange_logger(exchange, 'ws.public')
        
        # Log performance metrics
        with LoggingTimer(exchange_logger, "websocket_creation"):
            instance = implementation_class(
                config=config,
                logger=exchange_logger,  # Inject logger
                **kwargs
            )
        
        # Log factory metrics
        exchange_logger.metric("websocket_instances_created", 1, 
                              tags={"exchange": exchange, "type": "public"})
        
        return instance
```

### 1.3 REST Factory Integration

**Targets**:
- `src/core/factories/rest/public_rest_factory.py`
- `src/core/factories/rest/private_rest_factory.py`

**Metrics to Track**:
- REST client creation time
- HTTP response times
- Request/response rates
- Error rates by exchange
- Connection pool efficiency

## Phase 2: Exchange Implementation Layer (Week 2)

### 2.1 WebSocket Client Integration

**Pattern for All WebSocket Clients**:

```python
class BaseExchangePublicWebsocket:
    def __init__(self, config, logger=None, **kwargs):
        # Use injected logger or create default
        self.logger = logger or get_exchange_logger(config.name, 'ws.public')
        
        # Connection event logging with correlation
        self.correlation_id = self._generate_correlation_id()
        
    async def connect(self):
        self.logger.info("Initiating WebSocket connection", 
                        correlation_id=self.correlation_id)
        
        with LoggingTimer(self.logger, "websocket_connection"):
            await self._establish_connection()
            
        self.logger.metric("websocket_connections", 1,
                          tags={"exchange": self.config.name, "type": "public"})

    async def _handle_message(self, message):
        # Performance tracking
        with LoggingTimer(self.logger, "message_processing"):
            result = await self._process_message(message)
        
        # Response rate metrics
        self.logger.metric("messages_processed", 1,
                          tags={"exchange": self.config.name, "type": message.get("type")})
        
        return result
```

### 2.2 REST Client Integration

**Pattern for All REST Clients**:

```python
class BaseRestClient:
    def __init__(self, config, logger=None):
        self.logger = logger or get_exchange_logger(config.name, 'rest.client')
        
    async def _make_request(self, method, endpoint, **kwargs):
        correlation_id = kwargs.get('correlation_id', self._generate_correlation_id())
        
        self.logger.debug(f"{method} {endpoint}", 
                         correlation_id=correlation_id,
                         endpoint=endpoint)
        
        with LoggingTimer(self.logger, f"rest_request_{method.lower()}") as timer:
            try:
                response = await self._execute_request(method, endpoint, **kwargs)
                
                # Success metrics
                self.logger.metric("rest_requests_total", 1,
                                  tags={"exchange": self.config.name, 
                                       "method": method, 
                                       "endpoint": endpoint,
                                       "status": "success"})
                
                return response
                
            except Exception as e:
                # Error metrics and logging
                self.logger.error(f"REST request failed: {e}",
                                 correlation_id=correlation_id,
                                 endpoint=endpoint,
                                 error_type=type(e).__name__)
                
                self.logger.metric("rest_requests_total", 1,
                                  tags={"exchange": self.config.name,
                                       "method": method,
                                       "endpoint": endpoint,  
                                       "status": "error"})
                raise
```

## Phase 3: Data Collector Integration (Week 3)

### 3.1 Data Collector Module Transformation

**Target**: `src/data_collector/`

**Current Structure Analysis**:
- `collector.py` - Main data collection logic
- `analytics.py` - Data analysis and processing
- `config.py` - Configuration management
- `run.py` - Entry point

**Integration Strategy**:

```python
# src/data_collector/__init__.py
from src.core.logging import get_logger, setup_production_logging

# Auto-setup logging for data collector
setup_production_logging()

# src/data_collector/collector.py
from src.core.logging import get_logger, LoggingTimer

class DataCollector:
    def __init__(self, config):
        self.logger = get_logger('data_collector.main')
        self.config = config
        
    async def collect_data(self, exchange, symbols):
        correlation_id = self._generate_correlation_id()
        
        self.logger.info("Starting data collection",
                        correlation_id=correlation_id,
                        exchange=exchange,
                        symbols_count=len(symbols))
        
        with LoggingTimer(self.logger, "data_collection_full_cycle") as timer:
            for symbol in symbols:
                await self._collect_symbol_data(symbol, correlation_id)
        
        # Collection metrics
        self.logger.metric("data_collection_cycles", 1,
                          tags={"exchange": exchange})
        
        self.logger.metric("symbols_collected", len(symbols),
                          tags={"exchange": exchange})

# src/data_collector/analytics.py  
from src.core.logging import get_logger

class DataAnalytics:
    def __init__(self):
        self.logger = get_logger('data_collector.analytics')
        
    def analyze_arbitrage_opportunities(self, data):
        with LoggingTimer(self.logger, "arbitrage_analysis"):
            opportunities = self._find_opportunities(data)
            
        self.logger.metric("arbitrage_opportunities_found", len(opportunities))
        
        if opportunities:
            self.logger.info(f"Found {len(opportunities)} arbitrage opportunities",
                           opportunities_count=len(opportunities))
            
        return opportunities
```

### 3.2 Configuration Integration

**Target**: `src/data_collector/config.py`

```python
from src.core.logging import get_logger, configure_logging

class DataCollectorConfig:
    def __init__(self):
        self.logger = get_logger('data_collector.config')
        
        # Configure logging for data collector
        self._setup_logging()
        
    def _setup_logging(self):
        """Configure logging specifically for data collection."""
        config = {
            'environment': 'prod',
            'backends': {
                'file': {
                    'file_path': 'logs/data_collector.log',
                    'format': 'json',
                    'min_level': 'INFO'
                },
                'prometheus': {
                    'push_gateway_url': 'http://prometheus:9091',
                    'job_name': 'data_collector'
                }
            },
            'router': {'type': 'rule_based'}
        }
        
        configure_logging(config)
        self.logger.info("Data collector logging configured")
```

## Phase 4: Arbitrage Engine Integration (Week 4)

### 4.1 Arbitrage Component Integration

**Strategy**: Inject loggers into all arbitrage components with correlation tracking across the entire arbitrage cycle.

```python
# src/arbitrage/engine.py
from src.core.logging import get_arbitrage_logger, LoggingTimer

class ArbitrageEngine:
    def __init__(self, strategy_name):
        self.logger = get_arbitrage_logger(strategy_name)
        
    async def execute_arbitrage(self, opportunity):
        cycle_id = self._generate_cycle_id()
        
        self.logger.info("Starting arbitrage execution",
                        correlation_id=cycle_id,
                        opportunity_id=opportunity.id,
                        profit_estimate=opportunity.profit)
        
        with LoggingTimer(self.logger, "arbitrage_full_execution") as timer:
            try:
                result = await self._execute_trades(opportunity, cycle_id)
                
                # Success metrics
                self.logger.metric("arbitrage_executions", 1,
                                  tags={"status": "success", "strategy": self.strategy})
                
                self.logger.metric("arbitrage_profit_realized", result.profit,
                                  tags={"strategy": self.strategy})
                
                self.logger.audit("Arbitrage completed successfully",
                                 correlation_id=cycle_id,
                                 profit_realized=result.profit,
                                 trades_executed=len(result.trades))
                
            except Exception as e:
                self.logger.error("Arbitrage execution failed",
                                 correlation_id=cycle_id,
                                 error_type=type(e).__name__,
                                 opportunity_id=opportunity.id)
                
                self.logger.metric("arbitrage_executions", 1,
                                  tags={"status": "error", "strategy": self.strategy})
                raise
```

## Phase 5: Migration Execution Strategy

### 5.1 Automated Migration Script

```python
#!/usr/bin/env python3
"""
Automated migration script to replace Python logging with HFT logging.
"""

import re
import os
from pathlib import Path

def migrate_file(file_path):
    """Migrate a single Python file."""
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Replace imports
    content = re.sub(
        r'import logging',
        'from src.core.logging import get_logger',
        content
    )
    
    # Replace logger creation patterns
    content = re.sub(
        r'logging\.getLogger\(__name__\)',
        'get_logger(__name__)',
        content
    )
    
    content = re.sub(
        r'logging\.getLogger\([\'"]([^\'"]+)[\'"]\)',
        r'get_logger("\1")',
        content
    )
    
    # Add exchange context where applicable
    content = re.sub(
        r'logging\.getLogger\(f[\'"]([^\'"]*)\{([^}]+)\}([^\'"]*)[\'\"]\)',
        r'get_exchange_logger(\2, "\1\3")',
        content
    )
    
    with open(file_path, 'w') as f:
        f.write(content)

def migrate_project():
    """Migrate entire project."""
    project_root = Path('/Users/dasein/dev/cex_arbitrage')
    
    for py_file in project_root.rglob('*.py'):
        if 'test' not in str(py_file) and '__pycache__' not in str(py_file):
            print(f"Migrating {py_file}")
            migrate_file(py_file)

if __name__ == "__main__":
    migrate_project()
```

### 5.2 Testing Strategy

**Integration Tests**:

```python
# test_logger_integration.py
import asyncio
from src.core.logging import get_exchange_logger, setup_testing_logging

async def test_websocket_factory_injection():
    """Test WebSocket factory logger injection."""
    setup_testing_logging()
    
    # Test that logger is properly injected
    from src.core.factories.websocket.public_websocket_factory import PublicWebSocketExchangeFactory
    
    # Mock config
    config = ExchangeConfig(name='mexc')
    
    # Should create instance with injected logger
    # Test will verify logger is working and metrics are recorded
    pass

async def test_correlation_tracking():
    """Test correlation ID propagation across components."""
    logger = get_exchange_logger('mexc', 'test')
    
    correlation_id = "test-correlation-123"
    
    # Test that correlation ID flows through entire request cycle
    logger.info("Test message", correlation_id=correlation_id)
    
    # Verify correlation appears in all related log messages
    pass
```

## Phase 6: Monitoring and Validation

### 6.1 Metrics Dashboard

**Prometheus Metrics to Track**:

```yaml
# HFT Logging Metrics
hft_log_messages_total{level, component, exchange}
hft_log_performance_seconds{operation, component, exchange}
hft_websocket_connections_total{exchange, type, status}
hft_rest_requests_total{exchange, method, endpoint, status}  
hft_arbitrage_executions_total{strategy, status}
hft_arbitrage_profit_realized{strategy}
hft_data_collection_cycles_total{exchange}
```

**Grafana Dashboard Panels**:
- Log message rates by component
- WebSocket connection health
- REST API performance 
- Arbitrage execution metrics
- Error rates and correlation tracking

### 6.2 Performance Validation

**Benchmarks to Achieve**:
- Factory injection: <10μs overhead
- Logger creation: <50μs
- Log message dispatch: <1ms (already achieved: 0.006ms)
- Metric recording: <2ms (already achieved: 0.004ms)
- Memory overhead: <1MB per component

## Implementation Checklist

### Week 1: Core Infrastructure
- [ ] Integrate logger into BaseExchangeInterface
- [ ] Update WebSocket factories with logger injection
- [ ] Update REST factories with logger injection
- [ ] Create migration script
- [ ] Test factory integration

### Week 2: Exchange Layer
- [ ] Migrate all WebSocket clients
- [ ] Migrate all REST clients  
- [ ] Add performance metrics tracking
- [ ] Add correlation tracking
- [ ] Test exchange integration

### Week 3: Data Collector
- [ ] Migrate data collector module
- [ ] Add collection metrics
- [ ] Add analytics metrics
- [ ] Configure production logging
- [ ] Test data collection pipeline

### Week 4: Arbitrage Engine
- [ ] Migrate arbitrage components
- [ ] Add execution metrics
- [ ] Add audit logging
- [ ] Set up monitoring dashboard
- [ ] Performance validation

### Week 5: Validation and Optimization
- [ ] Run comprehensive integration tests
- [ ] Validate performance benchmarks
- [ ] Optimize hot paths
- [ ] Deploy to production
- [ ] Monitor and tune

## Expected Benefits

### Performance Benefits
- **Reduced Latency**: <1ms logging vs ~5-10ms Python logging
- **Better Throughput**: 170K+ messages/second vs ~10K with Python logging
- **Memory Efficiency**: Ring buffer vs unbounded Python logging queues

### Operational Benefits
- **Selective Routing**: Metrics→Prometheus, errors→file, debug→console
- **Correlation Tracking**: Full request tracing across all components
- **Rich Context**: Automatic exchange/symbol/operation context injection
- **Real-time Monitoring**: Prometheus metrics for all operations

### Development Benefits
- **Standardized Patterns**: Consistent logging across all components
- **Factory Injection**: Easy testing with mock loggers
- **Type Safety**: Full type checking for log calls
- **Zero Configuration**: Auto-setup based on environment

This comprehensive plan will transform the logging infrastructure while maintaining HFT performance requirements and providing rich operational visibility into the arbitrage system.