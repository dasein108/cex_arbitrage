# TASK 3.1: Composition-Based Exception Handling Refactoring

## Phase 3 - Exception Handling Architecture (Week 3-4)

### Task Overview
**Priority**: High  
**Estimated Effort**: 8-10 hours  
**Dependencies**: TASK_1_1 (Config Manager), TASK_1_2 (Data Collector)  
**Target**: Reduce nested try/catch complexity by 70% through composition patterns

### Current Problem Analysis

**Exception Handling Anti-Patterns Identified**:
1. **Deep Nesting**: 5+ levels of try/catch blocks in critical paths
2. **Repetitive Error Handling**: Same error patterns duplicated across 15+ files
3. **Resource Leaks**: Inconsistent cleanup in exception scenarios
4. **Performance Impact**: Exception handling adding 2-5ms latency in hot paths
5. **Maintenance Burden**: Error handling logic scattered across components

**Affected Components**:
- `src/exchanges/integrations/mexc/ws/strategies/public/connection.py` (7 nested levels)
- `src/exchanges/integrations/gateio/rest/gateio_rest_private.py` (6 nested levels)
- `src/infrastructure/networking/websocket/ws_client.py` (5 nested levels)
- `src/trading/arbitrage/engine.py` (complex error propagation)

### Solution Architecture

#### 1. Error Handler Composition Pattern

**Create Centralized Error Handlers**:

```python
# src/infrastructure/error_handling/handlers.py
from typing import TypeVar, Generic, Callable, Awaitable, Optional
from dataclasses import dataclass
from enum import Enum
import asyncio
from contextlib import asynccontextmanager

T = TypeVar('T')
R = TypeVar('R')

class ErrorSeverity(Enum):
    CRITICAL = "critical"      # System shutdown required
    HIGH = "high"             # Component restart required
    MEDIUM = "medium"         # Retry with backoff
    LOW = "low"               # Log and continue

@dataclass
class ErrorContext:
    component: str
    operation: str
    attempt: int = 1
    max_retries: int = 3
    metadata: dict = None

class ComposableErrorHandler:
    """High-performance error handler with composition pattern"""
    
    def __init__(self, component_name: str, logger: HFTLoggerInterface):
        self.component_name = component_name
        self.logger = logger
        self._handlers = {}
        self._fallback_handler = self._default_fallback
    
    def register_handler(self, exception_type: type, handler: Callable):
        """Register specific exception handlers"""
        self._handlers[exception_type] = handler
    
    async def handle_with_retry(
        self, 
        operation: Callable[[], Awaitable[T]], 
        context: ErrorContext,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM
    ) -> Optional[T]:
        """Execute operation with automatic retry and error handling"""
        
        for attempt in range(1, context.max_retries + 1):
            try:
                context.attempt = attempt
                result = await operation()
                
                if attempt > 1:
                    self.logger.info(f"Operation recovered after {attempt} attempts",
                                   component=self.component_name,
                                   operation=context.operation)
                return result
                
            except Exception as e:
                await self._handle_exception(e, context, severity, attempt)
                
                if attempt == context.max_retries:
                    if severity == ErrorSeverity.CRITICAL:
                        raise
                    return None
                    
                await asyncio.sleep(self._calculate_backoff(attempt))
        
        return None
    
    async def _handle_exception(
        self, 
        exception: Exception, 
        context: ErrorContext,
        severity: ErrorSeverity,
        attempt: int
    ):
        """Route exception to appropriate handler"""
        exception_type = type(exception)
        
        if exception_type in self._handlers:
            await self._handlers[exception_type](exception, context, severity)
        else:
            await self._fallback_handler(exception, context, severity, attempt)
    
    def _calculate_backoff(self, attempt: int) -> float:
        """Exponential backoff with jitter"""
        import random
        base_delay = 0.1 * (2 ** (attempt - 1))  # 0.1s, 0.2s, 0.4s, 0.8s
        jitter = random.uniform(0.8, 1.2)
        return min(base_delay * jitter, 5.0)  # Max 5 seconds
    
    async def _default_fallback(
        self, 
        exception: Exception, 
        context: ErrorContext,
        severity: ErrorSeverity,
        attempt: int
    ):
        """Default error handling logic"""
        self.logger.error(
            f"Operation failed: {context.operation}",
            component=self.component_name,
            exception_type=type(exception).__name__,
            exception_message=str(exception),
            attempt=attempt,
            severity=severity.value,
            **context.metadata or {}
        )

# Context manager for resource cleanup
@asynccontextmanager
async def managed_resource(resource_factory, cleanup_func, logger, component_name):
    """Guaranteed resource cleanup with error handling"""
    resource = None
    try:
        resource = await resource_factory()
        yield resource
    except Exception as e:
        logger.error(f"Resource operation failed in {component_name}: {e}")
        raise
    finally:
        if resource:
            try:
                await cleanup_func(resource)
            except Exception as cleanup_error:
                logger.warning(f"Resource cleanup failed in {component_name}: {cleanup_error}")
```

#### 2. WebSocket Connection Error Handler

**Specialized Handler for WebSocket Operations**:

```python
# src/infrastructure/error_handling/websocket_handlers.py
import websockets
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
from aiohttp import ClientError, ClientTimeout

class WebSocketErrorHandler(ComposableErrorHandler):
    """Specialized error handling for WebSocket connections"""
    
    def __init__(self, component_name: str, logger: HFTLoggerInterface):
        super().__init__(component_name, logger)
        self._register_websocket_handlers()
    
    def _register_websocket_handlers(self):
        """Register WebSocket-specific error handlers"""
        self.register_handler(ConnectionClosedError, self._handle_connection_closed)
        self.register_handler(ConnectionClosedOK, self._handle_connection_closed_ok)
        self.register_handler(ClientTimeout, self._handle_timeout)
        self.register_handler(ClientError, self._handle_client_error)
    
    async def _handle_connection_closed(self, exception: ConnectionClosedError, context: ErrorContext, severity: ErrorSeverity):
        """Handle WebSocket connection closed unexpectedly"""
        self.logger.warning(
            f"WebSocket connection closed unexpectedly: {context.operation}",
            component=self.component_name,
            close_code=exception.code,
            close_reason=exception.reason,
            attempt=context.attempt
        )
        
        # Trigger reconnection logic
        if hasattr(context, 'reconnect_callback'):
            await context.reconnect_callback()
    
    async def _handle_connection_closed_ok(self, exception: ConnectionClosedOK, context: ErrorContext, severity: ErrorSeverity):
        """Handle graceful WebSocket closure"""
        self.logger.info(
            f"WebSocket connection closed gracefully: {context.operation}",
            component=self.component_name
        )
    
    async def _handle_timeout(self, exception: ClientTimeout, context: ErrorContext, severity: ErrorSeverity):
        """Handle connection timeouts with exponential backoff"""
        self.logger.warning(
            f"Connection timeout in {context.operation}",
            component=self.component_name,
            attempt=context.attempt,
            timeout_duration=getattr(exception, 'timeout', 'unknown')
        )
    
    async def _handle_client_error(self, exception: ClientError, context: ErrorContext, severity: ErrorSeverity):
        """Handle HTTP client errors"""
        self.logger.error(
            f"HTTP client error in {context.operation}: {exception}",
            component=self.component_name,
            attempt=context.attempt
        )
```

#### 3. Trading Operation Error Handler

**Specialized Handler for Trading Operations**:

```python
# src/infrastructure/error_handling/trading_handlers.py
from exchanges.exceptions import (
    InsufficientFundsError, 
    OrderNotFoundError, 
    RateLimitExceededError,
    ExchangeMaintenanceError
)

class TradingErrorHandler(ComposableErrorHandler):
    """Specialized error handling for trading operations"""
    
    def __init__(self, component_name: str, logger: HFTLoggerInterface):
        super().__init__(component_name, logger)
        self._register_trading_handlers()
    
    def _register_trading_handlers(self):
        """Register trading-specific error handlers"""
        self.register_handler(InsufficientFundsError, self._handle_insufficient_funds)
        self.register_handler(OrderNotFoundError, self._handle_order_not_found)
        self.register_handler(RateLimitExceededError, self._handle_rate_limit)
        self.register_handler(ExchangeMaintenanceError, self._handle_maintenance)
    
    async def _handle_insufficient_funds(self, exception: InsufficientFundsError, context: ErrorContext, severity: ErrorSeverity):
        """Handle insufficient funds with balance refresh"""
        self.logger.warning(
            f"Insufficient funds for {context.operation}",
            component=self.component_name,
            required_amount=getattr(exception, 'required_amount', None),
            available_amount=getattr(exception, 'available_amount', None)
        )
        
        # Trigger balance refresh
        if hasattr(context, 'balance_refresh_callback'):
            await context.balance_refresh_callback()
    
    async def _handle_rate_limit(self, exception: RateLimitExceededError, context: ErrorContext, severity: ErrorSeverity):
        """Handle rate limits with intelligent backoff"""
        retry_after = getattr(exception, 'retry_after', 1.0)
        
        self.logger.warning(
            f"Rate limit exceeded for {context.operation}",
            component=self.component_name,
            retry_after=retry_after,
            attempt=context.attempt
        )
        
        # Wait for rate limit reset
        await asyncio.sleep(retry_after)
```

### Implementation Plan

#### Step 1: Create Error Handling Infrastructure (2-3 hours)

1. **Create base error handler**:
   - Implement `ComposableErrorHandler` with retry logic
   - Add exponential backoff with jitter
   - Implement resource management context managers

2. **Create specialized handlers**:
   - WebSocket error handler with connection management
   - Trading error handler with exchange-specific logic
   - REST API error handler with rate limiting

3. **Performance optimization**:
   - Pre-compile exception type mappings
   - Minimize object allocation in hot paths
   - Cache handler instances per component

#### Step 2: Refactor WebSocket Components (3-4 hours)

**Before (Current Anti-Pattern)**:
```python
# CURRENT: 7 levels of nested try/catch
async def _handle_message(self, message):
    try:
        parsed = json.loads(message)
        try:
            if 'channel' in parsed:
                try:
                    result = parsed['result']
                    try:
                        if 'orderbook' in parsed['channel']:
                            try:
                                orderbook = self._parse_orderbook(result)
                                try:
                                    await self._update_orderbook(orderbook)
                                except Exception as e:
                                    self.logger.error(f"Failed to update orderbook: {e}")
                            except Exception as e:
                                self.logger.error(f"Failed to parse orderbook: {e}")
                        # ... more nested blocks
                    except KeyError as e:
                        self.logger.error(f"Missing result field: {e}")
                except KeyError as e:
                    self.logger.error(f"Missing channel field: {e}")
            except Exception as e:
                self.logger.error(f"Invalid message structure: {e}")
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON: {e}")
    except Exception as e:
        self.logger.error(f"Message handling failed: {e}")
```

**After (Composition Pattern)**:
```python
# REFACTORED: Clean composition with centralized error handling
async def _handle_message(self, message):
    context = ErrorContext(
        component="message_handler",
        operation="parse_and_process",
        max_retries=1,  # No retry for message processing
        metadata={"message_length": len(message)}
    )
    
    result = await self.error_handler.handle_with_retry(
        lambda: self._parse_and_process_message(message),
        context,
        ErrorSeverity.LOW  # Continue processing other messages
    )
    
    return result

async def _parse_and_process_message(self, message: str) -> Optional[dict]:
    """Clean message processing without nested error handling"""
    parsed = json.loads(message)  # Let error handler catch JSONDecodeError
    
    channel = parsed['channel']  # Let error handler catch KeyError
    result = parsed['result']    # Let error handler catch KeyError
    
    if 'orderbook' in channel:
        orderbook = self._parse_orderbook(result)  # Clean parsing
        await self._update_orderbook(orderbook)    # Clean update
    
    return parsed  # Success case
```

#### Step 3: Refactor REST Components (2-3 hours)

**Before (Current Anti-Pattern)**:
```python
async def place_order(self, symbol, side, amount, price):
    try:
        # Validate parameters
        try:
            self._validate_order_params(symbol, side, amount, price)
        except ValueError as e:
            self.logger.error(f"Invalid order parameters: {e}")
            raise
        
        # Make request
        try:
            response = await self._make_request('/api/v3/order', {
                'symbol': symbol,
                'side': side,
                'quantity': amount,
                'price': price
            })
            
            try:
                order_data = response.json()
                try:
                    order = self._parse_order_response(order_data)
                    return order
                except Exception as e:
                    self.logger.error(f"Failed to parse order response: {e}")
                    raise
            except Exception as e:
                self.logger.error(f"Invalid response format: {e}")
                raise
        except aiohttp.ClientTimeout as e:
            self.logger.error(f"Request timeout: {e}")
            raise
        except aiohttp.ClientError as e:
            self.logger.error(f"Request failed: {e}")
            raise
    except Exception as e:
        self.logger.error(f"Order placement failed: {e}")
        raise
```

**After (Composition Pattern)**:
```python
async def place_order(self, symbol, side, amount, price):
    context = ErrorContext(
        component="order_placement",
        operation="place_limit_order",
        max_retries=3,
        metadata={
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "price": price
        }
    )
    
    return await self.error_handler.handle_with_retry(
        lambda: self._execute_order_placement(symbol, side, amount, price),
        context,
        ErrorSeverity.HIGH  # Trading operations are high severity
    )

async def _execute_order_placement(self, symbol, side, amount, price):
    """Clean order placement without nested error handling"""
    self._validate_order_params(symbol, side, amount, price)  # Let errors bubble up
    
    response = await self._make_request('/api/v3/order', {
        'symbol': symbol,
        'side': side,
        'quantity': amount,
        'price': price
    })
    
    order_data = response.json()
    return self._parse_order_response(order_data)
```

### Testing Strategy

#### Unit Tests for Error Handlers

```python
# tests/infrastructure/error_handling/test_composable_error_handler.py
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock

class TestComposableErrorHandler:
    
    @pytest.fixture
    def mock_logger(self):
        return Mock()
    
    @pytest.fixture
    def error_handler(self, mock_logger):
        return ComposableErrorHandler("test_component", mock_logger)
    
    async def test_successful_operation_no_retry(self, error_handler):
        """Test successful operation executes without retry"""
        operation = AsyncMock(return_value="success")
        context = ErrorContext(component="test", operation="test_op")
        
        result = await error_handler.handle_with_retry(operation, context)
        
        assert result == "success"
        assert operation.call_count == 1
    
    async def test_retry_with_exponential_backoff(self, error_handler):
        """Test retry logic with exponential backoff"""
        operation = AsyncMock(side_effect=[ValueError("error"), ValueError("error"), "success"])
        context = ErrorContext(component="test", operation="test_op", max_retries=3)
        
        start_time = asyncio.get_event_loop().time()
        result = await error_handler.handle_with_retry(operation, context, ErrorSeverity.MEDIUM)
        end_time = asyncio.get_event_loop().time()
        
        assert result == "success"
        assert operation.call_count == 3
        assert end_time - start_time >= 0.3  # Should have backoff delays
    
    async def test_critical_error_propagation(self, error_handler):
        """Test critical errors are propagated immediately"""
        operation = AsyncMock(side_effect=ValueError("critical error"))
        context = ErrorContext(component="test", operation="test_op", max_retries=3)
        
        with pytest.raises(ValueError):
            await error_handler.handle_with_retry(operation, context, ErrorSeverity.CRITICAL)
        
        assert operation.call_count == 3  # Should still retry even for critical
```

#### Integration Tests

```python
# tests/integration/test_websocket_error_handling.py
import pytest
from unittest.mock import AsyncMock, Mock
from websockets.exceptions import ConnectionClosedError

class TestWebSocketErrorHandling:
    
    async def test_connection_recovery_on_closed_error(self):
        """Test automatic reconnection on connection closed"""
        mock_reconnect = AsyncMock()
        handler = WebSocketErrorHandler("test_ws", Mock())
        
        context = ErrorContext(
            component="websocket",
            operation="receive_message",
            max_retries=3
        )
        context.reconnect_callback = mock_reconnect
        
        # Simulate connection error then success
        operation = AsyncMock(side_effect=[
            ConnectionClosedError(1006, "Connection lost"),
            "success"
        ])
        
        result = await handler.handle_with_retry(operation, context)
        
        assert result == "success"
        assert mock_reconnect.call_count == 1
```

### Success Metrics

#### Performance Targets
- **Error handling latency**: <0.5ms per error (currently 2-5ms)
- **Code complexity reduction**: 70% fewer nested try/catch blocks
- **Error recovery time**: <100ms for non-critical errors
- **Memory usage**: <10MB for error handler instances

#### Code Quality Metrics
- **Cyclomatic complexity**: Reduce from 15+ to <8 per method
- **Code duplication**: Eliminate 90% of repeated error handling patterns
- **Test coverage**: >95% for all error handling paths
- **Documentation**: Complete API docs for all error handler classes

### Risk Assessment

#### High Risk Areas
1. **Performance Regression**: Error handling in hot paths could add latency
   - **Mitigation**: Benchmark all changes, optimize handler instance caching
   
2. **Behavior Changes**: Existing error handling might have implicit dependencies
   - **Mitigation**: Comprehensive integration testing, gradual rollout

3. **Resource Leaks**: Context managers must guarantee cleanup
   - **Mitigation**: Extensive testing of cleanup paths, monitoring

#### Testing Requirements
- **Unit tests**: All error handler classes and utility functions
- **Integration tests**: Full error handling flows with real exceptions  
- **Performance tests**: Latency benchmarks for hot paths
- **Load tests**: Error handling under high message volumes

### Acceptance Criteria

#### Functional Requirements
- [ ] All WebSocket components use composition-based error handling
- [ ] All REST components use composition-based error handling
- [ ] All trading operations have specialized error handling
- [ ] Resource cleanup is guaranteed in all error scenarios
- [ ] Error handlers are configurable per component

#### Performance Requirements
- [ ] Error handling adds <0.5ms latency to hot paths
- [ ] Memory usage for error handlers is <10MB total
- [ ] Error recovery completes within 100ms for non-critical errors
- [ ] No performance regression in happy path scenarios

#### Code Quality Requirements
- [ ] Cyclomatic complexity <8 for all error handling methods
- [ ] 90% reduction in code duplication for error handling
- [ ] 100% test coverage for error handler classes
- [ ] Zero nested try/catch blocks deeper than 2 levels

#### Documentation Requirements
- [ ] Complete API documentation for all error handler classes
- [ ] Usage examples for each error handler type
- [ ] Migration guide from old error handling patterns
- [ ] Performance benchmarks and optimization notes

### Dependencies and Prerequisites

#### Required Completions
- **TASK_1_1**: Config manager decomposition (error handling uses config)
- **TASK_1_2**: Data collector decomposition (shared error handling patterns)

#### Parallel Tasks
- Can be developed alongside TASK_2_1 (Abstract Trading Base Class)
- Complements TASK_2_2 (WebSocket Utilities) error handling

#### External Dependencies
- No new external libraries required
- Uses existing logging infrastructure
- Leverages current async/await patterns