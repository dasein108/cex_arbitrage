"""
Base Arbitrage Task - Common Functionality for All Arbitrage Strategies

Provides common functionality for arbitrage trading tasks including:
- Exchange manager lifecycle management
- Order tracking and processing
- Position management utilities  
- Common validation methods
- Debug utilities and logging
- Basic lifecycle operations

This base class extracts common features to promote code reuse and maintainability
while allowing strategy-specific implementations to focus on trading logic.
"""

import asyncio
import time
from typing import Optional, Dict, Type, Literal
from abc import abstractmethod

from trading.tasks.base_task import BaseTradingTask, StateHandler
from trading.tasks.arbitrage_task_context import (
    ArbitrageTaskContext,
    ValidationResult
)
from exchanges.structs import Symbol, Side, ExchangeEnum, Order
from infrastructure.logging import HFTLoggerInterface, LoggerFactory
from utils.exchange_utils import is_order_done

# Import existing arbitrage components
from trading.task_manager.exchange_manager import (
    ExchangeManager,
    OrderPlacementParams,
    ExchangeRole,
    ArbitrageExchangeType
)


class BaseArbitrageTask(BaseTradingTask[ArbitrageTaskContext, str]):
    """
    Base class for arbitrage trading strategies.
    
    Provides common functionality including exchange management, order tracking,
    position management, and validation utilities. Subclasses should implement
    strategy-specific logic while leveraging the common infrastructure.
    
    Common Features:
    - Exchange manager initialization and lifecycle
    - Order tracking and processing
    - Position management utilities
    - Volume validation methods
    - Debug utilities and counters
    - Logger noise reduction
    - Basic cleanup operations
    """

    name: str = "BaseArbitrageTask"

    @property
    def context_class(self) -> Type[ArbitrageTaskContext]:
        return ArbitrageTaskContext

    def __init__(self,
                 logger: HFTLoggerInterface,
                 context: ArbitrageTaskContext,
                 spot_exchange: ExchangeEnum,
                 futures_exchange: ExchangeEnum,
                 **kwargs):
        """Initialize base arbitrage task with common setup."""
        
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

        # Common initialization
        self.exchange_manager: Optional[ExchangeManager] = None
        self._debug_info_counter = 0

        self.logger.info(f"✅ {self.name} initialized: {spot_exchange.name} spot + {futures_exchange.name} futures")

        # Setup logger overrides for noise reduction
        self._setup_logger_overrides()
        
        self._build_tag()

    def _build_tag(self) -> None:
        """Build logging tag with arbitrage-specific fields."""
        self._tag = f'{self.name}_{self.context.symbol}_{self.spot_exchange.name}_{self.futures_exchange.name}'

    def _setup_logger_overrides(self):
        """Setup logger overrides to reduce noise from exchange loggers."""
        # Disable noisy GATEIO loggers by setting minimum level to ERROR
        logger_names = [
            "GATEIO_SPOT.ws.private", "GATEIO_SPOT.ws.public", "GATEIO_SPOT.GATEIO_SPOT_private",
            "GATEIO_FUTURES.ws.private", "GATEIO_FUTURES.ws.public",
            "GATEIO_FUTURES.GATEIO_FUTURES_private", "GATEIO_FUTURES.GATEIO_FUTURES_public",
            "gateio.rest.private", "rest.client.gateio_futures",
            "MEXC_SPOT.MEXC_SPOT_private", "MEXC_SPOT.MEXC_SPOT_public",
            "MEXC_SPOT.ws.public", "rest.client.mexc_spot"
        ]

        for logger_name in logger_names:
            # Use min_level instead of enabled=False which might be more reliable
            LoggerFactory.override_logger(logger_name, min_level="ERROR")

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
                self.logger.info(
                    f"✅ Exchange manager initialized: {self.spot_exchange.name} + {self.futures_exchange.name}")
                return True
            else:
                self.logger.error("❌ Exchange manager initialization failed")
                return False

        except Exception as e:
            self.logger.error(f"❌ Exception during exchange manager initialization: {e}")
            return False

    def get_min_base_quantity(self, exchange_type: ArbitrageExchangeType, symbol: Symbol) -> float:
        """Get minimum base quantity for the given exchange type."""
        return self.exchange_manager.get_exchange(exchange_type).public.get_min_base_quantity(symbol)

    def _get_minimum_order_base_quantity(self, exchange_type: ArbitrageExchangeType) -> float:
        """Get minimum order quantity based on exchange requirements."""
        return self.get_min_base_quantity(exchange_type, self.context.symbol)

    def _prepare_order_quantity(self, exchange_type: ArbitrageExchangeType, quantity: float) -> float:
        """Prepare order quantity with all required adjustments including exchange minimums."""
        # Validate with exchange minimums
        min_base_qty = self.get_min_base_quantity(exchange_type, self.context.symbol)
        if quantity < min_base_qty:
            adjusted_quantity = min_base_qty * 1.001  # Small buffer for precision
            self.logger.info(f"📏 Adjusting {exchange_type} order size: {quantity:.6f} ->"
                             f" {adjusted_quantity:.6f} ")
            return adjusted_quantity

        return quantity

    def _validate_exit_volumes(self) -> ValidationResult:
        """Validate that exit volumes meet minimum requirements for both exchanges."""
        if not self.context.positions_state.has_positions:
            return ValidationResult(valid=False, reason="No positions to exit")

        spot_pos = self.context.positions_state.positions['spot']
        futures_pos = self.context.positions_state.positions['futures']

        # Get minimum quantities
        spot_min = self._get_minimum_order_base_quantity('spot')
        futures_min = self._get_minimum_order_base_quantity('futures')

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

    async def _check_order_updates(self):
        """Check order status updates using direct access to exchange orders."""
        for exchange_role in ['spot', 'futures']:  # type: ArbitrageExchangeType
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

                # self.logger.info(f"📝 New order tracked: {order} on {exchange_key}")
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
                exchange.remove_order(order.order_id)  # cleanup exchange
                self.logger.info(f"🏁 {exchange_key} order completed: {order.order_id} on {order}")

        except Exception as e:
            self.logger.error(f"Error processing partial fill: {e}")

    async def _update_active_orders_after_placement(self, placed_orders: Dict[ArbitrageExchangeType, Order]):
        """Update active orders tracking after placing new orders."""
        for exchange_role, order in placed_orders.items():
            self._process_order_fill(exchange_role, order)

        success = all(placed_orders.values())

        return success

    def _transition_arbitrage_state(self, new_state: str):
        """Transition to a new arbitrage state."""
        self._transition(new_state)

    def _increment_debug_counter(self) -> bool:
        """Increment debug counter and return True if should print debug info."""
        self._debug_info_counter += 1
        should_print = self._debug_info_counter % 1000 == 0
        if should_print:
            self._debug_info_counter = 0  # Reset counter
        return should_print

    # Base state handlers for common arbitrage states
    async def _handle_initializing(self):
        """Initialize exchange manager and connections."""
        if self.exchange_manager is None:
            await self._initialize_exchange_manager()

        if self.exchange_manager:
            self._transition_arbitrage_state('monitoring')
        else:
            self.logger.error("❌ Failed to initialize exchange manager")
            self._transition_arbitrage_state('error_recovery')

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

    async def cleanup(self):
        """Clean up strategy resources."""
        self.logger.info(f"🧹 Cleaning up {self.name} resources")
        
        if self.exchange_manager:
            await self.exchange_manager.shutdown()
        self.logger.info(f"✅ {self.name} cleanup completed")

    # Abstract methods that subclasses must implement
    @abstractmethod
    async def _handle_arbitrage_monitoring(self):
        """Monitor market and manage positions - strategy specific."""
        pass

    @abstractmethod
    async def _handle_arbitrage_analyzing(self):
        """Analyze current opportunity - strategy specific.""" 
        pass

    @abstractmethod
    async def _handle_executing(self):
        """Execute arbitrage trades - strategy specific."""
        pass

    @abstractmethod
    def get_unified_state_handlers(self) -> Dict[str, StateHandler]:
        """Provide complete unified state handler mapping - strategy specific."""
        pass