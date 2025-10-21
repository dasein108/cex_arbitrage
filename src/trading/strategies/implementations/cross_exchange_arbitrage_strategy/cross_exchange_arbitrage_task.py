import asyncio
from typing import Optional, Type, Dict, Literal, List
import msgspec
from msgspec import Struct
from exchanges.dual_exchange import DualExchange
from config.config_manager import get_exchange_config
from exchanges.structs import Order, SymbolInfo, ExchangeEnum, Symbol, OrderId, BookTicker
from exchanges.structs.common import Side
from infrastructure.exceptions.exchange import OrderNotFoundError
from infrastructure.logging import HFTLoggerInterface
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, PrivateWebsocketChannelType

from utils import get_decrease_vector
from .unfied_position import Position, PositionError

from trading.strategies.implementations.base_strategy.base_strategy import BaseStrategyContext, BaseStrategyTask
from trading.analysis.cross_arbitrage_ta import (CrossArbitrageDynamicSignalGenerator,
                                                 CrossArbitrageFixedSignalGenerator,
                                                 CrossArbitrageSignalConfig, CrossArbitrageSignal)

type PrimaryExchangeRole = Literal['source', 'dest']

type ExchangeRoleType = PrimaryExchangeRole | Literal['hedge']


class ExchangeData(Struct):
    exchange: ExchangeEnum
    tick_tolerance: int = 0
    ticks_offset: int = 0
    use_market: bool = False
    order_id: Optional[OrderId] = None


class CrossExchangeArbitrageTaskContext(BaseStrategyContext, kw_only=True):
    """Context for delta neutral execution.

    Extends SingleExchangeTaskContext with delta-neutral specific fields for tracking
    partial fills on both sides.
    """
    # Required fields  
    symbol: Symbol

    # Override default task type
    task_type: str = "cross_exchange_arbitrage_strategy"

    # Optional fields with defaults
    total_quantity: Optional[float] = None
    order_qty: Optional[float] = None  # size of each order for limit orders

    # Complex fields with factory defaults
    positions: Dict[ExchangeRoleType, Position] = msgspec.field(
        default_factory=lambda: {'source': Position(), 'dest': Position(), 'hedge': Position()})
    settings: Dict[ExchangeRoleType, ExchangeData] = msgspec.field(
        default_factory=lambda: {'source': ExchangeData(), 'dest': ExchangeData(), 'hedge': ExchangeData()})

    # Dynamic threshold configuration for TA module
    signal_config: CrossArbitrageSignalConfig = msgspec.field(default_factory=lambda: CrossArbitrageSignalConfig(
        lookback_hours=24,  # Historical data lookback
        refresh_minutes=30,  # How often to refresh thresholds
        entry_percentile=10,  # Top 10% of spreads for entry
        exit_percentile=85,  # 85th percentile for exit
        total_fees=0.2  # Total round-trip fees percentage
    ))

    @property
    def tag(self) -> str:
        """Generate logging tag based on task_id and symbol."""
        return f"{self.task_type}_{self.symbol}"


class CrossExchangeArbitrageTask(BaseStrategyTask[CrossExchangeArbitrageTaskContext]):
    """State machine for executing delta-neutral trading strategies.

    Executes simultaneous buy and sell orders across two exchanges to maintain
    market-neutral positions while capturing spread opportunities.
    """

    name: str = "DeltaNeutralTask"

    @property
    def context_class(self) -> Type[CrossExchangeArbitrageTaskContext]:
        """Return the delta-neutral context class."""
        return CrossExchangeArbitrageTaskContext

    def _build_tag(self) -> None:
        """Build logging tag with exchange-specific fields."""
        self._tag = f'{self.name}_{self.context.symbol}'

    def __init__(self,
                 logger: HFTLoggerInterface,
                 context: CrossExchangeArbitrageTaskContext,
                 **kwargs):
        """Initialize cross-exchange hedged arbitrage task.
        """
        super().__init__(logger, context, **kwargs)

        # DualExchange instances for each side (unified public/private)
        self._exchanges: Dict[ExchangeRoleType, DualExchange] = self.create_exchanges()

        self._current_order: Dict[ExchangeRoleType, Optional[Order]] = {'source': None, 'dest': None, 'hedge': None}
        self._symbol_info: Dict[ExchangeRoleType, Optional[SymbolInfo]] = {'source': None, 'dest': None, 'hedge': None}
        self._exchange_trading_allowed: Dict[ExchangeRoleType, bool] = {'source': False, 'dest': False}

        # Initialize dynamic threshold TA module
        # TODO: tmp disabled
        # self._ta_module = CrossArbitrageDynamicSignalGenerator(
        #     symbol=context.symbol,
        #     config=context.signal_config,
        #     logger=logger
        # )

        self._ta_module = CrossArbitrageFixedSignalGenerator(
            entry_threshold=-0.5,
            exit_threshold=-0.5,
            total_fees=0.2
        )

    def create_exchanges(self):
        exchanges = {}
        for exchange_type, settings in self.context.settings.items():
            config = get_exchange_config(settings.exchange.value)
            exchanges[exchange_type] = DualExchange.get_instance(config, self.logger)

        return exchanges

    async def start(self):
        if self.context is None:
            raise ValueError("Cannot start task: context is None (likely deserialization failed)")

        await super().start()

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
        await asyncio.gather(self._load_symbol_info(), self._force_load_active_orders())

        # Initialize TA module for dynamic thresholds
        await self._ta_module.initialize()
        self.logger.info("✅ Dynamic threshold TA module initialized",
                         entry_percentile=self.context.signal_config.entry_percentile,
                         exit_percentile=self.context.signal_config.exit_percentile,
                         lookback_hours=self.context.signal_config.lookback_hours)

    async def pause(self):
        """Pause task and cancel any active order."""
        await super().pause()
        await self.cancel_all()

    # Base state handlers (implementing BaseStateMixin states)
    async def cancel(self):
        """Handle cancelled state."""
        await super().cancel()
        await self.cancel_all()

    async def stop(self):
        """Handle stopped state."""
        await super().stop()
        await self.cancel_all()

    async def cancel_all(self):
        cancel_tasks = []
        for exchange_role, pos in self.context.positions.items():
            if pos.last_order:
                cancel_tasks.append(self._cancel_order_safe(exchange_role,
                                                            pos.last_order.order_id,
                                                            f"cancel_all"))

        canceled = await asyncio.gather(*cancel_tasks)

        self.logger.info(f"🛑 Canceled all orders", orders=str(canceled))

    async def _force_load_active_orders(self):
        for exchange_role, exchange in self._exchanges.items():
            # pos = self.context.positions[exchange_role]
            last_order = self.context.positions[exchange_role].last_order
            if last_order:
                try:
                    order = await exchange.private.fetch_order(last_order.symbol, last_order.order_id)
                except OrderNotFoundError as e:
                    self.logger.warning(f"⚠️ Could not find existing order '{last_order}' on {exchange_role} "
                                        f"during reload: {e}")
                    order = None

                self._track_order_execution(exchange_role, order)

    async def _sync_exchange_order(self, exchange_role: ExchangeRoleType) -> Order | None:
        """Get current order from exchange, track updates."""
        pos = self.context.positions[exchange_role]

        if pos.last_order:
            updated_order = await self._exchanges[exchange_role].private.get_active_order(
                self.context.symbol, pos.last_order.order_id
            )
            self._track_order_execution(exchange_role, updated_order)

    async def _load_symbol_info(self, force=False):
        for exchange_type, exchange in self._exchanges.items():
            if force:
                await exchange.public.load_symbols_info()

            self._symbol_info[exchange_type] = exchange.public.symbols_info[self.context.symbol]

    def _get_book_ticker(self, exchange_role: ExchangeRoleType) -> BookTicker:
        """Get current best price from public exchange."""
        book_ticker = self._exchanges[exchange_role].public.book_ticker[self.context.symbol]
        return book_ticker

    def _check_arbitrage_signal(self) -> List[CrossArbitrageSignal]:
        """
        Check for arbitrage entry/exit signals using dynamic thresholds.
        
        Returns:
            Tuple of (signal, spread_data) where signal is 'enter', 'exit', or 'none'
        """

        try:
            # Get current order books from all exchanges
            source_book = self._get_book_ticker('source')  # MEXC spot
            dest_book = self._get_book_ticker('dest')  # Gate.io spot
            hedge_book = self._get_book_ticker('hedge')  # Gate.io futures

            # TODO: position duration disabled for now
            # # Check if we have positions open
            # position_open = any(pos.qty > 0 for pos in self.context.positions.values())
            #
            # # Calculate position duration if open
            # position_duration_minutes = 0.0
            # if position_open:
            #     # Find the earliest position entry time
            #     earliest_entry = None
            #     for pos in self.context.positions.values():
            #         if pos.qty > 0 and pos.last_order and pos.last_order.create_time:
            #             if earliest_entry is None or pos.last_order.create_time < earliest_entry:
            #                 earliest_entry = pos.last_order.create_time
            #
            #     if earliest_entry:
            #         from datetime import datetime, timezone
            #         position_duration_minutes = (datetime.now(timezone.utc) - earliest_entry).total_seconds() / 60

            # Generate signal using dynamic thresholds
            signal = self._ta_module.generate_signal(
                source_book=source_book,
                dest_book=dest_book,
                hedge_book=hedge_book,
            )

            signals = signal.signals
            # Log signal with dynamic threshold info

            if signals:
                self.logger.info(f"🎯 Arbitrage signals: {signals}",
                                 current_spread=f"{signal.current_spread:.4f}%",
                                 entry_threshold=f"{signal.entry_threshold:.4f}% (dynamic)",
                                 exit_threshold=f"{signal.exit_threshold:.4f}% (dynamic)")

            return signals

        except Exception as e:
            self.logger.error(f"❌ Error checking arbitrage signal: {e}")
            return []

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

        self._track_order_execution(exchange_role, order)
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

            self._track_order_execution(exchange_role, order)

            self.logger.info(f"📈 Placed {tag_str} order",
                             order_id=order.order_id,
                             order=str(order))

            return order

        except Exception as e:
            self.logger.error(f"🚫 Failed to place order {tag_str}", error=str(e))
            return None

    async def _rebalance_hedge(self) -> bool:
        """Check if there is an imbalance for specific side and rebalance immediately."""
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
                                         is_market=True, tag="⏫ Rebalance Hedge")
        else:
            await self._place_order_safe('hedge', Side.SELL, abs(delta),
                                         self._get_book_ticker('hedge').ask_price,
                                         is_market=True, tag="⏬ Rebalance Hedge")

        return True

    async def _manage_order_place(self, exchange_role: PrimaryExchangeRole):
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

    async def _manage_order_cancel(self, exchange_role: ExchangeRoleType) -> bool:
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
        should_cancel = tick_difference > settings.tick_tolerance

        if should_cancel:
            self.logger.info(
                f"⚠️ Price moved significantly. Current {side.name}: {top_price}, "
                f"Our price: {order_price}")

            await self._cancel_order_safe(exchange_role, order_id=curr_order.order_id)

        return should_cancel

    def _track_order_execution(self, exchange_role: ExchangeRoleType, order: Optional[Order] = None):
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
        else:  # releasing direction
            quantity = filled_qty

        if quantity < self._symbol_info[exchange_role].min_base_quantity:
            return 0.0

        return quantity

    # Enhanced state machine handlers
    async def _sync_positions(self):
        """Sync order status from exchanges in parallel."""
        sync_tasks = [
            self._sync_exchange_order(exchange_role) for exchange_role in self.context.positions.keys()
        ]
        await asyncio.gather(*sync_tasks)

    async def _manage_position(self, exchange_role: PrimaryExchangeRole):
        """Manage limit orders for one side."""
        # Skip if no quantity to fill

        if (not self._exchange_trading_allowed[exchange_role] or
                self._get_exchange_quantity_remaining(exchange_role) == 0):
            return

        # Cancel if price moved too much,
        is_cancelled = await self._manage_order_cancel(exchange_role)
        if is_cancelled:
            # place order with new cycle
            return

        # place order if none exists
        await self._manage_order_place(exchange_role)

    async def _manage_positions(self):
        manage_tasks = [
            self._manage_position('source'),
            self._manage_position('dest')
        ]
        await asyncio.gather(*manage_tasks)

    async def _manage_arbitrage_signals(self):
        # Check arbitrage signals using dynamic thresholds
        signals = self._check_arbitrage_signal()
        source_allowed = 'enter' in signals
        dest_allowed = 'exit' in signals

        if self._exchange_trading_allowed['source'] != source_allowed:
            self._exchange_trading_allowed['source'] = source_allowed
            state = "🟢 enabled" if source_allowed else "⛔️ disabled"
            self.logger.info(f"🔔 Source trading {state} based on signal")

        if self._exchange_trading_allowed['dest'] != dest_allowed:
            self._exchange_trading_allowed['dest'] = dest_allowed
            state = "🟢 enabled" if dest_allowed else "⛔️ disabled"
            self.logger.info(f"🔔 Dest trading {state} based on signal")

    async def step(self):
        await self._sync_positions()

        await self._manage_arbitrage_signals()

        await self._rebalance_hedge()

        await self._manage_positions()

    async def cleanup(self):
        await super().cleanup()

        # Cleanup TA module
        await self._ta_module.cleanup()

        # Close exchange connections
        close_tasks = []
        for exchange in self._exchanges.values():
            close_tasks.append(exchange.close())
        await asyncio.gather(*close_tasks)
