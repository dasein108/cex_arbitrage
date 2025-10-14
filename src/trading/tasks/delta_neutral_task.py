import asyncio
from typing import Optional, Type, Dict, Callable, Awaitable, Literal
import msgspec

from exchanges.dual_exchange import DualExchange
from config.config_manager import get_exchange_config
from exchanges.structs import Order, SymbolInfo, ExchangeEnum, Symbol
from exchanges.structs.common import Side
from utils.exchange_utils import is_order_done
from infrastructure.logging import HFTLoggerInterface
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, PrivateWebsocketChannelType

from trading.tasks.base_task import TaskContext, BaseTradingTask, StateHandler
from utils import get_decrease_vector, flip_side, calculate_weighted_price
from enum import IntEnum


class Direction(IntEnum):
    FILL = 1
    RELEASE = -1
    NONE = 0


# Delta-neutral execution states using Literal strings for optimal performance
# Includes base states and delta-neutral specific states
DeltaNeutralState = Literal[
    # Base states
    'idle',
    'paused',
    'error',
    'completed',
    'cancelled',
    'executing',
    'adjusting',
    
    # Delta-neutral specific states
    'syncing',         # Sync order status from exchanges  
    'analyzing',       # Analyze imbalances and completion
    'rebalancing',     # Handle imbalances with market orders
    'managing_orders', # Cancel/place limit orders
    'completing'       # Finalize task
]


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


class DeltaNeutralTask(BaseTradingTask[DeltaNeutralTaskContext, str]):
    """State machine for executing delta-neutral trading strategies.
    
    Executes simultaneous buy and sell orders across two exchanges to maintain
    market-neutral positions while capturing spread opportunities.
    """
    name: str = "DeltaNeutralTask"

    @property
    def context_class(self) -> Type[DeltaNeutralTaskContext]:
        """Return the delta-neutral context class."""
        return DeltaNeutralTaskContext

    def _build_tag(self) -> None:
        """Build logging tag with exchange-specific fields."""
        buy_exchange = self.context.exchange_names[Side.BUY].name if self.context.exchange_names[Side.BUY] else "UNKNOWN"
        sell_exchange = self.context.exchange_names[Side.SELL].name if self.context.exchange_names[Side.SELL] else "UNKNOWN"
        self._tag = f'{self.name}_BUY:{buy_exchange}_SELL:{sell_exchange}_{self.context.symbol}'

    def __init__(self,
                 logger: HFTLoggerInterface,
                 context: DeltaNeutralTaskContext,
                 **kwargs):
        """Initialize delta-neutral task.
        
        Accepts DeltaNeutralTaskContext with parameters:
        - symbol: Trading symbol (required)
        - exchange_names: Dict mapping Side to ExchangeEnum (required)
        - total_quantity: Total amount to execute on each side
        - order_quantity: Size of each order slice
        - offset_ticks: Price offset in ticks for each side
        - tick_tolerance: Price movement tolerance for each side
        """
        super().__init__(logger, context, **kwargs)
        
        # DualExchange instances for each side (unified public/private)
        self._exchanges: Dict[Side, DualExchange] = {}
        
        # Initialize DualExchange for each side
        for side, exchange_enum in self.context.exchange_names.items():
            config = get_exchange_config(exchange_enum.value)
            self._exchanges[side] = DualExchange.get_instance(config, self.logger)

        self._current_orders: Dict[Side, Optional[Order]] = {Side.BUY: None, Side.SELL: None}
        self._symbol_info: Dict[Side, Optional[SymbolInfo]] = {Side.BUY: None, Side.SELL: None}

    async def start(self, **kwargs):
        if self.context is None:
            raise ValueError("Cannot start task: context is None (likely deserialization failed)")

        await super().start(**kwargs)
        
        # Initialize DualExchanges in parallel for HFT performance
        init_tasks = []
        for side in [Side.BUY, Side.SELL]:
            exchange = self._exchanges[side]
            specific_private_channels = [PrivateWebsocketChannelType.POSITION] if exchange.is_futures else [PrivateWebsocketChannelType.BALANCE]
            init_tasks.append(
                exchange.initialize(
                    [self.context.symbol],
                    public_channels=[PublicWebsocketChannelType.BOOK_TICKER],
                    private_channels=[PrivateWebsocketChannelType.ORDER] + specific_private_channels
                )
            )
            # if exchange.is_futures:
            #     exchange.bind_handlers(on_position=)
            # else:
            #     exchange.bind_handlers(on_balance=)

        await asyncio.gather(*init_tasks)
        
        # Set symbol info and restore orders
        for side in [Side.BUY, Side.SELL]:
            self._symbol_info[side] = self._exchanges[side].public.symbols_info[self.context.symbol]
            order_id = self.context.order_id[side]
            if order_id:
                self._current_orders[side] = await self._exchanges[side].private.fetch_order(
                    self.context.symbol, order_id
                )

    async def cancel_all(self):
        cancel_tasks = [self._cancel_side_order(Side.SELL), self._cancel_side_order(Side.BUY)]
        canceled = await asyncio.gather(*cancel_tasks)
        self.logger.info(f"🛑 Canceled all orders for {self._tag}", orders=str(canceled))

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

    def _update_side_context(self, side: Side, **updates):
        """Update context fields for specific side with explicit field updates.
        
        Args:
            side: Side (BUY or SELL) to update fields for
            **updates: Fields to update for the specified side
        """
        context_updates = {}
        
        for field, value in updates.items():
            if field in ['filled_quantity', 'avg_price', 'offset_ticks', 'tick_tolerance', 'order_id']:
                current_dict = dict(getattr(self.context, field))
                current_dict[side] = value
                context_updates[field] = current_dict
            else:
                raise ValueError(f"Unsupported side-specific field: {field}")
        
        self.evolve_context(**context_updates)

    def _get_current_top_price(self, side: Side) -> float:
        """Get current best price from public exchange."""
        book_ticker = self._exchanges[side].public.book_ticker[self.context.symbol]
        return book_ticker.ask_price if side == Side.SELL else book_ticker.bid_price

    async def _cancel_side_order(self, exchange_side: Side) -> bool:
        """Cancel the current active order if exists.
        Returns True if there was a fill, False otherwise.
        """
        if self._current_orders[exchange_side]:
            order = await self._cancel_order_safely_dual(
                self._exchanges[exchange_side],
                self.context.symbol,
                self._current_orders[exchange_side].order_id,
                exchange_side.name
            )
            has_fill = False

            if order:
                has_fill = order.filled_quantity > 0
                await self._process_order_execution(exchange_side, order)
            else:
                # Clear order references even if cancel failed
                self._current_orders[exchange_side] = None
                self._update_side_context(exchange_side, order_id=None)

            return has_fill
        return False

    def _validate_order_size(self, symbol_info: SymbolInfo, quantity: float, price: float) -> float:
        """Validate and adjust order size to meet exchange minimums."""
        min_quote_qty = symbol_info.min_quote_quantity
        if quantity * price < min_quote_qty:
            return min_quote_qty / price + 0.01
        return quantity
    
    def _get_minimum_order_quantity(self, symbol_info: SymbolInfo, current_price: float) -> float:
        """Get minimum order quantity based on exchange requirements."""
        return symbol_info.min_quote_quantity / current_price
    
    async def _cancel_order_safely_dual(
        self, 
        exchange: DualExchange, 
        symbol: Symbol, 
        order_id: str,
        tag: str = ""
    ) -> Optional[Order]:
        """Safely cancel order with consistent error handling."""
        try:
            order = await exchange.private.cancel_order(symbol, order_id)
            tag_str = f"{self._tag} {tag}".strip()
            self.logger.info(f"🛑 Cancelled order {tag_str}", order_id=order_id)
            return order
        except Exception as e:
            tag_str = f"{self._tag} {tag}".strip()
            self.logger.error(f"🚫 Failed to cancel order {tag_str}", error=str(e))
            # Try to fetch order status instead
            order = await exchange.private.fetch_order(symbol, order_id)
            return order

    async def _place_limit_order_safely_dual(
        self,
        exchange: DualExchange,
        symbol: Symbol,
        side: Side,
        quantity: float,
        price: float,
        tag: str = ""
    ) -> Optional[Order]:
        """Place limit order with validation and error handling."""
        try:
            order = await exchange.private.place_limit_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
            )
            
            tag_str = f"{self._tag} {tag}".strip()
            self.logger.info(f"📈 Placed {side.name} order {tag_str}", 
                        order_id=order.order_id,
                        order=str(order))
            return order
            
        except Exception as e:
            tag_str = f"{self._tag} {tag}".strip()
            self.logger.error(f"🚫 Failed to place order {tag_str}", error=str(e))
            return None

    async def _prepare_order_quantity(self, side: Side, base_quantity: float) -> float:
        """Prepare order quantity with all required adjustments."""
        # Adjust with exchange minimums
        price = self._get_current_top_price(side)
        quantity = self._validate_order_size(self._symbol_info[side], base_quantity, price)
        
        # Round to contracts if futures
        if self._exchanges[side].is_futures:
            quantity = self._exchanges[side].round_base_to_contracts(
                self.context.symbol, quantity
            )
        
        return quantity

    def _has_imbalance(self, side: Side) -> bool:
        """Check if side has significant imbalance."""
        flip_side_filled = self.context.filled_quantity[flip_side(side)]
        current_filled = self.context.filled_quantity[side]
        imbalance = flip_side_filled - current_filled
        return imbalance > self._get_min_quantity(side)
    
    async def _rebalance_side(self, side: Side):
        """Handle imbalance for specific side with market order."""
        flip_side_filled = self.context.filled_quantity[flip_side(side)]
        imbalance_quantity = flip_side_filled - self.context.filled_quantity[side]
        
        self.logger.info(f"📈 Rebalancing {side.name} imbalance: {imbalance_quantity}")
        
        # Cancel existing order first
        await self._cancel_side_order(side)
        
        # Calculate and place market order
        quote_quantity = abs(imbalance_quantity) / self._get_current_top_price(side)
        quote_quantity = await self._prepare_order_quantity(side, quote_quantity)
        
        order = await self._exchanges[side].private.place_market_order(
            symbol=self.context.symbol,
            side=side,
            price=self._get_current_top_price(side),
            quote_quantity=quote_quantity
        )
        
        await self._process_order_execution(side, order)

    async def _place_order(self, side: Side):
        """Place limit order to top-offset price."""
        quantity_to_fill = self._get_quantity_to_fill(side)
        if quantity_to_fill == 0:
            return

        offset_ticks = self.context.offset_ticks[side]
        top_price = self._get_current_top_price(side)

        # Get fresh price for order
        vector_ticks = get_decrease_vector(side, offset_ticks)
        order_price = top_price + vector_ticks * self._symbol_info[side].tick

        # adjust to rest unfilled total amount
        order_quantity = min(self.context.order_quantity, quantity_to_fill)
        # adjust with exchange minimums and futures contracts
        order_quantity = await self._prepare_order_quantity(side, order_quantity)

        order = await self._place_limit_order_safely_dual(
            self._exchanges[side],
            self.context.symbol,
            side,
            order_quantity,
            order_price,
            side.name
        )

        if order:
            await self._process_order_execution(side, order)

    async def _sync_exchange_order(self, side: Side) -> Order | None:
        """Get current order from exchange, track updates."""
        curr_order = self._current_orders[side]

        if curr_order:
            updated_order = await self._exchanges[side].private.get_active_order(
                self.context.symbol, curr_order.order_id
            )
            await self._process_order_execution(side, updated_order)
            return self._current_orders[side]
        else:
            return None

    async def _handle_idle(self):
        await super()._handle_idle()
        self._transition('syncing')

    def _should_cancel_order(self, side: Side) -> bool:
        """Determine if current order should be cancelled due to price movement."""
        curr_order = self._current_orders[side]

        if not curr_order:
            return False

        top_price = self._get_current_top_price(side)
        order_price = curr_order.price
        tick_difference = abs((order_price - top_price) / self._symbol_info[side].tick)
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

                self._update_side_context(exchange_side,
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
            self._current_orders[exchange_side] = None
        else:
            # Update active order state
            self._current_orders[exchange_side] = order
            self._update_side_context(exchange_side, order_id=order.order_id)


    def _buy_sell_imbalance(self):
        """Check if there is an imbalance between buy and sell filled quantities."""
        buy_filled = self.context.filled_quantity[Side.BUY]
        sell_filled = self.context.filled_quantity[Side.SELL]
        return buy_filled - sell_filled

    def _get_min_quantity(self, side: Side) -> float:
        """Get minimum order quantity for the given side."""
        return self._get_minimum_order_quantity(self._symbol_info[side], self._get_current_top_price(side))

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

    # Enhanced state machine handlers
    async def _handle_syncing(self):
        """Sync order status from both exchanges in parallel."""
        sync_tasks = [
            self._sync_exchange_order(Side.BUY),
            self._sync_exchange_order(Side.SELL)
        ]
        await asyncio.gather(*sync_tasks)
        self._transition('analyzing')

    async def _handle_analyzing(self):
        """Analyze current state and determine next action."""
        # Check completion first (highest priority)
        if self._check_completing():
            self._transition('completing')
            return
        
        # Check for imbalances
        has_imbalance = any([
            self._has_imbalance(Side.BUY),
            self._has_imbalance(Side.SELL)
        ])
        
        if has_imbalance:
            self._transition('rebalancing')
        else:
            self._transition('managing_orders')

    async def _handle_rebalancing(self):
        """Handle imbalances with market orders."""
        rebalance_tasks = []
        
        for side in [Side.BUY, Side.SELL]:
            if self._has_imbalance(side):
                rebalance_tasks.append(self._rebalance_side(side))
        
        if rebalance_tasks:
            await asyncio.gather(*rebalance_tasks)
            self.logger.info("⚖️ Rebalancing completed, returning to sync")
            self._transition('syncing')  # Re-sync after rebalancing
        else:
            self._transition('managing_orders')

    async def _handle_managing_orders(self):
        """Manage limit orders (cancel/place) for both sides."""
        management_tasks = [
            self._manage_side_orders(Side.BUY),
            self._manage_side_orders(Side.SELL)
        ]
        await asyncio.gather(*management_tasks)
        self._transition('syncing')  # Return to monitoring

    async def _handle_completing(self):
        """Finalize task execution."""
        await self.cancel_all()
    
    # Base state handlers (implementing BaseStateMixin states)
    async def _handle_cancelled(self):
        """Handle cancelled state."""
        self.logger.info("🚫 Delta neutral task cancelled")
        await self.cancel_all()
        await super().complete()
    
    async def _manage_side_orders(self, side: Side):
        """Manage limit orders for one side."""
        # Skip if no quantity to fill
        if self._get_quantity_to_fill(side) == 0:
            return
        
        # Cancel if price moved too much
        if self._should_cancel_order(side):
            await self._cancel_side_order(side)
        
        # Place new order if none exists
        if not self._current_orders[side]:
            await self._place_order(side)
    
    # Override executing handler to redirect to delta-neutral state machine
    async def _handle_executing(self):
        """Override base executing handler to use delta-neutral states."""
        self._transition('syncing')

    async def _handle_adjusting(self):
        """Handle external adjustments to task parameters."""
        self.logger.debug(f"ADJUSTING state for {self._tag}")
        # After adjustments, return to syncing to refresh state
        self._transition('syncing')

    async def complete(self):
        """Complete the task and clean up."""
        await self.cancel_all()
        await super().complete()
    
    def get_unified_state_handlers(self) -> Dict[str, StateHandler]:
        """Provide complete unified state handler mapping.
        
        Includes both base states and delta-neutral specific states using string keys.
        """
        return {
            # Base state handlers
            'idle': self._handle_idle,
            'paused': self._handle_paused,
            'error': self._handle_error,
            'completed': self._handle_complete,
            'cancelled': self._handle_cancelled,
            'executing': self._handle_executing,
            'adjusting': self._handle_adjusting,
            
            # Delta-neutral specific state handlers
            'syncing': self._handle_syncing,
            'analyzing': self._handle_analyzing, 
            'rebalancing': self._handle_rebalancing,
            'managing_orders': self._handle_managing_orders,
            'completing': self._handle_completing,
        }
