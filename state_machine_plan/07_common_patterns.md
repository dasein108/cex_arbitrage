# Common Patterns and Utilities

## Shared Patterns Across All State Machines

### State Transition Pattern

```python
class StateTransitionMixin:
    """Mixin providing common state transition functionality."""
    
    def transition_to(self, new_state: StrategyState, reason: str = None):
        """
        Transition to new state with logging and validation.
        
        Args:
            new_state: Target state to transition to
            reason: Optional reason for transition
        """
        old_state = self.current_state
        
        # Validate transition is allowed
        if not self._is_valid_transition(old_state, new_state):
            raise ValueError(f"Invalid transition from {old_state} to {new_state}")
        
        # Record transition timing
        transition_time = time.perf_counter()
        
        # Update state
        self.current_state = new_state
        self.state_transition_count += 1
        
        # Log transition
        self._log_state_transition(old_state, new_state, transition_time, reason)
        
        # Update timing for terminal states
        if new_state in self._terminal_states():
            self.end_time = transition_time
            if self.start_time > 0:
                self.execution_time_ms = (self.end_time - self.start_time) * 1000
    
    def _is_valid_transition(self, from_state: StrategyState, to_state: StrategyState) -> bool:
        """Validate state transition is allowed."""
        # Default implementation allows all transitions
        # Override in specific strategies for custom validation
        return True
    
    def _terminal_states(self) -> set:
        """Return set of terminal states."""
        return {StrategyState.COMPLETED, StrategyState.ERROR, StrategyState.CANCELLED}
    
    def _log_state_transition(self, old_state, new_state, timestamp, reason):
        """Log state transition with details."""
        if hasattr(self, 'logger'):
            self.logger.info(
                "State transition",
                strategy_id=getattr(self, 'strategy_id', 'unknown'),
                old_state=old_state.value if hasattr(old_state, 'value') else str(old_state),
                new_state=new_state.value if hasattr(new_state, 'value') else str(new_state),
                reason=reason,
                timestamp=timestamp
            )
```

### Order Management Pattern

```python
class OrderManagementMixin:
    """Mixin providing common order management functionality."""
    
    async def place_order_with_retry(
        self, 
        exchange: 'ExchangeInterface',
        symbol: Symbol,
        side: Side,
        quantity: float,
        price: Optional[float] = None,
        order_type: str = 'market',
        max_retries: int = 3,
        retry_delay: float = 0.1
    ) -> Order:
        """
        Place order with retry logic and error handling.
        
        Args:
            exchange: Exchange to place order on
            symbol: Trading symbol
            side: Order side (BUY/SELL)
            quantity: Order quantity
            price: Order price (None for market orders)
            order_type: 'market' or 'limit'
            max_retries: Maximum retry attempts
            retry_delay: Delay between retries
            
        Returns:
            Executed order
            
        Raises:
            OrderExecutionError: If order fails after all retries
        """
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                if order_type == 'market':
                    order = await exchange.place_market_order(symbol, side, quantity)
                else:
                    if price is None:
                        raise ValueError("Price required for limit orders")
                    order = await exchange.place_limit_order(symbol, side, quantity, price)
                
                # Log successful order
                if hasattr(self, 'logger'):
                    self.logger.info(
                        "Order placed successfully",
                        symbol=str(symbol),
                        side=side.value,
                        quantity=quantity,
                        price=price,
                        order_id=order.order_id,
                        attempt=attempt + 1
                    )
                
                return order
                
            except Exception as e:
                last_error = e
                
                if hasattr(self, 'logger'):
                    self.logger.warning(
                        "Order placement failed",
                        symbol=str(symbol),
                        side=side.value,
                        quantity=quantity,
                        price=price,
                        attempt=attempt + 1,
                        error=str(e)
                    )
                
                # Don't retry on certain errors
                if self._is_non_retryable_error(e):
                    break
                
                # Wait before retry (except on last attempt)
                if attempt < max_retries:
                    await asyncio.sleep(retry_delay * (2 ** attempt))  # Exponential backoff
        
        raise OrderExecutionError(f"Order failed after {max_retries + 1} attempts: {last_error}")
    
    async def wait_for_order_fill(
        self,
        exchange: 'ExchangeInterface',
        order: Order,
        timeout: float = 10.0,
        check_interval: float = 0.1
    ) -> bool:
        """
        Wait for order to fill with timeout.
        
        Args:
            exchange: Exchange to check order on
            order: Order to monitor
            timeout: Maximum wait time in seconds
            check_interval: How often to check order status
            
        Returns:
            True if order filled, False if timeout
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                updated_order = await exchange.get_order_status(order.symbol, order.order_id)
                
                # Update order object with latest status
                order.status = updated_order.status
                order.filled_quantity = updated_order.filled_quantity
                order.average_price = updated_order.average_price
                order.fee_amount = getattr(updated_order, 'fee_amount', 0.0)
                
                if is_order_filled(updated_order):
                    if hasattr(self, 'logger'):
                        self.logger.info(
                            "Order filled",
                            order_id=order.order_id,
                            filled_quantity=order.filled_quantity,
                            average_price=order.average_price,
                            fill_time=time.time() - start_time
                        )
                    return True
                
            except Exception as e:
                if hasattr(self, 'logger'):
                    self.logger.warning("Error checking order status", order_id=order.order_id, error=str(e))
            
            await asyncio.sleep(check_interval)
        
        # Timeout reached
        if hasattr(self, 'logger'):
            self.logger.warning(
                "Order fill timeout",
                order_id=order.order_id,
                timeout=timeout,
                current_status=order.status
            )
        
        return False
    
    def _is_non_retryable_error(self, error: Exception) -> bool:
        """Check if error should not be retried."""
        # Common non-retryable error patterns
        error_str = str(error).lower()
        
        non_retryable_patterns = [
            'insufficient balance',
            'insufficient funds',
            'invalid symbol',
            'invalid quantity',
            'invalid price',
            'market closed',
            'trading suspended',
            'account suspended'
        ]
        
        return any(pattern in error_str for pattern in non_retryable_patterns)
```

### Market Data Pattern

```python
class MarketDataMixin:
    """Mixin providing common market data functionality."""
    
    async def get_current_price(
        self,
        exchange: 'ExchangeInterface',
        symbol: Symbol,
        side: Optional[Side] = None
    ) -> float:
        """
        Get current market price for symbol.
        
        Args:
            exchange: Exchange to get price from
            symbol: Trading symbol
            side: Optional side (BUY uses ask, SELL uses bid)
            
        Returns:
            Current price
        """
        try:
            ticker = await exchange.get_ticker(symbol)
            
            if side == Side.BUY:
                return ticker.ask  # Price we pay when buying
            elif side == Side.SELL:
                return ticker.bid  # Price we receive when selling
            else:
                return (ticker.bid + ticker.ask) / 2  # Mid price
                
        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.error("Failed to get current price", symbol=str(symbol), error=str(e))
            raise
    
    async def calculate_volatility(
        self,
        exchange: 'ExchangeInterface',
        symbol: Symbol,
        periods: int = 20,
        interval: str = '1m'
    ) -> float:
        """
        Calculate recent price volatility.
        
        Args:
            exchange: Exchange to get data from
            symbol: Trading symbol
            periods: Number of periods for calculation
            interval: Time interval for each period
            
        Returns:
            Volatility as standard deviation of returns
        """
        try:
            # Get recent klines/candlestick data
            klines = await exchange.get_klines(symbol, interval, limit=periods + 1)
            
            if len(klines) < 2:
                return 0.0
            
            # Calculate returns
            prices = [float(kline.close) for kline in klines]
            returns = []
            
            for i in range(1, len(prices)):
                ret = (prices[i] - prices[i-1]) / prices[i-1]
                returns.append(ret)
            
            # Calculate standard deviation
            if len(returns) < 2:
                return 0.0
            
            mean_return = sum(returns) / len(returns)
            variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
            volatility = variance ** 0.5
            
            return volatility
            
        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.warning("Failed to calculate volatility", symbol=str(symbol), error=str(e))
            return 0.0  # Return default volatility on error
    
    async def validate_orderbook_depth(
        self,
        exchange: 'ExchangeInterface',
        symbol: Symbol,
        side: Side,
        quantity: float,
        max_slippage_bps: int = 50
    ) -> bool:
        """
        Validate sufficient orderbook depth for trade.
        
        Args:
            exchange: Exchange to check
            symbol: Trading symbol
            side: Order side
            quantity: Required quantity
            max_slippage_bps: Maximum acceptable slippage in basis points
            
        Returns:
            True if sufficient depth, False otherwise
        """
        try:
            orderbook = await exchange.get_orderbook(symbol, limit=20)
            
            # Select appropriate side of orderbook
            levels = orderbook.asks if side == Side.BUY else orderbook.bids
            
            if not levels:
                return False
            
            # Calculate required quantity and average execution price
            remaining_quantity = quantity
            total_cost = 0.0
            best_price = levels[0].price
            
            for level in levels:
                if remaining_quantity <= 0:
                    break
                
                level_quantity = min(remaining_quantity, level.quantity)
                total_cost += level_quantity * level.price
                remaining_quantity -= level_quantity
            
            # Check if we can fill the entire quantity
            if remaining_quantity > 0:
                return False
            
            # Calculate average execution price and slippage
            avg_execution_price = total_cost / quantity
            slippage = abs(avg_execution_price - best_price) / best_price
            slippage_bps = int(slippage * 10000)
            
            return slippage_bps <= max_slippage_bps
            
        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.warning(
                    "Failed to validate orderbook depth",
                    symbol=str(symbol),
                    error=str(e)
                )
            return False
```

### Performance Monitoring Pattern

```python
class PerformanceMonitoringMixin:
    """Mixin providing common performance monitoring functionality."""
    
    def __init__(self):
        self.performance_metrics = {
            'state_transitions': [],
            'order_executions': [],
            'market_data_updates': [],
            'error_events': []
        }
        self.timing_context = {}
    
    def start_timing(self, operation: str) -> str:
        """Start timing an operation."""
        timing_id = f"{operation}_{time.time()}"
        self.timing_context[timing_id] = {
            'operation': operation,
            'start_time': time.perf_counter(),
            'end_time': None
        }
        return timing_id
    
    def end_timing(self, timing_id: str) -> float:
        """End timing and return duration."""
        if timing_id not in self.timing_context:
            return 0.0
        
        context = self.timing_context[timing_id]
        context['end_time'] = time.perf_counter()
        duration = context['end_time'] - context['start_time']
        
        # Record performance metric
        self.performance_metrics['order_executions'].append({
            'operation': context['operation'],
            'duration_ms': duration * 1000,
            'timestamp': time.time()
        })
        
        return duration
    
    def record_state_transition_performance(
        self,
        from_state: str,
        to_state: str,
        duration_ms: float
    ):
        """Record state transition performance."""
        self.performance_metrics['state_transitions'].append({
            'from_state': from_state,
            'to_state': to_state,
            'duration_ms': duration_ms,
            'timestamp': time.time()
        })
    
    def record_market_data_update(self, symbol: str, latency_ms: float):
        """Record market data update latency."""
        self.performance_metrics['market_data_updates'].append({
            'symbol': symbol,
            'latency_ms': latency_ms,
            'timestamp': time.time()
        })
    
    def record_error_event(self, error_type: str, error_message: str):
        """Record error event."""
        self.performance_metrics['error_events'].append({
            'error_type': error_type,
            'error_message': error_message,
            'timestamp': time.time()
        })
    
    def get_performance_summary(self) -> dict:
        """Get performance summary statistics."""
        summary = {}
        
        # State transition performance
        transitions = self.performance_metrics['state_transitions']
        if transitions:
            durations = [t['duration_ms'] for t in transitions]
            summary['state_transitions'] = {
                'count': len(transitions),
                'avg_duration_ms': sum(durations) / len(durations),
                'max_duration_ms': max(durations),
                'min_duration_ms': min(durations)
            }
        
        # Order execution performance
        executions = self.performance_metrics['order_executions']
        if executions:
            durations = [e['duration_ms'] for e in executions]
            summary['order_executions'] = {
                'count': len(executions),
                'avg_duration_ms': sum(durations) / len(durations),
                'max_duration_ms': max(durations),
                'min_duration_ms': min(durations)
            }
        
        # Market data performance
        updates = self.performance_metrics['market_data_updates']
        if updates:
            latencies = [u['latency_ms'] for u in updates]
            summary['market_data'] = {
                'count': len(updates),
                'avg_latency_ms': sum(latencies) / len(latencies),
                'max_latency_ms': max(latencies),
                'min_latency_ms': min(latencies)
            }
        
        # Error summary
        errors = self.performance_metrics['error_events']
        summary['errors'] = {
            'count': len(errors),
            'types': list(set(e['error_type'] for e in errors))
        }
        
        return summary
```

### Risk Management Pattern

```python
class RiskManagementMixin:
    """Mixin providing common risk management functionality."""
    
    def __init__(self):
        self.risk_limits = {
            'max_position_value': 10000.0,
            'max_daily_loss': 1000.0,
            'max_order_size': 1000.0,
            'max_slippage_bps': 50,
            'max_execution_time_ms': 5000.0
        }
        self.risk_metrics = {
            'daily_pnl': 0.0,
            'current_positions': {},
            'order_count': 0,
            'error_count': 0
        }
    
    def validate_position_limit(self, symbol: Symbol, quantity: float, price: float) -> bool:
        """Validate position doesn't exceed limits."""
        position_value = quantity * price
        
        # Check individual position limit
        if position_value > self.risk_limits['max_position_value']:
            if hasattr(self, 'logger'):
                self.logger.warning(
                    "Position exceeds value limit",
                    symbol=str(symbol),
                    position_value=position_value,
                    limit=self.risk_limits['max_position_value']
                )
            return False
        
        # Check order size limit
        if quantity > self.risk_limits['max_order_size']:
            if hasattr(self, 'logger'):
                self.logger.warning(
                    "Order exceeds size limit",
                    symbol=str(symbol),
                    quantity=quantity,
                    limit=self.risk_limits['max_order_size']
                )
            return False
        
        return True
    
    def validate_daily_loss_limit(self, potential_loss: float) -> bool:
        """Validate potential loss doesn't exceed daily limit."""
        projected_daily_pnl = self.risk_metrics['daily_pnl'] + potential_loss
        
        if projected_daily_pnl < -self.risk_limits['max_daily_loss']:
            if hasattr(self, 'logger'):
                self.logger.warning(
                    "Trade would exceed daily loss limit",
                    current_pnl=self.risk_metrics['daily_pnl'],
                    potential_loss=potential_loss,
                    projected_pnl=projected_daily_pnl,
                    limit=self.risk_limits['max_daily_loss']
                )
            return False
        
        return True
    
    def validate_execution_time(self, start_time: float) -> bool:
        """Validate execution time hasn't exceeded limit."""
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        
        if elapsed_ms > self.risk_limits['max_execution_time_ms']:
            if hasattr(self, 'logger'):
                self.logger.warning(
                    "Execution time exceeded limit",
                    elapsed_ms=elapsed_ms,
                    limit=self.risk_limits['max_execution_time_ms']
                )
            return False
        
        return True
    
    def update_risk_metrics(self, pnl: float, symbol: Symbol, position_change: float):
        """Update risk metrics after trade."""
        self.risk_metrics['daily_pnl'] += pnl
        
        # Update position tracking
        symbol_str = str(symbol)
        if symbol_str not in self.risk_metrics['current_positions']:
            self.risk_metrics['current_positions'][symbol_str] = 0.0
        
        self.risk_metrics['current_positions'][symbol_str] += position_change
        
        # Clean up zero positions
        if abs(self.risk_metrics['current_positions'][symbol_str]) < 1e-8:
            del self.risk_metrics['current_positions'][symbol_str]
        
        self.risk_metrics['order_count'] += 1
    
    def get_risk_summary(self) -> dict:
        """Get current risk summary."""
        total_position_value = sum(
            abs(pos) for pos in self.risk_metrics['current_positions'].values()
        )
        
        return {
            'daily_pnl': self.risk_metrics['daily_pnl'],
            'total_position_value': total_position_value,
            'position_count': len(self.risk_metrics['current_positions']),
            'order_count': self.risk_metrics['order_count'],
            'error_count': self.risk_metrics['error_count'],
            'risk_utilization': {
                'position_value_pct': (total_position_value / self.risk_limits['max_position_value']) * 100,
                'daily_loss_pct': (abs(min(0, self.risk_metrics['daily_pnl'])) / self.risk_limits['max_daily_loss']) * 100
            }
        }
```

## Common Utility Functions

### Error Handling Utilities

```python
class StrategyError(Exception):
    """Base exception for strategy errors."""
    pass

class OrderExecutionError(StrategyError):
    """Error during order execution."""
    pass

class MarketDataError(StrategyError):
    """Error with market data."""
    pass

class RiskLimitError(StrategyError):
    """Risk limit exceeded."""
    pass

class TimeoutError(StrategyError):
    """Operation timeout."""
    pass

def handle_strategy_error(error: Exception, context: BaseStrategyContext) -> StrategyError:
    """Convert general exceptions to strategy-specific errors."""
    if isinstance(error, StrategyError):
        return error
    
    error_str = str(error).lower()
    
    # Classify error types
    if any(keyword in error_str for keyword in ['timeout', 'time out', 'timed out']):
        return TimeoutError(f"Operation timeout: {error}")
    
    if any(keyword in error_str for keyword in ['insufficient', 'balance', 'funds']):
        return RiskLimitError(f"Insufficient funds: {error}")
    
    if any(keyword in error_str for keyword in ['order', 'execution', 'fill']):
        return OrderExecutionError(f"Order execution failed: {error}")
    
    if any(keyword in error_str for keyword in ['price', 'market', 'data']):
        return MarketDataError(f"Market data error: {error}")
    
    # Default to generic strategy error
    return StrategyError(f"Strategy error: {error}")
```

### Timing Utilities

```python
class TimingContext:
    """Context manager for timing operations."""
    
    def __init__(self, operation_name: str, logger=None):
        self.operation_name = operation_name
        self.logger = logger
        self.start_time = None
        self.end_time = None
    
    def __enter__(self):
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.perf_counter()
        duration_ms = (self.end_time - self.start_time) * 1000
        
        if self.logger:
            self.logger.debug(
                "Operation timing",
                operation=self.operation_name,
                duration_ms=duration_ms,
                success=exc_type is None
            )
    
    @property
    def duration_ms(self) -> float:
        """Get duration in milliseconds."""
        if self.start_time is None:
            return 0.0
        
        end_time = self.end_time or time.perf_counter()
        return (end_time - self.start_time) * 1000

# Usage example:
# async def some_operation():
#     with TimingContext("order_execution", logger) as timer:
#         result = await place_order(...)
#     print(f"Order took {timer.duration_ms:.2f}ms")
```

These common patterns provide:

1. **Consistent Behavior**: All state machines use the same patterns
2. **Reusable Code**: Avoid duplicating common functionality
3. **Performance Monitoring**: Built-in timing and metrics collection
4. **Risk Management**: Consistent risk checks across strategies
5. **Error Handling**: Standardized error classification and handling
6. **Market Data**: Common market data access patterns
7. **Order Management**: Robust order execution with retries

By using these mixins and utilities, all state machines inherit robust, battle-tested functionality while maintaining the clarity and simplicity of the state machine pattern.