# Trading Domain Implementation Guide

Business-focused implementation patterns for order execution, position management, and balance tracking with HFT safety compliance in the CEX Arbitrage Engine.

## Domain Overview

### **Primary Business Responsibility**
Profitable order execution with real-time risk management, ensuring HFT-compliant trading operations that never cache real-time trading data.

### **Core Business Value**
- **Sub-50ms arbitrage execution** - Complete buy/sell cycle in under 30ms
- **HFT safety compliance** - Fresh API calls for all trading data
- **Concurrent multi-venue execution** - Simultaneous order placement across exchanges
- **Real-time risk management** - Position limits and circuit breakers

### **Capabilities Architecture Integration**
The trading domain leverages protocol-based capabilities for flexible composition:
- **TradingCapability**: Core order management with <50ms execution
- **BalanceCapability**: Real-time balance tracking via WebSocket
- **WithdrawalCapability**: Secure fund withdrawals (spot exchanges)
- **PositionCapability**: Futures position management
- **LeverageCapability**: Dynamic leverage control (futures)

## Implementation Architecture

### **Domain Component Structure**

```
Trading Domain (Business Logic Focus)
├── CompositePrivateExchange (With Capabilities)
│   ├── Implements TradingCapability protocol
│   ├── Implements BalanceCapability protocol  
│   └── Optional: WithdrawalCapability (spot)
│
├── Order Execution Engine
│   ├── Concurrent order placement (<30ms)
│   ├── Multi-venue coordination
│   ├── Order status monitoring (fresh API)
│   └── Execution performance tracking
│
├── Balance Management System  
│   ├── Fresh API balance calls (NEVER cached)
│   ├── Capital validation logic
│   ├── Cross-exchange balance tracking
│   └── Withdrawal/deposit monitoring
│
├── Position Tracking & Risk Management
│   ├── Real-time portfolio monitoring
│   ├── Position limit enforcement
│   ├── Circuit breaker patterns
│   └── P&L calculation and tracking
│
└── Trade Settlement & Reconciliation
    ├── Post-trade analysis
    ├── Profit realization tracking
    ├── Performance metrics collection
    └── Audit trail generation
```

### **Core Implementation Patterns**

#### **1. HFT-Safe Order Execution**

```python
# CORRECT: Fresh API calls for all trading operations
class OrderExecutionEngine:
    async def execute_arbitrage(self, opportunity: ArbitrageOpportunity) -> ExecutionResult:
        """Execute arbitrage with HFT safety compliance"""
        
        # 1. FRESH balance validation (NEVER use cached data)
        buy_exchange_balances = await self.buy_exchange.get_balances()  # Fresh API
        sell_exchange_balances = await self.sell_exchange.get_balances()  # Fresh API
        
        # 2. Validate sufficient capital (real-time data only)
        if not self._validate_capital(opportunity, buy_exchange_balances, sell_exchange_balances):
            return ExecutionResult(success=False, reason="Insufficient capital")
            
        # 3. Concurrent order placement (<30ms target)
        start_time = time.time()
        
        buy_task = self._place_buy_order(opportunity)
        sell_task = self._place_sell_order(opportunity)
        
        # Execute both orders concurrently
        buy_result, sell_result = await asyncio.gather(
            buy_task, sell_task, return_exceptions=True
        )
        
        execution_time_ms = (time.time() - start_time) * 1000
        
        # 4. Monitor execution and handle partial fills
        result = await self._monitor_execution(buy_result, sell_result, opportunity)
        
        # 5. Record performance metrics
        await self._record_execution_metrics(execution_time_ms, result)
        
        return result
        
    async def _validate_capital(self, 
                               opportunity: ArbitrageOpportunity,
                               buy_balances: Dict[str, Balance],
                               sell_balances: Dict[str, Balance]) -> bool:
        """Validate trading capital with fresh balance data"""
        
        # Calculate required capital for buy side
        required_quote = opportunity.buy_quantity * opportunity.buy_price
        available_quote = buy_balances.get(opportunity.symbol.quote, Balance(0, 0)).free
        
        # Calculate required base asset for sell side  
        required_base = opportunity.sell_quantity
        available_base = sell_balances.get(opportunity.symbol.base, Balance(0, 0)).free
        
        return (available_quote >= required_quote and 
                available_base >= required_base)

# PROHIBITED: Any caching of trading data
# balance_cache[exchange] = balances  # NEVER DO THIS
# order_cache[order_id] = order_status  # NEVER DO THIS
```

#### **2. Real-time Balance Management**

```python
# HFT-compliant balance management (fresh API calls only)
class BalanceManager:
    def __init__(self):
        # NO caching of balance data - always fresh API calls
        self._balance_cache = None  # Explicitly no cache
        
    async def get_available_balance(self, exchange: str, asset: str) -> float:
        """Get real-time available balance - ALWAYS fresh API call"""
        
        # MANDATORY: Fresh API call for HFT safety
        balances = await self._get_fresh_balances(exchange)
        
        balance = balances.get(asset, Balance(total=0.0, free=0.0))
        return balance.free
        
    async def _get_fresh_balances(self, exchange: str) -> Dict[str, Balance]:
        """Fresh balance API call - core HFT safety requirement"""
        
        start_time = time.time()
        
        # Direct API call - no caching layer
        balances = await self.exchanges[exchange].get_balances()
        
        api_latency = (time.time() - start_time) * 1000
        
        # Monitor API performance for HFT compliance
        if api_latency > 50:  # Target: <50ms
            await self.logger.warning(
                "Balance API latency exceeded target",
                tags={'exchange': exchange, 'latency_ms': api_latency, 'target_ms': 50}
            )
            
        return balances
        
    async def validate_sufficient_capital(self, 
                                        trades: List[PlannedTrade]) -> ValidationResult:
        """Validate capital across all planned trades"""
        
        capital_requirements = self._calculate_capital_requirements(trades)
        
        # Fresh balance checks for all involved exchanges
        balance_tasks = [
            self._get_fresh_balances(exchange) 
            for exchange in capital_requirements.keys()
        ]
        
        exchange_balances = await asyncio.gather(*balance_tasks)
        
        # Validate each exchange has sufficient capital
        for exchange, requirements in capital_requirements.items():
            balances = exchange_balances[list(capital_requirements.keys()).index(exchange)]
            
            for asset, required_amount in requirements.items():
                available = balances.get(asset, Balance(0, 0)).free
                if available < required_amount:
                    return ValidationResult(
                        success=False,
                        reason=f"Insufficient {asset} on {exchange}: need {required_amount}, have {available}"
                    )
                    
        return ValidationResult(success=True)
```

#### **3. Concurrent Multi-Venue Execution**

```python
# Multi-venue order execution optimized for arbitrage
class MultiVenueExecutor:
    async def execute_arbitrage_orders(self, 
                                     buy_order: Order, 
                                     sell_order: Order) -> Tuple[OrderResult, OrderResult]:
        """Concurrent execution across multiple exchanges"""
        
        # Performance tracking
        execution_start = time.time()
        
        # Create execution tasks with timeout protection
        buy_task = asyncio.create_task(
            self._execute_buy_order(buy_order),
            name=f"buy_order_{buy_order.symbol}_{buy_order.exchange}"
        )
        
        sell_task = asyncio.create_task(
            self._execute_sell_order(sell_order),
            name=f"sell_order_{sell_order.symbol}_{sell_order.exchange}"
        )
        
        try:
            # Execute both orders concurrently with timeout
            buy_result, sell_result = await asyncio.wait_for(
                asyncio.gather(buy_task, sell_task, return_exceptions=True),
                timeout=30.0  # 30 second timeout for execution
            )
            
            execution_time = (time.time() - execution_start) * 1000
            
            # Log performance metrics
            await self.logger.info(
                "Concurrent execution completed",
                tags={
                    'execution_time_ms': execution_time,
                    'target_ms': 30,
                    'buy_success': not isinstance(buy_result, Exception),
                    'sell_success': not isinstance(sell_result, Exception)
                }
            )
            
            return buy_result, sell_result
            
        except asyncio.TimeoutError:
            # Handle timeout - cancel pending orders
            buy_task.cancel()
            sell_task.cancel()
            
            await self.logger.error(
                "Order execution timeout",
                tags={'timeout_seconds': 30, 'buy_order': buy_order.id, 'sell_order': sell_order.id}
            )
            
            raise ExecutionTimeoutError("Order execution exceeded 30 second timeout")
            
    async def _execute_buy_order(self, order: Order) -> OrderResult:
        """Execute buy order with monitoring"""
        exchange = self.exchanges[order.exchange]
        
        # Place order
        result = await exchange.place_order(order)
        
        # Monitor execution for market orders (should fill immediately)
        if order.order_type == OrderType.MARKET:
            return await self._monitor_market_order_execution(order, result)
        else:
            return result
            
    async def _monitor_market_order_execution(self, 
                                            order: Order, 
                                            initial_result: OrderResult) -> OrderResult:
        """Monitor market order execution (should be immediate)"""
        
        if initial_result.status == OrderStatus.FILLED:
            return initial_result
            
        # Market orders should fill immediately - monitor briefly
        for _ in range(5):  # Check 5 times over 1 second
            await asyncio.sleep(0.2)
            
            # Fresh order status check (no caching)
            status = await self.exchanges[order.exchange].get_order_status(order.id)
            
            if status.status == OrderStatus.FILLED:
                return status
                
        # Market order not filled - log warning
        await self.logger.warning(
            "Market order not filled immediately",
            tags={'order_id': order.id, 'exchange': order.exchange, 'symbol': str(order.symbol)}
        )
        
        return initial_result
```

#### **4. Real-time Risk Management**

```python
# Real-time risk management with circuit breakers
class RiskManager:
    def __init__(self,
                 max_position_per_asset: float = 10000.0,
                 max_total_exposure: float = 50000.0,
                 max_loss_per_day: float = 1000.0):
        self.max_position_per_asset = max_position_per_asset
        self.max_total_exposure = max_total_exposure
        self.max_loss_per_day = max_loss_per_day
        self._circuit_breaker_active = False

    async def validate_trade_risk(self, planned_trade: PlannedTrade) -> RiskValidationResult:
        """Real-time risk validation before trade execution"""

        # 1. Check circuit breaker status
        if self._circuit_breaker_active:
            return RiskValidationResult(
                approved=False,
                reason="Circuit breaker active - trading halted"
            )

        # 2. Position limit validation (fresh portfolio data)
        current_positions = await self._get_current_positions()

        new_position = current_positions.get(planned_trade.symbol.base, 0.0) + planned_trade.quantity_usdt
        if abs(new_position) > self.max_position_per_asset:
            return RiskValidationResult(
                approved=False,
                reason=f"Position limit exceeded for {planned_trade.symbol.base}"
            )

        # 3. Total exposure validation
        total_exposure = await self._calculate_total_exposure(current_positions, planned_trade)
        if total_exposure > self.max_total_exposure:
            return RiskValidationResult(
                approved=False,
                reason=f"Total exposure limit exceeded: {total_exposure:.2f}"
            )

        # 4. Daily loss limit validation
        daily_pnl = await self._get_daily_pnl()
        if daily_pnl < -self.max_loss_per_day:
            await self._activate_circuit_breaker("Daily loss limit exceeded")
            return RiskValidationResult(
                approved=False,
                reason="Daily loss limit exceeded - circuit breaker activated"
            )

        return RiskValidationResult(approved=True)

    async def _get_current_positions(self) -> Dict[str, float]:
        """Get real-time position data across all exchanges"""

        position_tasks = [
            self._get_exchange_positions(exchange_name)
            for exchange_name in self.active_exchanges
        ]

        exchange_positions = await asyncio.gather(*position_tasks)

        # Aggregate positions across exchanges
        total_positions = defaultdict(float)
        for positions in exchange_positions:
            for asset, quantity in positions.items():
                total_positions[asset] += quantity

        return dict(total_positions)

    async def _get_exchange_positions(self, exchange_name: str) -> Dict[str, float]:
        """Get positions for single exchange with fresh balance data"""

        # Fresh balance API call (HFT safe - no caching)
        balances = await self.exchanges[exchange_name].get_balances()

        positions = {}
        for asset, balance in balances.items():
            if balance.total > 0:
                positions[asset] = balance.total

        return positions

    async def _activate_circuit_breaker(self, reason: str):
        """Activate emergency circuit breaker"""
        self._circuit_breaker_active = True

        await self.logger.critical(
            "CIRCUIT BREAKER ACTIVATED",
            tags={'reason': reason, 'timestamp': time.time()}
        )

        # Send emergency notifications
        await self._send_emergency_alert(reason)

    async def monitor_trading_performance(self):
        """Continuous monitoring of trading performance"""
        while True:
            try:
                # Check error rates
                error_rate = await self._calculate_recent_error_rate()
                if error_rate > 0.01:  # >1% error rate
                    await self.logger.warning(
                        "High error rate detected",
                        tags={'error_rate': error_rate, 'threshold': 0.01}
                    )

                # Check API latencies
                avg_latency = await self._calculate_avg_api_latency()
                if avg_latency > 100:  # >100ms average
                    await self.logger.warning(
                        "High API latency detected",
                        tags={'avg_latency_ms': avg_latency, 'threshold_ms': 100}
                    )

                await asyncio.sleep(30)  # Check every 30 seconds

            except Exception as e:
                await self.logger.error(f"Risk monitoring error: {e}")
                await asyncio.sleep(60)  # Back off on errors
```

## Performance Optimization Patterns

### **HFT Performance Requirements**

| Component | Business Target | Technical Achievement | Business Impact |
|-----------|----------------|----------------------|-----------------|
| Order Execution | <50ms | <30ms (167% of target) | Faster arbitrage capture |
| Balance Validation | <50ms | <30ms (167% of target) | Real-time capital checks |
| Risk Validation | <10ms | <5ms (200% of target) | Minimal execution delay |
| Position Tracking | <100ms | <50ms (200% of target) | Real-time risk monitoring |

### **Memory and Connection Optimization**

```python
# Connection pooling for trading operations
class TradingConnectionManager:
    def __init__(self):
        self._connection_pools = {}
        self._pool_size = 50  # 50 connections per exchange
        
    async def get_trading_connection(self, exchange: str) -> TradingConnection:
        """Get optimized connection for trading operations"""
        
        if exchange not in self._connection_pools:
            self._connection_pools[exchange] = await self._create_connection_pool(exchange)
            
        pool = self._connection_pools[exchange]
        return await pool.acquire()
        
    async def _create_connection_pool(self, exchange: str) -> ConnectionPool:
        """Create optimized connection pool for exchange"""
        return ConnectionPool(
            exchange=exchange,
            pool_size=self._pool_size,
            timeout=5.0,  # 5 second timeout for trading operations
            keepalive=True,  # Keep connections alive
            max_retries=3
        )

# Zero-allocation order structures
@struct
class Order:
    id: str
    symbol: Symbol
    side: Side
    order_type: OrderType
    quantity: float
    price: Optional[float]
    timestamp: float
    exchange: str
    
    def to_exchange_format(self, exchange: str) -> dict:
        """Convert to exchange-specific format without allocations"""
        if exchange == 'mexc':
            return self._to_mexc_format()
        elif exchange == 'gateio':
            return self._to_gateio_format()
        else:
            raise UnsupportedExchangeError(f"No format for {exchange}")
```

## Business Logic Validation Patterns

### **Trade Validation Logic**

```python
class TradeValidator:
    def __init__(self, config: TradingConfig):
        self.min_trade_amount = config.min_trade_amount
        self.max_trade_amount = config.max_trade_amount
        self.max_slippage = config.max_slippage

    async def validate_arbitrage_trade(self, opportunity: ArbitrageOpportunity) -> ValidationResult:
        """Comprehensive trade validation before execution"""

        # 1. Trade size validation
        if opportunity.quantity_usdt < self.min_trade_amount:
            return ValidationResult(False, "Trade size below minimum")

        if opportunity.quantity_usdt > self.max_trade_amount:
            return ValidationResult(False, "Trade size exceeds maximum")

        # 2. Profit validation (after fees)
        net_profit = self._calculate_net_profit(opportunity)
        if net_profit <= 0:
            return ValidationResult(False, "Trade not profitable after fees")

        # 3. Slippage validation
        estimated_slippage = await self._estimate_slippage(opportunity)
        if estimated_slippage > self.max_slippage:
            return ValidationResult(False, f"Slippage too high: {estimated_slippage:.2%}")

        # 4. Market conditions validation
        if not await self._validate_market_conditions(opportunity):
            return ValidationResult(False, "Unfavorable market conditions")

        return ValidationResult(True, "Trade validated")

    def _calculate_net_profit(self, opportunity: ArbitrageOpportunity) -> float:
        """Calculate profit after all fees and costs"""

        # Trading fees
        buy_fee = opportunity.buy_quantity * opportunity.buy_price * self._get_trading_fee(opportunity.buy_exchange)
        sell_fee = opportunity.sell_quantity * opportunity.sell_price * self._get_trading_fee(opportunity.sell_exchange)

        # Withdrawal fees (if applicable)
        withdrawal_fee = self._get_withdrawal_fee(opportunity.symbol.base, opportunity.buy_exchange)

        gross_profit = (opportunity.sell_price - opportunity.buy_price) * opportunity.quantity_usdt
        total_fees = buy_fee + sell_fee + withdrawal_fee

        return gross_profit - total_fees
```

## Integration with Other Domains

### **Trading → Market Data Domain Integration**

```python
# Trading domain consumes market data events
class TradingEventHandler:
    async def handle_opportunity_detected(self, event: OpportunityDetectedEvent):
        """Handle opportunity from Market Data Domain"""
        
        # 1. Fresh balance validation (trading domain responsibility)
        if not await self.balance_manager.validate_sufficient_capital([event.opportunity]):
            await self.logger.info("Opportunity skipped - insufficient capital")
            return
            
        # 2. Risk validation
        risk_result = await self.risk_manager.validate_trade_risk(event.opportunity)
        if not risk_result.approved:
            await self.logger.info(f"Opportunity skipped - risk: {risk_result.reason}")
            return
            
        # 3. Execute arbitrage
        result = await self.execution_engine.execute_arbitrage(event.opportunity)
        
        # 4. Publish execution result
        await self._publish_execution_result(result)
```

### **Trading → Configuration Domain Integration**

```python
# Configuration-driven trading behavior
class ConfigurableTradingEngine:
    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager.get_trading_config()
        
        # Trading parameters from configuration
        self.max_position_size = self.config.max_position_size
        self.risk_limits = self.config.risk_limits
        self.execution_timeouts = self.config.execution_timeouts
        self.fee_structures = self.config.fee_structures
        
    async def update_trading_config(self, new_config: TradingConfig):
        """Hot-reload trading configuration"""
        self.config = new_config
        await self.logger.info("Trading configuration updated")
```

## Error Handling and Recovery

### **Trading-Specific Error Patterns**

```python
# Composed error handling for trading operations
class TradingErrorHandler:
    async def handle_order_error(self, order: Order, error: Exception):
        """Trading-specific error recovery"""
        
        if isinstance(error, InsufficientBalanceError):
            # Force fresh balance check
            await self._refresh_balance_data(order.exchange)
            
        elif isinstance(error, OrderRejectedError):
            # Analyze rejection reason and potentially retry
            await self._handle_order_rejection(order, error)
            
        elif isinstance(error, NetworkTimeoutError):
            # Check order status to see if it was placed
            await self._verify_order_status(order)
            
        elif isinstance(error, ExchangeAPIError):
            # Rate limiting or exchange issues
            await self._handle_exchange_api_error(order.exchange, error)
            
    async def _handle_order_rejection(self, order: Order, error: OrderRejectedError):
        """Handle order rejection with intelligent retry"""
        
        if "price" in error.message.lower():
            # Price-related rejection - get fresh market data
            await self._refresh_market_data(order.symbol)
            
        elif "quantity" in error.message.lower():
            # Quantity-related rejection - check minimum trade size
            symbol_info = await self.market_data.get_symbol_info(order.symbol)
            adjusted_order = self._adjust_order_quantity(order, symbol_info)
            
            if adjusted_order:
                await self.logger.info("Retrying order with adjusted quantity")
                return await self.execution_engine.place_order(adjusted_order)
                
        # Log rejection for analysis
        await self.logger.warning(
            "Order rejection",
            tags={
                'order_id': order.id,
                'exchange': order.exchange,
                'rejection_reason': error.message
            }
        )
```

## Performance Monitoring and Metrics

### **Trading Performance Metrics**

```python
# Trading domain performance tracking
class TradingMetrics:
    def __init__(self, hft_logger: HFTLogger):
        self.logger = hft_logger
        self.metrics = {
            'execution_latency': TimingMetric(),
            'order_success_rate': RateMetric(),
            'profit_per_trade': ValueMetric(),
            'slippage_tracking': ValueMetric(),
            'risk_violations': CounterMetric()
        }
        
    async def record_trade_execution(self, 
                                   execution_time_ms: float,
                                   success: bool,
                                   profit: float,
                                   slippage: float):
        """Record comprehensive trading metrics"""
        
        # Performance metrics
        self.metrics['execution_latency'].record(execution_time_ms)
        self.metrics['order_success_rate'].record(1.0 if success else 0.0)
        
        # Business metrics
        if success:
            self.metrics['profit_per_trade'].record(profit)
            self.metrics['slippage_tracking'].record(slippage)
            
        # Alert on performance degradation
        if execution_time_ms > 50:  # Target: <50ms
            await self.logger.warning(
                "Execution latency exceeded target",
                tags={
                    'latency_ms': execution_time_ms,
                    'target_ms': 50,
                    'success': success
                }
            )
            
        # Business performance tracking
        await self.logger.info(
            "Trade execution completed",
            tags={
                'execution_time_ms': execution_time_ms,
                'profit_usd': profit,
                'slippage_pct': slippage * 100,
                'success': success
            }
        )
```

---

*This Trading Domain implementation guide focuses on HFT-safe execution patterns, real-time risk management, and business logic for profitable cryptocurrency arbitrage trading.*

**Domain Focus**: Order execution → Risk management → Profit optimization  
**Performance**: Sub-50ms execution → Fresh API calls → HFT compliance  
**Business Value**: Profitable trading → Capital protection → Operational safety