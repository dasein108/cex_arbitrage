"""
Spot-Futures Arbitrage Task - TaskManager Compatible

Exchange-agnostic arbitrage strategy that extends BaseTradingTask.
Supports arbitrage between any spot and futures exchanges with integrated profit tracking.

Key Features:
- Automatic profit calculation during position updates
- Real-time profit logging on exit operations
- HFT-optimized performance with sub-millisecond execution
- Comprehensive position and profit analytics
"""

import asyncio
import time
from typing import Optional, Dict, Type, Literal

from trading.tasks.base_arbitrage_task import BaseArbitrageTask
from trading.tasks.base_task import StateHandler
from trading.tasks.arbitrage_task_context import (
    ArbitrageTaskContext,
    TradingParameters,
    ArbitrageOpportunity,
    ValidationResult
)
from exchanges.structs import Symbol, Side, ExchangeEnum, Order
from infrastructure.logging import HFTLoggerInterface, get_logger
from utils import flip_side

# Import existing arbitrage components
from trading.task_manager.exchange_manager import (
    ExchangeManager,
    OrderPlacementParams,
    ExchangeRole,
    ArbitrageExchangeType
)


class SpotFuturesArbitrageTask(BaseArbitrageTask):
    """
    Exchange-agnostic spot-futures arbitrage strategy with integrated profit tracking.
    
    Extends BaseTradingTask to provide full TaskManager integration while preserving
    all arbitrage logic and performance optimizations. Supports any combination of
    spot and futures exchanges.
    
    Profit Tracking Features:
    - Automatic profit calculation during position updates
    - Real-time profit tracking per exchange (spot/futures)
    - Comprehensive profit logging on exit operations
    - HFT-optimized performance with minimal overhead
    """

    name: str = "SpotFuturesArbitrageTask"

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
        # Initialize base arbitrage task with common setup
        super().__init__(logger, context, spot_exchange, futures_exchange, **kwargs)


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


    async def _handle_arbitrage_monitoring(self):
        """Monitor market and manage positions."""
        try:
            await self.exchange_manager.check_connection(True)

            # Check order updates first
            await self._check_order_updates()

            # Check limit orders if enabled
            # if self.context.params.limit_orders_enabled:
            #     await self._check_limit_orders()

            await self._process_imbalance()



            # Check if should exit positions
            if await self._should_exit_positions():
                await self._exit_all_positions()
                return
            # else:
            #     # first try market exit if enabled
            #     if self.context.params.limit_orders_enabled:
            #         await self._place_limit_orders()

            # Look for new opportunities
            if not self.context.positions_state.has_positions:
                opportunity = await self._identify_arbitrage_opportunity()
                if opportunity:
                    self.logger.info(f"💰 Opportunity: {opportunity.spread_pct:.4f}% spread")
                    self.evolve_context(current_opportunity=opportunity)
                    self._transition_arbitrage_state('analyzing')
                # else:
                #     # No opportunity found, place limit orders if enabled
                #     if self.context.params.limit_orders_enabled:
                #         await self._place_limit_orders()

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



    # Unified utility methods

    def _get_entry_cost_pct(self, buy_price: float, sell_price: float) -> float:
        """Calculate entry cost percentage."""
        return ((buy_price - sell_price) / buy_price) * 100

    async def _identify_arbitrage_opportunity(self) -> Optional[ArbitrageOpportunity]:
        """Identify arbitrage opportunities using backtesting logic."""

        spot_ticker = self.spot_ticker
        futures_ticker = self.futures_ticker

        # Calculate entry cost
        entry_cost_pct = self._get_entry_cost_pct(spot_ticker.ask_price, futures_ticker.bid_price)

        if self._increment_debug_counter():
            print(f'Entry cost {entry_cost_pct:.4f}% ({self.spot_exchange.name} -> {self.futures_exchange.name})')

        # Check if profitable (enter when cost is LOW, not high)
        if entry_cost_pct > self.context.params.max_entry_cost_pct:
            return None

        # Calculate max quantity
        max_quantity = self.round_to_contract_size(
            min(
                spot_ticker.ask_quantity,
                futures_ticker.bid_quantity,
                self.context.single_order_size_usdt / spot_ticker.ask_price
            )
        )

        # Ensure meets minimum requirements
        min_required = max(
            self._get_minimum_order_base_quantity('spot'),
            self._get_minimum_order_base_quantity('futures')
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

        # # Calculate P&L using backtesting logic with fees
        # spot_fee = self.context.params.spot_fee
        # fut_fee = self.context.params.fut_fee
        #
        # # Entry costs (what we paid)
        # entry_spot_cost = spot_pos.price * (1 + spot_fee)  # Bought spot with fee
        # entry_fut_receive = futures_pos.price * (1 - fut_fee)  # Sold futures with fee
        #
        # # Exit revenues (what we get)
        # exit_spot_receive = self.spot_ticker.bid_price * (1 - spot_fee)  # Sell spot with fee
        # exit_fut_cost = self.futures_ticker.ask_price * (1 + fut_fee)  # Buy futures with fee
        #
        # # P&L calculation
        # spot_pnl_pts = exit_spot_receive - entry_spot_cost
        # fut_pnl_pts = entry_fut_receive - exit_fut_cost
        # total_pnl_pts = spot_pnl_pts + fut_pnl_pts
        #
        # # P&L percentage
        # capital = entry_spot_cost
        # net_pnl_pct = (total_pnl_pts / capital) * 100

        net_pnl_pct = self._get_pos_net_pnl(spot_pos.price, futures_pos.price,
                                            self.spot_ticker.bid_price, self.futures_ticker.ask_price)

        # Check exit conditions
        exit_now = False
        if self._increment_debug_counter():
            print(f'{self.context.symbol} Exit pnl {net_pnl_pct:.4f}% spread:'
                  f'spot {self.spot_ticker.spread_percentage:.4f}%, futures {self.futures_ticker.spread_percentage:.4f}%'
                  f' SPOT PNL: {(self.spot_ticker.bid_price - spot_pos.price) / spot_pos.price * 100:.4f}%,'
                  f' FUT PNL: {(futures_pos.price - self.futures_ticker.ask_price) / futures_pos.price * 100:.4f}%')

        # 1. PROFIT TARGET: Exit when profitable
        if net_pnl_pct >= self.context.params.min_profit_pct:
            print(f'{self.context.symbol} Exit pnl {net_pnl_pct:.4f}% spread:'
                  f'spot {self.spot_ticker.spread_percentage:.4f}%, futures {self.futures_ticker.spread_percentage:.4f}%'
                  f' SPOT PNL: {(self.spot_ticker.bid_price - spot_pos.price) / spot_pos.price * 100:.4f}%,'
                  f' FUT PNL: {(futures_pos.price - self.futures_ticker.ask_price) / futures_pos.price * 100:.4f}%')

            exit_now = True
            exit_reason = 'profit_target'
            self.logger.info(
                f"💰 Profit target reached: {net_pnl_pct:.4f}% >= {self.context.params.min_profit_pct:.4f}%")

        # 2. TIMEOUT: Position held too long
        elif self.context.position_start_time:
            hours_held = (time.time() - self.context.position_start_time) / 3600
            if hours_held >= self.context.params.max_hours:
                exit_now = True
                exit_reason = 'timeout'
                self.logger.info(
                    f"🕒 Timeout exit: {hours_held:.2f}h >= {self.context.params.max_hours:.2f}h (P&L: {net_pnl_pct:.4f}%)")

        return exit_now

    async def _process_imbalance(self) -> bool:
        # Check positions and imbalances
        if not self.context.positions_state.has_positions:
            return False
        positions = self.context.positions_state.positions
        delta_base = self.context.positions_state.delta
        min_spot_qty = self._get_minimum_order_base_quantity('spot')
        min_futures_qty = self._get_minimum_order_base_quantity('futures')

        if abs(delta_base) < max(min_spot_qty, min_futures_qty):
            return False

        self.logger.info(f'⚠️ Imbalance detected COINS: {delta_base} SPOT: {positions["spot"]}'
                         f' FUT: {positions["futures"]} ')

        # WRONG:
        # spot_imbalance = delta_base >= min_spot_qty
        # force
        # futures_imbalance_less_ = delta_usdt < 0 and abs(delta_usdt) < min_futures_usdt
        place_orders: Dict[ArbitrageExchangeType, OrderPlacementParams] = {}

        # if spot_imbalance:
        #     quantity = self._prepare_order_quantity('spot', delta_base)
        #     place_orders['spot'] = OrderPlacementParams(
        #         side=Side.BUY,
        #         quantity=quantity,
        #         price=self.spot_ticker.ask_price
        #     )
        # else:
        # imbalance < minimal futures quantity, force buy spot to reduce imbalance
        if delta_base < 0 and abs(delta_base) >= min_spot_qty:
            quantity = self._prepare_order_quantity('spot', abs(delta_base))
            place_orders['spot'] = OrderPlacementParams(
                side=Side.BUY,
                quantity=quantity,
                price=self.spot_ticker.ask_price
            )
        elif delta_base > 0 and abs(delta_base) >= min_futures_qty:
            quantity = self._prepare_order_quantity('futures', abs(delta_base))
            place_orders['futures'] = OrderPlacementParams(
                side=Side.SELL,
                quantity=quantity,
                price=self.futures_ticker.bid_price
            )
        else:
            self.logger.info('ℹ️ Imbalance detected but below minimums, no correction placed')

        placed_orders = await self.exchange_manager.place_order_parallel(place_orders)

        success = await self._update_active_orders_after_placement(placed_orders)

        if success:
            self.logger.info(f"✅ Delta correction order placed: {[str(o) for o in placed_orders]}")
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

            spot_min = self._get_minimum_order_base_quantity('spot')
            futures_min = self._get_minimum_order_base_quantity('futures')
            min_base_qty = max(spot_min, futures_min)

            if position_size < min_base_qty:
                self.logger.error(
                    f"❌ Calculated position size {position_size:.6f} < minimum required {min_base_qty:.6f}")
                return False

            self.logger.info(f"Calculated position size: {position_size:.6f} coins, base: {order_coin_size}, "
                             f"oppo: {opportunity.max_quantity} price: {index_price}")

            # Adjust order sizes to meet exchange minimums
            spot_quantity = self._prepare_order_quantity('spot', position_size)
            futures_quantity = self._prepare_order_quantity('futures', position_size)
            adjusted_quantity = max(spot_quantity, futures_quantity)

            # Ensure adjusted quantities are still equal for delta neutrality
            if abs(spot_quantity - futures_quantity) > 1e-6:
                # Use the larger quantity for both to maintain delta neutrality
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
            success = await self._update_active_orders_after_placement(placed_orders)

            execution_time = (time.time() - start_time) * 1000

            self.logger.info(f"⚡ Order execution completed in {execution_time:.1f}ms,"
                             f" placed orders: {placed_orders}")

            if success:
                entry_cost_pct = self._get_entry_cost_pct(opportunity.buy_price, opportunity.sell_price)
                entry_cost_real_pct = self._get_entry_cost_pct(placed_orders['spot'].price,
                                                               placed_orders['futures'].price)
                entry_cost_diff = entry_cost_real_pct - entry_cost_pct
                self.logger.info(f"✅ Both entry orders placed successfully, "
                                 f"oppo price, buy {opportunity.buy_price}, sell {opportunity.sell_price} qty: {adjusted_quantity} "
                                 f"real price, buy {placed_orders['spot']}, sell {placed_orders['futures']} "
                                 f"enter cost % {entry_cost_pct}:.3f real cost % {entry_cost_real_pct}:.3f "
                                 f"diff % {entry_cost_diff:.3f}")

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

    def round_to_contract_size(self, qty: float) -> float:
        """Round price based on exchange tick size."""
        symbol_info = self.exchange_manager.get_exchange('futures').public.symbols_info[self.context.symbol]
        return symbol_info.adjust_to_contract_size(qty)

    def get_tick_size(self, exchange_type: ArbitrageExchangeType) -> float:
        """Get tick size based on exchange type."""
        symbol_info = self.exchange_manager.get_exchange(exchange_type).public.symbols_info[self.context.symbol]
        return symbol_info.tick

    def _get_direction_price(self, direction: Literal['enter', 'exit'], exchange_type: ArbitrageExchangeType) -> \
    Optional[float]:
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
            for exchange_role in ['spot', 'futures']:  # type: ArbitrageExchangeType
                pos = self.context.positions_state.positions[exchange_role]
                if pos.has_position:
                    exit_side = flip_side(pos.side)
                    price = self._get_direction_price('exit', 'spot')

                    # Prepare exit quantity with minimum validations
                    exit_quantity = self._prepare_order_quantity('spot', pos.qty)

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
                    # Log realized profit before clearing positions
                    total_profit = self.context.positions_state.total_realized_profit
                    self.logger.info(f"✅ All exit orders placed successfully - Total profit: ${total_profit:.2f}")
                    # Reset position timing
                    self.evolve_context(position_start_time=None)
                else:
                    self.logger.warning("⚠️ Some exit orders failed")

                return success

        except Exception as e:
            self.logger.error(f"❌ Error exiting positions: {e}")
            return False


    async def _place_limit_orders(self):
        """Place limit orders for profit capture when market opportunity doesn't exist."""
        try:
            # Skip if already have active limit orders
            if self.context.active_limit_orders:
                return

            spot_bid, spot_ask = self.spot_ticker.bid_price, self.spot_ticker.ask_price
            fut_bid, fut_ask = self.futures_ticker.bid_price, self.futures_ticker.ask_price
            
            # Calculate limit profit threshold 
            limit_threshold = self.context.params.min_profit_pct + self.context.params.limit_profit_pct
            
            # Check for enter arbitrage opportunity (buy spot, sell futures)
            if not self.context.positions_state.has_positions:
                # Calculate price for exact limit_profit_pct offset
                # Goal: Find spot price where profit = limit_profit_pct
                # We want: (fut_bid - limit_spot_price) / limit_spot_price * 100 = limit_profit_pct
                # Solving: limit_spot_price = fut_bid / (1 + limit_profit_pct/100)
                # limit_spot_price = fut_bid / (1 + self.context.params.limit_profit_pct / 100)
                
                # Ensure we don't place limit above current ask (would be market order)
                # if limit_spot_price >= spot_ask:
                #     return  # No profitable limit order possible
                #
                limit_spot_price = self.spot_ticker.ask_price - (self.get_tick_size('spot') * 3)  # Place just below current ask
                # Calculate expected profit at this price
                entry_cost_pct = self._get_entry_cost_pct(limit_spot_price, fut_bid)
                # expected_profit_pct = -entry_cost_pct
                
                if self._debug_info_counter <= 1:
                    print(f'{self.context.symbol} Enter limit: target profit {self.context.params.limit_profit_pct:.3f}%, '
                          f'calculated price {limit_spot_price:.6f}, COST: {entry_cost_pct:.4f}%')

                if entry_cost_pct >= limit_threshold:
                    # Place limit buy on spot at calculated price
                    await self._place_single_limit_order('enter', Side.BUY, limit_spot_price)
                    self.logger.info(f"📋 Placing enter limit @{limit_spot_price:.6f}: "
                                   f"expected profit {entry_cost_pct:.4f}% >= threshold {limit_threshold:.4f}%")

            # Check for exit arbitrage opportunity (sell spot, buy futures)
            elif self.context.positions_state.has_positions:
                spot_pos = self.context.positions_state.positions['spot']
                futures_pos = self.context.positions_state.positions['futures']
                
                # Calculate price for exact limit_profit_pct improvement over current market exit
                # Current market exit PnL
                current_market_pnl = self._get_pos_net_pnl(
                    spot_pos.price, futures_pos.price, spot_bid, fut_ask
                )
                
                # Target PnL with limit improvement
                target_pnl = current_market_pnl + self.context.params.limit_profit_pct
                
                # Calculate required spot price for target PnL
                # We need to solve for limit_spot_price where net_pnl = target_pnl
                # For simplicity, add profit percentage to current bid
                # limit_spot_price = spot_bid * (1 + self.context.params.limit_profit_pct / 100)
                limit_spot_price = spot_bid + (self.get_tick_size('spot') * 3)  # Place just below current ask

                # Calculate expected PnL at this price
                net_pnl_pct = self._get_pos_net_pnl(
                    spot_pos.price, futures_pos.price, limit_spot_price, fut_ask
                )

                if self._debug_info_counter <= 1:
                    print(f'{self.context.symbol} Exit limit: target improvement {self.context.params.limit_profit_pct:.3f}%, '
                          f'calculated price {limit_spot_price:.6f}, expected PnL {net_pnl_pct:.4f}%')

                if net_pnl_pct >= limit_threshold:
                    # Place limit sell on spot at calculated price
                    await self._place_single_limit_order('exit', Side.SELL, limit_spot_price)
                    self.logger.info(f"📋 Placing exit limit @{limit_spot_price:.6f}: "
                                   f"expected PnL {net_pnl_pct:.4f}% >= threshold {limit_threshold:.4f}%")
                    
        except Exception as e:
            self.logger.error(f"Error placing limit orders: {e}")

    async def _place_single_limit_order(self, direction: Literal['enter', 'exit'], spot_side: Side, spot_price: float):
        """Place a single limit order on spot. Hedge will be placed when filled."""
        try:
            # Cancel existing limit orders if any
            await self._cancel_limit_orders()
            
            qty_usdt = self.context.single_order_size_usdt
            spot_qty = qty_usdt / spot_price
            
            # Prepare spot limit order using existing pattern
            spot_orders: Dict[ArbitrageExchangeType, OrderPlacementParams] = {
                'spot': OrderPlacementParams(side=spot_side, quantity=spot_qty, price=spot_price, order_type='limit')
            }
            
            # Place only spot limit order
            placed_orders = await self.exchange_manager.place_order_parallel(spot_orders)
            
            if placed_orders.get('spot'):
                # Track limit orders
                self.evolve_context(
                    active_limit_orders={direction: placed_orders['spot'].order_id},
                    limit_order_prices={direction: spot_price}
                )
                
                self.logger.info(f"📋 Placed {direction} limit order: spot {spot_side.name}@{spot_price:.6f}")
            
        except Exception as e:
            self.logger.error(f"Error placing single limit order: {e}")

    async def _check_limit_orders(self):
        """Check limit orders for fills and price updates."""
        try:
            if not self.context.active_limit_orders:
                return
                
            # Check for fills first - if filled, execute immediate hedge
            await self._check_limit_order_fills()
                
            # Then check if prices need updates based on tolerance percentage
            spot_bid, spot_ask = self.spot_ticker.bid_price, self.spot_ticker.ask_price
            fut_bid, fut_ask = self.futures_ticker.bid_price, self.futures_ticker.ask_price
            
            for direction, order_id in self.context.active_limit_orders.items():
                current_limit_price = self.context.limit_order_prices.get(direction)
                if not current_limit_price:
                    continue
                    
                # Calculate new optimal price based on current market
                new_optimal_price = None
                
                if direction == 'enter' and spot_ask and fut_bid:
                    # Recalculate optimal entry price
                    new_optimal_price = fut_bid / (1 + self.context.params.limit_profit_pct / 100)
                    # Ensure it's still below current ask
                    if new_optimal_price >= spot_ask:
                        new_optimal_price = None  # Can't improve
                        
                elif direction == 'exit' and spot_bid and fut_ask:
                    # Recalculate optimal exit price  
                    new_optimal_price = spot_bid * (1 + self.context.params.limit_profit_pct / 100)
                    # Ensure it's still above current bid
                    if new_optimal_price <= spot_bid:
                        new_optimal_price = None  # Can't improve
                
                # Check if price moved beyond tolerance threshold
                if new_optimal_price:
                    price_change_pct = abs(new_optimal_price - current_limit_price) / current_limit_price * 100
                    
                    if price_change_pct >= self.context.params.limit_profit_tolerance_pct:
                        self.logger.info(f"🔄 Price moved {price_change_pct:.3f}% >= tolerance {self.context.params.limit_profit_tolerance_pct:.3f}%, "
                                       f"updating {direction} limit: {current_limit_price:.6f} -> {new_optimal_price:.6f}")
                        await self._update_limit_order(direction, order_id, new_optimal_price)
                    
        except Exception as e:
            self.logger.error(f"Error checking limit orders: {e}")

    async def _check_limit_order_fills(self):
        """Check if limit orders are filled and execute immediate delta hedge."""
        try:
            for direction, order_id in list(self.context.active_limit_orders.items()):
                # Get order status from exchange
                exchange = self.exchange_manager.get_exchange('spot')
                if not exchange:
                    continue
                    
                # Check if order is filled by looking at active orders
                limit_order =  exchange.private.get_order(order_id)
                
                if not limit_order:
                    # Order not found - likely filled or cancelled
                    await self._handle_limit_order_fill('spot', direction, order_id)
                    
        except Exception as e:
            self.logger.error(f"Error checking limit order fills: {e}")

    async def _handle_limit_order_fill(self, exchange_key: ArbitrageExchangeType,
                                       direction: Literal['enter', 'exit'], order_id: str):
        """Handle limit order fill with immediate delta hedge."""
        try:
            self.logger.info(f"🎯 Limit order filled: {exchange_key} {direction} {order_id}")
            
            # Remove from tracking
            new_limit_orders = self.context.active_limit_orders.copy()
            new_limit_prices = self.context.limit_order_prices.copy()
            del new_limit_orders[direction]
            del new_limit_prices[direction]
            
            self.evolve_context(
                active_limit_orders=new_limit_orders,
                limit_order_prices=new_limit_prices
            )
            
            # Execute immediate delta hedge on futures
            fut_side = Side.SELL if direction == 'enter' else Side.BUY
            qty_usdt = self.context.single_order_size_usdt
            fut_price = self.futures_ticker.ask_price if fut_side == Side.BUY else self.futures_ticker.bid_price
            fut_qty = qty_usdt / fut_price
            
            # Place futures market order for immediate hedge
            fut_orders: Dict[ArbitrageExchangeType, OrderPlacementParams] = {
                'futures': OrderPlacementParams(side=fut_side, quantity=fut_qty, price=fut_price, order_type='market')
            }
            
            placed_orders = await self.exchange_manager.place_order_parallel(fut_orders)
            
            if placed_orders.get('futures'):
                self.logger.info(f"⚡ Immediate delta hedge: futures {fut_side.name} {fut_qty}@{fut_price:.6f}")
                # Update tracking as normal position
                await self._update_active_orders_after_placement(placed_orders)
            else:
                self.logger.error(f"❌ Failed to place delta hedge for {direction}")
                
        except Exception as e:
            self.logger.error(f"Error handling limit order fill: {e}")

    async def _update_limit_order(self, direction: Literal['enter', 'exit'], order_id: str, new_price: float):
        """Update limit order price."""
        try:
            # Cancel old order using exchange directly
            exchange = self.exchange_manager.get_exchange('spot')
            if exchange:
                o = await exchange.private.cancel_order(self.context.symbol, order_id)
                self._process_order_fill('spot', o)
                if o.filled_quantity > 0:
                    self.logger.info(f"⚠️ Partial fill detected when cancelling limit order {order_id}, processed fill.")
                    return
            
            # Place new order
            spot_side = Side.BUY if direction == 'enter' else Side.SELL
            qty_usdt = self.context.single_order_size_usdt  
            spot_qty = qty_usdt / new_price
            
            spot_orders: Dict[ArbitrageExchangeType, OrderPlacementParams] = {
                'spot': OrderPlacementParams(side=spot_side, quantity=spot_qty, price=new_price, order_type='limit')
            }
            
            placed_orders = await self.exchange_manager.place_order_parallel(spot_orders)
            
            if placed_orders.get('spot'):
                # Update tracking
                new_limit_orders = self.context.active_limit_orders.copy()
                new_limit_orders[direction] = placed_orders['spot'].order_id
                new_limit_prices = self.context.limit_order_prices.copy()
                new_limit_prices[direction] = new_price
                
                self.evolve_context(
                    active_limit_orders=new_limit_orders,
                    limit_order_prices=new_limit_prices
                )
                
                self.logger.info(f"🔄 Updated {direction} limit order: {new_price:.6f}")
            
        except Exception as e:
            self.logger.error(f"Error updating limit order: {e}")

    async def _cancel_limit_orders(self):
        """Cancel all active limit orders."""
        try:
            exchange = self.exchange_manager.get_exchange('spot')
            if not exchange:
                return

            for direction, order_id in self.context.active_limit_orders.items():
                o = await exchange.private.cancel_order(self.context.symbol, order_id)
                self._process_order_fill('spot', o)

            self.evolve_context(
                active_limit_orders={},
                limit_order_prices={}
            )
            
        except Exception as e:
            self.logger.error(f"Error cancelling limit orders: {e}")

    def _get_pos_net_pnl(self, entry_spot_price: float, entry_fut_price: float,
                         curr_spot_price: float, curr_fut_price: float) -> Optional[float]:
        # Calculate P&L using backtesting logic with fees
        spot_fee = self.context.params.spot_fee
        fut_fee = self.context.params.fut_fee

        # Entry costs (what we paid)
        entry_spot_cost = entry_spot_price * (1 + spot_fee)  # Bought spot with fee
        entry_fut_receive = entry_fut_price * (1 - fut_fee)  # Sold futures with fee

        # Exit revenues (what we get)
        exit_spot_receive = curr_spot_price * (1 - spot_fee)  # Sell spot with fee
        exit_fut_cost = curr_fut_price * (1 + fut_fee)  # Buy futures with fee

        # P&L calculation
        spot_pnl_pts = exit_spot_receive - entry_spot_cost
        fut_pnl_pts = entry_fut_receive - exit_fut_cost
        total_pnl_pts = spot_pnl_pts + fut_pnl_pts

        # P&L percentage
        capital = entry_spot_cost
        net_pnl_pct = (total_pnl_pts / capital) * 100

        return net_pnl_pct

    async def cleanup(self):
        """Clean up strategy resources."""
        # Cancel limit orders and rebalance if needed
        if self.context.params.limit_orders_enabled:
            await self._cancel_limit_orders()
            # do not exit on restart
            # if self.context.positions_state.has_positions:
            #     await self._exit_all_positions()  # Rebalance to delta neutral
            #
        # Call base cleanup
        await super().cleanup()


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
        max_hours=max_hours,
        limit_orders_enabled=True,
        limit_profit_pct=0.1,
        limit_profit_tolerance_pct=0.1
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
