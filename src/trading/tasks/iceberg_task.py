from typing import Optional, Type, Dict, Any

from config.structs import ExchangeConfig
from exchanges.dual_exchange import DualExchange
from exchanges.structs import Order, SymbolInfo
from exchanges.structs.common import Side, TimeInForce
from exchanges.utils.exchange_utils import is_order_done
from infrastructure.logging import HFTLoggerInterface
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, PrivateWebsocketChannelType
from trading.struct import TradingStrategyState

from trading.tasks.base_task import TradingTaskContext, BaseTradingTask
from utils import get_decrease_vector


class IcebergTaskContext(TradingTaskContext):
    """Context for iceberg order execution.
    
    Extends base context with iceberg-specific fields for tracking
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
                 config: ExchangeConfig,
                 logger: HFTLoggerInterface,
                 context=None,
                 task_id=None,
                 **kwargs):
        """Initialize iceberg task.
        
        Accepts either a pre-built IcebergTaskContext or individual parameters:
        - symbol: Trading symbol (required)
        - side: Buy or sell side (required for execution)
        - total_quantity: Total amount to execute
        - order_quantity: Size of each slice
        - offset_ticks: Price offset in ticks
        """
        super().__init__(config, logger, context, task_id=task_id, **kwargs)
        self._exchange = DualExchange.get_instance(self.config)
        self._curr_order: Optional[Order] = None
        self._si: Optional[SymbolInfo] = None

    async def start(self, **kwargs):
        await super().start(**kwargs)
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

    async def _place_order(self):
        """Place limit sell order to top-offset price."""
        self.logger.info(f"📈 Placing limit {self.context.side} order for quantity: {self.context.order_quantity}")
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
            self._curr_order = await self._exchange.private.get_order(self._curr_order.symbol, self._curr_order.order_id)
            return self._curr_order
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

                # Update total filled quantity
                self.context.filled_quantity += order.filled_quantity

                # Calculate new weighted average price
                total_cost = previous_cost + new_order_cost
                self.context.avg_price = total_cost / self.context.filled_quantity if self.context.filled_quantity > 0 else 0.0

                self.logger.info(f"✅ Order filled {self._tag}",
                                 order_price=order.price,
                                 order_filled=order.filled_quantity,
                                 total_filled=self.context.filled_quantity,
                                 avg_price=self.context.avg_price)

            # Clear current order reference
            self._curr_order = None
        else:
            self._curr_order = order

        # Check if completed
        await self._process_completing()

    async def _process_completing(self):
        """Check if total quantity has been filled."""
        if self.context.filled_quantity >= self.context.total_quantity:
            self.logger.info(f"💰 Iceberg execution completed {self._tag}",
                             total_filled=self.context.filled_quantity,
                             avg_price=self.context.avg_price)
            await self.complete()

    async def _handle_executing(self):
        # sync order updates
        await self._sync_exchange_order()

        if not self._curr_order:
            await self._place_order()
        elif self._should_cancel_order():
            await self._cancel_current_order()
