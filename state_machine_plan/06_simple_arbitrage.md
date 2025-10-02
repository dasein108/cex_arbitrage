# Simple Arbitrage State Machine

## Strategy Overview

**Purpose**: Exploit price differences between exchanges for the same asset by simultaneously buying low on one exchange and selling high on another (hedging + swap). This is the core arbitrage strategy that captures risk-free profit from price inefficiencies.

**Arbitrage Definition**: Hedging (risk elimination) + Swap (position exchange)
- **Hedging Component**: Eliminate market risk by taking offsetting positions
- **Swap Component**: Exchange positions between venues to capture price difference

**Use Cases**:
- Cross-exchange spot arbitrage (BTC/USDT on Exchange A vs Exchange B)
- Cross-pair arbitrage (BTC/USDT vs BTC/EUR with EUR/USDT conversion)
- Triangular arbitrage (multi-step currency conversion)
- Stablecoin arbitrage (USDT vs USDC price differences)

## State Flow Diagram

```
SCANNING_OPPORTUNITIES
    ↓
OPPORTUNITY_DETECTED
    ↓
VALIDATING_OPPORTUNITY
    ↓
EXECUTING_BUY_SIDE ←→ EXECUTING_SELL_SIDE
    ↓
MONITORING_EXECUTION
    ↓
PROFIT_REALIZED
    ↓
COMPLETED
```

## State Definitions

### 1. SCANNING_OPPORTUNITIES
**Purpose**: Continuously scan for arbitrage opportunities across exchanges

**Entry Conditions**:
- Strategy initialized with target symbol pairs
- Price feeds active from all target exchanges
- Sufficient balance on all exchanges

**Activities**:
- Monitor real-time prices from multiple exchanges
- Calculate price differences and potential profit
- Account for trading fees and transfer costs
- Filter opportunities by minimum profit threshold
- Check liquidity availability on both sides

**Exit Conditions**:
- **→ OPPORTUNITY_DETECTED**: Profitable opportunity found above threshold
- **→ ERROR**: Price feed issues or insufficient funds

**Performance Target**: <10ms scan cycle per opportunity

### 2. OPPORTUNITY_DETECTED
**Purpose**: Initial opportunity detected, lock in prices for validation

**Entry Conditions**:
- Price difference exceeds minimum profit threshold
- Basic liquidity check passed

**Activities**:
- Lock current price quotes from both exchanges
- Calculate exact profit potential including all fees
- Prepare order parameters for both sides
- Validate account balances and available funds

**Exit Conditions**:
- **→ VALIDATING_OPPORTUNITY**: Opportunity locked and ready for validation
- **→ SCANNING_OPPORTUNITIES**: Opportunity insufficient or disappeared

**Performance Target**: <50ms opportunity detection

### 3. VALIDATING_OPPORTUNITY
**Purpose**: Detailed validation of arbitrage opportunity

**Entry Conditions**:
- Opportunity detected and prices locked
- Order parameters calculated

**Activities**:
- Refresh price data to ensure opportunity still exists
- Validate orderbook depth for required trade sizes
- Check account balances on both exchanges
- Estimate execution slippage and timing risk
- Confirm minimum profit after all costs

**Exit Conditions**:
- **→ EXECUTING_BUY_SIDE**: Opportunity validated, begin execution
- **→ SCANNING_OPPORTUNITIES**: Opportunity no longer profitable

**Performance Target**: <100ms validation time

### 4. EXECUTING_BUY_SIDE
**Purpose**: Execute the buy order on the lower-priced exchange

**Entry Conditions**:
- Opportunity validated successfully
- Ready to execute buy side

**Activities**:
- Place market or aggressive limit order on buy exchange
- Monitor order execution and slippage
- Update position tracking
- Prepare for immediate sell side execution

**Exit Conditions**:
- **→ EXECUTING_SELL_SIDE**: Buy order filled, execute sell side
- **→ ERROR**: Buy order failed or significant slippage

**Performance Target**: <500ms buy execution

### 5. EXECUTING_SELL_SIDE
**Purpose**: Execute the sell order on the higher-priced exchange

**Entry Conditions**:
- Buy side executed successfully
- Ready for sell side execution

**Activities**:
- Place market or aggressive limit order on sell exchange
- Monitor execution to completion
- Validate both sides executed as expected
- Calculate actual arbitrage profit realized

**Exit Conditions**:
- **→ MONITORING_EXECUTION**: Both sides executed, monitor settlement
- **→ ERROR**: Sell side failed, may have directional exposure

**Performance Target**: <500ms sell execution

### 6. MONITORING_EXECUTION
**Purpose**: Monitor trade settlement and position reconciliation

**Entry Conditions**:
- Both buy and sell orders executed
- Arbitrage trade completed

**Activities**:
- Monitor trade settlement on both exchanges
- Reconcile actual fills vs expected quantities
- Handle any partial fills or execution issues
- Calculate final profit/loss including all fees
- Update performance metrics

**Exit Conditions**:
- **→ PROFIT_REALIZED**: Trades settled successfully
- **→ ERROR**: Settlement issues or reconciliation problems

**Performance Target**: <1s monitoring time

### 7. PROFIT_REALIZED
**Purpose**: Finalize arbitrage trade and record results

**Entry Conditions**:
- Both trades settled successfully
- Profit/loss calculated

**Activities**:
- Record final arbitrage results
- Update strategy performance metrics
- Log trade details for analysis
- Prepare for next arbitrage opportunity

**Exit Conditions**:
- **→ COMPLETED**: Arbitrage cycle completed successfully
- **→ SCANNING_OPPORTUNITIES**: Ready for next opportunity (if continuous mode)

**Performance Target**: <100ms finalization

## Context Structure

```python
@dataclass
class SimpleArbitrageContext(BaseStrategyContext):
    """Context for simple cross-exchange arbitrage strategy."""
    
    # Strategy configuration
    symbol: Symbol                          # Target trading symbol
    buy_exchange: str                       # Exchange to buy from (lower price)
    sell_exchange: str                      # Exchange to sell to (higher price)
    target_quantity: float                  # Target trade quantity
    
    # Opportunity parameters
    min_profit_bps: int = 50               # Minimum profit (50 bps = 0.5%)
    max_execution_time_ms: float = 2000.0  # Maximum execution time (2 seconds)
    max_slippage_bps: int = 10             # Maximum acceptable slippage
    
    # Current market data
    buy_price: float = 0.0                 # Current buy price
    sell_price: float = 0.0                # Current sell price
    price_difference: float = 0.0          # Absolute price difference
    profit_bps: int = 0                    # Current profit in basis points
    
    # Order tracking
    buy_order: Optional[Order] = None
    sell_order: Optional[Order] = None
    
    # Execution results
    buy_fill_price: float = 0.0
    sell_fill_price: float = 0.0
    buy_fill_quantity: float = 0.0
    sell_fill_quantity: float = 0.0
    
    # Profit calculation
    gross_profit: float = 0.0              # Profit before fees
    buy_fees: float = 0.0                  # Fees paid on buy side
    sell_fees: float = 0.0                 # Fees paid on sell side
    net_profit: float = 0.0                # Final profit after all costs
    
    # Risk management
    max_position_value: float = 10000.0    # Maximum position size
    balance_check_required: bool = True     # Require balance validation
    
    # Performance tracking
    opportunity_detection_time: float = 0.0
    validation_time: float = 0.0
    execution_time: float = 0.0
    total_cycle_time: float = 0.0
    
    # State tracking
    current_state: ArbitrageState = ArbitrageState.SCANNING_OPPORTUNITIES
    opportunities_scanned: int = 0
    opportunities_detected: int = 0
    opportunities_executed: int = 0
    
    @property
    def expected_profit_bps(self) -> int:
        """Calculate expected profit in basis points."""
        if self.buy_price == 0 or self.sell_price == 0:
            return 0
        
        price_diff_pct = (self.sell_price - self.buy_price) / self.buy_price
        return int(price_diff_pct * 10000)
    
    @property
    def position_value(self) -> float:
        """Calculate position value for risk management."""
        return self.target_quantity * max(self.buy_price, self.sell_price)
    
    @property
    def execution_efficiency(self) -> float:
        """Calculate execution efficiency vs expected."""
        if self.gross_profit == 0:
            return 0.0
        
        expected_profit = self.price_difference * self.target_quantity
        if expected_profit == 0:
            return 0.0
        
        return self.gross_profit / expected_profit
    
    def is_profitable_opportunity(self) -> bool:
        """Check if current opportunity meets profit threshold."""
        return self.expected_profit_bps >= self.min_profit_bps
    
    def calculate_expected_profit(self) -> float:
        """Calculate expected profit including fees."""
        if self.buy_price == 0 or self.sell_price == 0:
            return 0.0
        
        # Gross profit from price difference
        gross = (self.sell_price - self.buy_price) * self.target_quantity
        
        # Estimate fees (assuming 0.1% per side)
        estimated_buy_fee = self.buy_price * self.target_quantity * 0.001
        estimated_sell_fee = self.sell_price * self.target_quantity * 0.001
        
        return gross - estimated_buy_fee - estimated_sell_fee
    
    def validate_position_size(self) -> bool:
        """Validate position size against risk limits."""
        return self.position_value <= self.max_position_value
    
    def record_opportunity_detected(self):
        """Record opportunity detection metrics."""
        self.opportunities_detected += 1
        self.opportunity_detection_time = time.perf_counter() - self.start_time
    
    def record_validation_complete(self):
        """Record validation completion metrics."""
        self.validation_time = time.perf_counter() - self.start_time - self.opportunity_detection_time
    
    def record_execution_complete(self):
        """Record execution completion metrics."""
        current_time = time.perf_counter() - self.start_time
        self.execution_time = current_time - self.opportunity_detection_time - self.validation_time
        self.total_cycle_time = current_time
        self.opportunities_executed += 1
```

## Implementation Structure

```python
class SimpleArbitrageStateMachine(BaseStrategyStateMachine):
    """
    State machine for simple cross-exchange arbitrage.
    Implements hedging + swap to capture price differences.
    """
    
    def __init__(self, context: SimpleArbitrageContext):
        super().__init__(context)
        self.context: SimpleArbitrageContext = context
        
    async def run_cycle(self) -> StrategyResult:
        """Execute complete arbitrage cycle."""
        try:
            while not self.is_completed() and not self.is_error():
                
                if self.context.current_state == ArbitrageState.SCANNING_OPPORTUNITIES:
                    await self._handle_scanning_opportunities()
                    
                elif self.context.current_state == ArbitrageState.OPPORTUNITY_DETECTED:
                    await self._handle_opportunity_detected()
                    
                elif self.context.current_state == ArbitrageState.VALIDATING_OPPORTUNITY:
                    await self._handle_validating_opportunity()
                    
                elif self.context.current_state == ArbitrageState.EXECUTING_BUY_SIDE:
                    await self._handle_executing_buy_side()
                    
                elif self.context.current_state == ArbitrageState.EXECUTING_SELL_SIDE:
                    await self._handle_executing_sell_side()
                    
                elif self.context.current_state == ArbitrageState.MONITORING_EXECUTION:
                    await self._handle_monitoring_execution()
                    
                elif self.context.current_state == ArbitrageState.PROFIT_REALIZED:
                    await self._handle_profit_realized()
                
                # Prevent busy loop
                await asyncio.sleep(0.001)  # 1ms
                
                # Check timeout
                if self.context.is_timeout():
                    raise TimeoutError("Arbitrage execution timeout")
            
            return self._create_result()
            
        except Exception as e:
            await self.handle_error(e)
            return self._create_result()
    
    async def _handle_scanning_opportunities(self):
        """Scan for arbitrage opportunities."""
        # Update prices from both exchanges
        await self._update_market_prices()
        
        # Calculate price difference and profit potential
        self.context.price_difference = self.context.sell_price - self.context.buy_price
        self.context.profit_bps = self.context.expected_profit_bps
        
        # Increment scan counter
        self.context.opportunities_scanned += 1
        
        # Check if opportunity meets criteria
        if self.context.is_profitable_opportunity():
            self.context.record_opportunity_detected()
            self.context.transition_to(ArbitrageState.OPPORTUNITY_DETECTED)
        
        # Continue scanning
        await asyncio.sleep(0.01)  # 10ms scan interval
    
    async def _handle_opportunity_detected(self):
        """Handle detected opportunity."""
        # Validate position size
        if not self.context.validate_position_size():
            print(f"⚠️ Position size too large: {self.context.position_value}")
            self.context.transition_to(ArbitrageState.SCANNING_OPPORTUNITIES)
            return
        
        # Check account balances if required
        if self.context.balance_check_required:
            if not await self._validate_account_balances():
                print(f"⚠️ Insufficient account balance for arbitrage")
                self.context.transition_to(ArbitrageState.SCANNING_OPPORTUNITIES)
                return
        
        print(f"🎯 Arbitrage opportunity detected: {self.context.profit_bps} bps profit")
        self.context.transition_to(ArbitrageState.VALIDATING_OPPORTUNITY)
    
    async def _handle_validating_opportunity(self):
        """Validate opportunity in detail."""
        # Refresh prices to ensure opportunity still exists
        await self._update_market_prices()
        
        # Re-check profitability with fresh data
        if not self.context.is_profitable_opportunity():
            print(f"⚠️ Opportunity disappeared during validation")
            self.context.transition_to(ArbitrageState.SCANNING_OPPORTUNITIES)
            return
        
        # Validate orderbook depth
        if not await self._validate_orderbook_depth():
            print(f"⚠️ Insufficient liquidity for trade size")
            self.context.transition_to(ArbitrageState.SCANNING_OPPORTUNITIES)
            return
        
        self.context.record_validation_complete()
        print(f"✅ Opportunity validated, executing arbitrage...")
        
        # Execute both sides simultaneously for speed
        self.context.transition_to(ArbitrageState.EXECUTING_BUY_SIDE)
    
    async def _handle_executing_buy_side(self):
        """Execute buy order on lower-priced exchange."""
        try:
            print(f"🛒 Executing buy order: {self.context.target_quantity} @ {self.context.buy_price}")
            
            # Place market order for immediate execution
            self.context.buy_order = await self.buy_exchange.place_market_order(
                symbol=self.context.symbol,
                side=Side.BUY,
                quantity=self.context.target_quantity
            )
            
            # Immediately start sell side execution
            self.context.transition_to(ArbitrageState.EXECUTING_SELL_SIDE)
            
        except Exception as e:
            print(f"❌ Buy order failed: {e}")
            raise RuntimeError(f"Buy order execution failed: {e}")
    
    async def _handle_executing_sell_side(self):
        """Execute sell order on higher-priced exchange."""
        try:
            print(f"💰 Executing sell order: {self.context.target_quantity} @ {self.context.sell_price}")
            
            # Place market order for immediate execution
            self.context.sell_order = await self.sell_exchange.place_market_order(
                symbol=self.context.symbol,
                side=Side.SELL,
                quantity=self.context.target_quantity
            )
            
            self.context.transition_to(ArbitrageState.MONITORING_EXECUTION)
            
        except Exception as e:
            print(f"❌ Sell order failed: {e}")
            # May need to handle directional exposure from buy order
            raise RuntimeError(f"Sell order execution failed: {e}")
    
    async def _handle_monitoring_execution(self):
        """Monitor execution of both orders."""
        # Wait for both orders to fill
        buy_filled = await self._wait_for_order_fill(self.context.buy_order, timeout=5.0)
        sell_filled = await self._wait_for_order_fill(self.context.sell_order, timeout=5.0)
        
        if not (buy_filled and sell_filled):
            raise RuntimeError("Orders failed to fill within timeout")
        
        # Extract execution details
        self.context.buy_fill_price = self.context.buy_order.average_price
        self.context.sell_fill_price = self.context.sell_order.average_price
        self.context.buy_fill_quantity = self.context.buy_order.filled_quantity
        self.context.sell_fill_quantity = self.context.sell_order.filled_quantity
        
        # Calculate fees
        self.context.buy_fees = self.context.buy_order.fee_amount
        self.context.sell_fees = self.context.sell_order.fee_amount
        
        self.context.record_execution_complete()
        self.context.transition_to(ArbitrageState.PROFIT_REALIZED)
    
    async def _handle_profit_realized(self):
        """Calculate final profit and complete arbitrage."""
        # Calculate gross profit from price difference
        avg_quantity = (self.context.buy_fill_quantity + self.context.sell_fill_quantity) / 2
        self.context.gross_profit = (
            self.context.sell_fill_price - self.context.buy_fill_price
        ) * avg_quantity
        
        # Calculate net profit after fees
        self.context.net_profit = (
            self.context.gross_profit - 
            self.context.buy_fees - 
            self.context.sell_fees
        )
        
        print(f"🎉 Arbitrage completed!")
        print(f"   Gross profit: ${self.context.gross_profit:.4f}")
        print(f"   Total fees: ${self.context.buy_fees + self.context.sell_fees:.4f}")
        print(f"   Net profit: ${self.context.net_profit:.4f}")
        print(f"   Execution time: {self.context.execution_time:.3f}s")
        
        self.context.transition_to(ArbitrageState.COMPLETED)
    
    # Helper methods
    async def _update_market_prices(self):
        """Update current market prices from both exchanges."""
        # Get prices from both exchanges
        buy_ticker = await self.buy_exchange.get_ticker(self.context.symbol)
        sell_ticker = await self.sell_exchange.get_ticker(self.context.symbol)
        
        # Use ask price for buying, bid price for selling
        self.context.buy_price = buy_ticker.ask  # We pay the ask when buying
        self.context.sell_price = sell_ticker.bid  # We receive the bid when selling
    
    async def _validate_account_balances(self) -> bool:
        """Validate sufficient balances on both exchanges."""
        # Check buy exchange has enough quote currency
        buy_balance_needed = self.context.buy_price * self.context.target_quantity
        # Check sell exchange has enough base currency
        sell_balance_needed = self.context.target_quantity
        
        # Implementation would check actual balances
        return True  # Placeholder
    
    async def _validate_orderbook_depth(self) -> bool:
        """Validate sufficient orderbook depth for trade size."""
        # Check orderbook depth on both exchanges
        # Ensure sufficient liquidity for immediate execution
        return True  # Placeholder
    
    async def _wait_for_order_fill(self, order: Order, timeout: float = 10.0) -> bool:
        """Wait for order to fill with timeout."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            # Check order status
            updated_order = await self._get_order_status(order)
            
            if is_order_filled(updated_order):
                # Update order with latest status
                order.status = updated_order.status
                order.filled_quantity = updated_order.filled_quantity
                order.average_price = updated_order.average_price
                order.fee_amount = updated_order.fee_amount
                return True
            
            await asyncio.sleep(0.1)  # Check every 100ms
        
        return False
    
    async def _get_order_status(self, order: Order) -> Order:
        """Get current order status."""
        # Implementation would query exchange for order status
        return order  # Placeholder
    
    def _create_result(self) -> StrategyResult:
        """Create strategy result with arbitrage metrics."""
        return StrategyResult(
            success=self.is_completed(),
            strategy_id=self.context.strategy_id,
            strategy_type="simple_arbitrage",
            execution_time_ms=self.context.execution_time_ms,
            state_transition_count=self.context.state_transition_count,
            realized_pnl=self.context.net_profit,
            unrealized_pnl=0.0,  # Arbitrage is immediately settled
            total_fees=self.context.buy_fees + self.context.sell_fees,
            orders_executed=2,  # Buy + sell
            positions_opened=0,  # No lasting positions in arbitrage
            positions_closed=0,
            error=self.context.error,
            additional_data={
                'gross_profit': self.context.gross_profit,
                'price_difference': self.context.price_difference,
                'profit_bps': self.context.profit_bps,
                'execution_efficiency': self.context.execution_efficiency,
                'buy_price': self.context.buy_fill_price,
                'sell_price': self.context.sell_fill_price,
                'buy_exchange': self.context.buy_exchange,
                'sell_exchange': self.context.sell_exchange,
                'opportunities_scanned': self.context.opportunities_scanned,
                'opportunities_detected': self.context.opportunities_detected,
                'opportunity_detection_time': self.context.opportunity_detection_time,
                'validation_time': self.context.validation_time,
                'total_cycle_time': self.context.total_cycle_time
            }
        )
```

## Risk Management

### Position Limits
- Maximum position value per arbitrage trade
- Maximum number of concurrent arbitrage positions
- Balance requirements on all exchanges

### Execution Risk
- Maximum execution time limits (2 seconds default)
- Slippage monitoring and limits
- Partial fill handling

### Market Risk
- Price movement during execution
- Liquidity risk assessment
- Exchange connectivity monitoring

## Performance Targets

### Latency Requirements
- Opportunity scanning: <10ms per cycle
- Opportunity detection: <50ms
- Opportunity validation: <100ms
- Order execution: <500ms per side
- Total cycle time: <2s including settlement

### Accuracy Requirements
- Price difference calculation: 1 basis point accuracy
- Profit calculation: $0.01 accuracy
- Execution tracking: 100% order reconciliation

## Strategy Variations

### Cross-Exchange Spot Arbitrage
- Same symbol, different exchanges
- Focus on execution speed and fee optimization

### Cross-Pair Arbitrage
- Different trading pairs with conversion
- Example: BTC/USDT vs BTC/EUR + EUR/USDT

### Stablecoin Arbitrage
- Exploit price differences between stablecoins
- Lower risk but smaller profit margins

### Funding Rate Arbitrage
- Spot vs perpetual futures funding differences
- Longer holding periods, funding rate collection

This simple arbitrage state machine provides:

1. **Risk-Free Profit**: Captures price inefficiencies with minimal market risk
2. **High-Speed Execution**: Sub-second execution for time-sensitive opportunities
3. **Comprehensive Monitoring**: Real-time opportunity scanning and validation
4. **Risk Management**: Position limits and execution safeguards
5. **Performance Tracking**: Detailed metrics for strategy optimization
6. **Multi-Exchange Support**: Flexible exchange pair configuration