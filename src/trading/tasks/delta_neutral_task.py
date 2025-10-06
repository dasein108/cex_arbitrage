import asyncio
from typing import Optional, Type, Dict
import msgspec

from config.structs import ExchangeConfig
from exchanges.dual_exchange import DualExchange
from exchanges.structs import Order, SymbolInfo, ExchangeEnum, Symbol, OrderType
from exchanges.structs.common import Side, TimeInForce
from utils.exchange_utils import is_order_done
from infrastructure.logging import HFTLoggerInterface
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, PrivateWebsocketChannelType
from trading.struct import TradingStrategyState

from trading.tasks.base_task import TaskContext, BaseTradingTask
from trading.tasks.mixins import OrderManagementMixin
from utils import get_decrease_vector, flip_side, calculate_weighted_price
from enum import IntEnum


class Direction(IntEnum):
    FILL = 1
    RELEASE = -1
    NONE = 0


class DeltaNeutralTaskContext(TaskContext):
    """Context for delta neutral execution.
    
    Extends SingleExchangeTaskContext with delta-neutral specific fields for tracking
    partial fills on both sides.
    """
    symbol: Symbol
    total_quantity: Optional[float] = None
    filled_quantity: Dict[Side, float] = msgspec.field(default_factory=lambda: {Side.BUY: 0.0, Side.SELL: 0.0})
    avg_price: Dict[Side, float] = msgspec.field(default_factory=lambda: {Side.BUY: 0.0, Side.SELL: 0.0})
    exchange_names: Dict[Side, ExchangeEnum] = msgspec.field(default_factory=lambda: {Side.BUY: None, Side.SELL: None})
    direction: Direction = Direction.NONE
    order_quantity: Optional[float] = None
    offset_ticks: Dict[Side, int] = msgspec.field(default_factory=lambda: {Side.BUY: 0, Side.SELL: 0})  # offset_tick = -1 means MARKET order
    tick_tolerance: Dict[Side, int] = msgspec.field(default_factory=lambda: {Side.BUY: 0, Side.SELL: 0})
    order_id: Dict[Side, Optional[str]] = msgspec.field(default_factory=lambda: {Side.BUY: None, Side.SELL: None})


class DeltaNeutralTask(BaseTradingTask[DeltaNeutralTaskContext], OrderManagementMixin):
    """State machine for executing iceberg orders.
    
    Breaks large orders into smaller chunks to minimize market impact.
    """
    name: str = "DeltaNeutralTask"

    @property
    def context_class(self) -> Type[DeltaNeutralTaskContext]:
        """Return the iceberg context class."""
        return DeltaNeutralTaskContext

    def _build_tag(self) -> None:
        """Build logging tag with exchange-specific fields."""
        self._tag = (f'{self.name}_BUY:{self.context.exchange_names[Side.BUY].name}_'
                     f'SELL:{self.context.exchange_names[Side.SELL].name}'
                     f'{self.context.symbol}')

    def __init__(self,
                 logger: HFTLoggerInterface,
                 context: DeltaNeutralTaskContext,
                 **kwargs):
        """Initialize iceberg task.
        
        Accepts either a pre-built IcebergTaskContext or individual parameters:
        - symbol: Trading symbol (required)
        - side: Buy or sell side (required for execution)
        - total_quantity: Total amount to execute
        - order_quantity: Size of each slice
        - offset_ticks: Price offset in ticks
        """
        super().__init__(logger, context, **kwargs)
        self._exchange: Dict[Side, DualExchange] = {side: self._load_exchange(exchange)
                                                    for side, exchange in self.context.exchange_names.items()}

        self._curr_order: Dict[Side, Optional[Order]] = {Side.BUY: None, Side.SELL: None}
        self._si: Dict[Side, Optional[SymbolInfo]] = {Side.BUY: None, Side.SELL: None}

    async def start(self, **kwargs):
        if self.context is None:
            raise ValueError("Cannot start task: context is None (likely deserialization failed)")

        await super().start(**kwargs)
        for side, exchange in self.context.exchange_names.items():

            await self._exchange[side].initialize([self.context.symbol],
                                                  public_channels=[PublicWebsocketChannelType.BOOK_TICKER],
                                                  private_channels=[PrivateWebsocketChannelType.ORDER,
                                                                    PrivateWebsocketChannelType.BALANCE])
            self._si[side] = self._exchange[side].public.symbols_info[self.context.symbol]
            order_id = self.context.order_id[side]
            if order_id:
                self._curr_order[side] = await self._exchange[side].private.fetch_order(self.context.symbol,
                                                                                        order_id)

        pass

    async def cancel_all(self):
        await asyncio.gather(self._cancel_side_order(Side.SELL), self._cancel_side_order(Side.BUY))

    async def pause(self):
        """Pause task and cancel any active order."""
        await self.cancel_all()
        await super().pause()

    async def update(self, **context_updates):
        """Update iceberg parameters.
        
        Args:
            **context_updates: Partial updates (total_quantity, order_quantity, offset_ticks, etc.)
        """
        # Cancel current order before updating parameters
        await self.cancel_all()
        # Apply updates through base class
        await super().update(**context_updates)

    def _evolve_side_context(self, side: Side, **updates):
        """Helper to update dict fields for specific side using Django-like syntax.
        
        Args:
            side: Side (BUY or SELL) to update fields for
            **updates: Fields to update for the specified side
            
        Examples:
            # Update multiple fields atomically for a side
            self._evolve_side_context(Side.BUY, 
                filled_quantity=100.0,
                order_id=None,
                avg_price=50.5
            )
        """
        # side_key = 'buy' if side == Side.BUY else 'sell'
        context_updates = {}

        for field, value in updates.items():
            context_updates[f'{field}__{side.name}'] = value

        self.evolve_context(**context_updates)

    def _get_current_top_price(self, side: Side) -> float:
        """Get current ask price from public exchange."""
        book_ticker = self._exchange[side].public._book_ticker[self.context.symbol]
        return book_ticker.ask_price if side == Side.SELL else book_ticker.bid_price

    async def _cancel_side_order(self, exchange_side: Side) ->bool:
        """Cancel the current active order if exists.
        Returns True if there was a fill, False otherwise.
        """
        if self._curr_order[exchange_side]:
            order = await self.cancel_order_safely(
                self._exchange[exchange_side],
                self.context.symbol,
                self._curr_order[exchange_side].order_id,
                exchange_side.name
            )
            has_fill = False

            if order:
                has_fill = order.filled_quantity > 0
                await self._process_order_execution(exchange_side, order)
            else:
                # Clear order references even if cancel failed
                self._curr_order[exchange_side] = None
                self._evolve_side_context(exchange_side, order_id=None)

            return has_fill

    async def _adjust_to_min_quantity(self, side: Side, price: float, quantity: float) -> float:
        """Adjust order quantity and price to meet exchange minimums."""
        return self.validate_order_size(self._si[side], quantity, price)

    async def _place_order(self, side: Side):
        """Place limit sell order to top-offset price."""
        flip_side_filled_quantity = self.context.filled_quantity[flip_side(side)]
        imbalance_quantity = flip_side_filled_quantity - self.context.filled_quantity[side]
        has_imbalance = imbalance_quantity > self._get_min_quantity(side)
        try:
            # has imbalance immediately adjust
            if has_imbalance:
                self.logger.info(f"📈 Placing MARKET to adjust imbalance "
                                 f" {side.name} order for quantity: {imbalance_quantity}")
                has_fill = await self._cancel_side_order(side)
                quote_quantity = abs(imbalance_quantity) / self._get_current_top_price(side)

                # round to contracts if futures
                if self._exchange[side].is_futures:
                    quote_quantity = self._exchange[side].round_base_to_contracts(self.context.symbol, quote_quantity)

                # if got some fills need to recalc imbalance during next cycle
                if not has_fill:
                    # place market order to adjust imbalance
                    order = await self._exchange[side].private.place_market_order(
                        symbol=self.context.symbol,
                        side=side,
                        price=self._get_current_top_price(side),
                        quote_quantity=quote_quantity
                    )

                    await self._process_order_execution(side, order)
            else:
                quantity_to_fill = self._get_quantity_to_fill(side)
                if quantity_to_fill == 0:
                    # self.logger.info(f"ℹ️ No more quantity to fill for {side.name}, skipping order placement.")
                    return

                offset_ticks = self.context.offset_ticks[side]
                top_price = self._get_current_top_price(side)

                # Get fresh price for sale order
                vector_ticks = get_decrease_vector(side, offset_ticks)
                order_price = top_price + vector_ticks * self._si[side].tick

                # adjust to rest unfilled total amount
                order_quantity = min(self.context.order_quantity, quantity_to_fill)
                # adjust with exchange minimums
                order_quantity = await self._adjust_to_min_quantity(side, order_price, order_quantity)

                # round to contracts if futures
                if self._exchange[side].is_futures:
                    order_quantity = self._exchange[side].round_base_to_contracts(self.context.symbol, order_quantity)


                order = await self.place_limit_order_safely(
                    self._exchange[side],
                    self.context.symbol,
                    side,
                    order_quantity,
                    order_price,
                    side.name
                )

                if order:
                    await self._process_order_execution(side, order)
        except Exception as e:
            self.logger.error(f"🚫 Failed to place order {self._tag}", error=str(e))
            import traceback
            traceback.print_exc()

    async def _sync_exchange_order(self, side: Side) -> Order | None:
        """Get current order from exchange, track updates."""
        curr_order = self._curr_order[side]

        if curr_order:
            updated_order = await self._exchange[side].private.get_active_order(self.context.symbol,
                                                                                   curr_order.order_id)
            await self._process_order_execution(side, updated_order)
            return self._curr_order[side]
        else:
            return None

    async def _handle_idle(self):
        await super()._handle_idle()
        self._transition(TradingStrategyState.EXECUTING)

    def _should_cancel_order(self, side: Side) -> bool:
        """Determine if current order should be cancelled due to price movement."""
        curr_order = self._curr_order[side]

        if not curr_order:
            return False

        top_price = self._get_current_top_price(side)
        order_price = curr_order.price
        tick_difference = abs((order_price - top_price) / self._si[side].tick)
        should_cancel = tick_difference > self.context.tick_tolerance[side]

        if should_cancel:
            self.logger.info(
                f"⚠️ Price moved significantly. Current {side.name}: {top_price}, "
                f"Our price: {order_price}")

        return should_cancel

    async def _process_order_execution(self, exchange_side: Side, order: Order):
        """Process filled order and update context for specific exchange side."""
        if is_order_done(order):
            # Handle completed order
            if order.filled_quantity > 0:
                # Calculate weighted average price
                new_filled_quantity, new_avg_price = calculate_weighted_price(
                        self.context.avg_price[exchange_side],
                        self.context.filled_quantity[exchange_side],
                        order.price,
                        order.filled_quantity)

                self._evolve_side_context(exchange_side,
                    filled_quantity=new_filled_quantity,
                    order_id=None,
                    avg_price=new_avg_price
                )

                self.logger.info(f"✅ Order filled {order.side.name} {self._tag}",
                                 order_price=order.price,
                                 order_filled=order.filled_quantity,
                                 total_filled=self.context.filled_quantity,
                                 avg_price=self.context.avg_price)

            # Clear order state
            self._curr_order[exchange_side] = None
        else:
            # Update active order state
            self._curr_order[exchange_side] = order
            self._evolve_side_context(exchange_side, order_id=order.order_id)


    def _buy_sell_imbalance(self):
        """Check if there is an imbalance between buy and sell filled quantities."""
        buy_filled = self.context.filled_quantity[Side.BUY]
        sell_filled = self.context.filled_quantity[Side.SELL]
        return buy_filled - sell_filled

    def _get_min_quantity(self, side: Side) -> float:
        """Get minimum order quantity for the given side."""
        return self.get_minimum_order_quantity(self._si[side], self._get_current_top_price(side))

    def _get_quantity_to_fill(self, side: Side) -> float:
        """Get remaining quantity to fill for the given side."""
        quantity = max(0.0, self.context.total_quantity - self.context.filled_quantity[side])
        if quantity < self._get_min_quantity(side):
            quantity = 0.0

        return quantity

    def _check_completing(self):
        """Check if total quantity has been filled."""
        # max min order size tolerance

        is_complete = (self._get_quantity_to_fill(Side.BUY) < self._get_min_quantity(Side.BUY)
                       and self._get_quantity_to_fill(Side.SELL) < self._get_min_quantity(Side.SELL))
        if is_complete:
            self.logger.info(f"🎉 DeltaNeutralTask completed {self._tag}",
                             total_filled=self.context.filled_quantity,
                             avg_price_buy=self.context.avg_price[Side.BUY],
                             avg_price_sell=self.context.avg_price[Side.SELL])

        return is_complete

    async def _handle_executing(self):
        # sync order updates
        for side in [Side.SELL, Side.BUY]:
            await self._sync_exchange_order(side)
            if self._check_completing():
                await self.complete()
                return

            if self._should_cancel_order(side):
                await self._cancel_side_order(side)
            elif not self._curr_order[side]:
                await self._place_order(side)
        pass

    async def _handle_adjusting(self):
        """Default adjusting state handler."""
        # Actual for arbitrage/delta neutral tasks
        self.logger.debug(f"ADJUSTING state for {self._tag}")

    async def complete(self):
        """Complete the task and clean up."""
        await self.cancel_all()
        await super().complete()
