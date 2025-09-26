# Exception Handling Patterns

Documentation for the simplified exception handling architecture in the CEX Arbitrage Engine, designed to reduce complexity while maintaining reliability and HFT performance.

## Core Philosophy: Composed Exception Handling

**Principle**: Reduce nested try/catch complexity through composition and centralization.

Instead of deep exception handling hierarchies, compose error handling in higher-order functions and keep individual methods clean and focused.

## Exception Handling Architecture

### **Higher-Order Exception Handling**

**Pattern**: Compose exception handling at interface boundaries rather than deep nesting throughout the codebase.

```python
# CORRECT: Compose exception handling at interface level
class UnifiedCompositeExchange:
    """Exception handling composed at the interface boundary."""
    
    async def place_limit_order(self, symbol: Symbol, side: Side, quantity: float, price: float, **kwargs) -> Order:
        """Place limit order with composed exception handling."""
        try:
            # Attempt the operation
            order_data = await self._execute_limit_order(symbol, side, quantity, price, **kwargs)
            return self._parse_order_response(order_data)
            
        except ApiException as e:
            # Handle API-specific errors at interface level
            self.logger.error("API error during order placement", 
                            symbol=str(symbol), 
                            side=side.value,
                            error_code=e.code,
                            error_message=e.message)
            raise OrderPlacementError(f"Failed to place {side} order for {symbol}: {e.message}") from e
            
        except NetworkException as e:
            # Handle network errors at interface level
            self.logger.error("Network error during order placement",
                            symbol=str(symbol),
                            side=side.value, 
                            error=str(e))
            raise ExchangeConnectionError(f"Network error placing order: {e}") from e
            
        except Exception as e:
            # Catch-all for unexpected errors
            self.logger.error("Unexpected error during order placement",
                            symbol=str(symbol),
                            side=side.value,
                            error=str(e))
            raise ExchangeError(f"Unexpected error placing order: {e}") from e
    
    # Individual methods are clean without exception handling
    async def _execute_limit_order(self, symbol: Symbol, side: Side, quantity: float, price: float, **kwargs) -> Dict:
        """Execute limit order - clean implementation without exception handling."""
        order_params = self._build_order_params(symbol, side, quantity, price, **kwargs)
        response = await self._rest_client.post('/api/v3/order', data=order_params)
        return response
    
    def _parse_order_response(self, response: Dict) -> Order:
        """Parse order response - clean implementation without exception handling."""
        return Order(
            order_id=response['orderId'],
            symbol=self._parse_symbol(response['symbol']),
            side=Side(response['side']),
            order_type=OrderType(response['type']),
            quantity=float(response['origQty']),
            price=float(response['price']) if response.get('price') else None,
            status=OrderStatus(response['status']),
            timestamp=float(response['transactTime'])
        )
```

### **Exception Hierarchy**

**Structured Exception Types**:
```python
# Base exception for all exchange-related errors
class ExchangeError(Exception):
    """Base exception for all exchange operations."""
    
    def __init__(self, message: str, exchange: Optional[str] = None, details: Optional[Dict] = None):
        self.message = message
        self.exchange = exchange
        self.details = details or {}
        super().__init__(message)

# Specific exception types for different error categories
class ExchangeConnectionError(ExchangeError):
    """Network connectivity and connection errors."""
    pass

class ApiException(ExchangeError):
    """API-specific errors with error codes."""
    
    def __init__(self, message: str, code: int, exchange: Optional[str] = None):
        super().__init__(message, exchange)
        self.code = code
        
    def is_rate_limit_error(self) -> bool:
        """Check if this is a rate limiting error."""
        return self.code in [429, -1003, -1015]
    
    def is_authentication_error(self) -> bool:
        """Check if this is an authentication error."""
        return self.code in [401, -1022, -2015]

class OrderPlacementError(ExchangeError):
    """Specific errors related to order placement."""
    pass

class InsufficientBalanceError(ExchangeError):
    """Insufficient account balance for operation."""
    pass

class InvalidSymbolError(ExchangeError):
    """Invalid or unsupported trading symbol."""
    pass
```

### **HFT-Specific Exception Rules**

**Critical Trading Paths**: Minimal exception handling for sub-millisecond performance targets.

```python
# HFT CRITICAL PATH: Minimal exception handling
class SymbolResolver:
    """HFT-optimized symbol resolution with minimal exception overhead."""
    
    def resolve_symbol(self, symbol_str: str) -> Optional[Symbol]:
        """Fast symbol resolution - no exception handling in critical path."""
        # No try/catch here - let errors propagate to higher level
        # This method needs <1μs performance
        return self._symbol_cache.get(symbol_str)
    
    def resolve_symbol_safe(self, symbol_str: str) -> Optional[Symbol]:
        """Safe symbol resolution with exception handling."""
        # Use this version when error handling is more important than speed
        try:
            return self.resolve_symbol(symbol_str)
        except Exception as e:
            self.logger.warning(f"Symbol resolution failed: {e}")
            return None
```

**Non-Critical Paths**: Full error recovery and logging for better reliability.

```python
# NON-CRITICAL PATH: Full exception handling
class ConfigurationManager:
    """Configuration management with comprehensive error handling."""
    
    def load_exchange_config(self, exchange_name: str) -> Optional[ExchangeConfig]:
        """Load exchange configuration with full error handling."""
        try:
            config_path = self._get_config_path(exchange_name)
            raw_config = self._load_config_file(config_path)
            validated_config = self._validate_config_schema(raw_config)
            return self._parse_exchange_config(validated_config)
            
        except FileNotFoundError:
            self.logger.error(f"Configuration file not found for {exchange_name}")
            return None
            
        except yaml.YAMLError as e:
            self.logger.error(f"Invalid YAML in {exchange_name} config: {e}")
            return None
            
        except ValidationError as e:
            self.logger.error(f"Configuration validation failed for {exchange_name}: {e}")
            return None
            
        except Exception as e:
            self.logger.error(f"Unexpected error loading {exchange_name} config: {e}")
            return None
```

## Exception Composition Patterns

### **Message Processing Pattern**

**Compose exception handling for message processing workflows**:

```python
class WebSocketMessageProcessor:
    """WebSocket message processing with composed exception handling."""
    
    async def process_message(self, raw_message: str) -> Optional[ProcessedMessage]:
        """Process WebSocket message with composed error handling."""
        try:
            # Parse message structure
            message_data = json.loads(raw_message)
            message_type = message_data.get('channel', 'unknown')
            
            # Route to appropriate processor
            if 'orderbook' in message_type:
                return await self._process_orderbook_message(message_data)
            elif 'trade' in message_type:
                return await self._process_trade_message(message_data)
            elif 'ticker' in message_type:
                return await self._process_ticker_message(message_data)
            else:
                self.logger.warning(f"Unknown message type: {message_type}")
                return None
                
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in WebSocket message: {e}")
            return None
            
        except Exception as e:
            self.logger.error(f"Error processing WebSocket message: {e}")
            return None
    
    # Individual processors are clean without exception handling
    async def _process_orderbook_message(self, data: Dict) -> ProcessedMessage:
        """Process orderbook message - clean implementation."""
        symbol = Symbol.from_exchange_format(data['symbol'])
        orderbook = OrderBook(
            symbol=symbol,
            bids=[PriceLevel(float(bid[0]), float(bid[1])) for bid in data['bids']],
            asks=[PriceLevel(float(ask[0]), float(ask[1])) for ask in data['asks']],
            timestamp=float(data['timestamp'])
        )
        return ProcessedMessage(type='orderbook', data=orderbook)
    
    async def _process_trade_message(self, data: Dict) -> ProcessedMessage:
        """Process trade message - clean implementation."""
        symbol = Symbol.from_exchange_format(data['symbol'])
        trade = Trade(
            symbol=symbol,
            price=float(data['price']),
            quantity=float(data['quantity']),
            side=Side(data['side']),
            timestamp=float(data['timestamp'])
        )
        return ProcessedMessage(type='trade', data=trade)
```

### **Batch Operation Pattern**

**Handle exceptions in batch operations efficiently**:

```python
class BatchOrderManager:
    """Batch order operations with composed exception handling."""
    
    async def place_multiple_orders(self, orders: List[OrderRequest]) -> List[OrderResult]:
        """Place multiple orders with individual error handling."""
        results = []
        
        for order_request in orders:
            try:
                # Attempt to place individual order
                order = await self._place_single_order(order_request)
                results.append(OrderResult.success(order))
                
            except ApiException as e:
                # Handle API errors per order
                self.logger.warning(f"API error for order {order_request.symbol}: {e.message}")
                results.append(OrderResult.error(e))
                
            except InsufficientBalanceError as e:
                # Handle balance errors per order
                self.logger.warning(f"Insufficient balance for order {order_request.symbol}: {e}")
                results.append(OrderResult.error(e))
                
            except Exception as e:
                # Handle unexpected errors per order
                self.logger.error(f"Unexpected error for order {order_request.symbol}: {e}")
                results.append(OrderResult.error(e))
        
        # Log batch results summary
        successful = sum(1 for result in results if result.success)
        failed = len(results) - successful
        self.logger.info(f"Batch order results: {successful} successful, {failed} failed")
        
        return results
    
    async def _place_single_order(self, order_request: OrderRequest) -> Order:
        """Place single order - clean implementation."""
        # No exception handling here - handled at batch level
        return await self.exchange.place_limit_order(
            order_request.symbol,
            order_request.side,
            order_request.quantity,
            order_request.price
        )
```

### **Retry Pattern with Exception Handling**

**Compose retry logic with exception handling**:

```python
class RetryableOperation:
    """Retryable operations with composed exception handling."""
    
    async def execute_with_retry(self, operation: Callable, max_retries: int = 3, backoff_factor: float = 1.0) -> Any:
        """Execute operation with retry logic and exception handling."""
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                # Attempt the operation
                return await operation()
                
            except ApiException as e:
                last_exception = e
                
                # Don't retry certain error types
                if e.is_authentication_error():
                    self.logger.error(f"Authentication error - not retrying: {e}")
                    raise
                
                if e.code in [-1013, -1021]:  # Invalid quantity/price - don't retry
                    self.logger.error(f"Invalid order parameters - not retrying: {e}")
                    raise
                
                # Retry rate limit errors with backoff
                if e.is_rate_limit_error() and attempt < max_retries:
                    delay = backoff_factor * (2 ** attempt)
                    self.logger.warning(f"Rate limit error - retrying in {delay}s: {e}")
                    await asyncio.sleep(delay)
                    continue
                    
                # Log other API errors and retry
                if attempt < max_retries:
                    self.logger.warning(f"API error on attempt {attempt + 1} - retrying: {e}")
                    await asyncio.sleep(backoff_factor)
                    continue
                    
            except NetworkException as e:
                last_exception = e
                
                # Always retry network errors with backoff
                if attempt < max_retries:
                    delay = backoff_factor * (2 ** attempt)
                    self.logger.warning(f"Network error on attempt {attempt + 1} - retrying in {delay}s: {e}")
                    await asyncio.sleep(delay)
                    continue
                    
            except Exception as e:
                # Don't retry unexpected errors
                self.logger.error(f"Unexpected error - not retrying: {e}")
                raise
        
        # All retries exhausted
        self.logger.error(f"Operation failed after {max_retries + 1} attempts")
        if last_exception:
            raise last_exception
        else:
            raise RuntimeError("Operation failed - no exception information")

# Usage
retry_manager = RetryableOperation()

async def place_order_with_retry(symbol, side, quantity, price):
    """Place order with automatic retry on transient errors."""
    return await retry_manager.execute_with_retry(
        lambda: exchange.place_limit_order(symbol, side, quantity, price),
        max_retries=3,
        backoff_factor=1.0
    )
```

## Fast-Fail Principle

### **HFT Critical Paths**

**Don't over-handle in critical paths** - let errors propagate to higher levels for better performance:

```python
# HFT CRITICAL: Symbol resolution in hot path
def get_best_bid_price(self, symbol: Symbol) -> float:
    """Get best bid price - HFT critical path."""
    # No exception handling - let errors fail fast
    orderbook = self.exchange.get_orderbook(symbol)  # May raise
    return orderbook.bids[0].price  # May raise IndexError - that's OK
    
# Higher-level caller handles exceptions
def calculate_arbitrage_profit(self, symbol: Symbol) -> Optional[float]:
    """Calculate arbitrage profit with exception handling."""
    try:
        buy_price = self.buy_exchange.get_best_ask_price(symbol)
        sell_price = self.sell_exchange.get_best_bid_price(symbol)
        return sell_price - buy_price
        
    except (ExchangeError, IndexError, KeyError) as e:
        self.logger.debug(f"Cannot calculate arbitrage for {symbol}: {e}")
        return None  # Fail gracefully at business logic level
```

### **Maximum Nesting Rule**

**Limit to 2 levels of nesting maximum**:

```python
# CORRECT: Maximum 2 levels of exception nesting
async def execute_arbitrage_opportunity(self, opportunity: ArbitrageOpportunity) -> ArbitrageResult:
    """Execute arbitrage with 2-level exception handling."""
    
    try:
        # Level 1: Main operation
        buy_task = self.buy_exchange.place_market_order(
            opportunity.symbol, Side.BUY, opportunity.quantity
        )
        sell_task = self.sell_exchange.place_limit_order(
            opportunity.symbol, Side.SELL, opportunity.quantity, opportunity.sell_price
        )
        
        buy_order, sell_order = await asyncio.gather(buy_task, sell_task)
        
        return ArbitrageResult.success(buy_order, sell_order)
        
    except ExchangeError as e:
        # Level 2: Specific error handling
        try:
            # Attempt cleanup if first order succeeded
            if 'buy_order' in locals():
                await self._attempt_order_cleanup(buy_order)
        except Exception as cleanup_error:
            self.logger.error(f"Cleanup failed: {cleanup_error}")
            
        return ArbitrageResult.error(e)

# WRONG: Too many nested levels
async def bad_exception_handling(self):  # ❌ Avoid this pattern
    try:
        # Level 1
        try:
            # Level 2
            try:
                # Level 3 - too deep!
                pass
            except Exception:
                pass
        except Exception:
            pass
    except Exception:
        pass
```

## Error Recovery Patterns

### **Circuit Breaker Pattern**

**Prevent cascade failures with composed error handling**:

```python
class CircuitBreaker:
    """Circuit breaker with composed error handling."""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN
        
    async def call(self, operation: Callable) -> Any:
        """Execute operation through circuit breaker."""
        if self.state == 'OPEN':
            # Check if we should attempt recovery
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = 'HALF_OPEN'
                self.logger.info("Circuit breaker entering HALF_OPEN state")
            else:
                raise CircuitBreakerOpenError("Circuit breaker is OPEN")
        
        try:
            # Attempt the operation
            result = await operation()
            
            # Success - reset failure count if we were in HALF_OPEN
            if self.state == 'HALF_OPEN':
                self.state = 'CLOSED'
                self.failure_count = 0
                self.logger.info("Circuit breaker reset to CLOSED state")
                
            return result
            
        except Exception as e:
            # Failure - increment count and check threshold
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.failure_count >= self.failure_threshold:
                self.state = 'OPEN'
                self.logger.error(f"Circuit breaker opened after {self.failure_count} failures")
                
            raise  # Re-raise the original exception
```

### **Graceful Degradation Pattern**

**Provide fallback behavior when primary operations fail**:

```python
class ExchangeWithFallback:
    """Exchange operations with graceful degradation."""
    
    def __init__(self, primary_exchange: UnifiedCompositeExchange, 
                 fallback_exchange: Optional[UnifiedCompositeExchange] = None):
        self.primary = primary_exchange
        self.fallback = fallback_exchange
        
    async def get_orderbook(self, symbol: Symbol) -> Optional[OrderBook]:
        """Get orderbook with fallback handling."""
        # Try primary exchange
        try:
            return self.primary.get_orderbook(symbol)
            
        except ExchangeError as e:
            self.logger.warning(f"Primary exchange failed for orderbook {symbol}: {e}")
            
            # Try fallback exchange if available
            if self.fallback:
                try:
                    orderbook = self.fallback.get_orderbook(symbol)
                    self.logger.info(f"Using fallback exchange for orderbook {symbol}")
                    return orderbook
                    
                except ExchangeError as fallback_error:
                    self.logger.error(f"Fallback exchange also failed: {fallback_error}")
                    
            # Both failed - return None for graceful degradation
            return None
            
    async def place_limit_order(self, symbol: Symbol, side: Side, quantity: float, price: float) -> Order:
        """Place order with no fallback - trading operations shouldn't degrade."""
        # For trading operations, don't use fallback - fail fast instead
        return await self.primary.place_limit_order(symbol, side, quantity, price)
```

## Error Monitoring and Alerting

### **Structured Error Logging**

**Log exceptions with structured context for monitoring**:

```python
class ErrorLogger:
    """Structured error logging for monitoring."""
    
    def log_exchange_error(self, operation: str, exchange: str, symbol: Optional[Symbol], error: Exception):
        """Log exchange error with structured context."""
        error_context = {
            'operation': operation,
            'exchange': exchange,
            'symbol': str(symbol) if symbol else None,
            'error_type': type(error).__name__,
            'error_message': str(error),
            'timestamp': time.time()
        }
        
        # Add specific context for different error types
        if isinstance(error, ApiException):
            error_context.update({
                'api_error_code': error.code,
                'is_rate_limit': error.is_rate_limit_error(),
                'is_auth_error': error.is_authentication_error()
            })
        
        if isinstance(error, NetworkException):
            error_context.update({
                'network_error_type': error.error_type,
                'retry_after': getattr(error, 'retry_after', None)
            })
        
        # Log with appropriate level based on error severity
        if isinstance(error, (InsufficientBalanceError, InvalidSymbolError)):
            self.logger.warning("Exchange operation failed", **error_context)
        else:
            self.logger.error("Exchange operation error", **error_context)
            
    def log_error_pattern(self, pattern_type: str, count: int, time_window: int):
        """Log error patterns for alerting."""
        self.logger.error("Error pattern detected",
                         pattern_type=pattern_type,
                         error_count=count,
                         time_window_seconds=time_window,
                         severity="PATTERN_ALERT")
```

### **Error Pattern Detection**

**Detect error patterns that require attention**:

```python
class ErrorPatternDetector:
    """Detect error patterns for alerting."""
    
    def __init__(self):
        self.error_counts = defaultdict(list)
        self.pattern_thresholds = {
            'rate_limit_errors': {'count': 10, 'window': 300},  # 10 in 5 minutes
            'network_errors': {'count': 5, 'window': 60},       # 5 in 1 minute  
            'auth_errors': {'count': 3, 'window': 300},         # 3 in 5 minutes
            'unexpected_errors': {'count': 5, 'window': 600}    # 5 in 10 minutes
        }
        
    def record_error(self, error: Exception, exchange: str):
        """Record error for pattern detection."""
        now = time.time()
        error_type = self._classify_error(error)
        
        # Record error with timestamp
        self.error_counts[f"{exchange}_{error_type}"].append(now)
        
        # Check for patterns
        self._check_error_patterns(error_type, exchange)
        
    def _classify_error(self, error: Exception) -> str:
        """Classify error for pattern detection."""
        if isinstance(error, ApiException):
            if error.is_rate_limit_error():
                return 'rate_limit_errors'
            elif error.is_authentication_error():
                return 'auth_errors'
            else:
                return 'api_errors'
        elif isinstance(error, NetworkException):
            return 'network_errors'
        else:
            return 'unexpected_errors'
            
    def _check_error_patterns(self, error_type: str, exchange: str):
        """Check if error pattern exceeds thresholds."""
        threshold_config = self.pattern_thresholds.get(error_type)
        if not threshold_config:
            return
            
        key = f"{exchange}_{error_type}"
        now = time.time()
        window_start = now - threshold_config['window']
        
        # Count recent errors
        recent_errors = [
            timestamp for timestamp in self.error_counts[key] 
            if timestamp >= window_start
        ]
        
        # Clean old errors
        self.error_counts[key] = recent_errors
        
        # Check threshold
        if len(recent_errors) >= threshold_config['count']:
            self.logger.error("Error pattern threshold exceeded",
                            pattern_type=error_type,
                            exchange=exchange,
                            error_count=len(recent_errors),
                            time_window=threshold_config['window'],
                            severity="ALERT")
```

## Summary

### **Exception Handling Rules**

1. **Compose at Interface Boundaries** - Handle exceptions at interface level, keep methods clean
2. **Maximum 2 Levels Nesting** - Avoid deep exception handling hierarchies
3. **Fast-Fail in HFT Paths** - Minimal exception handling for critical performance paths
4. **Full Recovery in Non-Critical Paths** - Comprehensive error handling where performance isn't critical
5. **Structured Error Logging** - Log errors with rich context for monitoring and alerting

### **Performance Impact**

- **HFT Critical Paths**: <1μs overhead for exception-free operations
- **Non-Critical Paths**: Full error recovery without performance penalties
- **Composed Handling**: Reduces code complexity while maintaining reliability
- **Pattern Detection**: Proactive error monitoring prevents systemic issues

### **Maintainability Benefits**

- **Cleaner Code**: Individual methods focus on logic, not error handling
- **Centralized Error Logic**: Exception handling concentrated at interface boundaries
- **Better Testing**: Easier to test business logic separately from error handling
- **Clear Error Types**: Structured exception hierarchy provides clear error semantics

This exception handling architecture provides the reliability needed for financial trading systems while maintaining the performance characteristics required for HFT operations.

---

*This exception handling pattern documentation ensures reliable error handling while maintaining sub-millisecond performance for critical trading operations in the CEX Arbitrage Engine.*