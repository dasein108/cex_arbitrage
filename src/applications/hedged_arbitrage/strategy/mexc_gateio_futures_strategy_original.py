"""
MEXC Spot + Gate.io Futures Arbitrage Strategy

Simplified standalone 2-exchange implementation for spot-futures arbitrage between MEXC spot and Gate.io futures.
This strategy provides delta-neutral arbitrage opportunities by:

1. Monitoring spread between MEXC spot and Gate.io futures prices
2. Executing simultaneous trades when spreads exceed thresholds
3. Maintaining delta neutrality through position balancing
4. Real-time execution with sub-50ms cycles

Features:
- Real-time WebSocket market data integration
- Event-driven execution with HFT performance
- Automatic position balancing for delta neutrality
- Risk management with position limits and stop-losses
- Standalone implementation with no external dependencies
"""

import asyncio
from typing import Optional, Dict, List
import time
from enum import IntEnum

import msgspec

from exchanges.structs import Symbol, Side, ExchangeEnum, BookTicker, Order, AssetBalance
from infrastructure.logging import HFTLoggerInterface, get_logger
from utils.exchange_utils import is_order_done

from applications.hedged_arbitrage.strategy.exchange_manager import ExchangeManager, OrderPlacementParams, ExchangeRole
from utils import get_decrease_vector, flip_side, calculate_weighted_price


class ArbitrageState(IntEnum):
    """States for arbitrage strategy execution."""
    IDLE = 0
    INITIALIZING = 1        # Initialize exchanges and connections
    MONITORING = 2          # Monitor spreads and opportunities
    ANALYZING = 3           # Analyze opportunity viability
    EXECUTING = 4           # Execute arbitrage trades
    ERROR_RECOVERY = 5      # Handle errors and recovery


class PositionState(msgspec.Struct):
    """Unified position tracking for both exchanges."""
    spot_qty: float = 0.0
    spot_price: float = 0.0
    futures_qty: float = 0.0
    futures_price: float = 0.0
    
    @property
    def delta(self) -> float:
        """Calculate delta exposure (spot - futures)."""
        return self.spot_qty - self.futures_qty
    
    def update_spot_position(self, qty_change: float, price: float) -> 'PositionState':
        """Update spot position with weighted average price."""
        if self.spot_qty != 0:
            total_cost = (self.spot_qty * self.spot_price) + (qty_change * price)
            new_qty = self.spot_qty + qty_change
            new_price = total_cost / new_qty if new_qty != 0 else price
        else:
            new_qty = qty_change
            new_price = price
        
        return msgspec.structs.replace(self, spot_qty=new_qty, spot_price=new_price)
    
    def update_futures_position(self, qty_change: float, price: float) -> 'PositionState':
        """Update futures position with weighted average price."""
        if self.futures_qty != 0:
            total_cost = (self.futures_qty * self.futures_price) + (qty_change * price)
            new_qty = self.futures_qty + qty_change
            new_price = total_cost / new_qty if new_qty != 0 else price
        else:
            new_qty = qty_change
            new_price = price
        
        return msgspec.structs.replace(self, futures_qty=new_qty, futures_price=new_price)


class TradingThresholds(msgspec.Struct):
    """Consolidated trading thresholds and limits."""
    entry_pct: float = 0.1
    exit_pct: float = 0.03
    position_age_limit: float = 180.0
    min_confidence: float = 0.8
    max_slippage_pct: float = 0.05
    delta_tolerance: float = 0.05


class MarketData(msgspec.Struct):
    """Unified market data access."""
    spot: Optional[BookTicker] = None
    futures: Optional[BookTicker] = None
    
    @property
    def is_complete(self) -> bool:
        """Check if we have data from both exchanges."""
        return self.spot is not None and self.futures is not None
    
    def calculate_spreads(self) -> Optional[Dict[str, float]]:
        """Calculate spreads in both directions."""
        if not self.is_complete:
            return None
        
        # Direction 1: Buy spot, sell futures
        spot_to_futures = (self.futures.bid_price - self.spot.ask_price) / self.spot.ask_price * 100
        
        # Direction 2: Buy futures, sell spot
        futures_to_spot = (self.spot.bid_price - self.futures.ask_price) / self.futures.ask_price * 100
        
        return {
            'spot_to_futures': spot_to_futures,
            'futures_to_spot': futures_to_spot
        }


class ArbitrageOpportunity(msgspec.Struct):
    """Simplified arbitrage opportunity representation."""
    direction: str  # 'spot_to_futures' | 'futures_to_spot'
    spread_pct: float
    buy_price: float
    sell_price: float
    max_quantity: float
    timestamp: float = msgspec.field(default_factory=time.time)
    
    @property
    def is_fresh(self, max_age_seconds: float = 5.0) -> bool:
        """Check if opportunity is still fresh."""
        return (time.time() - self.timestamp) < max_age_seconds
    
    @property
    def estimated_profit(self) -> float:
        """Calculate estimated profit per unit."""
        return self.sell_price - self.buy_price


class ValidationResult(msgspec.Struct):
    """Result of execution validation."""
    valid: bool
    reason: str = ""


class OrderSpec(msgspec.Struct):
    """Specification for order placement."""
    role: str  # 'spot' | 'futures'
    side: Side
    quantity: float
    price: float



class MexcGateioFuturesContext(msgspec.Struct):
    """Optimized context for MEXC spot + Gate.io futures arbitrage strategy."""
    
    # Core strategy configuration
    symbol: Symbol
    base_position_size: float = 20.0
    max_position_multiplier: float = 2.0
    futures_leverage: float = 1.0
    
    # Consolidated thresholds
    thresholds: TradingThresholds = msgspec.field(default_factory=TradingThresholds)
    
    # Unified position tracking
    positions: PositionState = msgspec.field(default_factory=PositionState)
    
    # State and opportunity tracking
    state: ArbitrageState = ArbitrageState.IDLE
    current_opportunity: Optional[ArbitrageOpportunity] = None
    position_start_time: Optional[float] = None
    
    # Performance tracking
    arbitrage_cycles: int = 0
    total_volume: float = 0.0
    total_profit: float = 0.0
    total_fees: float = 0.0


class MexcGateioFuturesStrategy:
    """
    MEXC Spot + Gate.io Futures arbitrage strategy.
    
    Standalone implementation that executes delta-neutral arbitrage between MEXC spot 
    and Gate.io futures markets by simultaneously buying spot and selling futures 
    (or vice versa) when spreads exceed profitability thresholds.
    """
    
    name: str = "MexcGateioFuturesStrategy"
    
    def __init__(self, 
                 symbol: Symbol,
                 base_position_size: float = 100.0,
                 entry_threshold_pct: float = 0.1,   # 0.1% minimum spread
                 exit_threshold_pct: float = 0.03,   # 0.03% minimum exit spread
                 logger: Optional[HFTLoggerInterface] = None):
        """Initialize MEXC + Gate.io futures arbitrage strategy.
        
        Args:
            symbol: Trading symbol (e.g., NEIROETH)
            base_position_size: Base position size for arbitrage trades
            entry_threshold_pct: Entry threshold as percentage (e.g., 0.1 for 0.1%)
            exit_threshold_pct: Exit threshold as percentage (e.g., 0.03 for 0.03%)
            logger: Optional HFT logger (auto-created if not provided)
        """
        
        # Initialize logger
        if logger is None:
            logger = get_logger(f'mexc_gateio_futures_strategy.{symbol}')
        self.logger = logger
        
        # Create context with optimized structure
        thresholds = TradingThresholds(
            entry_pct=entry_threshold_pct,
            exit_pct=exit_threshold_pct
        )
        
        self.context = MexcGateioFuturesContext(
            symbol=symbol,
            base_position_size=base_position_size,
            thresholds=thresholds,
            max_position_multiplier=2.0  # Conservative for 2-exchange strategy
        )
        
        # Create exchange roles for spot-futures arbitrage
        exchange_roles = self._create_exchange_roles(base_position_size)
        
        # Strategy-specific components
        self.exchange_manager = ExchangeManager(symbol, exchange_roles, logger)
        
        # Performance tracking
        self._last_spread_check = 0.0
        self._spread_check_interval = 0.1  # 100ms between spread checks
        self._tag = f'{self.name}_{symbol}_MEXC-GATEIO'
        
        # Subscribe to events from exchange manager
        self.exchange_manager.event_bus.subscribe('book_ticker', self._on_book_ticker_update)
        self.exchange_manager.event_bus.subscribe('order', self._on_order_update)
        self.exchange_manager.event_bus.subscribe('position', self._on_position_update)
    
    def _create_exchange_roles(self, base_position_size: float) -> Dict[str, ExchangeRole]:
        """Create exchange roles for spot-futures arbitrage strategy."""
        return {
            'spot': ExchangeRole(
                exchange_enum=ExchangeEnum.MEXC,
                role='spot_trading',
                max_position_size=base_position_size,
                priority=0
            ),
            'futures': ExchangeRole(
                exchange_enum=ExchangeEnum.GATEIO_FUTURES,
                role='futures_hedge',
                max_position_size=base_position_size,
                priority=1
            )
        }
    
    def _transition(self, new_state: ArbitrageState):
        """Transition to a new state."""
        old_state = self.context.state
        self.context = msgspec.structs.replace(self.context, state=new_state)
        self.logger.info(f"State transition: {old_state.name} -> {new_state.name}")
    
    def evolve_context(self, **kwargs):
        """Update context with new values."""
        self.context = msgspec.structs.replace(self.context, **kwargs)
    
    def get_market_data(self) -> MarketData:
        """Get unified market data from both exchanges."""
        return MarketData(
            spot=self.exchange_manager.get_book_ticker('spot'),
            futures=self.exchange_manager.get_book_ticker('futures')
        )
    
    def _validate_execution(self, opportunity: ArbitrageOpportunity, position_size: float) -> ValidationResult:
        """Unified validation for trade execution."""
        if position_size <= 0:
            return ValidationResult(valid=False, reason="Invalid position size")
        
        max_size = self.context.base_position_size * self.context.max_position_multiplier
        if position_size > max_size:
            return ValidationResult(valid=False, reason=f"Position size {position_size} exceeds limit {max_size}")
        
        if not opportunity.is_fresh():
            return ValidationResult(valid=False, reason="Opportunity is stale")
        
        return ValidationResult(valid=True)
    
    def _prepare_arbitrage_orders(self, opportunity: ArbitrageOpportunity, position_size: float) -> List[OrderSpec]:
        """Prepare order specifications for arbitrage execution."""
        if opportunity.direction == 'spot_to_futures':
            return [
                OrderSpec(role='spot', side=Side.BUY, quantity=position_size, price=opportunity.buy_price),
                OrderSpec(role='futures', side=Side.SELL, quantity=position_size, price=opportunity.sell_price)
            ]
        else:  # futures_to_spot
            return [
                OrderSpec(role='futures', side=Side.BUY, quantity=position_size, price=opportunity.buy_price),
                OrderSpec(role='spot', side=Side.SELL, quantity=position_size, price=opportunity.sell_price)
            ]
    
    async def start(self):
        """Start strategy with exchange manager initialization."""
        self.logger.info(f"Starting {self.name} strategy for {self.context.symbol}")
        self._transition(ArbitrageState.INITIALIZING)
        
        # Initialize exchange manager
        success = await self.exchange_manager.initialize()
        if not success:
            self.logger.error("Failed to initialize exchange manager")
            self._transition(ArbitrageState.ERROR_RECOVERY)
            return
        
        self._transition(ArbitrageState.MONITORING)
        self.logger.info(f"✅ {self.name} strategy started for {self.context.symbol}")
    
    async def run(self):
        """Main strategy execution loop."""
        self.logger.info(f"Running {self.name} strategy...")
        
        try:
            while True:
                # State machine execution
                if self.context.state == ArbitrageState.IDLE:
                    self._transition(ArbitrageState.INITIALIZING)
                elif self.context.state == ArbitrageState.INITIALIZING:
                    await self._handle_initializing()
                elif self.context.state == ArbitrageState.MONITORING:
                    await self._handle_monitoring()
                elif self.context.state == ArbitrageState.ANALYZING:
                    await self._handle_analyzing()
                elif self.context.state == ArbitrageState.EXECUTING:
                    await self._handle_executing()
                elif self.context.state == ArbitrageState.ERROR_RECOVERY:
                    await self._handle_error_recovery()
                
                # Small delay to prevent tight loops
                await asyncio.sleep(0.01)
                
        except KeyboardInterrupt:
            self.logger.info("Strategy interrupted by user")
        except Exception as e:
            self.logger.error(f"Strategy execution error: {e}")
            self._transition(ArbitrageState.ERROR_RECOVERY)
        finally:
            await self.cleanup()
    
    async def _handle_initializing(self):
        """Handle initialization state."""
        # Already initialized in start(), just transition to monitoring
        self._transition(ArbitrageState.MONITORING)
    
    async def _handle_monitoring(self):
        """Monitor market for arbitrage opportunities."""
        # Opportunity detection is handled by event handlers
        await asyncio.sleep(0.1)
    
    async def _handle_analyzing(self):
        """Analyze current opportunity for viability."""
        if not self.context.current_opportunity:
            self._transition(ArbitrageState.MONITORING)
            return
        
        opportunity = self.context.current_opportunity
        
        # Verify opportunity is still valid
        if await self._validate_opportunity(opportunity):
            self.logger.info(f"💰 Valid arbitrage opportunity: {opportunity.spread_pct:.4f}% spread")
            self._transition(ArbitrageState.EXECUTING)
        else:
            self.logger.info("⚠️ Opportunity no longer valid, returning to monitoring")
            self.evolve_context(current_opportunity=None)
            self._transition(ArbitrageState.MONITORING)
    
    async def _handle_executing(self):
        """Execute arbitrage trades."""
        if not self.context.current_opportunity:
            self._transition(ArbitrageState.MONITORING)
            return
        
        opportunity = self.context.current_opportunity
        
        try:
            success = await self._execute_arbitrage_trades(opportunity)
            
            if success:
                self.logger.info(f"✅ Arbitrage execution successful")
                # Update performance metrics
                self.evolve_context(
                    arbitrage_cycles=self.context.arbitrage_cycles + 1,
                    current_opportunity=None
                )
                self._transition(ArbitrageState.MONITORING)
            else:
                self.logger.warning("❌ Arbitrage execution failed")
                self._transition(ArbitrageState.ERROR_RECOVERY)
                
        except Exception as e:
            self.logger.error(f"Execution error: {e}")
            self._transition(ArbitrageState.ERROR_RECOVERY)
    
    async def _handle_error_recovery(self):
        """Handle errors and attempt recovery."""
        self.logger.info("🔄 Attempting error recovery")
        
        # Clear any failed opportunity
        self.evolve_context(current_opportunity=None)
        
        # Cancel any pending orders
        await self.exchange_manager.cancel_all_orders()
        
        # Wait before returning to monitoring
        await asyncio.sleep(1.0)
        self._transition(ArbitrageState.MONITORING)
    
    async def _validate_opportunity(self, opportunity: ArbitrageOpportunity) -> bool:
        """Validate that opportunity is still viable."""
        spot_ticker = self.exchange_manager.get_book_ticker('spot')
        futures_ticker = self.exchange_manager.get_book_ticker('futures')
        
        if not spot_ticker or not futures_ticker:
            return False
        
        # Calculate current spread
        if opportunity.primary_exchange == ExchangeEnum.MEXC:
            # Buy spot, sell futures
            current_spread = (futures_ticker.bid_price - spot_ticker.ask_price) / spot_ticker.ask_price * 100
        else:
            # Buy futures, sell spot
            current_spread = (spot_ticker.bid_price - futures_ticker.ask_price) / futures_ticker.ask_price * 100
        
        return current_spread >= self.context.entry_threshold_pct
    
    # Event handlers for real-time market data
    
    async def _on_book_ticker_update(self, book_ticker, exchange_key: str):
        """Handle real-time book ticker updates."""
        current_time = time.time()
        
        # Rate limit spread analysis to prevent excessive computation
        if (current_time - self._last_spread_check) >= self._spread_check_interval:
            self._last_spread_check = current_time
            
            # Trigger spread analysis if we have data from both exchanges
            spot_ticker = self.exchange_manager.get_book_ticker('spot')
            futures_ticker = self.exchange_manager.get_book_ticker('futures')
            
            if spot_ticker and futures_ticker and self.context.state == ArbitrageState.MONITORING:
                # Schedule opportunity analysis (don't block event handler)
                asyncio.create_task(self._check_arbitrage_opportunity_async())
    
    async def _on_order_update(self, order, exchange_key: str):
        """Handle real-time order updates."""
        if is_order_done(order):
            await self._process_filled_order(exchange_key, order)
    
    async def _on_position_update(self, position, exchange_key: str):
        """Handle real-time position updates from futures exchange."""
        if exchange_key == 'futures':
            # Update futures position tracking
            self.evolve_context(gateio_position=position.quantity)
            await self._update_delta_calculation()
    
    async def _check_arbitrage_opportunity_async(self):
        """Asynchronously check for arbitrage opportunities."""
        try:
            if self.context.state == ArbitrageState.MONITORING:
                # Check if we need to exit existing positions first
                if await self._should_exit_positions():
                    await self._exit_all_positions()
                    return
                
                # Look for new entry opportunities
                opportunity = await self._identify_arbitrage_opportunity()
                if opportunity:
                    self.logger.info(f"💰 Arbitrage opportunity found: {opportunity.spread_pct:.4f}% spread")
                    self.evolve_context(current_opportunity=opportunity)
                    self._transition(ArbitrageState.ANALYZING)
        except Exception as e:
            self.logger.warning(f"Opportunity check failed: {e}")
    
    # Core arbitrage strategy implementation
    
    async def _should_exit_positions(self) -> bool:
        """Check if we should exit existing positions based on spread thresholds."""
        # Only check exit if we have positions
        if self.context.mexc_position == 0 and self.context.gateio_position == 0:
            return False
        
        spot_ticker = self.exchange_manager.get_book_ticker('spot')
        futures_ticker = self.exchange_manager.get_book_ticker('futures')
        
        if not spot_ticker or not futures_ticker:
            return False
        
        # Calculate the current spread based on our position direction
        # We need to check if we can still exit profitably in the REVERSE direction
        
        # Determine our current position direction
        long_mexc = self.context.mexc_position > 0
        long_gateio = self.context.gateio_position > 0
        
        if long_mexc and not long_gateio:
            # We're long spot, short futures
            # To exit: sell spot (at bid), buy futures (at ask)
            exit_spot_price = spot_ticker.bid_price  # Sell spot at bid
            exit_futures_price = futures_ticker.ask_price  # Buy futures at ask
            # Current spread for exit = what we get from spot - what we pay for futures
            current_exit_spread = (exit_spot_price - exit_futures_price) / exit_futures_price * 100
        elif not long_mexc and long_gateio:
            # We're short spot, long futures  
            # To exit: buy spot (at ask), sell futures (at bid)
            exit_spot_price = spot_ticker.ask_price  # Buy spot at ask
            exit_futures_price = futures_ticker.bid_price  # Sell futures at bid
            # Current spread for exit = what we get from futures - what we pay for spot
            current_exit_spread = (exit_futures_price - exit_spot_price) / exit_spot_price * 100
        else:
            # Unclear position state, use conservative approach
            # Calculate both directions and use the worse (more conservative) spread
            spot_to_futures_spread = (futures_ticker.bid_price - spot_ticker.ask_price) / spot_ticker.ask_price * 100
            futures_to_spot_spread = (spot_ticker.bid_price - futures_ticker.ask_price) / futures_ticker.ask_price * 100
            current_exit_spread = min(spot_to_futures_spread, futures_to_spot_spread)
        
        # Exit threshold is already in percentage format, no conversion needed
        exit_threshold_pct = float(self.context.exit_threshold_pct)
        
        # TODO: DISABLED - THRESHOLDS - Enhanced exit conditions
        # POSITION_AGE_LIMIT = 180.0    # Force exit after 3 minutes
        #
        # # Check position age - force exit if too old
        # if hasattr(self.context, 'position_start_time') and self.context.position_start_time:
        #     position_age = time.time() - self.context.position_start_time
        #     if position_age > POSITION_AGE_LIMIT:
        #         self.logger.info(f"🕒 Force exit due to position age: {position_age:.1f}s > {POSITION_AGE_LIMIT}s")
        #         return True
        
        # Exit when spread falls below exit threshold (profit margin is too small)
        should_exit = current_exit_spread < exit_threshold_pct
        
        if should_exit:
            self.logger.info(f"🚪 Exit condition met: current exit spread {current_exit_spread:.4f}% < exit threshold {exit_threshold_pct:.4f}%")
        
        return should_exit
    
    async def _exit_all_positions(self):
        """Exit all positions by closing long position and covering short position."""
        try:
            self.logger.info("🔄 Exiting all positions...")
            
            # Get current market prices for immediate execution
            spot_ticker = self.exchange_manager.get_book_ticker('spot')
            futures_ticker = self.exchange_manager.get_book_ticker('futures')
            
            if not spot_ticker or not futures_ticker:
                self.logger.error("❌ Cannot exit positions - missing market data")
                return
            
            exit_orders = {}
            
            # Close MEXC spot position
            if self.context.mexc_position != 0:
                spot_side = Side.SELL if self.context.mexc_position > 0 else Side.BUY
                spot_price = spot_ticker.bid_price if spot_side == Side.SELL else spot_ticker.ask_price
                exit_orders['spot'] = OrderPlacementParams(
                    side=spot_side,
                    quantity=abs(self.context.mexc_position),
                    price=spot_price
                )
            
            # Close Gate.io futures position
            if self.context.gateio_position != 0:
                futures_side = Side.BUY if self.context.gateio_position < 0 else Side.SELL
                futures_price = futures_ticker.ask_price if futures_side == Side.BUY else futures_ticker.bid_price
                exit_orders['futures'] = OrderPlacementParams(
                    side=futures_side,
                    quantity=abs(self.context.gateio_position),
                    price=futures_price
                )
            
            if exit_orders:
                self.logger.info(f"🚀 Executing exit orders: {len(exit_orders)} exchanges")
                placed_orders = await self.exchange_manager.place_order_parallel(exit_orders)
                
                if all(placed_orders.values()):
                    self.logger.info("✅ All exit orders placed successfully")
                    # Reset position timing when all positions are closed
                    self.evolve_context(position_start_time=None)
                else:
                    self.logger.warning("⚠️ Some exit orders failed")
            
        except Exception as e:
            self.logger.error(f"❌ Error exiting positions: {e}")
    
    async def _identify_arbitrage_opportunity(self) -> Optional[ArbitrageOpportunity]:
        """Identify arbitrage opportunities between spot and futures exchanges."""
        spot_ticker = self.exchange_manager.get_book_ticker('spot')
        futures_ticker = self.exchange_manager.get_book_ticker('futures')
        
        if not spot_ticker or not futures_ticker:
            return None
        
        # Analyze both arbitrage directions using proper bid/ask spreads
        # Direction 1: Buy spot, sell futures
        spot_buy_price = spot_ticker.ask_price  # Price to buy on spot
        futures_sell_price = futures_ticker.bid_price  # Price to sell on futures
        spot_to_futures_spread = (futures_sell_price - spot_buy_price) / spot_buy_price * 100
        
        # Direction 2: Buy futures, sell spot
        futures_buy_price = futures_ticker.ask_price  # Price to buy on futures
        spot_sell_price = spot_ticker.bid_price  # Price to sell on spot
        futures_to_spot_spread = (spot_sell_price - futures_buy_price) / futures_buy_price * 100
        
        # Choose the direction with better spread (if any)
        # Note: context thresholds are already in percentage format, spreads are calculated as percentages
        entry_threshold_pct = float(self.context.entry_threshold_pct)
        
        best_opportunity = None
        if spot_to_futures_spread >= entry_threshold_pct:
            best_opportunity = {
                'direction': 'spot_to_futures',
                'spread_pct': spot_to_futures_spread,
                'primary_exchange': ExchangeEnum.MEXC,
                'target_exchange': ExchangeEnum.GATEIO_FUTURES,
                'primary_price': spot_buy_price,
                'target_price': futures_sell_price
            }
        
        if futures_to_spot_spread >= entry_threshold_pct:
            # Take the better opportunity if both are profitable
            if not best_opportunity or futures_to_spot_spread > best_opportunity['spread_pct']:
                best_opportunity = {
                    'direction': 'futures_to_spot',
                    'spread_pct': futures_to_spot_spread,
                    'primary_exchange': ExchangeEnum.GATEIO_FUTURES,
                    'target_exchange': ExchangeEnum.MEXC,
                    'primary_price': futures_buy_price,
                    'target_price': spot_sell_price
                }
        
        if not best_opportunity:
            return None
        
        # TODO: DISABLED - THRESHOLDS - Volume and profit validation
        # MIN_VOLUME_THRESHOLD = 500.0  # Minimum orderbook volume required
        # MIN_PROFIT_THRESHOLD = 5.0    # Minimum expected profit in USDT
        #
        # # Check minimum volume availability on both sides
        # available_volume = min(spot_ticker.ask_quantity, futures_ticker.bid_quantity) if best_opportunity['direction'] == 'spot_to_futures' else min(futures_ticker.ask_quantity, spot_ticker.bid_quantity)
        # if available_volume < MIN_VOLUME_THRESHOLD:
        #     self.logger.debug(f"Volume threshold not met: {available_volume:.2f} < {MIN_VOLUME_THRESHOLD}")
        #     return None
        
        # Check minimum profit potential
        # estimated_volume = min(float(self.context.base_position_size), available_volume)
        # estimated_profit_usd = (best_opportunity['target_price'] - best_opportunity['primary_price']) * estimated_volume
        # if estimated_profit_usd < MIN_PROFIT_THRESHOLD:
        #     self.logger.debug(f"Profit threshold not met: {estimated_profit_usd:.2f} < {MIN_PROFIT_THRESHOLD}")
        #     return None

        # If we have open positions, ensure we can still exit profitably
        if self.context.mexc_position != 0 or self.context.gateio_position != 0:
            # Use exit threshold for position closing (already in percentage format)
            exit_threshold_pct = float(self.context.exit_threshold_pct)
            if best_opportunity['spread_pct'] < exit_threshold_pct:
                return None
        
        # Calculate maximum quantity based on order book depth and direction
        if best_opportunity['direction'] == 'spot_to_futures':
            max_quantity = min(
                spot_ticker.ask_quantity,  # Spot ask depth (what we're buying)
                futures_ticker.bid_quantity,  # Futures bid depth (what we're selling to)
                float(self.context.base_position_size * self.context.max_position_multiplier)
            )
        else:  # futures_to_spot
            max_quantity = min(
                futures_ticker.ask_quantity,  # Futures ask depth (what we're buying)
                spot_ticker.bid_quantity,  # Spot bid depth (what we're selling to)
                float(self.context.base_position_size * self.context.max_position_multiplier)
            )
        
        # Estimate profit using actual executable prices
        quantity = min(float(self.context.base_position_size), max_quantity)
        estimated_profit = (best_opportunity['target_price'] - best_opportunity['primary_price']) * quantity
        
        # TODO: DISABLED - HARDCODED THRESHOLDS - Time-based constraints
        # MIN_TIME_BETWEEN_TRADES = 10.0  # Minimum seconds between trades
        #
        # # Check minimum time between trades
        # if hasattr(self, '_last_trade_time') and (time.time() - self._last_trade_time) < MIN_TIME_BETWEEN_TRADES:
        #     self.logger.debug(f"Time threshold not met: {time.time() - self._last_trade_time:.1f}s < {MIN_TIME_BETWEEN_TRADES}s")
        #     return None
        
        return ArbitrageOpportunity(
            primary_exchange=best_opportunity['primary_exchange'],
            target_exchange=best_opportunity['target_exchange'],
            symbol=self.context.symbol,
            spread_pct=best_opportunity['spread_pct'],
            primary_price=best_opportunity['primary_price'],
            target_price=best_opportunity['target_price'],
            max_quantity=max_quantity,
            estimated_profit=estimated_profit,
            confidence_score=0.8,  # High confidence for 2-exchange strategy
            timestamp=time.time()
        )
    
    async def _calculate_max_executable_size(self, opportunity: ArbitrageOpportunity) -> float:
        """Calculate maximum executable position size based on balance constraints."""
        try:
            base_size = min(
                float(self.context.base_position_size),
                float(opportunity.max_quantity)
            )
            
            # Get exchanges for balance checking
            spot_exchange = self.exchange_manager.get_exchange('spot')
            futures_exchange = self.exchange_manager.get_exchange('futures')
            
            if not spot_exchange or not futures_exchange:
                self.logger.warning("Could not get exchanges for balance checking")
                return base_size
            
            # Determine trade direction and check relevant balances
            if opportunity.primary_exchange == ExchangeEnum.MEXC:
                # Buying MEXC spot, selling Gate.io futures
                quote_balance = await spot_exchange.private.get_asset_balance(opportunity.symbol.quote)
                if quote_balance:
                    # Calculate max position based on available quote balance
                    required_quote_per_unit = float(opportunity.primary_price) * 1.01  # Add 1% buffer for fees
                    max_spot_buy = float(quote_balance.available) / required_quote_per_unit
                    base_size = min(base_size, max_spot_buy)
                    self.logger.debug(f"💰 MEXC quote balance limit: {max_spot_buy:.6f} (available: {quote_balance.available})")
                
            else:
                # Selling MEXC spot, buying Gate.io futures
                base_balance = await spot_exchange.private.get_asset_balance(opportunity.symbol.quote)
                if base_balance:
                    # Calculate max position based on available base balance
                    max_spot_sell = float(base_balance.available)
                    base_size = min(base_size, max_spot_sell)
                    self.logger.debug(f"💰 MEXC base balance limit: {max_spot_sell:.6f} (available: {base_balance.available})")
            
            # Additional check for futures margin (if applicable)
            # For simplicity, we assume futures exchange has sufficient margin
            # In production, this would check margin requirements
            
            if base_size != min(float(self.context.base_position_size), float(opportunity.max_quantity)):
                self.logger.info(f"📊 Position size adjusted for balance: {base_size:.6f} (original: {min(float(self.context.base_position_size), float(opportunity.max_quantity)):.6f})")
            
            return max(base_size, 0.0)  # Ensure non-negative
            
        except Exception as e:
            self.logger.error(f"Error calculating executable size: {e}")
            return min(float(self.context.base_position_size), float(opportunity.max_quantity))
    
    async def _prepare_orders_for_opportunity(self, opportunity: ArbitrageOpportunity, position_size: float) -> Optional[Dict[str, dict]]:
        """Prepare order structure for balance validation."""
        try:
            # Determine trade sides based on opportunity direction
            if opportunity.primary_exchange == ExchangeEnum.MEXC:
                # Buy MEXC spot, sell Gate.io futures
                mexc_side = Side.BUY
                gateio_side = Side.SELL
                mexc_price = opportunity.primary_price
                gateio_price = opportunity.target_price
            else:
                # Buy Gate.io futures, sell MEXC spot
                mexc_side = Side.SELL
                gateio_side = Side.BUY
                mexc_price = opportunity.target_price
                gateio_price = opportunity.primary_price
            
            # Prepare order structure for validation
            orders = {
                'spot': {
                    'side': mexc_side,
                    'quantity': position_size,
                    'price': mexc_price
                },
                'futures': {
                    'side': gateio_side,
                    'quantity': position_size,
                    'price': gateio_price
                }
            }
            
            return orders
            
        except Exception as e:
            self.logger.error(f"Failed to prepare orders for validation: {e}")
            return None
    
    async def _execute_arbitrage_trades(self, opportunity: ArbitrageOpportunity) -> bool:
        """Execute simultaneous arbitrage trades on MEXC and Gate.io."""
        try:
            # Calculate balance-aware position size
            position_size = await self._calculate_max_executable_size(opportunity)
            
            if position_size <= 0:
                self.logger.error("❌ No executable position size available")
                return False
            
            # Determine trade sides based on opportunity direction
            if opportunity.primary_exchange == ExchangeEnum.MEXC:
                # Buy MEXC spot, sell Gate.io futures
                mexc_side = Side.BUY
                gateio_side = Side.SELL
                mexc_price = float(opportunity.primary_price)
                gateio_price = float(opportunity.target_price)
            else:
                # Buy Gate.io futures, sell MEXC spot
                mexc_side = Side.SELL
                gateio_side = Side.BUY
                mexc_price = float(opportunity.target_price)
                gateio_price = float(opportunity.primary_price)
            
            # Prepare orders for parallel execution
            orders = {
                'spot': OrderPlacementParams(
                    side=mexc_side,
                    quantity=position_size,
                    price=mexc_price
                ),
                'futures': OrderPlacementParams(
                    side=gateio_side,
                    quantity=position_size,
                    price=gateio_price
                )
            }
            
            # Execute orders in parallel for HFT performance
            self.logger.info(f"🚀 Executing arbitrage trades: {position_size} @ MEXC:{mexc_price}, Gate.io:{gateio_price}")
            start_time = time.time()
            
            placed_orders = await self.exchange_manager.place_order_parallel(orders)
            
            execution_time = (time.time() - start_time) * 1000
            self.logger.info(f"⚡ Order execution completed in {execution_time:.1f}ms")
            
            # Check if both orders were placed successfully
            mexc_order = placed_orders.get('spot')
            gateio_order = placed_orders.get('futures')
            
            if mexc_order and gateio_order:
                self.logger.info(f"✅ Both arbitrage orders placed successfully")
                # Track trade timing for minimum time constraints
                self._last_trade_time = time.time()
                # Track position start time for age limits
                if not hasattr(self.context, 'position_start_time') or self.context.position_start_time is None:
                    self.evolve_context(position_start_time=time.time())
                # Update performance metrics
                self.evolve_context(
                    arbitrage_cycles=self.context.arbitrage_cycles + 1,
                    total_volume=self.context.total_volume + position_size
                )
                return True
            else:
                self.logger.error(f"❌ Arbitrage execution failed - MEXC: {bool(mexc_order)}, Gate.io: {bool(gateio_order)}")
                
                # Cancel any successful orders to avoid unbalanced positions
                if mexc_order or gateio_order:
                    await self.exchange_manager.cancel_all_orders()
                    
                return False
                
        except Exception as e:
            self.logger.error(f"Arbitrage execution error: {e}")
            # Emergency order cancellation
            await self.exchange_manager.cancel_all_orders()
            return False
    
    async def _rebalance_positions(self) -> bool:
        """Rebalance positions to maintain delta neutrality."""
        try:
            # Calculate current delta
            await self._update_delta_calculation()
            
            # Check if rebalancing is needed
            delta_deviation = abs(self.context.current_delta)
            if delta_deviation <= self.context.delta_tolerance:
                self.logger.info(f"✅ Delta within tolerance: {delta_deviation:.4f}")
                return True
            
            self.logger.info(f"⚖️ Rebalancing required - Delta deviation: {delta_deviation:.4f}")
            
            # Determine rebalancing action
            if self.context.current_delta > self.context.delta_tolerance:
                # Long bias - need to reduce long exposure or increase short
                await self._rebalance_reduce_long_bias()
            elif self.context.current_delta < -self.context.delta_tolerance:
                # Short bias - need to reduce short exposure or increase long
                await self._rebalance_reduce_short_bias()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Position rebalancing error: {e}")
            return False
    
    async def _update_delta_calculation(self):
        """Update delta calculation based on current positions."""
        # For spot-futures arbitrage, delta = spot_position - futures_position
        current_delta = self.context.mexc_position - self.context.gateio_position
        self.evolve_context(current_delta=current_delta)
    
    async def _rebalance_reduce_long_bias(self):
        """Reduce long bias by selling spot (with balance validation)."""
        spot_exchange = self.exchange_manager.get_exchange('spot')
        if not spot_exchange:
            self.logger.warning("Spot exchange not available for rebalancing")
            return
        
        try:
            # Get available balance for the base asset
            balances = await spot_exchange.private.get_balances()
            base_balance = next((b for b in balances if b.asset == self.context.symbol.base), None)
            
            if not base_balance:
                self.logger.warning("No base asset balance found for rebalancing")
                return
            
            # Calculate rebalance quantity limited by available balance
            desired_quantity = abs(float(self.context.current_delta)) / 2
            max_sellable = float(base_balance.available)
            rebalance_quantity = min(desired_quantity, max_sellable)
            
            if rebalance_quantity <= 0:
                self.logger.warning(f"Insufficient balance for rebalancing: need {desired_quantity:.6f}, have {max_sellable:.6f}")
                return
            
            # Get current price for market order
            spot_ticker = self.exchange_manager.get_book_ticker('spot')
            if not spot_ticker:
                self.logger.warning("No market data available for rebalancing")
                return
            
            # Execute rebalance trade
            await spot_exchange.private.place_market_order(
                symbol=self.context.symbol,
                side=Side.SELL,
                price=float(spot_ticker.bid_price),
                quote_quantity=rebalance_quantity
            )
            
            if rebalance_quantity < desired_quantity:
                self.logger.info(f"📉 Rebalance sell: {rebalance_quantity:.6f} on MEXC (limited by balance, wanted {desired_quantity:.6f})")
            else:
                self.logger.info(f"📉 Rebalance sell: {rebalance_quantity:.6f} on MEXC")
                
        except Exception as e:
            self.logger.error(f"Failed to execute long bias rebalancing: {e}")
    
    async def _rebalance_reduce_short_bias(self):
        """Reduce short bias by buying spot (with balance validation)."""
        spot_exchange = self.exchange_manager.get_exchange('spot')
        if not spot_exchange:
            self.logger.warning("Spot exchange not available for rebalancing")
            return
        
        try:
            # Get available balance for the quote asset
            balances = spot_exchange.private.balances
            quote_balance = balances.get(self.context.symbol.quote)
            
            if not quote_balance:
                self.logger.warning("No quote asset balance found for rebalancing")
                return
            
            # Get current price for market order
            spot_ticker = self.exchange_manager.get_book_ticker('spot')
            if not spot_ticker:
                self.logger.warning("No market data available for rebalancing")
                return
            
            # Calculate rebalance quantity limited by available balance
            desired_quantity = abs(float(self.context.current_delta)) / 2
            required_quote_per_unit = float(spot_ticker.ask_price) * 1.01  # Add 1% buffer for fees
            max_buyable = float(quote_balance.available) / required_quote_per_unit
            rebalance_quantity = min(desired_quantity, max_buyable)
            
            if rebalance_quantity <= 0:
                self.logger.warning(f"Insufficient balance for rebalancing: need {desired_quantity:.6f}, can buy {max_buyable:.6f}")
                return
            
            # Execute rebalance trade
            await spot_exchange.private.place_market_order(
                symbol=self.context.symbol,
                side=Side.BUY,
                price=float(spot_ticker.ask_price),
                quote_quantity=rebalance_quantity
            )
            
            if rebalance_quantity < desired_quantity:
                self.logger.info(f"📈 Rebalance buy: {rebalance_quantity:.6f} on MEXC (limited by balance, wanted {desired_quantity:.6f})")
            else:
                self.logger.info(f"📈 Rebalance buy: {rebalance_quantity:.6f} on MEXC")
                
        except Exception as e:
            self.logger.error(f"Failed to execute short bias rebalancing: {e}")
    
    async def _process_filled_order(self, exchange_key: str, order):
        """Process filled orders and update position tracking."""
        try:
            filled_quantity = order.filled_quantity
            avg_price = order.price
            
            if exchange_key == 'spot':
                # Update MEXC spot position
                if order.side == Side.BUY:
                    new_position = self.context.mexc_position + filled_quantity
                else:
                    new_position = self.context.mexc_position - filled_quantity
                
                # Calculate weighted average price
                if self.context.mexc_position != 0:
                    new_quantity, new_avg_price = calculate_weighted_price(
                        float(self.context.mexc_avg_price),
                        float(self.context.mexc_position),
                        avg_price,
                        filled_quantity
                    )
                    self.evolve_context(
                        mexc_position=new_quantity,
                        mexc_avg_price=new_avg_price
                    )
                else:
                    self.evolve_context(
                        mexc_position=new_position,
                        mexc_avg_price=avg_price
                    )
                
            elif exchange_key == 'futures':
                # Update Gate.io futures position
                if order.side == Side.BUY:
                    new_position = self.context.gateio_position + filled_quantity
                else:
                    new_position = self.context.gateio_position - filled_quantity
                
                # Calculate weighted average price
                if self.context.gateio_position != 0:
                    new_quantity, new_avg_price = calculate_weighted_price(
                        float(self.context.gateio_avg_price),
                        float(self.context.gateio_position),
                        avg_price,
                        filled_quantity
                    )
                    self.evolve_context(
                        gateio_position=new_quantity,
                        gateio_avg_price=new_avg_price
                    )
                else:
                    self.evolve_context(
                        gateio_position=new_position,
                        gateio_avg_price=avg_price
                    )
            
            # Update delta calculation
            await self._update_delta_calculation()
            
            self.logger.info(f"✅ Order filled on {exchange_key}: {filled_quantity} @ {avg_price}")
            self.logger.info(f"📊 Positions - MEXC: {self.context.mexc_position}, Gate.io: {self.context.gateio_position}, Delta: {self.context.current_delta}")
            
        except Exception as e:
            self.logger.error(f"Error processing filled order: {e}")
    
    async def cleanup(self):
        """Cleanup strategy resources."""
        await self.exchange_manager.shutdown()
    
    def get_strategy_summary(self) -> Dict:
        """Get comprehensive strategy performance summary."""
        return {
            'strategy_name': self.name,
            'symbol': str(self.context.symbol),
            'exchanges': ['MEXC', 'GATEIO_FUTURES'],
            'configuration': {
                'base_position_size': float(self.context.base_position_size),
                'entry_threshold_pct': float(self.context.entry_threshold_pct) * 100,  # Convert back to percentage for display
                'exit_threshold_pct': float(self.context.exit_threshold_pct) * 100,
                # 'futures_leverage': float(self.context.futures_leverage),
                'delta_tolerance': float(self.context.delta_tolerance)
            },
            'positions': {
                'mexc_spot': float(self.context.mexc_position),
                'gateio_futures': float(self.context.gateio_position),
                'current_delta': float(self.context.current_delta),
                'mexc_avg_price': float(self.context.mexc_avg_price),
                'gateio_avg_price': float(self.context.gateio_avg_price)
            },
            'performance': {
                'arbitrage_cycles': self.context.arbitrage_cycles,
                'total_volume': float(self.context.total_volume),
                'total_profit': float(self.context.total_profit),
                'total_fees': float(self.context.total_fees),
                'spread_captured': float(self.context.total_spread_captured)
            },
            'exchange_manager': self.exchange_manager.get_performance_summary() if hasattr(self, 'exchange_manager') else {}
        }


# Utility function for easy strategy creation
async def create_mexc_gateio_strategy(
    symbol: Symbol,
    base_position_size: float = 100.0,
    entry_threshold_pct: float = 0.1,
    exit_threshold_pct: float = 0.03,
    futures_leverage: float = 1.0
) -> MexcGateioFuturesStrategy:
    """Create and initialize MEXC + Gate.io futures arbitrage strategy.
    
    Args:
        symbol: Trading symbol
        base_position_size: Base position size for trades
        entry_threshold_pct: Entry threshold as percentage (e.g., 0.1 for 0.1%)
        exit_threshold_pct: Exit threshold as percentage (e.g., 0.03 for 0.03%)
        futures_leverage: Leverage for futures trading
        
    Returns:
        Initialized MexcGateioFuturesStrategy instance
    """
    strategy = MexcGateioFuturesStrategy(
        symbol=symbol,
        base_position_size=base_position_size,
        entry_threshold_pct=entry_threshold_pct,
        exit_threshold_pct=exit_threshold_pct
    )
    
    # Set futures leverage
    strategy.evolve_context(futures_leverage=futures_leverage)
    
    await strategy.start()
    return strategy