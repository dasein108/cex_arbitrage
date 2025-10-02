# Futures/Futures Hedging State Machine

## Strategy Overview

**Purpose**: Hedge between different futures contracts to capture spread opportunities while maintaining market-neutral exposure. This includes cross-exchange futures arbitrage, calendar spreads, and basis trading.

**Use Cases**:
- Cross-exchange futures arbitrage (same contract, different exchanges)
- Calendar spread trading (near vs far dated contracts)
- Basis spread trading (different contract specifications)
- Cross-margin hedging (utilize margin efficiency)

## State Flow Diagram

```
SCANNING_SPREADS
    ↓
SPREAD_DETECTED
    ↓
VALIDATING_OPPORTUNITY
    ↓
OPENING_LONG_LEG ←→ OPENING_SHORT_LEG
    ↓
MONITORING_SPREAD ←→ ADJUSTING_POSITIONS
    ↓
CLOSING_SPREAD
    ↓
COMPLETED
```

## State Definitions

### 1. SCANNING_SPREADS
**Purpose**: Continuously monitor spread opportunities between futures contracts

**Entry Conditions**:
- Strategy initialized with target contract pairs
- Market data available for both contracts
- Sufficient margin available

**Activities**:
- Monitor spread between target contracts
- Calculate potential profit after fees
- Check margin requirements
- Assess spread volatility and mean reversion

**Exit Conditions**:
- **→ SPREAD_DETECTED**: Profitable spread identified above threshold
- **→ ERROR**: Market data issues or margin insufficient

**Performance Target**: <50ms scan cycle

### 2. SPREAD_DETECTED
**Purpose**: Initial spread opportunity detected, prepare for validation

**Entry Conditions**:
- Spread exceeds minimum profit threshold
- Basic liquidity requirements met

**Activities**:
- Lock in current spread prices for validation
- Check account positions and available margin
- Prepare order parameters for both legs
- Calculate position sizes

**Exit Conditions**:
- **→ VALIDATING_OPPORTUNITY**: Ready to validate detailed opportunity
- **→ SCANNING_SPREADS**: Spread disappeared or insufficient margin

**Performance Target**: <100ms preparation time

### 3. VALIDATING_OPPORTUNITY
**Purpose**: Detailed validation of spread opportunity

**Entry Conditions**:
- Spread opportunity prepared for validation
- Order parameters calculated

**Activities**:
- Refresh market data for both contracts
- Validate spread still exists and profitable
- Check orderbook depth for required size
- Estimate execution slippage
- Confirm margin requirements

**Exit Conditions**:
- **→ OPENING_LONG_LEG**: Opportunity validated, begin execution
- **→ SCANNING_SPREADS**: Opportunity no longer valid

**Performance Target**: <200ms validation time

### 4. OPENING_LONG_LEG
**Purpose**: Execute the long side of the spread

**Entry Conditions**:
- Spread opportunity validated
- Ready to execute first leg

**Activities**:
- Place limit or market order for long position
- Monitor order execution and slippage
- Update position tracking
- Prepare for short leg execution

**Exit Conditions**:
- **→ OPENING_SHORT_LEG**: Long leg filled, execute short leg
- **→ ERROR**: Long leg execution failed

**Performance Target**: <1s execution time

### 5. OPENING_SHORT_LEG
**Purpose**: Execute the short side of the spread

**Entry Conditions**:
- Long leg successfully executed
- Short leg parameters ready

**Activities**:
- Place order for short position
- Monitor execution to completion
- Validate spread establishment
- Calculate actual spread captured

**Exit Conditions**:
- **→ MONITORING_SPREAD**: Both legs established successfully
- **→ ERROR**: Short leg failed, may need to unwind long leg

**Performance Target**: <1s execution time

### 6. MONITORING_SPREAD
**Purpose**: Monitor spread convergence and manage positions

**Entry Conditions**:
- Both legs of spread established
- Position tracking initialized

**Activities**:
- Monitor current spread value
- Track unrealized PnL on the spread
- Check for spread convergence
- Monitor margin utilization
- Check for exit conditions

**Exit Conditions**:
- **→ ADJUSTING_POSITIONS**: Spread needs adjustment or rebalancing
- **→ CLOSING_SPREAD**: Exit conditions met
- **→ ERROR**: Position monitoring failed or margin call

**Performance Target**: <50ms monitoring cycle

### 7. ADJUSTING_POSITIONS
**Purpose**: Adjust positions to optimize spread or manage risk

**Entry Conditions**:
- Spread monitoring indicates need for adjustment
- Sufficient margin for position changes

**Activities**:
- Calculate required position adjustments
- Execute position size changes
- Rebalance hedge ratios if needed
- Update spread tracking

**Exit Conditions**:
- **→ MONITORING_SPREAD**: Adjustments completed successfully
- **→ ERROR**: Position adjustment failed

**Performance Target**: <2s adjustment time

### 8. CLOSING_SPREAD
**Purpose**: Exit both positions and realize PnL

**Entry Conditions**:
- Exit strategy triggered (profit target, stop loss, time limit)
- Both positions still active

**Activities**:
- Close both legs simultaneously or sequentially
- Monitor execution to minimize slippage
- Calculate final PnL including fees
- Update performance metrics

**Exit Conditions**:
- **→ COMPLETED**: Both positions closed successfully
- **→ ERROR**: Position closing failed

**Performance Target**: <3s total closing time

## Context Structure

```python
@dataclass
class FuturesFuturesHedgingContext(BaseStrategyContext):
    """Context for futures/futures hedging strategy."""
    
    # Strategy configuration
    long_contract: FuturesContract          # Contract to go long
    short_contract: FuturesContract         # Contract to go short
    target_notional: float                  # Target position size per leg
    min_spread_bps: int = 20               # Minimum spread (20 bps = 0.2%)
    
    # Contract specifications
    long_exchange: str                      # Exchange for long position
    short_exchange: str                     # Exchange for short position
    long_symbol: Symbol                     # Symbol for long contract
    short_symbol: Symbol                    # Symbol for short contract
    
    # Position tracking
    long_position: Optional[Position] = None
    short_position: Optional[Position] = None
    
    # Orders
    long_order: Optional[Order] = None
    short_order: Optional[Order] = None
    
    # Market data
    long_price: float = 0.0
    short_price: float = 0.0
    spread_value: float = 0.0               # long_price - short_price
    spread_pct: float = 0.0                 # spread as percentage
    
    # Spread tracking
    entry_spread: float = 0.0
    current_spread: float = 0.0
    max_favorable_spread: float = 0.0
    min_favorable_spread: float = float('inf')
    
    # Performance tracking
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    transaction_costs: float = 0.0
    
    # Risk management
    max_loss_bps: int = 50                  # 50 bps max loss (0.5%)
    profit_target_bps: int = 30             # 30 bps profit target (0.3%)
    max_holding_time_hours: int = 48        # Maximum holding period
    max_slippage_bps: int = 5              # Maximum acceptable slippage
    
    # State tracking
    current_state: FuturesHedgingState = FuturesHedgingState.SCANNING_SPREADS
    adjustment_count: int = 0
    spread_samples: list = field(default_factory=list)
    
    @property
    def current_spread_bps(self) -> int:
        """Current spread in basis points."""
        if self.long_price == 0 or self.short_price == 0:
            return 0
        
        spread_pct = (self.long_price - self.short_price) / self.short_price
        return int(spread_pct * 10000)  # Convert to basis points
    
    @property
    def spread_pnl(self) -> float:
        """PnL from spread movement."""
        if self.entry_spread == 0:
            return 0.0
        
        spread_change = self.current_spread - self.entry_spread
        return spread_change * self.target_notional
    
    @property
    def total_pnl(self) -> float:
        """Total PnL including realized and unrealized."""
        return self.realized_pnl + self.unrealized_pnl + self.spread_pnl
    
    def is_profitable_opportunity(self) -> bool:
        """Check if current spread represents profitable opportunity."""
        return abs(self.current_spread_bps) >= self.min_spread_bps
    
    def should_exit(self) -> bool:
        """Check if strategy should exit positions."""
        # Profit target hit
        if self.total_pnl > self.target_notional * self.profit_target_bps / 10000:
            return True
        
        # Stop loss hit
        if self.total_pnl < -self.target_notional * self.max_loss_bps / 10000:
            return True
        
        # Maximum holding time exceeded
        holding_time_hours = (time.time() - self.start_time) / 3600
        if holding_time_hours > self.max_holding_time_hours:
            return True
        
        # Spread has converged significantly
        if abs(self.current_spread_bps) < self.min_spread_bps / 2:
            return True
        
        return False
    
    def add_spread_sample(self, spread: float):
        """Add spread sample for statistical analysis."""
        self.spread_samples.append({
            'spread': spread,
            'timestamp': time.time()
        })
        
        # Keep only last 100 samples
        if len(self.spread_samples) > 100:
            self.spread_samples.pop(0)
    
    def get_spread_volatility(self) -> float:
        """Calculate spread volatility from recent samples."""
        if len(self.spread_samples) < 10:
            return 0.0
        
        spreads = [s['spread'] for s in self.spread_samples[-20:]]  # Last 20 samples
        mean_spread = sum(spreads) / len(spreads)
        variance = sum((s - mean_spread) ** 2 for s in spreads) / len(spreads)
        return variance ** 0.5
```

## Implementation Structure

```python
class FuturesFuturesHedgingStateMachine(BaseStrategyStateMachine):
    """
    State machine for futures/futures hedging strategy.
    Implements spread trading between different futures contracts.
    """
    
    def __init__(self, context: FuturesFuturesHedgingContext):
        super().__init__(context)
        self.context: FuturesFuturesHedgingContext = context
        
    async def run_cycle(self) -> StrategyResult:
        """Execute complete futures hedging cycle."""
        try:
            while not self.is_completed() and not self.is_error():
                
                if self.context.current_state == FuturesHedgingState.SCANNING_SPREADS:
                    await self._handle_scanning_spreads()
                    
                elif self.context.current_state == FuturesHedgingState.SPREAD_DETECTED:
                    await self._handle_spread_detected()
                    
                elif self.context.current_state == FuturesHedgingState.VALIDATING_OPPORTUNITY:
                    await self._handle_validating_opportunity()
                    
                elif self.context.current_state == FuturesHedgingState.OPENING_LONG_LEG:
                    await self._handle_opening_long_leg()
                    
                elif self.context.current_state == FuturesHedgingState.OPENING_SHORT_LEG:
                    await self._handle_opening_short_leg()
                    
                elif self.context.current_state == FuturesHedgingState.MONITORING_SPREAD:
                    await self._handle_monitoring_spread()
                    
                elif self.context.current_state == FuturesHedgingState.ADJUSTING_POSITIONS:
                    await self._handle_adjusting_positions()
                    
                elif self.context.current_state == FuturesHedgingState.CLOSING_SPREAD:
                    await self._handle_closing_spread()
                
                # Prevent busy loop
                await asyncio.sleep(0.01)
                
                # Check timeout
                if self.context.is_timeout():
                    raise TimeoutError("Strategy execution timeout")
            
            return self._create_result()
            
        except Exception as e:
            await self.handle_error(e)
            return self._create_result()
    
    async def _handle_scanning_spreads(self):
        """Scan for profitable spread opportunities."""
        # Update market data for both contracts
        await self._update_market_data()
        
        # Calculate current spread
        self.context.current_spread = self.context.long_price - self.context.short_price
        self.context.add_spread_sample(self.context.current_spread)
        
        # Check if spread is profitable
        if self.context.is_profitable_opportunity():
            self.context.transition_to(FuturesHedgingState.SPREAD_DETECTED)
        
        # Continue scanning
        await asyncio.sleep(0.05)  # 50ms scan interval
    
    async def _handle_spread_detected(self):
        """Handle detected spread opportunity."""
        # Validate margin requirements
        if not await self._check_margin_requirements():
            self.context.transition_to(FuturesHedgingState.SCANNING_SPREADS)
            return
        
        # Prepare order parameters
        await self._prepare_order_parameters()
        
        self.context.transition_to(FuturesHedgingState.VALIDATING_OPPORTUNITY)
    
    async def _handle_validating_opportunity(self):
        """Validate spread opportunity in detail."""
        # Refresh market data
        await self._update_market_data()
        
        # Re-check spread profitability
        if not self.context.is_profitable_opportunity():
            self.context.transition_to(FuturesHedgingState.SCANNING_SPREADS)
            return
        
        # Check orderbook depth
        if not await self._validate_liquidity():
            self.context.transition_to(FuturesHedgingState.SCANNING_SPREADS)
            return
        
        # Record entry spread
        self.context.entry_spread = self.context.current_spread
        
        self.context.transition_to(FuturesHedgingState.OPENING_LONG_LEG)
    
    async def _handle_opening_long_leg(self):
        """Open long position."""
        long_quantity = self.context.target_notional / self.context.long_price
        
        # Place long order
        self.context.long_order = await self.long_exchange.place_market_order(
            symbol=self.context.long_symbol,
            side=Side.BUY,
            quantity=long_quantity
        )
        
        # Wait for fill
        if await self._wait_for_order_fill(self.context.long_order):
            self.context.long_position = await self._get_position(
                self.context.long_symbol, self.long_exchange
            )
            self.context.transition_to(FuturesHedgingState.OPENING_SHORT_LEG)
        else:
            raise RuntimeError("Long leg failed to fill")
    
    async def _handle_opening_short_leg(self):
        """Open short position."""
        # Use actual filled quantity from long leg for hedge
        short_quantity = self.context.long_position.quantity
        
        # Place short order
        self.context.short_order = await self.short_exchange.place_market_order(
            symbol=self.context.short_symbol,
            side=Side.SELL,
            quantity=short_quantity
        )
        
        # Wait for fill
        if await self._wait_for_order_fill(self.context.short_order):
            self.context.short_position = await self._get_position(
                self.context.short_symbol, self.short_exchange
            )
            self.context.transition_to(FuturesHedgingState.MONITORING_SPREAD)
        else:
            # Consider unwinding long position
            raise RuntimeError("Short leg failed to fill")
    
    async def _handle_monitoring_spread(self):
        """Monitor spread and positions."""
        # Update market data and PnL
        await self._update_market_data()
        await self._update_pnl()
        
        # Check exit conditions
        if self.context.should_exit():
            self.context.transition_to(FuturesHedgingState.CLOSING_SPREAD)
            return
        
        # Check for position adjustment needs
        if await self._needs_position_adjustment():
            self.context.transition_to(FuturesHedgingState.ADJUSTING_POSITIONS)
            return
        
        # Continue monitoring
        await asyncio.sleep(0.1)  # 100ms monitoring interval
    
    async def _handle_adjusting_positions(self):
        """Adjust positions if needed."""
        # Calculate required adjustments
        adjustment_size = await self._calculate_position_adjustment()
        
        if adjustment_size != 0:
            # Execute position adjustments
            await self._execute_position_adjustment(adjustment_size)
            self.context.adjustment_count += 1
        
        self.context.transition_to(FuturesHedgingState.MONITORING_SPREAD)
    
    async def _handle_closing_spread(self):
        """Close both positions."""
        # Close positions simultaneously to minimize spread risk
        tasks = []
        
        if self.context.long_position:
            tasks.append(self._close_long_position())
        
        if self.context.short_position:
            tasks.append(self._close_short_position())
        
        # Execute closes in parallel
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        # Calculate final PnL
        await self._calculate_final_pnl()
        
        self.context.transition_to(FuturesHedgingState.COMPLETED)
    
    # Helper methods
    async def _update_market_data(self):
        """Update current market prices for both contracts."""
        # Implementation depends on exchange interfaces
        pass
    
    async def _check_margin_requirements(self) -> bool:
        """Check if sufficient margin is available."""
        # Calculate required margin for both positions
        # Check against available margin
        return True  # Placeholder
    
    async def _validate_liquidity(self) -> bool:
        """Validate sufficient liquidity for position sizes."""
        # Check orderbook depth for both contracts
        return True  # Placeholder
    
    async def _prepare_order_parameters(self):
        """Prepare order parameters for both legs."""
        # Calculate position sizes based on target notional
        pass
    
    async def _wait_for_order_fill(self, order: Order, timeout: float = 10.0) -> bool:
        """Wait for order to fill with timeout."""
        # Implementation depends on exchange interfaces
        return True  # Placeholder
    
    async def _needs_position_adjustment(self) -> bool:
        """Check if positions need adjustment."""
        # Monitor for significant position drift or margin issues
        return False  # Placeholder
    
    async def _calculate_position_adjustment(self) -> float:
        """Calculate required position adjustment size."""
        return 0.0  # Placeholder
    
    async def _execute_position_adjustment(self, adjustment_size: float):
        """Execute position adjustment."""
        pass
    
    async def _close_long_position(self):
        """Close long position."""
        if self.context.long_position:
            await self.long_exchange.place_market_order(
                symbol=self.context.long_symbol,
                side=Side.SELL,
                quantity=self.context.long_position.quantity
            )
    
    async def _close_short_position(self):
        """Close short position."""
        if self.context.short_position:
            await self.short_exchange.place_market_order(
                symbol=self.context.short_symbol,
                side=Side.BUY,
                quantity=abs(self.context.short_position.quantity)
            )
    
    def _create_result(self) -> StrategyResult:
        """Create strategy result with performance metrics."""
        return StrategyResult(
            success=self.is_completed(),
            strategy_id=self.context.strategy_id,
            strategy_type="futures_futures_hedging",
            execution_time_ms=self.context.execution_time_ms,
            state_transition_count=self.context.state_transition_count,
            realized_pnl=self.context.realized_pnl,
            unrealized_pnl=self.context.unrealized_pnl,
            total_fees=self.context.transaction_costs,
            orders_executed=2,  # Long + short
            positions_opened=2,
            positions_closed=2 if self.is_completed() else 0,
            error=self.context.error,
            additional_data={
                'entry_spread': self.context.entry_spread,
                'exit_spread': self.context.current_spread,
                'spread_pnl': self.context.spread_pnl,
                'adjustment_count': self.context.adjustment_count,
                'spread_volatility': self.context.get_spread_volatility(),
                'max_favorable_spread': self.context.max_favorable_spread,
                'long_contract': str(self.context.long_contract),
                'short_contract': str(self.context.short_contract)
            }
        )
```

## Strategy Variations

### Cross-Exchange Arbitrage
- Same contract on different exchanges
- Exploit price differences between venues
- Focus on execution speed and liquidity

### Calendar Spreads
- Near vs far dated contracts
- Capture time decay and volatility differences
- Monitor term structure changes

### Basis Trading
- Futures vs perpetual swaps
- Capture funding rate inefficiencies
- Monitor basis convergence patterns

## Risk Management

### Position Limits
- Maximum notional per strategy instance
- Cross-margin utilization limits
- Maximum number of concurrent spreads

### Stop Loss Mechanisms
- Spread-based stops (if spread moves against position)
- PnL-based stops (absolute loss limits)
- Time-based stops (maximum holding period)
- Volatility-based stops (if market becomes too volatile)

### Monitoring Requirements
- Real-time spread tracking
- Margin utilization monitoring
- Position drift detection
- Liquidity monitoring for exit

## Performance Targets

### Latency Requirements
- Spread scanning: <50ms per cycle
- Opportunity validation: <200ms
- Position opening: <2s total (both legs)
- Monitoring cycle: <100ms
- Position closing: <3s total

### Accuracy Requirements
- Spread calculation accuracy: 1 basis point
- PnL calculation accuracy: $0.01
- Position tracking accuracy: 100%

This futures/futures hedging state machine provides:

1. **Flexible Spread Trading**: Support for various spread types
2. **Risk Management**: Comprehensive stop loss and position limits
3. **Performance Optimization**: Sub-second execution and monitoring
4. **Market Neutral**: Delta-neutral spread positions
5. **Statistical Analysis**: Spread volatility and convergence tracking
6. **Multi-Exchange Support**: Cross-venue arbitrage capabilities