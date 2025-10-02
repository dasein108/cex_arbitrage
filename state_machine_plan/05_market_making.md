# Market Making State Machine

## Strategy Overview

**Purpose**: Enhanced market making strategy that provides liquidity by continuously quoting bid and ask prices, capturing the spread while managing inventory risk and adapting to market conditions.

**Improvements over Current Demo**:
- Multi-level order management (not just single order)
- Dynamic spread adjustment based on volatility and inventory
- Inventory risk management and position balancing
- Support for multiple symbols simultaneously
- Advanced market microstructure awareness

## State Flow Diagram

```
IDLE
    ↓
CALCULATING_SPREADS
    ↓
PLACING_ORDERS
    ↓
MONITORING_ORDERS ←→ ADJUSTING_SPREADS
    ↓
ORDER_FILLED
    ↓
INVENTORY_MANAGEMENT
    ↓
[IDLE] or [COMPLETED]
```

## State Definitions

### 1. IDLE
**Purpose**: Initial state and reset point for market making cycles

**Entry Conditions**:
- Strategy initialized or previous cycle completed
- Market data available and exchanges connected
- Sufficient balance for market making operations

**Activities**:
- Initialize market data subscriptions
- Check account balances and positions
- Validate symbol configurations
- Prepare for spread calculation

**Exit Conditions**:
- **→ CALCULATING_SPREADS**: Initialization complete, ready to quote
- **→ ERROR**: Initialization failed or insufficient funds

**Performance Target**: <100ms initialization

### 2. CALCULATING_SPREADS
**Purpose**: Calculate optimal bid/ask spreads based on market conditions

**Entry Conditions**:
- Market data is current and valid
- No pending order adjustments

**Activities**:
- Analyze current market volatility
- Calculate base spread from market conditions
- Adjust spread for current inventory position
- Determine order quantities and price levels
- Factor in recent fill rates and adverse selection

**Exit Conditions**:
- **→ PLACING_ORDERS**: Spreads calculated successfully
- **→ ERROR**: Market data issues or calculation errors

**Performance Target**: <50ms calculation time

### 3. PLACING_ORDERS
**Purpose**: Place bid and ask orders at calculated prices

**Entry Conditions**:
- Spread calculation completed
- Order parameters prepared

**Activities**:
- Cancel any existing orders that need adjustment
- Place new bid orders at calculated prices
- Place new ask orders at calculated prices
- Validate order placement success
- Update order tracking

**Exit Conditions**:
- **→ MONITORING_ORDERS**: Orders placed successfully
- **→ ERROR**: Order placement failed

**Performance Target**: <500ms total placement time

### 4. MONITORING_ORDERS
**Purpose**: Monitor order status and market conditions for adjustments

**Entry Conditions**:
- Orders are live in the market
- Order tracking initialized

**Activities**:
- Monitor order fill status
- Track market price movements
- Check if spread adjustment is needed
- Monitor inventory levels
- Assess adverse selection risk

**Exit Conditions**:
- **→ ORDER_FILLED**: One or more orders filled
- **→ ADJUSTING_SPREADS**: Market conditions changed, need new spreads
- **→ ERROR**: Order monitoring failed or risk limits breached

**Performance Target**: <10ms monitoring cycle

### 5. ADJUSTING_SPREADS
**Purpose**: Adjust spreads and reposition orders based on market changes

**Entry Conditions**:
- Market conditions have changed significantly
- Current orders no longer optimal

**Activities**:
- Recalculate optimal spreads
- Cancel orders that need adjustment
- Update order prices and quantities
- Maintain market presence during adjustment

**Exit Conditions**:
- **→ MONITORING_ORDERS**: Adjustments completed successfully
- **→ ERROR**: Adjustment failed

**Performance Target**: <300ms adjustment time

### 6. ORDER_FILLED
**Purpose**: Handle order fills and update positions

**Entry Conditions**:
- One or more market making orders filled
- Fill notifications received

**Activities**:
- Process fill notifications
- Update inventory positions
- Calculate realized PnL from fills
- Update performance metrics
- Assess new inventory risk

**Exit Conditions**:
- **→ INVENTORY_MANAGEMENT**: Fills processed, check inventory
- **→ ERROR**: Fill processing failed

**Performance Target**: <50ms fill processing

### 7. INVENTORY_MANAGEMENT
**Purpose**: Manage inventory risk and rebalance positions

**Entry Conditions**:
- Recent order fills processed
- Inventory position updated

**Activities**:
- Assess current inventory risk
- Determine if inventory hedging needed
- Execute inventory adjustment trades if required
- Update risk metrics
- Decide on next market making cycle

**Exit Conditions**:
- **→ IDLE**: Ready for next market making cycle
- **→ COMPLETED**: Strategy session completed (e.g., end of day)
- **→ ERROR**: Inventory management failed

**Performance Target**: <200ms inventory assessment

## Context Structure

```python
@dataclass
class MarketMakingContext(BaseStrategyContext):
    """Context for enhanced market making strategy."""
    
    # Strategy configuration
    symbol: Symbol
    target_spread_bps: int = 10                # Target spread in basis points
    base_order_size: float = 100.0            # Base order size in quote currency
    max_inventory_pct: float = 0.1             # Max inventory as % of capital
    
    # Market making parameters
    num_price_levels: int = 3                  # Number of price levels to quote
    level_size_decay: float = 0.7              # Size decay factor per level
    level_spread_multiplier: float = 1.5       # Spread multiplier per level
    
    # Current market data
    mid_price: float = 0.0
    bid_price: float = 0.0
    ask_price: float = 0.0
    market_spread_bps: int = 0
    volatility: float = 0.0
    
    # Order management
    active_bid_orders: List[Order] = field(default_factory=list)
    active_ask_orders: List[Order] = field(default_factory=list)
    pending_cancels: Set[str] = field(default_factory=set)
    
    # Position tracking
    base_position: float = 0.0                 # Position in base currency
    quote_position: float = 0.0                # Position in quote currency
    inventory_value: float = 0.0               # Current inventory value
    
    # Performance metrics
    total_volume: float = 0.0                  # Total volume traded
    total_trades: int = 0                      # Number of trades executed
    realized_pnl: float = 0.0                 # Realized profit/loss
    unrealized_pnl: float = 0.0               # Unrealized profit/loss
    fees_paid: float = 0.0                    # Total fees paid
    
    # Risk management
    max_position_size: float = 1000.0          # Maximum position size
    max_quote_exposure: float = 10000.0        # Maximum quote exposure
    adverse_selection_threshold: float = 0.02  # 2% adverse selection limit
    
    # Spread calculation parameters
    volatility_multiplier: float = 2.0         # Volatility adjustment factor
    inventory_adjustment_factor: float = 0.5   # Inventory skew factor
    min_spread_bps: int = 5                   # Minimum spread
    max_spread_bps: int = 50                  # Maximum spread
    
    # State tracking
    current_state: MarketMakingState = MarketMakingState.IDLE
    last_fill_time: float = 0.0
    last_spread_calculation: float = 0.0
    fill_count: int = 0
    adjustment_count: int = 0
    
    @property
    def current_inventory_pct(self) -> float:
        """Calculate current inventory as percentage of max."""
        if self.max_position_size == 0:
            return 0.0
        return abs(self.base_position) / self.max_position_size
    
    @property
    def inventory_skew(self) -> float:
        """Calculate inventory skew for spread adjustment."""
        if self.max_position_size == 0:
            return 0.0
        return self.base_position / self.max_position_size
    
    @property
    def net_pnl(self) -> float:
        """Calculate net PnL after fees."""
        return (self.realized_pnl + self.unrealized_pnl) - self.fees_paid
    
    @property
    def average_spread_captured(self) -> float:
        """Calculate average spread captured per trade."""
        if self.total_trades == 0:
            return 0.0
        return self.realized_pnl / self.total_trades
    
    def needs_inventory_management(self) -> bool:
        """Check if inventory management is needed."""
        return self.current_inventory_pct > self.max_inventory_pct
    
    def calculate_optimal_spread(self) -> int:
        """Calculate optimal spread in basis points."""
        # Base spread from target
        base_spread = self.target_spread_bps
        
        # Adjust for volatility
        volatility_adjustment = self.volatility * self.volatility_multiplier * 10000
        
        # Adjust for inventory (widen spread if carrying inventory)
        inventory_adjustment = abs(self.inventory_skew) * self.inventory_adjustment_factor * 100
        
        # Combine adjustments
        total_spread = base_spread + volatility_adjustment + inventory_adjustment
        
        # Apply bounds
        return max(self.min_spread_bps, min(self.max_spread_bps, int(total_spread)))
    
    def calculate_order_quantities(self, level: int) -> tuple[float, float]:
        """Calculate bid and ask quantities for given price level."""
        base_size = self.base_order_size * (self.level_size_decay ** level)
        
        # Adjust for inventory skew
        bid_size = base_size * (1 + self.inventory_skew * 0.5)
        ask_size = base_size * (1 - self.inventory_skew * 0.5)
        
        # Ensure positive sizes
        bid_size = max(0.01, bid_size)
        ask_size = max(0.01, ask_size)
        
        return bid_size, ask_size
    
    def get_order_prices(self, spread_bps: int, level: int) -> tuple[float, float]:
        """Calculate bid and ask prices for given level."""
        if self.mid_price == 0:
            return 0.0, 0.0
        
        # Calculate spread for this level
        level_spread_bps = spread_bps * (self.level_spread_multiplier ** level)
        spread_amount = self.mid_price * (level_spread_bps / 10000) / 2
        
        # Apply inventory skew
        skew_adjustment = self.mid_price * self.inventory_skew * 0.001
        
        bid_price = self.mid_price - spread_amount + skew_adjustment
        ask_price = self.mid_price + spread_amount + skew_adjustment
        
        return bid_price, ask_price
    
    def should_adjust_spreads(self) -> bool:
        """Check if spreads need adjustment."""
        current_time = time.time()
        
        # Time-based adjustment (every 5 seconds)
        if current_time - self.last_spread_calculation > 5.0:
            return True
        
        # Market movement adjustment (if mid price moved >1%)
        if len(self.active_bid_orders) > 0:
            best_bid = max(order.price for order in self.active_bid_orders)
            if abs(self.mid_price - best_bid) / self.mid_price > 0.01:
                return True
        
        # Inventory adjustment (if inventory changed significantly)
        if self.current_inventory_pct > self.max_inventory_pct * 0.8:
            return True
        
        return False
```

## Implementation Structure

```python
class MarketMakingStateMachine(BaseStrategyStateMachine):
    """
    Enhanced market making state machine with multi-level orders,
    dynamic spreads, and inventory management.
    """
    
    def __init__(self, context: MarketMakingContext):
        super().__init__(context)
        self.context: MarketMakingContext = context
        
    async def run_cycle(self) -> StrategyResult:
        """Execute market making session."""
        try:
            while not self.is_completed() and not self.is_error():
                
                if self.context.current_state == MarketMakingState.IDLE:
                    await self._handle_idle()
                    
                elif self.context.current_state == MarketMakingState.CALCULATING_SPREADS:
                    await self._handle_calculating_spreads()
                    
                elif self.context.current_state == MarketMakingState.PLACING_ORDERS:
                    await self._handle_placing_orders()
                    
                elif self.context.current_state == MarketMakingState.MONITORING_ORDERS:
                    await self._handle_monitoring_orders()
                    
                elif self.context.current_state == MarketMakingState.ADJUSTING_SPREADS:
                    await self._handle_adjusting_spreads()
                    
                elif self.context.current_state == MarketMakingState.ORDER_FILLED:
                    await self._handle_order_filled()
                    
                elif self.context.current_state == MarketMakingState.INVENTORY_MANAGEMENT:
                    await self._handle_inventory_management()
                
                # Short cycle delay
                await asyncio.sleep(0.001)  # 1ms
                
                # Check timeout
                if self.context.is_timeout():
                    raise TimeoutError("Market making session timeout")
            
            return self._create_result()
            
        except Exception as e:
            await self.handle_error(e)
            return self._create_result()
    
    async def _handle_idle(self):
        """Initialize market making session."""
        # Update market data
        await self._update_market_data()
        
        # Check account balances
        if not await self._validate_balances():
            raise ValueError("Insufficient balance for market making")
        
        # Initialize position tracking
        await self._initialize_positions()
        
        self.context.transition_to(MarketMakingState.CALCULATING_SPREADS)
    
    async def _handle_calculating_spreads(self):
        """Calculate optimal spreads for current market conditions."""
        # Update market data
        await self._update_market_data()
        
        # Calculate volatility
        self.context.volatility = await self._calculate_volatility()
        
        # Calculate optimal spread
        optimal_spread = self.context.calculate_optimal_spread()
        
        # Update calculation timestamp
        self.context.last_spread_calculation = time.time()
        
        self.context.transition_to(MarketMakingState.PLACING_ORDERS)
    
    async def _handle_placing_orders(self):
        """Place bid and ask orders at multiple price levels."""
        # Cancel existing orders if needed
        await self._cancel_stale_orders()
        
        # Calculate spread
        spread_bps = self.context.calculate_optimal_spread()
        
        # Place orders at multiple levels
        for level in range(self.context.num_price_levels):
            # Calculate prices and quantities for this level
            bid_price, ask_price = self.context.get_order_prices(spread_bps, level)
            bid_qty, ask_qty = self.context.calculate_order_quantities(level)
            
            # Place bid order
            if await self._should_place_bid(bid_price, bid_qty):
                bid_order = await self._place_bid_order(bid_price, bid_qty)
                if bid_order:
                    self.context.active_bid_orders.append(bid_order)
            
            # Place ask order
            if await self._should_place_ask(ask_price, ask_qty):
                ask_order = await self._place_ask_order(ask_price, ask_qty)
                if ask_order:
                    self.context.active_ask_orders.append(ask_order)
        
        self.context.transition_to(MarketMakingState.MONITORING_ORDERS)
    
    async def _handle_monitoring_orders(self):
        """Monitor orders and market conditions."""
        # Check for order fills
        filled_orders = await self._check_order_fills()
        
        if filled_orders:
            self.context.transition_to(MarketMakingState.ORDER_FILLED)
            return
        
        # Check if spreads need adjustment
        if self.context.should_adjust_spreads():
            self.context.transition_to(MarketMakingState.ADJUSTING_SPREADS)
            return
        
        # Update unrealized PnL
        await self._update_unrealized_pnl()
        
        # Continue monitoring
        await asyncio.sleep(0.01)  # 10ms monitoring cycle
    
    async def _handle_adjusting_spreads(self):
        """Adjust spreads based on market conditions."""
        # Recalculate spreads
        await self._handle_calculating_spreads()
        
        # Cancel orders that need adjustment
        await self._cancel_outdated_orders()
        
        # Place new orders
        self.context.adjustment_count += 1
        self.context.transition_to(MarketMakingState.PLACING_ORDERS)
    
    async def _handle_order_filled(self):
        """Process order fills."""
        # Process all pending fills
        filled_orders = await self._process_order_fills()
        
        for order in filled_orders:
            # Update positions
            await self._update_position_from_fill(order)
            
            # Calculate realized PnL
            self._calculate_realized_pnl(order)
            
            # Update performance metrics
            self.context.total_volume += order.filled_quantity * order.average_price
            self.context.total_trades += 1
            self.context.fill_count += 1
        
        # Remove filled orders from active lists
        self._clean_active_orders()
        
        self.context.transition_to(MarketMakingState.INVENTORY_MANAGEMENT)
    
    async def _handle_inventory_management(self):
        """Manage inventory risk."""
        # Check if inventory management needed
        if self.context.needs_inventory_management():
            await self._rebalance_inventory()
        
        # Check if should continue market making
        if await self._should_continue_market_making():
            self.context.transition_to(MarketMakingState.IDLE)
        else:
            # Wind down positions and complete
            await self._wind_down_positions()
            self.context.transition_to(MarketMakingState.COMPLETED)
    
    # Helper methods
    async def _update_market_data(self):
        """Update current market data."""
        # Get current ticker
        ticker = await self.exchange.get_ticker(self.context.symbol)
        
        self.context.mid_price = (ticker.bid + ticker.ask) / 2
        self.context.bid_price = ticker.bid
        self.context.ask_price = ticker.ask
        self.context.market_spread_bps = int(
            ((ticker.ask - ticker.bid) / self.context.mid_price) * 10000
        )
    
    async def _calculate_volatility(self) -> float:
        """Calculate recent price volatility."""
        # Implementation would calculate volatility from recent price history
        return 0.02  # Placeholder: 2% volatility
    
    async def _validate_balances(self) -> bool:
        """Validate sufficient balances for market making."""
        # Check base and quote currency balances
        return True  # Placeholder
    
    async def _should_place_bid(self, price: float, quantity: float) -> bool:
        """Check if bid order should be placed."""
        # Check position limits, price validity, etc.
        return True  # Placeholder
    
    async def _should_place_ask(self, price: float, quantity: float) -> bool:
        """Check if ask order should be placed."""
        # Check position limits, price validity, etc.
        return True  # Placeholder
    
    async def _place_bid_order(self, price: float, quantity: float) -> Optional[Order]:
        """Place bid order."""
        try:
            return await self.exchange.place_limit_order(
                symbol=self.context.symbol,
                side=Side.BUY,
                quantity=quantity,
                price=price,
                time_in_force=TimeInForce.GTC
            )
        except Exception as e:
            self.logger.error("Failed to place bid order", error=str(e))
            return None
    
    async def _place_ask_order(self, price: float, quantity: float) -> Optional[Order]:
        """Place ask order."""
        try:
            return await self.exchange.place_limit_order(
                symbol=self.context.symbol,
                side=Side.SELL,
                quantity=quantity,
                price=price,
                time_in_force=TimeInForce.GTC
            )
        except Exception as e:
            self.logger.error("Failed to place ask order", error=str(e))
            return None
    
    def _create_result(self) -> StrategyResult:
        """Create strategy result with market making metrics."""
        return StrategyResult(
            success=self.is_completed(),
            strategy_id=self.context.strategy_id,
            strategy_type="market_making",
            execution_time_ms=self.context.execution_time_ms,
            state_transition_count=self.context.state_transition_count,
            realized_pnl=self.context.realized_pnl,
            unrealized_pnl=self.context.unrealized_pnl,
            total_fees=self.context.fees_paid,
            orders_executed=len(self.context.active_bid_orders) + len(self.context.active_ask_orders),
            error=self.context.error,
            additional_data={
                'total_volume': self.context.total_volume,
                'total_trades': self.context.total_trades,
                'average_spread_captured': self.context.average_spread_captured,
                'inventory_pct': self.context.current_inventory_pct,
                'adjustment_count': self.context.adjustment_count,
                'fill_rate': self.context.fill_count / max(1, self.context.total_trades),
                'base_position': self.context.base_position,
                'quote_position': self.context.quote_position
            }
        )
```

## Key Enhancements Over Current Demo

### 1. Multi-Level Order Management
- Place orders at multiple price levels for better market presence
- Size decay across levels to optimize capital efficiency
- Level-specific spread multipliers

### 2. Dynamic Spread Calculation
- Volatility-based spread adjustment
- Inventory-based spread skewing
- Market condition adaptation

### 3. Inventory Risk Management
- Real-time inventory tracking
- Position rebalancing when limits exceeded
- Inventory-adjusted pricing

### 4. Performance Optimization
- Sub-10ms monitoring cycles
- Efficient order management
- Minimal state transitions

### 5. Advanced Market Microstructure
- Adverse selection monitoring
- Fill rate optimization
- Market impact assessment

This enhanced market making state machine provides professional-grade liquidity provision with sophisticated risk management and performance optimization while maintaining the clarity and debuggability of the state machine pattern.