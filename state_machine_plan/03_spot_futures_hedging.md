# Spot/Futures Hedging State Machine

## Strategy Overview

**Purpose**: Hedge spot cryptocurrency positions with futures contracts to achieve delta-neutral exposure while capturing funding rate differences and basis spread opportunities.

**Use Cases**:
- Long spot position hedged with short futures (classic hedge)
- Funding rate arbitrage (capture positive funding rates)
- Basis spread trading (convergence at expiration)
- Risk management for large spot holdings

## State Flow Diagram

```
ANALYZING_MARKET
    ↓
OPENING_SPOT_POSITION
    ↓
OPENING_FUTURES_HEDGE
    ↓
MONITORING_POSITIONS ←→ REBALANCING
    ↓
CLOSING_POSITIONS
    ↓
COMPLETED
```

## State Definitions

### 1. ANALYZING_MARKET
**Purpose**: Analyze market conditions and identify hedging opportunities

**Entry Conditions**:
- Strategy initialized with target symbol and position size
- Market data available for both spot and futures

**Activities**:
- Check funding rates and basis spread
- Validate liquidity in both spot and futures markets
- Calculate expected returns and costs
- Assess market volatility and risk

**Exit Conditions**:
- **→ OPENING_SPOT_POSITION**: Opportunity validated, proceed to execution
- **→ ERROR**: Market conditions unsuitable or data unavailable

**Performance Target**: <500ms analysis time

### 2. OPENING_SPOT_POSITION
**Purpose**: Execute the spot position (typically long)

**Entry Conditions**:
- Market analysis completed successfully
- Sufficient account balance for spot purchase

**Activities**:
- Place market order for spot position
- Monitor order execution and slippage
- Update position tracking
- Calculate actual cost basis

**Exit Conditions**:
- **→ OPENING_FUTURES_HEDGE**: Spot position filled successfully
- **→ ERROR**: Spot order failed or insufficient liquidity

**Performance Target**: <2s execution time

### 3. OPENING_FUTURES_HEDGE
**Purpose**: Execute the futures hedge position (typically short)

**Entry Conditions**:
- Spot position opened successfully
- Futures position size calculated based on hedge ratio

**Activities**:
- Calculate optimal hedge ratio (default 1:1)
- Place futures market/limit order for hedge
- Monitor hedge execution
- Validate hedge effectiveness

**Exit Conditions**:
- **→ MONITORING_POSITIONS**: Hedge position established successfully  
- **→ ERROR**: Hedge failed, consider unwinding spot position

**Performance Target**: <2s execution time

### 4. MONITORING_POSITIONS
**Purpose**: Monitor hedge effectiveness and market conditions

**Entry Conditions**:
- Both spot and futures positions established
- Position tracking initialized

**Activities**:
- Monitor position delta and hedge ratio
- Track funding rate changes
- Monitor basis spread evolution
- Check for rebalancing triggers
- Monitor for exit conditions

**Exit Conditions**:
- **→ REBALANCING**: Hedge ratio drift exceeds threshold
- **→ CLOSING_POSITIONS**: Exit conditions met or strategy timeout
- **→ ERROR**: Position monitoring failed or risk limits breached

**Performance Target**: <100ms monitoring cycle

### 5. REBALANCING
**Purpose**: Adjust hedge ratio to maintain delta neutrality

**Entry Conditions**:
- Hedge ratio has drifted beyond tolerance (e.g., >5% deviation)
- Sufficient margin for position adjustments

**Activities**:
- Calculate required position adjustment
- Execute futures position adjustment (buy/sell futures)
- Update hedge ratio tracking
- Validate new hedge effectiveness

**Exit Conditions**:
- **→ MONITORING_POSITIONS**: Rebalancing completed successfully
- **→ ERROR**: Rebalancing failed, may need manual intervention

**Performance Target**: <3s rebalancing time

### 6. CLOSING_POSITIONS
**Purpose**: Exit both positions and realize PnL

**Entry Conditions**:
- Exit strategy triggered (time, profit target, loss limit)
- Both positions still active

**Activities**:
- Close futures position first (typically faster execution)
- Close spot position  
- Calculate final PnL including funding received/paid
- Update performance metrics

**Exit Conditions**:
- **→ COMPLETED**: Both positions closed successfully
- **→ ERROR**: Position closing failed (may require manual intervention)

**Performance Target**: <5s total closing time

## Context Structure

```python
@dataclass
class SpotFuturesHedgingContext(BaseStrategyContext):
    """Context for spot/futures hedging strategy."""
    
    # Strategy configuration
    spot_symbol: Symbol                    # e.g., BTC/USDT spot
    futures_symbol: Symbol                 # e.g., BTC/USDT futures
    target_notional: float                # Target position size in USDT
    hedge_ratio: float = 1.0              # Target hedge ratio (default 1:1)
    
    # Position tracking
    spot_position: Optional[Position] = None
    futures_position: Optional[Position] = None
    
    # Orders
    spot_order: Optional[Order] = None
    futures_order: Optional[Order] = None
    
    # Market data
    spot_price: float = 0.0
    futures_price: float = 0.0
    funding_rate: float = 0.0
    basis_spread: float = 0.0              # futures_price - spot_price
    
    # Performance tracking
    initial_basis: float = 0.0
    funding_received: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    
    # Risk management
    max_hedge_ratio_drift: float = 0.05    # 5% maximum drift
    stop_loss_pct: float = 0.02            # 2% stop loss
    profit_target_pct: float = 0.01        # 1% profit target
    max_holding_time_hours: int = 24       # Maximum holding period
    
    # State tracking
    current_state: HedgingState = HedgingState.ANALYZING_MARKET
    rebalance_count: int = 0
    
    @property
    def current_hedge_ratio(self) -> float:
        """Calculate current hedge ratio."""
        if not self.spot_position or not self.futures_position:
            return 0.0
        
        spot_notional = abs(self.spot_position.quantity * self.spot_price)
        futures_notional = abs(self.futures_position.quantity * self.futures_price)
        
        if spot_notional == 0:
            return 0.0
        
        return futures_notional / spot_notional
    
    @property
    def hedge_ratio_drift(self) -> float:
        """Calculate drift from target hedge ratio."""
        return abs(self.current_hedge_ratio - self.hedge_ratio)
    
    @property
    def total_pnl(self) -> float:
        """Calculate total PnL including funding."""
        return self.realized_pnl + self.unrealized_pnl + self.funding_received
    
    def needs_rebalancing(self) -> bool:
        """Check if hedge needs rebalancing."""
        return self.hedge_ratio_drift > self.max_hedge_ratio_drift
    
    def should_exit(self) -> bool:
        """Check if strategy should exit positions."""
        # Profit target hit
        if self.total_pnl > self.target_notional * self.profit_target_pct:
            return True
        
        # Stop loss hit
        if self.total_pnl < -self.target_notional * self.stop_loss_pct:
            return True
        
        # Maximum holding time exceeded
        holding_time_hours = (time.time() - self.start_time) / 3600
        if holding_time_hours > self.max_holding_time_hours:
            return True
        
        return False
```

## Implementation Structure

```python
class SpotFuturesHedgingStateMachine(BaseStrategyStateMachine):
    """
    State machine for spot/futures hedging strategy.
    Implements delta-neutral hedging with automatic rebalancing.
    """
    
    def __init__(self, context: SpotFuturesHedgingContext):
        super().__init__(context)
        self.context: SpotFuturesHedgingContext = context
        
    async def run_cycle(self) -> StrategyResult:
        """Execute complete hedging cycle."""
        try:
            while not self.is_completed() and not self.is_error():
                
                if self.context.current_state == HedgingState.ANALYZING_MARKET:
                    await self._handle_analyzing_market()
                    
                elif self.context.current_state == HedgingState.OPENING_SPOT_POSITION:
                    await self._handle_opening_spot_position()
                    
                elif self.context.current_state == HedgingState.OPENING_FUTURES_HEDGE:
                    await self._handle_opening_futures_hedge()
                    
                elif self.context.current_state == HedgingState.MONITORING_POSITIONS:
                    await self._handle_monitoring_positions()
                    
                elif self.context.current_state == HedgingState.REBALANCING:
                    await self._handle_rebalancing()
                    
                elif self.context.current_state == HedgingState.CLOSING_POSITIONS:
                    await self._handle_closing_positions()
                
                # Prevent busy loop
                await asyncio.sleep(0.01)
                
                # Check timeout
                if self.context.is_timeout():
                    raise TimeoutError("Strategy execution timeout")
            
            return self._create_result()
            
        except Exception as e:
            await self.handle_error(e)
            return self._create_result()
    
    async def _handle_analyzing_market(self):
        """Analyze market conditions for hedging opportunity."""
        # Get current market data
        await self._update_market_data()
        
        # Validate opportunity
        if await self._validate_hedging_opportunity():
            self.context.transition_to(HedgingState.OPENING_SPOT_POSITION)
        else:
            raise ValueError("No suitable hedging opportunity found")
    
    async def _handle_opening_spot_position(self):
        """Open spot position."""
        spot_quantity = self.context.target_notional / self.context.spot_price
        
        # Place spot market order
        self.context.spot_order = await self.spot_exchange.place_market_order(
            symbol=self.context.spot_symbol,
            side=Side.BUY,  # Typically long spot
            quote_quantity=self.context.target_notional
        )
        
        # Wait for fill and update position
        if await self._wait_for_order_fill(self.context.spot_order):
            self.context.spot_position = await self._get_position(
                self.context.spot_symbol
            )
            self.context.transition_to(HedgingState.OPENING_FUTURES_HEDGE)
        else:
            raise RuntimeError("Spot order failed to fill")
    
    async def _handle_opening_futures_hedge(self):
        """Open futures hedge position."""
        # Calculate hedge quantity based on actual spot fill
        hedge_quantity = (
            self.context.spot_position.quantity * 
            self.context.hedge_ratio
        )
        
        # Place futures order (short to hedge long spot)
        self.context.futures_order = await self.futures_exchange.place_market_order(
            symbol=self.context.futures_symbol,
            side=Side.SELL,  # Short futures to hedge long spot
            quantity=hedge_quantity
        )
        
        # Wait for fill and update position
        if await self._wait_for_order_fill(self.context.futures_order):
            self.context.futures_position = await self._get_position(
                self.context.futures_symbol
            )
            self.context.initial_basis = self.context.basis_spread
            self.context.transition_to(HedgingState.MONITORING_POSITIONS)
        else:
            raise RuntimeError("Futures hedge failed to fill")
    
    async def _handle_monitoring_positions(self):
        """Monitor positions and check for exit/rebalance conditions."""
        # Update market data and PnL
        await self._update_market_data()
        await self._update_pnl()
        
        # Check exit conditions
        if self.context.should_exit():
            self.context.transition_to(HedgingState.CLOSING_POSITIONS)
            return
        
        # Check rebalancing needs
        if self.context.needs_rebalancing():
            self.context.transition_to(HedgingState.REBALANCING)
            return
        
        # Continue monitoring
        await asyncio.sleep(1.0)  # Monitor every second
    
    async def _handle_rebalancing(self):
        """Rebalance hedge ratio."""
        # Calculate required adjustment
        current_ratio = self.context.current_hedge_ratio
        target_ratio = self.context.hedge_ratio
        
        # Adjust futures position to restore target ratio
        # Implementation details depend on specific requirements
        
        self.context.rebalance_count += 1
        self.context.transition_to(HedgingState.MONITORING_POSITIONS)
    
    async def _handle_closing_positions(self):
        """Close both positions."""
        # Close futures first (typically faster)
        if self.context.futures_position:
            await self._close_futures_position()
        
        # Close spot position
        if self.context.spot_position:
            await self._close_spot_position()
        
        # Calculate final PnL
        await self._calculate_final_pnl()
        
        self.context.transition_to(HedgingState.COMPLETED)
    
    # Helper methods
    async def _update_market_data(self):
        """Update current market prices and funding rate."""
        # Implementation depends on exchange interfaces
        pass
    
    async def _validate_hedging_opportunity(self) -> bool:
        """Validate that hedging opportunity exists."""
        # Check minimum basis spread
        # Check funding rate favorability  
        # Check liquidity requirements
        return True  # Placeholder
    
    async def _wait_for_order_fill(self, order: Order, timeout: float = 10.0) -> bool:
        """Wait for order to fill with timeout."""
        # Implementation depends on exchange interfaces
        return True  # Placeholder
    
    def _create_result(self) -> StrategyResult:
        """Create strategy result with performance metrics."""
        return StrategyResult(
            success=self.is_completed(),
            strategy_id=self.context.strategy_id,
            strategy_type="spot_futures_hedging",
            execution_time_ms=self.context.execution_time_ms,
            state_transition_count=self.context.state_transition_count,
            realized_pnl=self.context.realized_pnl,
            unrealized_pnl=self.context.unrealized_pnl,
            total_fees=0.0,  # Calculate from orders
            orders_executed=2,  # Spot + futures
            positions_opened=2,
            positions_closed=2 if self.is_completed() else 0,
            error=self.context.error,
            additional_data={
                'funding_received': self.context.funding_received,
                'initial_basis': self.context.initial_basis,
                'final_basis': self.context.basis_spread,
                'rebalance_count': self.context.rebalance_count,
                'hedge_ratio': self.context.current_hedge_ratio
            }
        )
```

## Risk Management

### Position Limits
- **Maximum Notional**: Configurable per strategy instance
- **Hedge Ratio Bounds**: 0.8 - 1.2 (80% - 120% hedge)
- **Maximum Drift**: 5% from target hedge ratio before rebalancing

### Stop Loss Mechanisms
- **PnL Stop**: -2% of notional (configurable)
- **Time Stop**: 24 hours maximum holding period
- **Basis Stop**: Basis moves against position by more than threshold

### Monitoring Requirements
- **Real-time PnL tracking**: Updated every monitoring cycle
- **Funding rate monitoring**: Track changes in funding rate expectations
- **Liquidity monitoring**: Ensure sufficient liquidity for exit
- **Position drift alerts**: Alert when hedge ratio drifts significantly

## Performance Targets

### Latency Requirements
- **Strategy initialization**: <1s
- **Position opening**: <5s total (spot + futures)
- **Monitoring cycle**: <100ms per cycle
- **Rebalancing**: <3s execution time
- **Position closing**: <5s total

### Throughput Requirements
- **Concurrent strategies**: Support 10+ concurrent hedge positions
- **Market data updates**: Process 100+ updates per second
- **Order processing**: Handle 5+ orders per second

## Testing Strategy

### Unit Tests
- State transition logic
- Hedge ratio calculations
- Exit condition evaluation
- PnL calculation accuracy

### Integration Tests  
- End-to-end strategy execution with mock exchanges
- Error handling and recovery scenarios
- Performance benchmarking

### Simulation Tests
- Historical data backtesting
- Stress testing with extreme market conditions
- Monte Carlo analysis of strategy performance

This spot/futures hedging state machine provides:

1. **Clear State Flow**: Logical progression from analysis to completion
2. **Risk Management**: Built-in stop losses and position limits
3. **Performance Monitoring**: Real-time PnL and hedge effectiveness tracking
4. **Automatic Rebalancing**: Maintains target hedge ratio
5. **Robust Error Handling**: Graceful handling of execution failures
6. **Performance Optimization**: Sub-second state transitions and monitoring