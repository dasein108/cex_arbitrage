"""
Spot-Futures Arbitrage Task - TaskManager Compatible

Exchange-agnostic arbitrage strategy that extends BaseTradingTask.
Supports arbitrage between any spot and futures exchanges.
"""

import asyncio
import time
from typing import Optional, Dict, Type, Literal

from trading.tasks.base_task import BaseTradingTask, StateHandler
from trading.tasks.arbitrage_task_context import (
    ArbitrageTaskContext,
    TradingParameters,
    ArbitrageOpportunity,
    ValidationResult
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

    @property
    def spot_ticker(self):
        return self.exchange_manager.get_exchange('spot').public.book_ticker.get(self.context.symbol)

    @property
    def futures_ticker(self):
        return self.exchange_manager.get_exchange('futures').public.book_ticker.get(self.context.symbol)
    
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
        super().__init__(logger, context, delay=0.01)  # 10ms for HFT
        
        # Store exchange configuration as instance variables for easy access
        self.spot_exchange = spot_exchange
        self.futures_exchange = futures_exchange
        
        # Strategy-specific initialization
        self.exchange_manager: Optional[ExchangeManager] = None
        self._debug_info_counter = 0
        self.min_quote_quantity: Dict[ArbitrageExchangeType, float] = {'spot': 0, 'futures': 0}  # Default minimums

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
                    max_position_size=self.context.single_order_size_usdt,
                    priority=0
                ),
                'futures': ExchangeRole(
                    exchange_enum=self.futures_exchange,
                    role='futures_hedge',
                    max_position_size=self.context.single_order_size_usdt,
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
                    self.min_quote_quantity[exchange_type] =  symbol_info.min_quote_quantity

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

            await self._process_imbalance()

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
            success = await self._enter_positions(self.context.current_opportunity)
            
            if success:
                self.logger.info("✅ Arbitrage execution successful")
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
    
    def _get_minimum_order_quantity_usdt(self, exchange_type: ArbitrageExchangeType,
                                         current_price: Optional[float] = None) -> float:
        if not current_price:
            current_price = self._get_direction_price('enter', exchange_type)

        """Get minimum order quantity based on exchange requirements."""
        return self.min_quote_quantity[exchange_type] / current_price
    
    def _validate_order_size(self, exchange_type: ArbitrageExchangeType, quantity: float, price: float) -> float:
        """Validate and adjust order size to meet exchange minimums."""
        min_quote_qty = self.min_quote_quantity[exchange_type]

        if quantity * price < min_quote_qty:
            adjusted_quantity = min_quote_qty / price + 0.001  # Small buffer for precision
            self.logger.info(f"📏 Adjusting {exchange_type} order size: {quantity:.6f} -> {adjusted_quantity:.6f} to meet minimum {min_quote_qty}")
            return adjusted_quantity

        return quantity
    
    def _prepare_order_quantity(self, exchange_type: ArbitrageExchangeType, base_quantity: float, price: float) -> float:
        """Prepare order quantity with all required adjustments including exchange minimums."""
        # Validate with exchange minimums
        quantity = self._validate_order_size(exchange_type, base_quantity, price)
        
        # Round to contracts if futures
        exchange = self.exchange_manager.get_exchange(exchange_type)
        if exchange.is_futures:
            quantity = exchange.round_base_to_contracts(self.context.symbol, quantity)
        
        return quantity
    
    def _validate_exit_volumes(self) -> ValidationResult:
        """Validate that exit volumes meet minimum requirements for both exchanges."""
        if not self.context.positions_state.has_positions:
            return ValidationResult(valid=False, reason="No positions to exit")


        spot_pos = self.context.positions_state.positions['spot']
        futures_pos = self.context.positions_state.positions['futures']

        # Get exit prices for minimum calculations
        spot_exit_price = self._get_direction_price('exit', 'spot')
        futures_exit_price = self._get_direction_price('exit', 'futures')
        
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

    async def _identify_arbitrage_opportunity(self) -> Optional[ArbitrageOpportunity]:
        """Identify arbitrage opportunities using backtesting logic."""

        spot_ticker = self.spot_ticker
        futures_ticker = self.futures_ticker
        
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
            self.context.single_order_size_usdt / spot_ticker.ask_price
        )
        
        # Ensure meets minimum requirements
        min_required = max(
            self._get_minimum_order_quantity_usdt('spot', spot_ticker.ask_price),
            self._get_minimum_order_quantity_usdt('futures', futures_ticker.bid_price)
        )
        
        if max_quantity < min_required:
            return None
        
        return ArbitrageOpportunity(
            direction='enter',
            spread_pct=entry_cost_pct,
            buy_price=spot_ticker.ask_price,
            sell_price=futures_ticker.bid_price,
            max_quantity=max_quantity
        )
    
    async def _should_exit_positions(self) -> bool:
        """Check if should exit existing positions."""
        if not self.context.positions_state.has_positions:
            return False
        
        # Get position details
        spot_pos = self.context.positions_state.positions['spot']
        futures_pos = self.context.positions_state.positions['futures']
        
        # Calculate P&L using backtesting logic with fees
        spot_fee = self.context.params.spot_fee
        fut_fee = self.context.params.fut_fee
        
        # Entry costs (what we paid)
        entry_spot_cost = spot_pos.price * (1 + spot_fee)  # Bought spot with fee
        entry_fut_receive = futures_pos.price * (1 - fut_fee)  # Sold futures with fee
        
        # Exit revenues (what we get)
        exit_spot_receive = self.spot_ticker.bid_price * (1 - spot_fee)  # Sell spot with fee
        exit_fut_cost = self.futures_ticker.ask_price * (1 + fut_fee)  # Buy futures with fee
        
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

    async def _process_imbalance(self) -> bool:
        # Check positions and imbalances
        if not self.context.positions_state.has_positions:
            return False

        delta_usdt = self.context.positions_state.delta_usdt
        delta_base = self.context.positions_state.delta
        min_spot_usdt = self._get_minimum_order_quantity_usdt('spot')
        min_futures_usdt = self._get_minimum_order_quantity_usdt('futures')

        if abs(delta_usdt) < min_spot_usdt:
            return False

        self.logger.info(f'⚠️ Imbalance detected: Delta USDT {delta_usdt:.2f}')

        spot_imbalance = delta_usdt >= min_spot_usdt
        # force
        # futures_imbalance_less_ = delta_usdt < 0 and abs(delta_usdt) < min_futures_usdt
        place_orders: Dict[ArbitrageExchangeType, OrderPlacementParams] = {}

        if spot_imbalance:
            quantity = self._prepare_order_quantity('spot', delta_base,
                                                 self.spot_ticker.ask_price)
            place_orders['spot'] = OrderPlacementParams(
                side=Side.BUY,
                quantity=quantity,
                price=self.spot_ticker.ask_price
            )
        else:
            # imbalance < minimal futures quantity, force buy spot to reduce imbalance
            if abs(delta_usdt) >= min_futures_usdt:
                quantity = self._prepare_order_quantity('spot', abs(delta_base),
                                                        self.spot_ticker.ask_price)
                place_orders['spot'] = OrderPlacementParams(
                    side=Side.BUY,
                    quantity=quantity,
                    price=self.spot_ticker.ask_price
                )
            else:
                quantity = self._prepare_order_quantity('futures', abs(delta_base),
                                                        self.spot_ticker.ask_price)
                place_orders['futures'] = OrderPlacementParams(
                    side=Side.SELL,
                    quantity=quantity,
                    price=self.futures_ticker.bid_price
                )

        placed_orders = await self.exchange_manager.place_order_parallel(place_orders)

        success = await self._update_active_orders_after_placement(placed_orders)

        if success:
            self.logger.info(f"✅ Delta correction order placed: {placed_orders}")
        else:
            self.logger.error(f"❌ Failed to place delta correction orders {placed_orders}")

        return success


    async def _enter_positions(self, opportunity: ArbitrageOpportunity) -> bool:
        """Execute arbitrage trades using unified order preparation."""
        try:
            index_price = self.spot_ticker.ask_price
            # CRITICAL FIX: Convert USDT to coin units before comparison
            order_coin_size = self.context.single_order_size_usdt / index_price

            position_size = min(order_coin_size, opportunity.max_quantity)

            spot_min = self._get_minimum_order_quantity_usdt('spot', opportunity.buy_price)
            futures_min = self._get_minimum_order_quantity_usdt('futures', opportunity.sell_price)
            min_coin_required = max(spot_min, futures_min)

            if position_size < min_coin_required:
                self.logger.error(f"❌ Calculated position size {position_size:.6f} < minimum required {min_coin_required:.6f}")
                return False

            self.logger.info(f"Calculated position size: {position_size:.6f} coins, base: {order_coin_size}, "
                             f"oppo: {opportunity.max_quantity} price: {index_price}")
            
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
            enter_orders: Dict[ArbitrageExchangeType, OrderPlacementParams] = {
                'spot': OrderPlacementParams(side=Side.BUY, quantity=spot_quantity, price=opportunity.buy_price),
                'futures': OrderPlacementParams(side=Side.SELL, quantity=futures_quantity, price=opportunity.sell_price)
            }
            
            # Execute orders in parallel
            self.logger.info(f"🚀 Executing arbitrage trades: {position_size}")
            start_time = time.time()
            
            placed_orders = await self.exchange_manager.place_order_parallel(enter_orders)

            # Update active orders tracking for successfully placed orders
            success =await self._update_active_orders_after_placement(placed_orders)
            
            execution_time = (time.time() - start_time) * 1000

            self.logger.info(f"⚡ Order execution completed in {execution_time:.1f}ms,"
                             f" placed orders: {placed_orders}")
            
            if success:
                # Track position start time
                if self.context.position_start_time is None:
                    self.evolve_context(position_start_time=time.time())
                # TODO: use index price
                position_usdt = max(spot_quantity, futures_quantity) * self.spot_ticker.ask_price
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

    def _get_direction_price(self, direction: Literal['enter', 'exit'], exchange_type: ArbitrageExchangeType) -> Optional[float]:
        """Get trade price for entry or exit based on direction and exchange type."""
        if direction == 'enter':
            return self.spot_ticker.ask_price if exchange_type == 'spot' else self.futures_ticker.bid_price
        # elif direction == 'exit':

        return self.spot_ticker.bid_price if exchange_type == 'spot' else self.futures_ticker.ask_price

    async def _exit_all_positions(self):
        """Exit all positions using simplified logic with volume validation."""
        try:
            self.logger.info("🔄 Exiting all positions...")

            # CRITICAL: Validate exit volumes meet minimum requirements
            volume_validation = self._validate_exit_volumes()
            if not volume_validation.valid:
                self.logger.error(f"❌ Exit volume validation failed: {volume_validation.reason}")
                return
            
            exit_orders: Dict[ArbitrageExchangeType, OrderPlacementParams] = {}
            
            # Close spot position (exit is opposite side) with volume validation
            for exchange_role in ['spot', 'futures']: # type: ArbitrageExchangeType
                pos =  self.context.positions_state.positions[exchange_role]
                if pos.has_position:
                    exit_side = flip_side(pos.side)
                    price = self._get_direction_price('exit', 'spot')

                    # Prepare exit quantity with minimum validations
                    exit_quantity = self._prepare_order_quantity('spot', pos.qty, price)

                    exit_orders[exchange_role] = OrderPlacementParams(
                        side=exit_side,
                        quantity=exit_quantity,
                        price=price
                    )

            if exit_orders:
                placed_orders = await self.exchange_manager.place_order_parallel(exit_orders)
                
                # Update active orders tracking for exit orders
                success = await self._update_active_orders_after_placement(placed_orders)
                
                if success:
                    self.logger.info("✅ All exit orders placed successfully")
                    # Reset position timing
                    self.evolve_context(position_start_time=None)
                else:
                    self.logger.warning("⚠️ Some exit orders failed")

                return success
            
        except Exception as e:
            self.logger.error(f"❌ Error exiting positions: {e}")
            return False
    
    async def _update_active_orders_after_placement(self, placed_orders: Dict[ArbitrageExchangeType, Order]):
        """Update active orders tracking after placing new orders."""
        for exchange_role, order in placed_orders.items():
            self._process_order_fill(exchange_role, order)

        success = all(placed_orders.values())

        return success

    async def _check_order_updates(self):
        """Check order status updates using direct access to exchange orders."""
        for exchange_role in ['spot', 'futures']: # type: ArbitrageExchangeType
            # Get exchange directly
            for order_id, order in self.context.active_orders[exchange_role].copy().items():
                self._process_order_fill(exchange_role, order)

    def _process_order_fill(self, exchange_key: ArbitrageExchangeType, order: Order):
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
                    positions_state=new_positions,
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
                        positions_state=new_positions,
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
        single_order_size_usdt=base_position_size_usdt,
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