import asyncio
from typing import Optional, Type, Dict, Callable, Awaitable, Literal
import msgspec
from msgspec import Struct
from exchanges.dual_exchange import DualExchange
from config.config_manager import get_exchange_config
from exchanges.structs import Order, SymbolInfo, ExchangeEnum, Symbol, OrderId, BookTicker
from exchanges.structs.common import Side
from infrastructure.exceptions.exchange import OrderNotFoundError
from utils.exchange_utils import is_order_done
from infrastructure.logging import HFTLoggerInterface
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, PrivateWebsocketChannelType

from trading.tasks.base_task import TaskContext, BaseTradingTask, StateHandler
from utils import get_decrease_vector, flip_side, calculate_weighted_price
from enum import IntEnum
from .unfied_position import Position, PositionChange, PositionError
from ..base.base_strategy import BaseStrategyContext

type PrimaryExchangeRole = Literal['source', 'dest']

type ExchangeRoleType = PrimaryExchangeRole | Literal['hedge']

class ExchangeData(Struct):
    exchange: ExchangeEnum
    tick_tolerance: int = 0
    ticks_offset: int = 0
    use_market: bool = False
    order_id: Optional[OrderId] = None


class CrossExchangeArbTaskContext(BaseStrategyContext):
    """Context for delta neutral execution.

    Extends SingleExchangeTaskContext with delta-neutral specific fields for tracking
    partial fills on both sides.
    """
    symbol: Symbol
    total_quantity: Optional[float] = None
    positions: Dict[ExchangeRoleType, Position] = msgspec.field(default_factory=lambda: {'source': Position(), 'dest': Position(), 'hedge': Position()})
    settings: Dict[ExchangeRoleType, ExchangeData] = msgspec.field(default_factory=lambda: {'source': ExchangeData(), 'dest': ExchangeData(), 'hedge': ExchangeData()})
    order_qty: Optional[float] = None # size of each order for limit orders

    task_type: str = "cross_exchange_arbitrage"

    @property
    def tag(self) -> str:
        """Generate logging tag based on task_id and symbol."""
        return f"{self.task_type}_{self.symbol}"

class CrossExchangeArbitrageTask(BaseTradingTask[CrossExchangeArbTaskContext, str]):
    """State machine for executing delta-neutral trading strategies.

    Executes simultaneous buy and sell orders across two exchanges to maintain
    market-neutral positions while capturing spread opportunities.
    """
    name: str = "DeltaNeutralTask"

    @property
    def context_class(self) -> Type[CrossExchangeArbTaskContext]:
        """Return the delta-neutral context class."""
        return CrossExchangeArbTaskContext

    def _build_tag(self) -> None:
        """Build logging tag with exchange-specific fields."""
        self._tag = f'{self.name}_{self.context.symbol}'

    def __init__(self,
                 logger: HFTLoggerInterface,
                 context: CrossExchangeArbTaskContext,
                 **kwargs):
        """Initialize cross-exchange hedged arbitrage task.
        """
        super().__init__(logger, context, **kwargs)

        # DualExchange instances for each side (unified public/private)
        self._exchanges: Dict[ExchangeRoleType, DualExchange] = self.create_exchanges()

        self._current_order: Dict[ExchangeRoleType, Optional[Order]] = {'source': None, 'dest': None, 'hedge': None}
        self._symbol_info: Dict[ExchangeRoleType, Optional[SymbolInfo]] = {'source': None, 'dest': None, 'hedge': None}
        self._exchange_trading_allowed: Dict[ExchangeRoleType, bool] = {'source': False, 'dest': False}

    def create_exchanges(self):
        exchanges = {}
        for exchange_type, settings in self.context.settings.items():
            config = get_exchange_config(settings.exchange.value)
            exchanges[exchange_type] = DualExchange.get_instance(config, self.logger)

        return exchanges

    async def start(self, **kwargs):
        if self.context is None:
            raise ValueError("Cannot start task: context is None (likely deserialization failed)")

        await super().start(**kwargs)

        # Initialize DualExchanges in parallel for HFT performance
        init_tasks = []
        for exchange_type, exchange in self._exchanges.items():
            init_tasks.append(
                exchange.initialize(
                    [self.context.symbol],
                    public_channels=[PublicWebsocketChannelType.BOOK_TICKER],
                    # all balance/position sync is synthetic based on order fills
                    private_channels=[PrivateWebsocketChannelType.ORDER]
                )
            )
        await asyncio.gather(*init_tasks)

        # init symbol info, reload active orders
        await asyncio.gather(self._load_symbol_info(), self._reload_active_orders())


    async def _reload_active_orders(self):
        for exchange_role, exchange in self._exchanges.items():
            pos = self.context.positions[exchange_role]
            last_order = self.context.positions[exchange_role].last_order
            if last_order:
                try:
                    order = await exchange.private.fetch_order(last_order.symbol, last_order.order_id)
                except OrderNotFoundError as e:
                    self.logger.warning(f"⚠️ Could not find existing order '{last_order}' on {exchange_role} "
                                        f"during reload: {e}")
                    order = None

                await self._track_order_execution(exchange_role, order)


    async def _load_symbol_info(self, force = False):
        for exchange_type, exchange in self._exchanges.items():
            if force:
                await exchange.public.load_symbols_info()

            self._symbol_info[exchange_type] = exchange.public.symbols_info[self.context.symbol]

    async def cancel_all(self):
        cancel_tasks = []
        for exchange_role, pos in self.context.positions.items():
            if pos.last_order:
                cancel_tasks.append(self._cancel_order_safe(exchange_role,
                                                            pos.last_order.order_id,
                                                            f"cancel_all"))

        canceled = await asyncio.gather(*cancel_tasks)

        self.logger.info(f"🛑 Canceled all orders", orders=str(canceled))

    async def pause(self):
        """Pause task and cancel any active order."""
        await self.cancel_all()
        await super().pause()

    # TODO: remove candidate
    # async def update(self, **context_updates):
    #     """Update iceberg parameters.
    #
    #     Args:
    #         **context_updates: Partial updates (total_quantity, order_quantity, offset_ticks, etc.)
    #     """
    #     # Cancel current order before updating parameters
    #     await self.cancel_all()
    #     # Apply updates through base class
    #     await super().update(**context_updates)


    def _get_book_ticker(self, exchange_role: ExchangeRoleType) -> BookTicker:
        """Get current best price from public exchange."""
        book_ticker = self._exchanges[exchange_role].public.book_ticker[self.context.symbol]
        return book_ticker

    async def _cancel_order_safe(
            self,
            exchange_role: ExchangeRoleType,
            order_id: str,
            tag: str = ""
    ) -> Optional[Order]:
        """Safely cancel order with consistent error handling."""
        tag_str = f"'{exchange_role.upper()}' {tag}".strip()
        symbol = self.context.symbol
        exchange = self._exchanges[exchange_role].private
        try:

            order = await exchange.cancel_order(symbol, order_id)
            self.logger.info(f"🛑 Cancelled {tag_str}", order=str(order), order_id=order_id)
        except Exception as e:
            tag_str = f"{self._tag} {tag}".strip()
            self.logger.error(f"🚫 Failed to cancel {tag_str} order", error=str(e))
            # Try to fetch order status instead
            order = await exchange.fetch_order(symbol, order_id)

        await self._track_order_execution(exchange_role, order)
        return order

    async def _place_order_safe(
            self,
            exchange_role: ExchangeRoleType,
            side: Side,
            quantity: float,
            price: float,
            is_market: bool = False,
            tag: str = ""
    ) -> Optional[Order]:
        """Place limit order with validation and error handling."""
        tag_str = f"'{exchange_role}' {side.name} {tag}"
        symbol = self.context.symbol

        try:
            exchange = self._exchanges[exchange_role].private
            if is_market:
                order = await exchange.place_market_order(
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    price=price,
                )
            else:
                order = await exchange.place_limit_order(
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    price=price,
                )

            change = self._track_order_execution(exchange_role, order)

            self.logger.info(f"📈 Placed {tag_str} order",
                             order_id=order.order_id,
                             change=str(change),
                             order=str(order))

            return order

        except Exception as e:
            self.logger.error(f"🚫 Failed to place order {tag_str}", error=str(e))
            return None


    async def _rebalance(self) -> bool:
        """Check if there is an imbalance for specific side."""
        source_qty = self.context.positions['source'].qty
        dest_qty = self.context.positions['dest'].qty
        hedge_qty = self.context.positions['hedge'].qty

        delta = (source_qty + dest_qty) - hedge_qty

        if abs(delta) < self._symbol_info['hedge'].min_base_quantity:
            return False

        self.logger.info(f"⚖️ Detected imbalance: delta={delta}:.f8, "
                         f"source={source_qty}, dest={dest_qty}, hedge={hedge_qty}")
        if delta > 0:
            await self._place_order_safe('hedge', Side.BUY, abs(delta),
                                         self._get_book_ticker('hedge').bid_price,
                                         is_market=True, tag="Rebalance Hedge")
        else:
            await self._place_order_safe('hedge', Side.SELL, abs(delta),
                                         self._get_book_ticker('hedge').ask_price,
                                         is_market=True, tag="Rebalance Hedge")

        return True

    async def _place_order_process(self, exchange_role: PrimaryExchangeRole):
        """
        Place limit order to top-offset price or market order.
        Hedge should be rebalanced relative to source/dest.
        """

        if not self._exchange_trading_allowed[exchange_role]:
            return

        max_quantity_to_fill = self._get_exchange_quantity_remaining(exchange_role)
        if max_quantity_to_fill == 0:
            return

        curr_book_ticker = self._get_book_ticker(exchange_role)
        settings = self.context.settings[exchange_role]
        offset_ticks = settings.ticks_offset
        side = Side.BUY if exchange_role == 'source' else Side.SELL

        if settings.use_market:
            hedge_book_ticker = self._get_book_ticker(exchange_role)

            max_hedge_top_qty = hedge_book_ticker.bid_quantity if side == Side.BUY else hedge_book_ticker.ask_quantity
            max_curr_top_qty = curr_book_ticker.ask_quantity if side == Side.BUY else curr_book_ticker.bid_quantity
            market_order_qty = min(max_hedge_top_qty, max_curr_top_qty, max_quantity_to_fill)

            order_price = hedge_book_ticker.ask_price if side == Side.BUY else hedge_book_ticker.bid_price

            await self._place_order_safe(
                exchange_role,
                side,
                market_order_qty,
                order_price,
                is_market=True,
                tag=f"{exchange_role}:{side.name}:market"
            )
        else:
            top_price = curr_book_ticker.bid_price if side == Side.BUY else curr_book_ticker.ask_price

            # Get fresh price for order
            vector_ticks = get_decrease_vector(side, offset_ticks)
            order_price = top_price + vector_ticks * self._symbol_info[exchange_role].tick

            # adjust to rest unfilled total amount
            limit_order_qty = min(self.context.order_qty, max_quantity_to_fill)
            # adjust with exchange minimums and futures contracts

            await self._place_order_safe(
                exchange_role,
                side,
                limit_order_qty,
                order_price,
                is_market=False,
                tag=f"{exchange_role}:{side.name}:limit"
            )


    async def _sync_exchange_order(self, exchange_role: ExchangeRoleType) -> Order | None:
        """Get current order from exchange, track updates."""
        pos = self.context.positions[exchange_role]

        if pos.last_order:
            updated_order = await self._exchanges[exchange_role].private.get_active_order(
                self.context.symbol, pos.last_order.order_id
            )
            await self._track_order_execution(exchange_role, updated_order)

    async def _handle_idle(self):
        await super()._handle_idle()
        self._transition('syncing')

    async def _cancel_order_process(self, exchange_role: ExchangeRoleType) -> bool:
        """Determine if current order should be cancelled due to price movement."""
        curr_order = self.context.positions[exchange_role].last_order
        settings = self.context.settings[exchange_role]

        if not curr_order or settings.use_market:
            return False

        side = curr_order.side
        book_ticker = self._get_book_ticker(exchange_role)
        order_price = curr_order.price

        top_price = book_ticker.bid_price if side == Side.BUY else book_ticker.ask_price
        tick_difference = abs((order_price - top_price) / self._symbol_info[exchange_role].tick)
        should_cancel = tick_difference > settings.tick_tolerance[exchange_role]

        if should_cancel:
            self.logger.info(
                f"⚠️ Price moved significantly. Current {side.name}: {top_price}, "
                f"Our price: {order_price}")

            await self._cancel_order_safe(exchange_role, order_id=curr_order.order_id)


        return should_cancel

    async def _track_order_execution(self, exchange_role: ExchangeRoleType, order: Optional[Order]=None):
        """Process filled order and update context for specific exchange side."""

        if not order:
            return

        try:
            pos_change = self.context.positions[exchange_role].update_position_with_order(order)

            self.logger.info(f"📊 Updated position on {exchange_role}",
                             side=order.side.name,
                             qty_before=pos_change.qty_before,
                             price_before=pos_change.price_before,
                             qty_after=pos_change.qty_after,
                             price_after=pos_change.price_after)

        except PositionError as pe:
            self.logger.error(f"🚫 Position update error on {exchange_role} after order fill {self._tag}",
                              error=str(pe))
        finally:
            self.context.save()


    def _get_exchange_quantity_remaining(self, exchange_role: PrimaryExchangeRole) -> float:
        """Get remaining quantity to fill for the given side."""
        filled_qty = self.context.positions[exchange_role].qty

        # filling direction
        if exchange_role == 'source':
            quantity = max(0.0, self.context.total_quantity - filled_qty)
        else: # releasing direction
            quantity = filled_qty

        if quantity < self._symbol_info[exchange_role].min_base_quantity:
            return 0.0

        return quantity

    # Enhanced state machine handlers
    async def _handle_syncing(self):
        """Sync order status from both exchanges in parallel."""
        sync_tasks = [
            self._sync_exchange_order(exchange_role) for exchange_role in self.context.positions.keys()
        ]
        await asyncio.gather(*sync_tasks)
        self._transition('analyzing')

    async def _handle_analyzing(self):
        """Analyze current state and determine next action."""
        # Check completion first (highest priority)

        await self._rebalance()

        self._transition('managing_orders')

    async def _handle_managing_orders(self):
        """Manage limit orders (cancel/place) for both sides."""
        management_tasks = [

        ]
        await asyncio.gather(*management_tasks)
        self._transition('syncing')  # Return to monitoring

    async def _handle_completing(self):
        """Finalize task execution."""
        await self.cancel_all()
        self._transition('completed')

    # Base state handlers (implementing BaseStateMixin states)
    async def _handle_cancelled(self):
        """Handle cancelled state."""
        self.logger.info("🚫 Delta neutral task cancelled")
        await self.cancel_all()
        await super().complete()


    async def _manage_positions(self, exchange_role: PrimaryExchangeRole):
        """Manage limit orders for one side."""
        # Skip if no quantity to fill

        if (not self._exchange_trading_allowed[exchange_role] or
                self._get_exchange_quantity_remaining(exchange_role) == 0):
            return

        # Cancel if price moved too much,
        is_cancelled = await self._cancel_order_process(exchange_role)
        if is_cancelled:
            # place order with new cycle
            return

        # place order if none exists
        await self._place_order_process(exchange_role)

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
            'managing_orders': self._handle_managing_orders,
            'completing': self._handle_completing,
        }
