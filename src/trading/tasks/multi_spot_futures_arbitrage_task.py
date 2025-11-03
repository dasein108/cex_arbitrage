"""
Multi-Spot Futures Arbitrage Task - TaskManager Compatible

Exchange-agnostic arbitrage strategy that extends SpotFuturesArbitrageTask to support
multiple spot exchanges with intelligent position migration while maintaining single futures hedge.

Key Features:
- Multiple spot exchanges + single futures exchange architecture
- Two operation modes: traditional (exit both) and spot switching (migrate positions)
- Intelligent opportunity scanning across all spot exchanges
- Delta neutrality validation with emergency rebalance
- Integrated profit tracking with multi-spot analytics
- Real-time profit logging for multi-spot exit operations
- HFT performance compliance (<50ms execution targets)
"""

import asyncio
import time
from typing import Optional, Dict, List, Literal

from trading.tasks.spot_futures_arbitrage_task import SpotFuturesArbitrageTask
from trading.tasks.arbitrage_task_context import (
    ArbitrageTaskContext,
    TradingParameters,
    SpotOpportunity,
    SpotSwitchOpportunity,
    ValidationResult,
    MultiSpotPositionState
)
from exchanges.structs import Symbol, Side, ExchangeEnum, Order
from infrastructure.logging import HFTLoggerInterface, get_logger
from utils.exchange_utils import is_order_done
from utils.exchange_utils import flip_side

# Import existing arbitrage components
from trading.task_manager.exchange_manager import (
    ExchangeManager, 
    OrderPlacementParams, 
    ExchangeRole, 
    ArbitrageExchangeType
)

# Import new position management
from trading.strategies.implementations.base_strategy.position_manager import PositionManager
from trading.strategies.implementations.base_strategy.position_data import PositionData


class MultiSpotFuturesArbitrageTask(SpotFuturesArbitrageTask):
    """
    Multi-spot futures arbitrage strategy with intelligent position migration and profit tracking.
    
    Extends SpotFuturesArbitrageTask to support multiple spot exchanges with:
    - Best spot selection for initial entry
    - Spot switching while maintaining futures hedge
    - Two operation modes: traditional exit vs dynamic spot switching
    - Enhanced risk management with delta neutrality validation
    - Comprehensive profit tracking across multiple spot exchanges
    - Real-time profit analytics and logging for multi-spot operations
    """
    
    name: str = "MultiSpotFuturesArbitrageTask"
    
    def __init__(self,
                 logger: HFTLoggerInterface,
                 context: ArbitrageTaskContext,
                 spot_exchanges: List[ExchangeEnum],
                 futures_exchange: ExchangeEnum,
                 operation_mode: Literal['traditional', 'spot_switching'] = 'traditional',
                 **kwargs):
        """Initialize multi-spot arbitrage strategy."""
        
        # Enhance context with multi-spot configuration
        context = context.evolve(
            spot_exchanges=spot_exchanges,
            futures_exchange=futures_exchange,
            operation_mode=operation_mode,
            multi_spot_positions=MultiSpotPositionState()
        )
        
        # Initialize parent with first spot exchange for compatibility
        super().__init__(logger, context, spot_exchanges[0], futures_exchange, **kwargs)
        
        # Store multi-spot configuration
        self.spot_exchanges = spot_exchanges
        self.operation_mode = operation_mode
        self.spot_exchange_keys = [f"{ex.name.lower()}_spot" for ex in spot_exchanges]
        
        # Initialize position manager
        self.position_manager = PositionManager(self.logger, self._save_context_callback)
        
        self.logger.info(f"✅ {self.name} initialized: {len(spot_exchanges)} spots + {futures_exchange.name} futures (mode: {operation_mode})")
        
        self._build_multi_spot_tag()

    def _build_multi_spot_tag(self) -> None:
        """Build logging tag with multi-spot specific fields."""
        spot_names = "_".join([ex.name for ex in self.spot_exchanges])
        self._tag = f'{self.name}_{self.context.symbol}_{spot_names}_{self.futures_exchange.name}'

    def _save_context_callback(self):
        """Callback for position manager to save context after position updates."""
        # This method can be used to trigger context saves when positions change
        # For now, it's a placeholder for potential future context synchronization
        pass

    @property
    def futures_ticker(self):
        """Get futures ticker (unchanged from parent)."""
        return self.position_manager.get_book_ticker('futures')

    def get_spot_ticker(self, exchange_key: str):
        """Get spot ticker for specific exchange."""
        return self.position_manager.get_book_ticker(exchange_key)

    async def _initialize_exchange_manager(self) -> bool:
        """Initialize exchange manager with multiple spot exchanges + single futures."""
        try:
            exchange_roles: Dict[str, ExchangeRole] = {}
            
            # Add all spot exchanges with unique keys
            for i, spot_exchange in enumerate(self.spot_exchanges):
                role_key = f"{spot_exchange.name.lower()}_spot"
                exchange_roles[role_key] = ExchangeRole(
                    exchange_enum=spot_exchange,
                    role='spot_candidate',
                    max_position_size=self.context.single_order_size_usdt,
                    priority=i
                )
            
            # Add single futures exchange
            exchange_roles['futures'] = ExchangeRole(
                exchange_enum=self.futures_exchange,
                role='futures_hedge',
                max_position_size=self.context.single_order_size_usdt,
                priority=100
            )
            
            # Initialize exchange manager
            self.exchange_manager = ExchangeManager(self.context.symbol, exchange_roles, self.logger)
            success = await self.exchange_manager.initialize()
            
            if success:
                # Get minimum quote quantities for all exchanges
                self.min_quote_quantity = {}
                for exchange_key in self.spot_exchange_keys + ['futures']:
                    exchange = self.exchange_manager.get_exchange(exchange_key)
                    symbol_info = exchange.public.symbols_info.get(self.context.symbol)
                    self.min_quote_quantity[exchange_key] = symbol_info.min_quote_quantity

                # Initialize position manager with exchange connections
                await self._initialize_position_manager()

                self.logger.info(f"✅ Multi-spot exchange manager initialized: {len(self.spot_exchanges)} spots + 1 futures")
                return True
            else:
                self.logger.error("❌ Multi-spot exchange manager initialization failed")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Exception during multi-spot exchange manager initialization: {e}")
            return False

    async def _initialize_position_manager(self) -> bool:
        """Initialize position manager with position data and exchanges."""
        try:
            # Create position data for each spot exchange
            for exchange_key in self.spot_exchange_keys:
                position_data = PositionData(symbol=str(self.context.symbol))
                exchange = self.exchange_manager.get_exchange(exchange_key)
                self.position_manager.add_position(exchange_key, position_data, exchange)
            
            # Create futures position data
            futures_position_data = PositionData(symbol=str(self.context.symbol))
            futures_exchange = self.exchange_manager.get_exchange('futures')
            self.position_manager.add_position('futures', futures_position_data, futures_exchange)
            
            # Initialize all positions
            success = await self.position_manager.initialize_all()
            
            if success:
                self.logger.info(f"✅ Position manager initialized with {len(self.spot_exchange_keys)} spots + 1 futures")
            else:
                self.logger.error("❌ Position manager initialization failed")
                
            return success
            
        except Exception as e:
            self.logger.error(f"❌ Exception during position manager initialization: {e}")
            return False

    async def _handle_arbitrage_monitoring(self):
        """Enhanced monitoring with operation mode logic."""
        try:
            # Check order updates first
            await self._check_order_updates()

            # Process imbalance if needed
            await self._process_imbalance()

            # Delegate to operation mode handlers
            if self.operation_mode == 'traditional':
                await self._handle_traditional_mode()
            elif self.operation_mode == 'spot_switching':
                await self._handle_spot_switching_mode()
            else:
                self.logger.error(f"❌ Unknown operation mode: {self.operation_mode}")
                self._transition_arbitrage_state('error_recovery')
        
        except Exception as e:
            self.logger.error(f"Multi-spot monitoring failed: {e}")
            self._transition_arbitrage_state('error_recovery')

    async def _handle_traditional_mode(self):
        """Traditional mode: Find best spot entry, trade once, exit both."""
        if not self._has_active_positions():
            # Scan all spots for best opportunity
            best_opportunity = await self._find_best_spot_entry()
            if best_opportunity:
                self.logger.info(f"💰 Best opportunity: {best_opportunity.exchange_key} at {best_opportunity.cost_pct:.4f}%")
                await self._enter_spot_futures_position(best_opportunity)
        else:
            # Standard exit logic
            if await self._should_exit_positions():
                await self._exit_all_positions()

    async def _handle_spot_switching_mode(self):
        """Spot switching mode: Dynamic spot switching while maintaining futures hedge."""
        if not self._has_active_positions():
            # Initial entry same as traditional
            await self._handle_traditional_mode()
        else:
            # Check for spot switching opportunity
            if self.context.spot_switch_enabled:
                switch_opportunity = await self._evaluate_spot_switch()
                if switch_opportunity:
                    self.logger.info(f"🔄 Spot switch opportunity: {switch_opportunity.current_exchange_key} → {switch_opportunity.target_exchange_key} ({switch_opportunity.profit_pct:.4f}%)")
                    await self._execute_spot_switch(switch_opportunity)
                    return
            
            # Check for exit conditions
            if await self._should_exit_positions():
                await self._exit_all_positions()

    async def _find_best_spot_entry(self) -> Optional[SpotOpportunity]:
        """Scan all spot exchanges for best entry opportunity."""
        opportunities = []
        futures_ticker = self.futures_ticker
        
        if not futures_ticker:
            return None
        
        for exchange_key in self.spot_exchange_keys:
            spot_ticker = self.get_spot_ticker(exchange_key)
            if not spot_ticker:
                continue
                
            # Calculate entry cost vs futures
            entry_cost_pct = self._get_entry_cost_pct(spot_ticker.ask_price, futures_ticker.bid_price)
            
            if self._debug_info_counter % 1000 == 0:
                print(f'Entry cost {entry_cost_pct:.4f}% ({exchange_key} -> {self.futures_exchange.name})')
            
            self._debug_info_counter += 1
            
            if entry_cost_pct < self.context.params.max_entry_cost_pct:
                # Get exchange enum for this key
                exchange_enum = next(ex for ex in self.spot_exchanges if f"{ex.name.lower()}_spot" == exchange_key)
                
                opportunities.append(SpotOpportunity(
                    exchange_key=exchange_key,
                    exchange_enum=exchange_enum,
                    entry_price=spot_ticker.ask_price,
                    cost_pct=entry_cost_pct,
                    max_quantity=min(
                        spot_ticker.ask_quantity,
                        futures_ticker.bid_quantity,
                        self.context.single_order_size_usdt / spot_ticker.ask_price
                    )
                ))
        
        if not opportunities:
            return None
        
        # Return best opportunity (lowest cost)
        return min(opportunities, key=lambda x: x.cost_pct)

    async def _evaluate_spot_switch(self) -> Optional[SpotSwitchOpportunity]:
        """Evaluate if switching to different spot exchange is profitable."""
        if not self.context.multi_spot_positions or not self.context.multi_spot_positions.active_spot_exchange:
            return None
        
        current_exchange_key = self.context.multi_spot_positions.active_spot_exchange
        current_spot_ticker = self.get_spot_ticker(current_exchange_key)
        
        if not current_spot_ticker:
            return None
        
        best_switch = None
        current_exit_price = current_spot_ticker.bid_price
        
        # Check all other spot exchanges
        for target_exchange_key in self.spot_exchange_keys:
            if target_exchange_key == current_exchange_key:
                continue
                
            target_spot_ticker = self.get_spot_ticker(target_exchange_key)
            if not target_spot_ticker:
                continue
            
            target_entry_price = target_spot_ticker.ask_price
            
            # Calculate profit from switching: sell current @ bid, buy target @ ask
            profit_per_unit = current_exit_price - target_entry_price
            profit_pct = (profit_per_unit / current_exit_price) * 100
            
            if profit_pct >= self.context.min_switch_profit_pct:
                # Get exchange enum for target
                target_exchange_enum = next(ex for ex in self.spot_exchanges if f"{ex.name.lower()}_spot" == target_exchange_key)
                
                switch_opportunity = SpotSwitchOpportunity(
                    current_exchange_key=current_exchange_key,
                    target_exchange_key=target_exchange_key,
                    target_exchange_enum=target_exchange_enum,
                    current_exit_price=current_exit_price,
                    target_entry_price=target_entry_price,
                    profit_pct=profit_pct,
                    max_quantity=min(
                        current_spot_ticker.bid_quantity,
                        target_spot_ticker.ask_quantity,
                        self.context.multi_spot_positions.active_spot_position.qty
                    )
                )
                
                if not best_switch or switch_opportunity.profit_pct > best_switch.profit_pct:
                    best_switch = switch_opportunity
        
        return best_switch

    async def _enter_spot_futures_position(self, opportunity: SpotOpportunity) -> bool:
        """Enter position on selected spot exchange + futures hedge."""
        try:
            # Calculate position size
            index_price = opportunity.entry_price
            order_coin_size = self.context.single_order_size_usdt / index_price
            position_size = min(order_coin_size, opportunity.max_quantity)
            
            # Validate minimum requirements
            spot_min = self._get_minimum_order_base_quantity(opportunity.exchange_key, opportunity.entry_price)
            futures_min = self._get_minimum_order_base_quantity('futures', self.futures_ticker.bid_price)
            min_coin_required = max(spot_min, futures_min)
            
            if position_size < min_coin_required:
                self.logger.error(f"❌ Position size {position_size:.6f} < minimum required {min_coin_required:.6f}")
                return False
            
            # Prepare order quantities
            spot_quantity = self._prepare_order_quantity_for_exchange(opportunity.exchange_key, position_size, opportunity.entry_price)
            futures_quantity = self._prepare_order_quantity_for_exchange('futures', position_size, self.futures_ticker.bid_price)
            
            # Ensure delta neutrality
            if abs(spot_quantity - futures_quantity) > 1e-6:
                adjusted_quantity = max(spot_quantity, futures_quantity)
                self.logger.info(f"⚖️ Adjusting both quantities to {adjusted_quantity:.6f} for delta neutrality")
                spot_quantity = futures_quantity = adjusted_quantity
            
            # Execute orders in parallel
            enter_orders = {
                opportunity.exchange_key: OrderPlacementParams(side=Side.BUY, quantity=spot_quantity, price=opportunity.entry_price),
                'futures': OrderPlacementParams(side=Side.SELL, quantity=futures_quantity, price=self.futures_ticker.bid_price)
            }
            
            self.logger.info(f"🚀 Executing multi-spot arbitrage: {opportunity.exchange_key} + futures")
            start_time = time.time()
            
            placed_orders = await self.exchange_manager.place_order_parallel(enter_orders)
            success = await self._update_multi_spot_orders_after_placement(placed_orders, opportunity.exchange_key)
            
            execution_time = (time.time() - start_time) * 1000
            self.logger.info(f"⚡ Multi-spot execution completed in {execution_time:.1f}ms")
            
            if success:
                # Update multi-spot position state
                self._update_active_spot_exchange(opportunity.exchange_key)
                
                # Track position start time
                if self.context.position_start_time is None:
                    self.evolve_context(position_start_time=time.time())
                
                position_usdt = max(spot_quantity, futures_quantity) * opportunity.entry_price
                if position_usdt:
                    self.evolve_context(
                        total_volume_usdt=self.context.total_volume_usdt + position_usdt
                    )
            else:
                # Cancel any successful orders
                await self.exchange_manager.cancel_all_orders()
            
            return success
            
        except Exception as e:
            self.logger.error(f"Multi-spot arbitrage execution error: {e}")
            await self.exchange_manager.cancel_all_orders()
            return False

    async def _execute_spot_switch(self, opportunity: SpotSwitchOpportunity) -> bool:
        """Execute spot switching while maintaining futures hedge."""
        if not opportunity.is_fresh():
            self.logger.warning("⚠️ Spot switch opportunity is no longer fresh")
            return False
        
        try:
            # Validate delta neutrality before switch
            if not self._validate_delta_neutrality():
                self.logger.error("❌ Cannot switch: delta not neutral before operation")
                return False
            
            current_position = self.context.multi_spot_positions.active_spot_position
            if not current_position or not current_position.has_position:
                self.logger.error("❌ No active spot position to switch")
                return False
            
            # Calculate switch quantities
            switch_quantity = min(current_position.qty, opportunity.max_quantity)
            
            # Prepare exit and entry orders
            switch_orders = {
                opportunity.current_exchange_key: OrderPlacementParams(
                    side=flip_side(current_position.side),
                    quantity=switch_quantity,
                    price=opportunity.current_exit_price
                ),
                opportunity.target_exchange_key: OrderPlacementParams(
                    side=current_position.side,
                    quantity=switch_quantity,
                    price=opportunity.target_entry_price
                )
            }
            
            self.logger.info(f"🔄 Executing spot switch: {opportunity.current_exchange_key} → {opportunity.target_exchange_key}")
            start_time = time.time()
            
            # Execute both orders simultaneously
            placed_orders = await self.exchange_manager.place_order_parallel(switch_orders)
            success = all(placed_orders.values())
            
            execution_time = (time.time() - start_time) * 1000
            
            if success:
                # Update multi-spot position tracking
                await self._process_spot_switch_orders(placed_orders, opportunity)
                
                self.logger.info(f"✅ Spot switch completed in {execution_time:.1f}ms: {opportunity.current_exchange_key} → {opportunity.target_exchange_key}")
                
                # Verify delta neutrality after switch
                if not self._validate_delta_neutrality():
                    self.logger.warning("⚠️ Delta neutrality lost after spot switch - triggering emergency rebalance")
                    await self._emergency_rebalance()
                
                return True
            else:
                self.logger.error(f"❌ Spot switch failed in {execution_time:.1f}ms")
                # Cancel any successful orders
                await self.exchange_manager.cancel_all_orders()
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Spot switch execution error: {e}")
            await self.exchange_manager.cancel_all_orders()
            await self._emergency_rebalance()
            return False

    def _validate_delta_neutrality(self, tolerance_pct: float = 0.1) -> bool:
        """Validate that total positions maintain delta neutrality."""
        if not self.context.multi_spot_positions:
            return True
        
        delta = self.context.multi_spot_positions.delta
        total_spot_qty = self.context.multi_spot_positions.total_spot_qty
        
        if total_spot_qty == 0:
            return True
        
        delta_pct = abs(delta / total_spot_qty) * 100
        is_neutral = delta_pct <= tolerance_pct
        
        if not is_neutral:
            self.logger.warning(f"⚠️ Delta neutrality violated: {delta:.6f} delta ({delta_pct:.3f}% of position)")
        
        return is_neutral

    async def _emergency_rebalance(self):
        """Emergency delta neutrality restoration."""
        try:
            if not self.context.multi_spot_positions:
                return
            
            delta = self.context.multi_spot_positions.delta
            delta_usdt = self.context.multi_spot_positions.delta_usdt
            
            if abs(delta_usdt) < 5.0:  # Minimum threshold for rebalance
                return
            
            self.logger.info(f"🚨 Emergency rebalance: delta={delta:.6f}, delta_usdt={delta_usdt:.2f}")
            
            # Determine corrective action
            if delta > 0:  # Excess spot, need more futures short
                corrective_order = OrderPlacementParams(
                    side=Side.SELL,
                    quantity=abs(delta),
                    price=self.futures_ticker.bid_price
                )
                placed_orders = await self.exchange_manager.place_order_parallel({'futures': corrective_order})
            else:  # Excess futures, need to reduce futures or add spot
                corrective_order = OrderPlacementParams(
                    side=Side.BUY,
                    quantity=abs(delta),
                    price=self.futures_ticker.ask_price
                )
                placed_orders = await self.exchange_manager.place_order_parallel({'futures': corrective_order})
            
            if all(placed_orders.values()):
                self.logger.info("✅ Emergency rebalance completed")
            else:
                self.logger.error("❌ Emergency rebalance failed")
                
        except Exception as e:
            self.logger.error(f"❌ Emergency rebalance error: {e}")

    async def _exit_all_positions(self):
        """Override parent method to support multi-spot profit logging."""
        try:
            # Use multi-spot position tracking if available
            if self.context.multi_spot_positions and self.context.multi_spot_positions.has_positions:
                # Build exit orders for multi-spot positions
                exit_orders = {}
                
                # Exit active spot position
                if (self.context.multi_spot_positions.active_spot_position and 
                    self.context.multi_spot_positions.active_spot_position.has_position):
                    
                    active_exchange = self.context.multi_spot_positions.active_spot_exchange
                    spot_pos = self.context.multi_spot_positions.active_spot_position
                    
                    spot_ticker = self.get_spot_ticker(active_exchange)
                    if spot_ticker:
                        exit_side = flip_side(spot_pos.side)
                        price = spot_ticker.bid_price if exit_side == Side.SELL else spot_ticker.ask_price
                        
                        exit_orders[active_exchange] = OrderPlacementParams(
                            side=exit_side,
                            quantity=spot_pos.qty,
                            price=price
                        )
                
                # Exit futures position
                if (self.context.multi_spot_positions.futures_position and 
                    self.context.multi_spot_positions.futures_position.has_position):
                    
                    futures_pos = self.context.multi_spot_positions.futures_position
                    futures_ticker = self.futures_ticker
                    
                    if futures_ticker:
                        exit_side = flip_side(futures_pos.side)
                        price = futures_ticker.bid_price if exit_side == Side.SELL else futures_ticker.ask_price
                        
                        exit_orders['futures'] = OrderPlacementParams(
                            side=exit_side,
                            quantity=futures_pos.qty,
                            price=price
                        )
                
                # Place exit orders
                if exit_orders:
                    placed_orders = await self.exchange_manager.place_order_parallel(exit_orders)
                    
                    # Update position tracking
                    success = await self._update_multi_spot_orders_after_placement(
                        placed_orders, self.context.multi_spot_positions.active_spot_exchange
                    )
                    
                    if success:
                        # Log realized profit from multi-spot positions
                        total_profit = self.context.multi_spot_positions.total_realized_profit
                        self.logger.info(f"✅ All multi-spot exit orders placed successfully - Total profit: ${total_profit:.2f}")
                        # Reset position timing
                        self.evolve_context(position_start_time=None)
                    else:
                        self.logger.warning("⚠️ Some multi-spot exit orders failed")
                    
                    return success
            else:
                # Fall back to parent implementation for traditional positions
                return await super()._exit_all_positions()
                
        except Exception as e:
            self.logger.error(f"❌ Error exiting multi-spot positions: {e}")
            return False

    def _has_active_positions(self) -> bool:
        """Check if strategy has active positions using position manager."""
        # Check if any position in the position manager has a position
        for key in self.spot_exchange_keys + ['futures']:
            position = self.position_manager.get_position(key)
            if position and position.has_position:
                return True
        
        # Fallback to context-based check if position manager positions are not set
        if self.context.multi_spot_positions:
            return self.context.multi_spot_positions.has_positions
        return self.context.positions_state.has_positions

    def _update_active_spot_exchange(self, exchange_key: str):
        """Update the active spot exchange in context."""
        if self.context.multi_spot_positions:
            updated_positions = msgspec.structs.replace(
                self.context.multi_spot_positions,
                active_spot_exchange=exchange_key
            )
            self.evolve_context(multi_spot_positions=updated_positions)

    def _prepare_order_quantity_for_exchange(self, exchange_key: str, base_quantity: float, price: float) -> float:
        """Prepare order quantity for specific exchange with all adjustments."""
        # Validate with exchange minimums
        quantity = self._validate_order_size_for_exchange(exchange_key, base_quantity, price)

        # TODO: refactoring, check
        # Round to contracts if futures
        # exchange = self.exchange_manager.get_exchange(exchange_key)
        # if exchange.is_futures:
        #     quantity = exchange.round_base_to_contracts(self.context.symbol, quantity)

        return quantity

    def _validate_order_size_for_exchange(self, exchange_key: str, quantity: float, price: float) -> float:
        """Validate and adjust order size for specific exchange."""
        min_quote_qty = self.min_quote_quantity.get(exchange_key, 0)
        
        if quantity * price < min_quote_qty:
            adjusted_quantity = min_quote_qty / price + 0.001
            self.logger.info(f"📏 Adjusting {exchange_key} order size: {quantity:.6f} → {adjusted_quantity:.6f}")
            return adjusted_quantity
        
        return quantity

    def _get_minimum_order_base_quantity(self, exchange_key: str, current_price: Optional[float] = None) -> float:
        """Get minimum order quantity for specific exchange."""
        if not current_price:
            if exchange_key == 'futures':
                current_price = self.futures_ticker.bid_price
            else:
                current_price = self.get_spot_ticker(exchange_key).ask_price
        
        min_quote_qty = self.min_quote_quantity.get(exchange_key, 0)
        return min_quote_qty / current_price

    async def _update_multi_spot_orders_after_placement(self, placed_orders: Dict[str, Order], active_spot_key: str) -> bool:
        """Update order tracking after multi-spot order placement."""
        success = True
        
        for exchange_key, order in placed_orders.items():
            if order:
                if exchange_key == 'futures':
                    self._process_futures_order_fill(order)
                else:
                    self._process_spot_order_fill(exchange_key, order)
            else:
                success = False
                
        return success

    async def _process_spot_switch_orders(self, placed_orders: Dict[str, Order], opportunity: SpotSwitchOpportunity):
        """Process orders from spot switching operation."""
        for exchange_key, order in placed_orders.items():
            if order:
                if exchange_key == opportunity.current_exchange_key:
                    # Exiting current spot position
                    self._process_spot_order_fill(exchange_key, order)
                elif exchange_key == opportunity.target_exchange_key:
                    # Entering new spot position
                    self._process_spot_order_fill(exchange_key, order)
                    # Update active spot exchange
                    self._update_active_spot_exchange(exchange_key)

    def _process_spot_order_fill(self, exchange_key: str, order: Order):
        """Process spot order fill using position manager."""
        try:
            # Update position through position manager
            pos_change = self.position_manager.update_position_with_order(exchange_key, order)
            
            # Update multi-spot context if available
            if self.context.multi_spot_positions:
                updated_positions = self.context.multi_spot_positions.update_active_spot_position(
                    exchange_key, order.filled_quantity, order.price, order.side
                )
                self.evolve_context(multi_spot_positions=updated_positions)
            
            self.logger.info(f"📝 Spot order processed: {order} on {exchange_key}")
            
        except Exception as e:
            self.logger.error(f"Error processing spot order fill: {e}")

    def _process_futures_order_fill(self, order: Order):
        """Process futures order fill using position manager."""
        try:
            # Update position through position manager
            pos_change = self.position_manager.update_position_with_order('futures', order)
            
            # Update multi-spot context if available
            if self.context.multi_spot_positions:
                updated_positions = self.context.multi_spot_positions.update_futures_position(
                    order.filled_quantity, order.price, order.side
                )
                self.evolve_context(multi_spot_positions=updated_positions)
            
            self.logger.info(f"📝 Futures order processed: {order}")
            
        except Exception as e:
            self.logger.error(f"Error processing futures order fill: {e}")

    async def _should_exit_positions(self) -> bool:
        """Enhanced exit logic for multi-spot positions."""
        if not self._has_active_positions():
            return False
        
        # Use multi-spot position if available, otherwise fall back to legacy
        if self.context.multi_spot_positions and self.context.multi_spot_positions.has_positions:
            active_spot_pos = self.context.multi_spot_positions.active_spot_position
            futures_pos = self.context.multi_spot_positions.futures_position
            
            if not active_spot_pos or not futures_pos:
                return False
            
            # Calculate P&L using spot position prices
            net_pnl_pct = self._get_pos_net_pnl(
                active_spot_pos.price, futures_pos.price,
                self.get_spot_ticker(self.context.multi_spot_positions.active_spot_exchange).bid_price,
                self.futures_ticker.ask_price
            )
        else:
            # Fall back to legacy position tracking
            return await super()._should_exit_positions()
        
        # Standard exit conditions
        exit_now = False
        
        if self._debug_info_counter % 1000 == 0:
            # Get current spot ticker for spread info
            spot_ticker = self.get_spot_ticker(self.context.multi_spot_positions.active_spot_exchange)
            print(f'Multi-spot exit pnl {net_pnl_pct:.4f}% spot {spot_ticker.spread_percentage:.4f}%, futures {self.futures_ticker.spread_percentage:.4f}%')
            self._debug_info_counter = 0
        
        self._debug_info_counter += 1
        
        # Profit target
        if net_pnl_pct >= self.context.params.min_profit_pct:
            exit_now = True
            self.logger.info(f"💰 Profit target reached: {net_pnl_pct:.4f}% >= {self.context.params.min_profit_pct:.4f}%")
        
        # Timeout
        elif self.context.position_start_time:
            hours_held = (time.time() - self.context.position_start_time) / 3600
            if hours_held >= self.context.params.max_hours:
                exit_now = True
                self.logger.info(f"🕒 Timeout exit: {hours_held:.2f}h >= {self.context.params.max_hours:.2f}h (P&L: {net_pnl_pct:.4f}%)")
        
        return exit_now


# Factory function for multi-spot arbitrage task
async def create_multi_spot_futures_arbitrage_task(
    symbol: Symbol,
    spot_exchanges: List[ExchangeEnum],
    futures_exchange: ExchangeEnum,
    operation_mode: Literal['traditional', 'spot_switching'] = 'traditional',
    base_position_size_usdt: float = 100.0,
    max_entry_cost_pct: float = 0.5,
    min_profit_pct: float = 0.1,
    max_hours: float = 6.0,
    min_switch_profit_pct: float = 0.05,
    logger: Optional[HFTLoggerInterface] = None
) -> MultiSpotFuturesArbitrageTask:
    """Create and initialize multi-spot futures arbitrage task."""
    
    if logger is None:
        spot_names = "_".join([ex.name for ex in spot_exchanges])
        logger = get_logger(f'multi_spot_arbitrage.{symbol}.{spot_names}_{futures_exchange.name}')
    
    params = TradingParameters(
        max_entry_cost_pct=max_entry_cost_pct,
        min_profit_pct=min_profit_pct,
        max_hours=max_hours
    )
    
    context = ArbitrageTaskContext(
        symbol=symbol,
        single_order_size_usdt=base_position_size_usdt,
        params=params,
        arbitrage_state='initializing',
        min_switch_profit_pct=min_switch_profit_pct,
        operation_mode=operation_mode
    )
    
    task = MultiSpotFuturesArbitrageTask(
        logger=logger,
        context=context,
        spot_exchanges=spot_exchanges,
        futures_exchange=futures_exchange,
        operation_mode=operation_mode
    )
    await task.start()
    return task


# Convenience function for common exchange combinations
async def create_mexc_binance_gateio_arbitrage_task(
    symbol: Symbol,
    operation_mode: Literal['traditional', 'spot_switching'] = 'spot_switching',
    base_position_size_usdt: float = 100.0,
    max_entry_cost_pct: float = 0.5,
    min_profit_pct: float = 0.1,
    max_hours: float = 6.0,
    min_switch_profit_pct: float = 0.05,
    logger: Optional[HFTLoggerInterface] = None
) -> MultiSpotFuturesArbitrageTask:
    """Create MEXC + Binance spots + Gate.io futures arbitrage task."""
    return await create_multi_spot_futures_arbitrage_task(
        symbol=symbol,
        spot_exchanges=[ExchangeEnum.MEXC, ExchangeEnum.BINANCE],
        futures_exchange=ExchangeEnum.GATEIO_FUTURES,
        operation_mode=operation_mode,
        base_position_size_usdt=base_position_size_usdt,
        max_entry_cost_pct=max_entry_cost_pct,
        min_profit_pct=min_profit_pct,
        max_hours=max_hours,
        min_switch_profit_pct=min_switch_profit_pct,
        logger=logger
    )