from typing import Optional, Type, Dict, Any

from config.structs import ExchangeConfig
from exchanges.dual_exchange import DualExchange
from exchanges.structs import Order, SymbolInfo, ExchangeEnum
from exchanges.structs.common import Side, TimeInForce
from exchanges.utils.exchange_utils import is_order_done
from infrastructure.logging import HFTLoggerInterface
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, PrivateWebsocketChannelType
from trading.struct import TradingStrategyState

from trading.tasks.base_task import TaskContext, BaseTradingTask
from utils import get_decrease_vector


class IcebergTaskContext(TaskContext):
    """Context for iceberg order execution.
    
    Extends TaskContext with iceberg-specific fields for tracking
    partial fills and order slicing parameters.
    """
    total_quantity: Optional[float] = None
    order_quantity: Optional[float] = None
    filled_quantity: float = 0.0
    offset_ticks: int = 0
    tick_tolerance: int = 1
    avg_price: float = 0.0


class IcebergTask(BaseTradingTask[IcebergTaskContext]):
    """State machine for executing iceberg orders.
    
    Breaks large orders into smaller chunks to minimize market impact.
    """
    name: str = "IcebergTask"

    @property
    def context_class(self) -> Type[IcebergTaskContext]:
        """Return the iceberg context class."""
        return IcebergTaskContext

    def __init__(self, 
                 logger: HFTLoggerInterface,
                 context: IcebergTaskContext,
                 **kwargs):
        """Initialize iceberg task.
        
        Args:
            logger: HFT logger instance
            context: IcebergTaskContext with exchange_name, symbol, and iceberg parameters
        """
        super().__init__(logger, context, **kwargs)
        self._exchange = DualExchange.get_instance(self.config)
        self._curr_order: Optional[Order] = None
        self._si: Optional[SymbolInfo] = None
        self.config: Optional[ExchangeConfig] = None


    async def start(self, **kwargs):
        await super().start(**kwargs)
        # Load exchange config if context has exchange_name
        # (for SingleExchangeTaskContext and its subclasses)

        self.config = self._load_exchange_config(self.context.exchange_name)

        await self._exchange.initialize([self.context.symbol],
                                        public_channels=[PublicWebsocketChannelType.BOOK_TICKER],
                                        private_channels=[PrivateWebsocketChannelType.ORDER,
                                                   PrivateWebsocketChannelType.BALANCE])

        self._si = self._exchange.public.symbols_info[self.context.symbol]

    async def pause(self):
        """Pause task and cancel any active order."""
        await self._cancel_current_order()
        await super().pause()

    async def update(self, **context_updates):
        """Update iceberg parameters.
        
        Args:
            **context_updates: Partial updates (total_quantity, order_quantity, offset_ticks, etc.)
        """
        # Cancel current order before updating parameters
        await self._cancel_current_order()

        # Apply updates through base class
        await super().update(**context_updates)

        await self._process_completing()

    def _get_current_top_price(self) -> float:
        """Get current ask price from public exchange."""
        book_ticker = self._exchange.public._book_ticker[self.context.symbol]
        return book_ticker.ask_price if self.context.side == Side.SELL else book_ticker.bid_price

    async def _cancel_current_order(self):
        """Cancel the current active order if exists."""
        if self._curr_order:
            try:
                order = await self._exchange.private.cancel_order(self.context.symbol, self._curr_order.order_id)
                self.logger.info(f"🛑 Cancelled current order {self._tag}", order_id=order.order_id)
                await self._process_order_execution(order)
            except Exception as e:
                self.logger.error(f"🚫 Failed to cancel current order {self._tag}", error=str(e))
                # Clear order references even if cancel failed
                self._curr_order = None
                self.evolve_context(order_id=None)

    async def _place_order(self):
        """Place limit sell order to top-offset price."""
        self.logger.info(f"📈 Placing limit {self.context.side.name} order for quantity: {self.context.order_quantity}")
        if self._curr_order:
            self.logger.warning(f"Existing order found, cancelling before placing new one {self._tag}")
            await self._cancel_current_order()

        try:
            # Get fresh price for sale order
            vector_ticks = get_decrease_vector(self.context.side, self.context.offset_ticks)
            order_price = self._get_current_top_price() + vector_ticks * self._si.tick

            # adjust to rest unfilled total amount
            order_quantity = min(self.context.order_quantity,
                                 self.context.total_quantity - self.context.filled_quantity)

            # adjust with exchange minimums
            if order_quantity * order_price < self._si.min_quote_quantity:
                order_quantity = self._si.min_quote_quantity / order_price + 0.01

            order = await self._exchange.private.place_limit_order(
                symbol=self.context.symbol,
                side=self.context.side,
                quantity=order_quantity,
                price=order_price,
                time_in_force=TimeInForce.GTC
            )

            await self._process_order_execution(order)
        except Exception as e:
            self.logger.error(f"🚫 Failed to place order {self._tag}", error=str(e))

    async def _sync_exchange_order(self) -> Order | None:
        """Get current order from exchange, track updates."""
        if self._curr_order:
            order = await self._exchange.private.get_active_order(self._curr_order.symbol, self._curr_order.order_id)
            return await self._process_order_execution(order)
        else:
            return None

    async def _handle_idle(self):
        await super()._handle_idle()
        self._transition(TradingStrategyState.EXECUTING)

    def _should_cancel_order(self):
        if not self._curr_order:
            return True

        top_price = self._get_current_top_price()
        order_price = self._curr_order.price
        tick_difference = abs((order_price - top_price) / self._si.tick)
        should_cancel = tick_difference > self.context.tick_tolerance

        if should_cancel:
            self.logger.info(
                f"⚠️ Price moved significantly. Current {self.context.side.name}: {top_price}, "
                f"Our price: {order_price}")

        return should_cancel

    async def _process_order_execution(self, order: Order):
        """Process filled order and update context."""
        if is_order_done(order):
            if order.filled_quantity > 0:
                # Calculate weighted average price
                # Previous total cost = previous avg_price * previous filled_quantity
                previous_filled = self.context.filled_quantity
                previous_cost = self.context.avg_price * previous_filled if previous_filled > 0 else 0.0

                # New order cost = order execution price * order filled quantity
                new_order_cost = order.price * order.filled_quantity

                # Update total filled quantity and clear order_id in context
                self.evolve_context(
                    filled_quantity=self.context.filled_quantity + order.filled_quantity,
                    order_id=None  # Clear order_id when order is done
                )

                # Calculate new weighted average price
                total_cost = previous_cost + new_order_cost
                new_avg_price = total_cost / self.context.filled_quantity if self.context.filled_quantity > 0 else 0.0
                self.evolve_context(avg_price=new_avg_price)

                self.logger.info(f"✅ Order filled {self._tag}",
                                 order_price=order.price,
                                 order_filled=order.filled_quantity,
                                 total_filled=self.context.filled_quantity,
                                 avg_price=self.context.avg_price)

            # Clear current order reference
            self._curr_order = None
        else:
            # Order is still active - sync order_id in context
            self._curr_order = order
            self.evolve_context(order_id=order.order_id)

        # Check if completed
        await self._process_completing()

    async def _process_completing(self):
        """Check if total quantity has been filled."""
        if self.context.filled_quantity >= self.context.total_quantity:
            self.logger.info(f"💰 Iceberg execution completed {self._tag}",
                             total_filled=self.context.filled_quantity,
                             avg_price=self.context.avg_price)
            await self.complete()

    async def restore_from_json(self, json_data: str) -> None:
        """Restore iceberg task from JSON with order recovery.
        
        Extends base recovery to fetch current order from exchange
        if order_id is present in the saved context.
        
        Args:
            json_data: JSON string containing task context
        """
        # First restore basic context (config is automatically reloaded from exchange_name)
        super().restore_from_json(json_data)
        
        # Reinitialize exchange with the reloaded config (if available)
        # Reload config if exchange_name is available
        if self.context.exchange_name:
            self.config = self._load_exchange_config(self.context.exchange_name)
            self._exchange = DualExchange.get_instance(self.config)
            await self._exchange.initialize([self.context.symbol])

        # If we have an order_id, try to recover the order from exchange
        if self.context.order_id:
            try:
                # Try to fetch the order from exchange
                order = await self._exchange.private.get_active_order(
                    self.context.symbol, 
                    self.context.order_id
                )
                
                if order:
                    self._curr_order = order
                    self.logger.info(f"✅ Recovered active order {self._tag}", 
                                   order_id=order.order_id,
                                   order_price=order.price,
                                   order_quantity=order.quantity,
                                   filled_quantity=order.filled_quantity)
                else:
                    # Order not found, probably filled or cancelled
                    self.logger.warning(f"⚠️ Order {self.context.order_id} not found on exchange, marking as completed {self._tag}")
                    self._curr_order = None
                    self.evolve_context(order_id=None)
                    
            except Exception as e:
                # Failed to recover order, log and continue
                self.logger.error(f"🚫 Failed to recover order {self.context.order_id} {self._tag}", error=str(e))
                self._curr_order = None
                self.evolve_context(order_id=None)
        else:
            # No order_id in context, clear current order
            self._curr_order = None

    async def _handle_executing(self):
        # sync order updates
        await self._sync_exchange_order()

        if not self._curr_order:
            await self._place_order()
        elif self._should_cancel_order():
            await self._cancel_current_order()

    async def cleanup(self):
        """Clean up exchange resources."""
        if self._exchange:
            await self._exchange.close()
