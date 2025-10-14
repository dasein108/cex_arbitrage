"""
Spot-Futures Arbitrage Task - TaskManager Compatible

Exchange-agnostic arbitrage strategy that extends BaseTradingTask.
Supports arbitrage between any spot and futures exchanges.
"""

import asyncio
import time
from typing import Optional, Dict, Type

from trading.tasks.base_task import BaseTradingTask, StateHandler
from trading.tasks.arbitrage_task_context import (
    ArbitrageTaskContext,
    TradingParameters,
    ArbitrageOpportunity,
    MarketData,
    ValidationResult,
    DeltaImbalanceResult
)
from exchanges.structs import Symbol, Side, ExchangeEnum, Order
from infrastructure.logging import HFTLoggerInterface, get_logger
from utils.exchange_utils import is_order_done
from utils import flip_side

# Import existing arbitrage components
from trading.task_manager.exchange_manager import (
    ExchangeManager, 
    OrderPlacementParams, 
    ExchangeRole, 
    ArbitrageExchangeType
)


class SpotFuturesArbitrageTask(BaseTradingTask[ArbitrageTaskContext, str]):
    """
    Exchange-agnostic spot-futures arbitrage strategy - TaskManager Compatible.
    
    Extends BaseTradingTask to provide full TaskManager integration while preserving
    all arbitrage logic and performance optimizations. Supports any combination of
    spot and futures exchanges.
    """
    
    name: str = "SpotFuturesArbitrageTask"
    
    @property
    def context_class(self) -> Type[ArbitrageTaskContext]:
        return ArbitrageTaskContext
    
    def __init__(self,
                 logger: HFTLoggerInterface,
                 context: ArbitrageTaskContext,
                 spot_exchange: ExchangeEnum,
                 futures_exchange: ExchangeEnum,
                 **kwargs):
        """Initialize exchange-agnostic spot-futures arbitrage strategy."""
        
        # Store exchange configuration in context for persistence
        context = context.evolve(
            spot_exchange=spot_exchange,
            futures_exchange=futures_exchange
        )
        
        # Generate deterministic task_id for strategy recovery-awareness
        if not context.task_id:
            strategy_task_id = context.generate_strategy_task_id(
                self.name, spot_exchange, futures_exchange
            )
            context = context.evolve(task_id=strategy_task_id)
        
        # Initialize BaseTradingTask with updated context
        super().__init__(logger, context, delay=0.01, **kwargs)  # 10ms for HFT
        
        # Store exchange configuration as instance variables for easy access
        self.spot_exchange = spot_exchange
        self.futures_exchange = futures_exchange
        
        # Strategy-specific initialization
        self.exchange_manager: Optional[ExchangeManager] = None
        self._debug_info_counter = 0
        
        self.logger.info(f"✅ {self.name} initialized: {spot_exchange.name} spot + {futures_exchange.name} futures")

        self._build_tag()

    def _build_tag(self) -> None:
        """Build logging tag with arbitrage-specific fields."""
        self._tag = f'{self.name}_{self.context.symbol}_{self.spot_exchange.name}_{self.futures_exchange.name}'
    
    def get_unified_state_handlers(self) -> Dict[str, StateHandler]:
        """Provide complete unified state handler mapping.
        
        Includes both base states and arbitrage-specific states using string keys.
        """
        return {
            # Base state handlers
            'idle': self._handle_idle,
            'paused': self._handle_paused,
            'error': self._handle_error,
            'completed': self._handle_complete,
            'cancelled': self._handle_cancelled,
            'executing': self._handle_executing,
            # 'adjusting': self._handle_adjusting,
            
            # Arbitrage-specific state handlers
            'initializing': self._handle_initializing,
            'monitoring': self._handle_arbitrage_monitoring,
            'analyzing': self._handle_arbitrage_analyzing,
            'error_recovery': self._handle_arbitrage_error_recovery,
        }
    
    # async def _handle_executing(self):
    #     """Main execution logic - delegates to arbitrage state handlers."""
    #     # Delegate to arbitrage state machine
    #     arbitrage_state = self.context.arbitrage_state
    #
    #     if arbitrage_state == ArbitrageState.INITIALIZING:
    #         await self._handle_arbitrage_initializing()
    #     elif arbitrage_state == ArbitrageState.MONITORING:
    #         await self._handle_arbitrage_monitoring()
    #     elif arbitrage_state == ArbitrageState.ANALYZING:
    #         await self._handle_arbitrage_analyzing()
    #     elif arbitrage_state == ArbitrageState.EXECUTING:
    #         await self._handle_arbitrage_executing()
    #     elif arbitrage_state == ArbitrageState.ERROR_RECOVERY:
    #         await self._handle_arbitrage_error_recovery()
    #     else:
    #         # Default to monitoring
    #         self._transition_arbitrage_state('monitoring')
    #
    def _transition_arbitrage_state(self, new_state: str):
        """Transition to a new arbitrage state."""
        # old_state = self.context.arbitrage_state
        # self.logger.info(f"Arbitrage state transition: {old_state} -> {new_state}")
        # self.evolve_context(arbitrage_state=new_state)
        self._transition(new_state)
    
    async def _handle_initializing(self):
        """Initialize exchange manager and connections."""
        if self.exchange_manager is None:
            await self._initialize_exchange_manager()
        
        if self.exchange_manager:
            self._transition_arbitrage_state('monitoring')
        else:
            self.logger.error("❌ Failed to initialize exchange manager")
            self._transition_arbitrage_state('error_recovery')
    
    async def _initialize_exchange_manager(self) -> bool:
        """Initialize exchange manager with configured exchanges."""
        try:
            # Create exchange roles with configured exchanges
            exchange_roles: Dict[ArbitrageExchangeType, ExchangeRole] = {
                'spot': ExchangeRole(
                    exchange_enum=self.spot_exchange,
                    role='spot_trading',
                    max_position_size=self.context.base_position_size_usdt,
                    priority=0
                ),
                'futures': ExchangeRole(
                    exchange_enum=self.futures_exchange,
                    role='futures_hedge',
                    max_position_size=self.context.base_position_size_usdt,
                    priority=1
                )
            }
            
            # Initialize exchange manager
            self.exchange_manager = ExchangeManager(self.context.symbol, exchange_roles, self.logger)
            success = await self.exchange_manager.initialize()
            
            if success:
                # Get minimum quote quantities
                for exchange_type in ['spot', 'futures']: # type: ArbitrageExchangeType
                    exchange = self.exchange_manager.get_exchange(exchange_type)
                    symbol_info = exchange.public.symbols_info.get(self.context.symbol)
                    if symbol_info:
                        update_key = f'min_quote_quantity__{exchange_type}'
                        self.evolve_context(**{update_key: symbol_info.min_quote_quantity})
                
                self.logger.info(f"✅ Exchange manager initialized: {self.spot_exchange.name} + {self.futures_exchange.name}")
                return True
            else:
                self.logger.error("❌ Exchange manager initialization failed")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Exception during exchange manager initialization: {e}")
            return False
    
    async def _handle_arbitrage_monitoring(self):
        """Monitor market and manage positions."""
        try:
            # Check order updates first
            await self._check_order_updates()
            
            # Check positions and imbalances
            if self.context.positions_state.has_positions:
                delta_imbalance = self._has_delta_imbalance()
                if delta_imbalance.has_imbalance:
                    self.logger.warning(f"⚖️ Delta imbalance: {delta_imbalance.reason}")
                    await self._correct_delta_imbalance(delta_imbalance)
            
            # Check if should exit positions
            if await self._should_exit_positions():
                await self._exit_all_positions()
                return
            
            # Look for new opportunities
            if not self.context.positions_state.has_positions:
                opportunity = await self._identify_arbitrage_opportunity()
                if opportunity:
                    self.logger.info(f"💰 Opportunity: {opportunity.spread_pct:.4f}% spread")
                    self.evolve_context(current_opportunity=opportunity)
                    self._transition_arbitrage_state('analyzing')
        
        except Exception as e:
            self.logger.error(f"Monitoring failed: {e}")
            self._transition_arbitrage_state('error_recovery')
    
    async def _handle_arbitrage_analyzing(self):
        """Analyze current opportunity."""
        if not self.context.current_opportunity:
            self._transition_arbitrage_state('monitoring')
            return
        
        opportunity = self.context.current_opportunity
        if opportunity.is_fresh():
            self._transition_arbitrage_state('executing')
        else:
            self.logger.info("⚠️ Opportunity no longer fresh")
            self.evolve_context(current_opportunity=None)
            self._transition_arbitrage_state('monitoring')
    
    async def _handle_executing(self):
        """Execute arbitrage trades."""
        if not self.context.current_opportunity:
            self._transition_arbitrage_state('monitoring')
            return
        
        try:
            success = await self._execute_arbitrage_trades(self.context.current_opportunity)
            
            if success:
                self.logger.info("✅ Arbitrage execution successful")
                self.evolve_context(
                    arbitrage_cycles=self.context.arbitrage_cycles + 1,
                    current_opportunity=None
                )
            else:
                self.logger.warning("❌ Arbitrage execution failed")
                self.evolve_context(current_opportunity=None)
                
        except Exception as e:
            self.logger.error(f"Execution error: {e}")
            
        self._transition_arbitrage_state('monitoring')
    
    # Base state handlers (implementing BaseStateMixin states)
    async def _handle_cancelled(self):
        """Handle cancelled state."""
        self.logger.info("🚫 Task cancelled")
        if self.exchange_manager:
            await self.exchange_manager.cancel_all_orders()
    
    async def _handle_arbitrage_error_recovery(self):
        """Handle errors and recovery."""
        self.logger.info("🔄 Error recovery")
        
        # Clear failed opportunity
        self.evolve_context(current_opportunity=None)
        
        # Cancel pending orders
        if self.exchange_manager:
            await self.exchange_manager.cancel_all_orders()
        
        # Wait before returning to monitoring
        await asyncio.sleep(1.0)
        self._transition_arbitrage_state('monitoring')
    
    # Volume validation methods following delta neutral task patterns
    
    def _get_minimum_order_quantity_usdt(self, exchange_type: str, current_price: float) -> float:
        """Get minimum order quantity based on exchange requirements."""
        return self.context.min_quote_quantity[exchange_type] / current_price
    
    def _validate_order_size(self, exchange_type: str, quantity: float, price: float) -> float:
        """Validate and adjust order size to meet exchange minimums."""
        min_quote_qty = self.context.min_quote_quantity[exchange_type]

        if quantity * price < min_quote_qty:
            adjusted_quantity = min_quote_qty / price + 0.001  # Small buffer for precision
            self.logger.info(f"📏 Adjusting {exchange_type} order size: {quantity:.6f} -> {adjusted_quantity:.6f} to meet minimum {min_quote_qty}")
            return adjusted_quantity

        return quantity
    
    def _prepare_order_quantity(self, exchange_type: str, base_quantity: float, price: float) -> float:
        """Prepare order quantity with all required adjustments including exchange minimums."""
        # Validate with exchange minimums
        quantity = self._validate_order_size(exchange_type, base_quantity, price)
        
        # Round to contracts if futures
        exchange = self.exchange_manager.get_exchange(exchange_type)
        if exchange.is_futures:
            quantity = exchange.round_base_to_contracts(self.context.symbol, quantity)
        
        return quantity
    
    def _validate_entry_volumes(self, spot_quantity: float, futures_quantity: float, 
                               spot_price: float, futures_price: float) -> ValidationResult:
        """Validate that entry volumes meet minimum requirements for both exchanges."""
        # Get minimum quantities for both exchanges
        spot_min = self._get_minimum_order_quantity_usdt('spot', spot_price)
        futures_min = self._get_minimum_order_quantity_usdt('futures', futures_price)
        
        # Check spot volume
        if spot_quantity < spot_min:
            return ValidationResult(
                valid=False, 
                reason=f"Spot volume {spot_quantity:.6f} < minimum {spot_min:.6f}"
            )
        
        # Check futures volume
        if futures_quantity < futures_min:
            return ValidationResult(
                valid=False, 
                reason=f"Futures volume {futures_quantity:.6f} < minimum {futures_min:.6f}"
            )
        
        # Check that volumes are executable (max of minimums)
        max_min = max(spot_min, futures_min)
        if spot_quantity < max_min or futures_quantity < max_min:
            return ValidationResult(
                valid=False, 
                reason=f"Entry volume {min(spot_quantity, futures_quantity):.6f} < max minimum {max_min:.6f}"
            )
        
        return ValidationResult(valid=True)
    
    def _validate_exit_volumes(self) -> ValidationResult:
        """Validate that exit volumes meet minimum requirements for both exchanges."""
        spot_pos = self.context.positions_state.positions['spot']
        futures_pos = self.context.positions_state.positions['futures']
        
        if spot_pos.qty < 1e-8 or futures_pos.qty < 1e-8:
            return ValidationResult(valid=False, reason="No positions to exit")
        
        market_data = self.get_market_data()
        if not market_data.is_complete:
            return ValidationResult(valid=False, reason="Missing market data for exit validation")
        
        # Get exit prices for minimum calculations
        spot_exit_price = market_data.spot.bid_price if spot_pos.side == Side.BUY else market_data.spot.ask_price
        futures_exit_price = market_data.futures.bid_price if futures_pos.side == Side.BUY else market_data.futures.ask_price
        
        # Get minimum quantities
        spot_min = self._get_minimum_order_quantity_usdt('spot', spot_exit_price)
        futures_min = self._get_minimum_order_quantity_usdt('futures', futures_exit_price)
        
        # Check if positions are large enough to exit
        if spot_pos.qty < spot_min:
            return ValidationResult(
                valid=False, 
                reason=f"Spot position {spot_pos.qty:.6f} < minimum exit {spot_min:.6f}"
            )
        
        if futures_pos.qty < futures_min:
            return ValidationResult(
                valid=False, 
                reason=f"Futures position {futures_pos.qty:.6f} < minimum exit {futures_min:.6f}"
            )
        
        # Check max minimum requirement
        max_min = max(spot_min, futures_min)
        if spot_pos.qty < max_min or futures_pos.qty < max_min:
            return ValidationResult(
                valid=False, 
                reason=f"Exit volume {min(spot_pos.qty, futures_pos.qty):.6f} < max minimum {max_min:.6f}"
            )
        
        return ValidationResult(valid=True)

    # Unified utility methods
    
    def _usdt_to_coins(self, usdt_amount: float) -> Optional[float]:
        """Convert USDT amount to coin quantity using current market price."""
        market_data = self.get_market_data()
        if not market_data.is_complete:
            self.logger.warning("Cannot convert USDT to coins: missing market data")
            return None
        if market_data.spot.ask_price <= 0:
            self.logger.warning(f"Invalid ask price for conversion: {market_data.spot.ask_price}")
            return None
        return usdt_amount / market_data.spot.ask_price
    
    def _coins_to_usdt(self, coin_amount: float) -> Optional[float]:
        """Convert coin quantity to USDT amount using current market price."""
        market_data = self.get_market_data()
        if not market_data.is_complete:
            self.logger.warning("Cannot convert coins to USDT: missing market data")
            return None
        return coin_amount * market_data.spot.ask_price

    # Core arbitrage logic methods (enhanced versions)
    
    def get_market_data(self) -> MarketData:
        """Get unified market data from both exchanges using direct access."""
        try:
            # Get exchanges directly from exchange manager
            spot_exchange = self.exchange_manager.get_exchange('spot')
            futures_exchange = self.exchange_manager.get_exchange('futures')
            
            spot_ticker = spot_exchange.public._book_ticker.get(self.context.symbol)
            futures_ticker = futures_exchange.public._book_ticker.get(self.context.symbol)
            
            return MarketData(
                spot=spot_ticker,
                futures=futures_ticker
            )
        except Exception as e:
            self.logger.warning(f"⚠️ Error accessing market data directly: {e}")
            return MarketData(spot=None, futures=None)
    
    async def _identify_arbitrage_opportunity(self) -> Optional[ArbitrageOpportunity]:
        """Identify arbitrage opportunities using backtesting logic."""
        market_data = self.get_market_data()
        
        if not market_data.is_complete:
            return None
        
        spot_ticker = market_data.spot
        futures_ticker = market_data.futures
        
        # Calculate entry cost
        entry_cost_pct = ((spot_ticker.ask_price - futures_ticker.bid_price) / 
                          spot_ticker.ask_price) * 100
        
        if self._debug_info_counter % 1000 == 0:
            print(f'Entry cost {entry_cost_pct:.4f}% ({self.spot_exchange.name} -> {self.futures_exchange.name})')
            self._debug_info_counter = 0
        self._debug_info_counter += 1
        
        # Check if profitable
        if entry_cost_pct >= self.context.params.max_entry_cost_pct:
            return None
        
        # Calculate max quantity
        max_quantity = min(
            spot_ticker.ask_quantity,
            futures_ticker.bid_quantity,
            self.context.base_position_size_usdt / spot_ticker.ask_price
        )
        
        # Ensure meets minimum requirements
        min_required = max(
            self.context.min_quote_quantity.get('spot', 10.0) / spot_ticker.ask_price,
            self.context.min_quote_quantity.get('futures', 10.0) / futures_ticker.bid_price
        )
        
        if max_quantity < min_required:
            return None
        
        return ArbitrageOpportunity(
            direction='spot_to_futures',
            spread_pct=entry_cost_pct,
            buy_price=spot_ticker.ask_price,
            sell_price=futures_ticker.bid_price,
            max_quantity=max_quantity
        )
    
    async def _should_exit_positions(self) -> bool:
        """Check if should exit existing positions."""
        if not self.context.positions_state.has_positions:
            return False
        
        market_data = self.get_market_data()
        if not market_data.is_complete:
            return False
        
        # Get position details
        spot_pos = self.context.positions_state.positions['spot']
        futures_pos = self.context.positions_state.positions['futures']
        
        if spot_pos.qty < 1e-8 or futures_pos.qty < 1e-8:
            return False
        
        # Calculate P&L using backtesting logic with fees
        spot_fee = self.context.params.spot_fee
        fut_fee = self.context.params.fut_fee
        
        # Entry costs (what we paid)
        entry_spot_cost = spot_pos.price * (1 + spot_fee)  # Bought spot with fee
        entry_fut_receive = futures_pos.price * (1 - fut_fee)  # Sold futures with fee
        
        # Exit revenues (what we get)
        exit_spot_receive = market_data.spot.bid_price * (1 - spot_fee)  # Sell spot with fee
        exit_fut_cost = market_data.futures.ask_price * (1 + fut_fee)  # Buy futures with fee
        
        # P&L calculation
        spot_pnl_pts = exit_spot_receive - entry_spot_cost
        fut_pnl_pts = entry_fut_receive - exit_fut_cost
        total_pnl_pts = spot_pnl_pts + fut_pnl_pts
        
        # P&L percentage
        capital = entry_spot_cost
        net_pnl_pct = (total_pnl_pts / capital) * 100
        
        # Check exit conditions
        exit_now = False

        # 1. PROFIT TARGET: Exit when profitable
        if net_pnl_pct >= self.context.params.min_profit_pct:
            exit_now = True
            exit_reason = 'profit_target'
            self.logger.info(f"💰 Profit target reached: {net_pnl_pct:.4f}% >= {self.context.params.min_profit_pct:.4f}%")
        
        # 2. TIMEOUT: Position held too long
        elif self.context.position_start_time:
            hours_held = (time.time() - self.context.position_start_time) / 3600
            if hours_held >= self.context.params.max_hours:
                exit_now = True
                exit_reason = 'timeout'
                self.logger.info(f"🕒 Timeout exit: {hours_held:.2f}h >= {self.context.params.max_hours:.2f}h (P&L: {net_pnl_pct:.4f}%)")
        
        return exit_now
    
    def _has_delta_imbalance(self) -> DeltaImbalanceResult:
        """Check for delta imbalance and determine correction needed.
        
        Returns detailed analysis of any position imbalance that requires correction.
        Uses proper signed position values and percentage-based tolerance.
        """
        if not self.context.positions_state.has_positions:
            return DeltaImbalanceResult(has_imbalance=False, reason="No positions to balance")
        
        spot_pos = self.context.positions_state.positions['spot']
        futures_pos = self.context.positions_state.positions['futures']
        
        # Calculate signed position values (positive for long, negative for short)
        spot_signed = spot_pos.qty if spot_pos.side == Side.BUY else -spot_pos.qty if spot_pos.side else 0.0
        futures_signed = futures_pos.qty if futures_pos.side == Side.BUY else -futures_pos.qty if futures_pos.side else 0.0
        
        # For delta-neutral arbitrage: spot + futures should equal zero
        # spot_signed + futures_signed = 0 (perfect balance)
        net_exposure = spot_signed + futures_signed
        
        # Use percentage-based tolerance (e.g., 2% imbalance threshold)
        tolerance_pct = 2.0  # 2% tolerance for delta neutrality
        total_exposure = abs(spot_signed) + abs(futures_signed)
        
        if total_exposure < 1e-8:
            return DeltaImbalanceResult(has_imbalance=False, reason="No meaningful positions")
        
        imbalance_pct = abs(net_exposure) / total_exposure * 100
        
        if imbalance_pct <= tolerance_pct:
            return DeltaImbalanceResult(
                has_imbalance=False, 
                imbalance_percentage=imbalance_pct,
                reason=f"Delta balanced within tolerance: {imbalance_pct:.2f}% <= {tolerance_pct}%"
            )
        
        # Determine imbalance direction and correction needed
        if net_exposure > 0:
            # Net long position - need to reduce spot or increase short futures
            if abs(spot_signed) > abs(futures_signed):
                direction = 'spot_excess'
                imbalance_qty = abs(spot_signed) - abs(futures_signed)
            else:
                direction = 'futures_excess' 
                imbalance_qty = net_exposure
        else:
            # Net short position - need to reduce short futures or increase spot
            if abs(futures_signed) > abs(spot_signed):
                direction = 'futures_excess'
                imbalance_qty = abs(futures_signed) - abs(spot_signed)
            else:
                direction = 'spot_excess'
                imbalance_qty = abs(net_exposure)
        
        return DeltaImbalanceResult(
            has_imbalance=True,
            imbalance_direction=direction,
            imbalance_quantity=imbalance_qty,
            imbalance_percentage=imbalance_pct,
            reason=f"Delta imbalance: {imbalance_pct:.2f}% ({direction}: {imbalance_qty:.6f})"
        )
    
    async def _correct_delta_imbalance(self, imbalance: DeltaImbalanceResult) -> bool:
        """Actively correct delta imbalance by executing balancing trades.
        
        Args:
            imbalance: Result from _has_delta_imbalance() indicating the correction needed
            
        Returns:
            bool: True if correction was successful, False otherwise
        """
        if not imbalance.has_imbalance:
            self.logger.info("✅ No delta imbalance to correct")
            return True
        
        self.logger.info(f"🔄 Correcting delta imbalance: {imbalance.reason}")
        
        try:
            # Get current market data for pricing
            market_data = self.get_market_data()
            if not market_data.is_complete:
                self.logger.error("❌ Cannot correct imbalance - missing market data")
                return False
            
            correction_order: Optional[OrderPlacementParams] = None
            exchange_key: Optional[str] = None
            
            if imbalance.imbalance_direction == 'spot_excess':
                # Too much spot exposure - need to add futures short position
                # Execute market SELL on futures to balance
                exchange_key = 'futures'
                price = market_data.futures.bid_price  # Market sell - use bid
                quantity = self._prepare_order_quantity('futures', imbalance.imbalance_quantity, price)
                
                correction_order = OrderPlacementParams(
                    side=Side.SELL,
                    quantity=quantity,
                    price=price
                )
                
                self.logger.info(f"🎯 Correcting spot excess: SELL {quantity:.6f} futures @ {price:.6f}")
                
            elif imbalance.imbalance_direction == 'futures_excess':
                # Too much futures exposure - need to add spot long position
                # Execute market BUY on spot to balance
                exchange_key = 'spot'
                price = market_data.spot.ask_price  # Market buy - use ask
                quantity = self._prepare_order_quantity('spot', imbalance.imbalance_quantity, price)
                
                correction_order = OrderPlacementParams(
                    side=Side.BUY,
                    quantity=quantity,
                    price=price
                )
                
                self.logger.info(f"🎯 Correcting futures excess: BUY {quantity:.6f} spot @ {price:.6f}")
            
            if not correction_order or not exchange_key:
                self.logger.error(f"❌ Could not determine correction order for {imbalance.imbalance_direction}")
                return False
            
            # Validate minimum order requirements
            min_qty = self._get_minimum_order_quantity_usdt(exchange_key, correction_order.price)
            if correction_order.quantity < min_qty:
                self.logger.warning(f"⚠️ Correction quantity {correction_order.quantity:.6f} < minimum {min_qty:.6f}")
                
                # Check if imbalance is too small to correct profitably
                if imbalance.imbalance_quantity < min_qty * 1.5:
                    self.logger.info(f"📏 Imbalance too small to correct profitably, tolerating {imbalance.imbalance_percentage:.2f}%")
                    return True  # Accept the small imbalance
                
                # Adjust to minimum if possible
                correction_order = OrderPlacementParams(
                    side=correction_order.side,
                    quantity=min_qty * 1.01,  # Add small buffer
                    price=correction_order.price
                )
                self.logger.info(f"📏 Adjusted correction quantity to {correction_order.quantity:.6f}")
            
            # Execute the correction order
            placed_orders = await self.exchange_manager.place_order_parallel({exchange_key: correction_order})
            
            if exchange_key in placed_orders and placed_orders[exchange_key]:
                order = placed_orders[exchange_key]
                self.logger.info(f"✅ Delta correction order placed: {order.order_id} on {exchange_key}")
                
                # Update active orders tracking
                await self._update_active_orders_after_placement(placed_orders)
                return True
            else:
                self.logger.error(f"❌ Failed to place delta correction order on {exchange_key}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Error correcting delta imbalance: {e}")
            return False
    
    def _validate_execution(self, opportunity: ArbitrageOpportunity, position_size: float) -> ValidationResult:
        """Unified validation for trade execution."""
        if position_size <= 0:
            return ValidationResult(valid=False, reason="Invalid position size")
        
        # Get market data for unit conversion
        market_data = self.get_market_data()
        if not market_data.is_complete:
            return ValidationResult(valid=False, reason="Missing market data for validation")
        
        # CRITICAL FIX: Convert to consistent units (coins)
        max_size_coins = (self.context.base_position_size_usdt * 2.0 / market_data.spot.ask_price)  # 2x multiplier like source
        
        if position_size > max_size_coins:
            return ValidationResult(valid=False, reason=f"Position size {position_size:.6f} coins exceeds limit {max_size_coins:.6f} coins")
        
        if not opportunity.is_fresh():
            return ValidationResult(valid=False, reason="Opportunity is stale")
        
        return ValidationResult(valid=True)

    async def _execute_arbitrage_trades(self, opportunity: ArbitrageOpportunity) -> bool:
        """Execute arbitrage trades using unified order preparation."""
        try:
            # Get market data for USDT to coin conversion
            market_data = self.get_market_data()
            if not market_data.is_complete:
                self.logger.error("❌ Missing market data for position sizing")
                return False
            
            # CRITICAL FIX: Convert USDT to coin units before comparison
            base_position_coin_size = self.context.base_position_size_usdt / market_data.spot.ask_price

            position_size = min(
                base_position_coin_size,    # Now in coin units
                opportunity.max_quantity    # Already in coin units
            )

            self.logger.info(f"Calculated position size: {position_size:.6f} coins, base: {base_position_coin_size}, "
                             f"oppo: {opportunity.max_quantity} price: {market_data.spot.ask_price}")

            # Validate execution parameters
            validation = self._validate_execution(opportunity, position_size)

            if not validation.valid:
                self.logger.error(f"❌ Execution validation failed: {validation.reason}")
                return False
            
            # CRITICAL: Validate entry volumes meet minimum requirements
            volume_validation = self._validate_entry_volumes(
                spot_quantity=position_size, 
                futures_quantity=position_size,
                spot_price=opportunity.buy_price,
                futures_price=opportunity.sell_price
            )

            if not volume_validation.valid:
                self.logger.error(f"❌ Entry volume validation failed: {volume_validation.reason}")
                return False
            
            # Adjust order sizes to meet exchange minimums
            spot_quantity = self._prepare_order_quantity('spot', position_size, opportunity.buy_price)
            futures_quantity = self._prepare_order_quantity('futures', position_size, opportunity.sell_price)
            
            # Ensure adjusted quantities are still equal for delta neutrality
            if abs(spot_quantity - futures_quantity) > 1e-6:
                # Use the larger quantity for both to maintain delta neutrality
                adjusted_quantity = max(spot_quantity, futures_quantity)
                self.logger.info(f"⚖️ Adjusting both quantities to {adjusted_quantity:.6f} for delta neutrality")
                spot_quantity = futures_quantity = adjusted_quantity

            # Convert to OrderPlacementParams
            enter_orders: Dict[str, OrderPlacementParams] = {
                'spot': OrderPlacementParams(side=Side.BUY, quantity=spot_quantity, price=opportunity.buy_price),
                'futures': OrderPlacementParams(side=Side.SELL, quantity=futures_quantity, price=opportunity.sell_price)
            }
            
            # Execute orders in parallel
            self.logger.info(f"🚀 Executing arbitrage trades: {position_size}")
            start_time = time.time()
            
            placed_orders = await self.exchange_manager.place_order_parallel(enter_orders)

            # Update active orders tracking for successfully placed orders
            await self._update_active_orders_after_placement(placed_orders)
            
            execution_time = (time.time() - start_time) * 1000

            self.logger.info(f"⚡ Order execution completed in {execution_time:.1f}ms,"
                             f" placed orders: {placed_orders}")
            
            # Check success
            success = all(placed_orders.values())
            if success:
                # Track position start time
                if self.context.position_start_time is None:
                    self.evolve_context(position_start_time=time.time())
                # Update performance metrics (convert to USDT for consistent tracking)
                position_usdt = self._coins_to_usdt(max(spot_quantity, futures_quantity))
                if position_usdt:
                    self.evolve_context(
                        total_volume_usdt=self.context.total_volume_usdt + position_usdt
                    )
            else:
                # Cancel any successful orders
                await self.exchange_manager.cancel_all_orders()
            
            return success
            
        except Exception as e:
            self.logger.error(f"Arbitrage execution error: {e}")
            await self.exchange_manager.cancel_all_orders()
            return False
    
    async def _exit_all_positions(self):
        """Exit all positions using simplified logic with volume validation."""
        try:
            self.logger.info("🔄 Exiting all positions...")
            
            market_data = self.get_market_data()
            if not market_data.is_complete:
                self.logger.error("❌ Cannot exit positions - missing market data")
                return
            
            # CRITICAL: Validate exit volumes meet minimum requirements
            volume_validation = self._validate_exit_volumes()
            if not volume_validation.valid:
                self.logger.error(f"❌ Exit volume validation failed: {volume_validation.reason}")
                return
            
            exit_orders: Dict[str, OrderPlacementParams] = {}
            
            # Close spot position (exit is opposite side) with volume validation
            spot_pos = self.context.positions_state.positions['spot']
            if spot_pos.qty > 1e-8:
                exit_side = flip_side(spot_pos.side)
                price = market_data.spot.bid_price if exit_side == Side.SELL else market_data.spot.ask_price
                
                # Prepare exit quantity with minimum validations
                exit_quantity = self._prepare_order_quantity('spot', spot_pos.qty, price)
                
                exit_orders['spot'] = OrderPlacementParams(
                    side=exit_side,
                    quantity=exit_quantity,
                    price=price
                )
            
            # Close futures position (exit is opposite side) with volume validation
            futures_pos = self.context.positions_state.positions['futures']
            if futures_pos.qty > 1e-8:
                exit_side = flip_side(futures_pos.side)
                price = market_data.futures.bid_price if exit_side == Side.SELL else market_data.futures.ask_price
                
                # Prepare exit quantity with minimum validations
                exit_quantity = self._prepare_order_quantity('futures', futures_pos.qty, price)
                
                exit_orders['futures'] = OrderPlacementParams(
                    side=exit_side,
                    quantity=exit_quantity,
                    price=price
                )
            
            if exit_orders:
                placed_orders = await self.exchange_manager.place_order_parallel(exit_orders)
                
                # Update active orders tracking for exit orders
                await self._update_active_orders_after_placement(placed_orders)
                
                if all(placed_orders.values()):
                    self.logger.info("✅ All exit orders placed successfully")
                    # Reset position timing
                    self.evolve_context(position_start_time=None)
                else:
                    self.logger.warning("⚠️ Some exit orders failed")
            
        except Exception as e:
            self.logger.error(f"❌ Error exiting positions: {e}")
    
    async def _update_active_orders_after_placement(self, placed_orders: Dict[str, Order]):
        """Update active orders tracking after placing new orders."""
        for exchange_role, order in placed_orders.items():
            await self._process_order_fill(exchange_role, order)

    async def _check_order_updates(self):
        """Check order status updates using direct access to exchange orders."""
        for exchange_role in ['spot', 'futures']: # type: ArbitrageExchangeType
            # Get exchange directly
            for order_id, order in self.context.active_orders[exchange_role].copy().items():
                await self._process_order_fill(exchange_role, order)

    async def _process_order_fill(self, exchange_key: str, order: Order):
        """Process partial fill and update position tracking incrementally with delta validation."""
        try:
            if order is None:
                self.logger.error(f"❌ Cannot process None order from {exchange_key}")
                return

            previous_order = self.context.active_orders[exchange_key].get(order.order_id, None)

            if not previous_order:
                # New order - track it
                new_active_orders = self.context.active_orders.copy()
                new_active_orders[exchange_key][order.order_id] = order
                
                new_positions = self.context.positions_state.update_position(
                    exchange_key, order.filled_quantity, order.price, order.side
                )

                self.evolve_context(
                    positions=new_positions,
                    active_orders=new_active_orders
                )

                self.logger.info(f"📝 New order tracked: {order} on {exchange_key}")
            else:
                # Update stored order with latest state
                new_active_orders = self.context.active_orders.copy()
                new_active_orders[exchange_key][order.order_id] = order
                
                # Existing order - check for new fills
                previous_filled = previous_order.filled_quantity
                current_filled = order.filled_quantity

                fill_amount = current_filled - previous_filled

                if fill_amount > 0:
                    new_positions = self.context.positions_state.update_position(
                        exchange_key, fill_amount, order.price, order.side
                    )

                    self.evolve_context(
                        positions=new_positions,
                        active_orders=new_active_orders
                    )

                    self.logger.info(f"🔄 Processed partial fill for order {order} on {exchange_key}: {fill_amount} ")
                else:
                    # Update active orders even if no new fill
                    self.evolve_context(active_orders=new_active_orders)

            if is_order_done(order):
                new_active_orders = self.context.active_orders.copy()
                del new_active_orders[exchange_key][order.order_id]
                self.evolve_context(active_orders=new_active_orders)
                
                exchange = self.exchange_manager.get_exchange(exchange_key).private
                exchange.remove_order(order.order_id) # cleanup exchange
                self.logger.info(f"🏁 Order completed: {order.order_id} on {exchange_key} {order}")

        except Exception as e:
            self.logger.error(f"Error processing partial fill: {e}")
    
    async def cleanup(self):
        """Clean up strategy resources."""
        self.logger.info(f"🧹 Cleaning up {self.name} resources")
        if self.exchange_manager:
            await self.exchange_manager.shutdown()
        self.logger.info(f"✅ {self.name} cleanup completed")


# Exchange-agnostic factory function
async def create_spot_futures_arbitrage_task(
    symbol: Symbol,
    spot_exchange: ExchangeEnum,
    futures_exchange: ExchangeEnum,
    base_position_size_usdt: float = 100.0,
    max_entry_cost_pct: float = 0.5,
    min_profit_pct: float = 0.1,
    max_hours: float = 6.0,
    logger: Optional[HFTLoggerInterface] = None
) -> SpotFuturesArbitrageTask:
    """Create and initialize spot-futures arbitrage task for any exchange pair."""
    
    if logger is None:
        logger = get_logger(f'spot_futures_arbitrage.{symbol}.{spot_exchange.name}_{futures_exchange.name}')
    
    params = TradingParameters(
        max_entry_cost_pct=max_entry_cost_pct,
        min_profit_pct=min_profit_pct,
        max_hours=max_hours
    )
    
    context = ArbitrageTaskContext(
        symbol=symbol,
        base_position_size_usdt=base_position_size_usdt,
        params=params,
        arbitrage_state='initializing'
    )
    
    task = SpotFuturesArbitrageTask(
        logger=logger,
        context=context,
        spot_exchange=spot_exchange,
        futures_exchange=futures_exchange
    )
    await task.start()
    return task


# Convenience function for MEXC + Gate.io (backward compatibility)
async def create_mexc_gateio_arbitrage_task(
    symbol: Symbol,
    base_position_size_usdt: float = 100.0,
    max_entry_cost_pct: float = 0.5,
    min_profit_pct: float = 0.1,
    max_hours: float = 6.0,
    logger: Optional[HFTLoggerInterface] = None
) -> SpotFuturesArbitrageTask:
    """Create MEXC + Gate.io arbitrage task (convenience function for backward compatibility)."""
    return await create_spot_futures_arbitrage_task(
        symbol=symbol,
        spot_exchange=ExchangeEnum.MEXC,
        futures_exchange=ExchangeEnum.GATEIO_FUTURES,
        base_position_size_usdt=base_position_size_usdt,
        max_entry_cost_pct=max_entry_cost_pct,
        min_profit_pct=min_profit_pct,
        max_hours=max_hours,
        logger=logger
    )