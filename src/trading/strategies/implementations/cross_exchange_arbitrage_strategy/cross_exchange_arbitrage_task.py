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
from .asset_transfer_module import AssetTransferModule, TransferRequest
from .unified_position import Position, PositionError

from trading.strategies.implementations.base_strategy.base_strategy import BaseStrategyContext, BaseStrategyTask
from trading.analysis.cross_arbitrage_ta import (CrossArbitrageDynamicSignalGenerator,
                                                 CrossArbitrageFixedSignalGenerator,
                                                 CrossArbitrageSignalConfig, CrossArbitrageSignal)

type PrimaryExchangeRole = Literal['source', 'dest']

type ExchangeRoleType = PrimaryExchangeRole | Literal['hedge']

TRANSFER_REFRESH_SECONDS = 30

class ExchangeData(Struct):
    exchange: Optional[ExchangeEnum] = None
    tick_tolerance: int = 0
    ticks_offset: int = 0
    use_market: bool = False
    order_id: Optional[OrderId] = None

class ActiveTransferState(Struct):
    transfer_id: Optional[str] = None
    exchange_enum: Optional[ExchangeEnum] = None

CROSS_EXCHANGE_ARBITRAGE_TASK_TYPE = "cross_exchange_arbitrage_strategy"

class CrossExchangeArbitrageTaskContext(BaseStrategyContext, kw_only=True):
    """Context for delta neutral execution.

    Extends SingleExchangeTaskContext with delta-neutral specific fields for tracking
    partial fills on both sides.
    """
    # Required fields  
    symbol: Symbol

    # Override default task type
    task_type: str = CROSS_EXCHANGE_ARBITRAGE_TASK_TYPE
    # Optional fields with defaults
    total_quantity: Optional[float] = None
    order_qty: Optional[float] = None  # size of each order for limit orders

    # Complex fields with factory defaults
    positions: Dict[ExchangeRoleType, Position] = msgspec.field(
        default_factory=lambda: {'source': Position(side=Side.BUY, mode='accumulate'),
                                 'dest': Position(side=Side.BUY, mode='release'),
                                 'hedge': Position(side=Side.SELL, mode='hedge')})
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

    active_transfer: Optional[ActiveTransferState] = None


    @property
    def tag(self) -> str:
        """Generate logging tag based on task_id and symbol."""
        return f"{self.task_type}.{self.symbol.base}_{self.symbol.quote}"

    @staticmethod
    def from_json(json_bytes: str) -> 'CrossExchangeArbitrageTaskContext':
        """Deserialize context from dict data."""
        return msgspec.json.decode(json_bytes, type=CrossExchangeArbitrageTaskContext)



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
                 context: CrossExchangeArbitrageTaskContext,
                 logger: HFTLoggerInterface = None,
                 **kwargs):
        """Initialize cross-exchange hedged arbitrage task.
        """
        super().__init__(context, logger, **kwargs)

        # DualExchange instances for each side (unified public/private)
        self._exchanges: Dict[ExchangeRoleType, DualExchange] = self.create_exchanges()

        self._current_order: Dict[ExchangeRoleType, Optional[Order]] = {'source': None, 'dest': None, 'hedge': None}
        self._symbol_info: Dict[ExchangeRoleType, Optional[SymbolInfo]] = {'source': None, 'dest': None, 'hedge': None}
        self._exchange_trading_allowed: Dict[ExchangeRoleType, bool] = {'source': False, 'dest': False}


        # Initialize dynamic threshold TA module
        # TODO: tmp disabled
        USE_STATIC_TA = True
        if USE_STATIC_TA:
            self._ta_module = CrossArbitrageFixedSignalGenerator(
                entry_threshold=-0.75,
                exit_threshold=-0.5,
                total_fees=0.2
            )
        else:
            self._ta_module = CrossArbitrageDynamicSignalGenerator(
                symbol=context.symbol,
                config=context.signal_config,
                logger=logger
            )

        source_exchange = self.context.settings['source'].exchange
        dest_exchange = self.context.settings['dest'].exchange
        # Create transfer module
        self._transfer_module = AssetTransferModule(
            exchanges={source_exchange: self._exchanges['source'].private, # type: ignore
                       dest_exchange: self._exchanges['dest'].private},
            logger=self.logger
        )

        self.transfer_request: Optional[TransferRequest] = None
        self._transfer_task: Optional[asyncio.Task] = None
        self.context.status = 'inactive'

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

        self.context.status = 'inactive' # prevent step() while not loaded

        # Initialize DualExchanges in parallel for HFT performance
        init_tasks = []
        for exchange_type, exchange in self._exchanges.items():
            private_channels = [PrivateWebsocketChannelType.POSITION] if exchange.is_futures else [PrivateWebsocketChannelType.BALANCE]
            init_tasks.append(
                exchange.initialize(
                    [self.context.symbol],
                    public_channels=[PublicWebsocketChannelType.BOOK_TICKER],
                    # all balance/position sync is synthetic based on order fills
                    private_channels=[PrivateWebsocketChannelType.ORDER] + private_channels
                )
            )
        await asyncio.gather(*init_tasks)
        print("STARTED EXCHANGES")
        # init symbol info, reload active orders
        await asyncio.gather(self._load_symbol_info(),
                             self._force_load_active_orders(),
                             self._load_initial_balances())

        # Initialize TA module for dynamic thresholds
        await self._ta_module.initialize()

        # if there is an active transfer, restore state
        if self.context.active_transfer:
            self.transfer_request = await self._transfer_module.get_transfer_request(
                self.context.active_transfer.exchange_enum,
                self.context.active_transfer.transfer_id
            )

            if not self.transfer_request:
                self.logger.warning(f"⚠️ Could not restore active transfer - remove")
                self.context.active_transfer = None
                self.context.set_save_flag()
            else:
                self.logger.warning(f"Waiting for active transfer to complete")
                await self._start_transfer_monitor()

        self.logger.info("✅ Dynamic threshold TA module initialized",
                         entry_percentile=self.context.signal_config.entry_percentile,
                         exit_percentile=self.context.signal_config.exit_percentile,
                         lookback_hours=self.context.signal_config.lookback_hours)

        self.context.status = 'active'

    async def _start_transfer_monitor(self):
        self._transfer_task = asyncio.create_task(self._update_transfer_status())

    async def _stop_transfer_monitor(self):
        if self._transfer_task:
            self._transfer_task.cancel()
            try:
                await self._transfer_task
            except asyncio.CancelledError:
                pass
            self._transfer_task = None

    async def _update_transfer_status(self):
        while self.transfer_request:
            if not self.transfer_request.in_progress:
                break
            try:
                self.transfer_request = await self._transfer_module.update_transfer_request(self.transfer_request)
                if not self.transfer_request:
                    break
            except Exception as e:
                self.logger.error(f"❌ Error updating transfer status: {e}")
                break
            await asyncio.sleep(TRANSFER_REFRESH_SECONDS)

    async def _load_initial_balances(self):
        pass
        for exchange_role, exchange in self._exchanges.items():
            current_position = self.context.positions[exchange_role]
            if exchange.is_futures:
                position = exchange.private.positions.get(self.context.symbol, None)
                if position:
                    current_position.qty = position.qty_base
                    current_position.price =position.entry_price
                    self.logger.info(f"🔄 Loaded initial futures position for {exchange_role} {current_position}")
                else:
                    self.logger.info(f"ℹ️ No existing futures position for {exchange_role}")
                    current_position.reset()
            else:
                balance = await exchange.private.get_asset_balance(self.context.symbol.base)
                if abs(current_position.qty - balance.available) > 1e-8:
                    current_position.qty = balance.available
                    current_position.side = Side.BUY
                    book_ticker = exchange.public.book_ticker.get(self.context.symbol)

                    # guess price from bid if not set
                    if current_position.price == 0:
                        current_position.price = book_ticker.bid_price
                    self.logger.info(f"🔄 Loaded initial spot position for {exchange_role} {current_position}")

                if exchange_role == "dest":
                    current_position.target_qty = min(self.context.total_quantity, current_position.qty)
                else:
                    current_position.target_qty = self.context.total_quantity

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

            await exchange.public.get_book_ticker(self.context.symbol)

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

            # if signals:
            #     self.logger.info(f"🎯 Arbitrage signals: {signals}",
            #                      current_spread=f"{signal.current_spread:.4f}%",
            #                      entry_threshold=f"{signal.entry_threshold:.4f}% (dynamic)",
            #                      exit_threshold=f"{signal.exit_threshold:.4f}% (dynamic)")

            return signals

        except Exception as e:
            self.logger.error(f"❌ Error checking arbitrage signal: {e}")
            return []

    async def _cancel_order_safe(
            self,
            exchange_role: ExchangeRoleType,
            order_id: OrderId,
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

    def _get_min_base_qty(self, exchange_role: ExchangeRoleType) -> float:
        price = self._get_book_ticker(exchange_role).bid_price  # approx. price to calc base qty for MEXC

        return self._symbol_info[exchange_role].get_abs_min_quantity(price)

    async def _rebalance_hedge(self) -> bool:
        """Check if there is an imbalance for specific side and rebalance immediately."""
        source_qty = self.context.positions['source'].qty
        dest_qty = self.context.positions['dest'].qty
        hedge_qty = self.context.positions['hedge'].qty

        external_qty = 0.0 # qty that is being transferred between exchanges

        # has active transfer - inter exchange liquidity keep hedge
        if self.transfer_request and self.transfer_request.asset == self.context.symbol.base:
            external_qty = self.transfer_request.qty

        delta = (source_qty + dest_qty + external_qty) - hedge_qty

        if abs(delta) < self._get_min_base_qty('hedge'):
            return False

        self.logger.info(f"⚖️ Detected imbalance: delta={delta:.8f}, "
                         f"source={source_qty}, dest={dest_qty}, hedge={hedge_qty}")
        if delta > 0:
            await self._place_order_safe('hedge', Side.SELL, abs(delta),
                                         self._get_book_ticker('hedge').bid_price,
                                         is_market=True, tag="⏬ Increase Short Hedge")
        else:
            await self._place_order_safe('hedge', Side.BUY, abs(delta),
                                         self._get_book_ticker('hedge').ask_price,
                                         is_market=True, tag="⏫ Decrease Short Hedge")

        return True

    async def _manage_order_place(self, exchange_role: PrimaryExchangeRole):
        """
        Place limit order to top-offset price or market order.
        Hedge should be rebalanced relative to source/dest.
        """

        if not self._exchange_trading_allowed[exchange_role]:
            return

        max_quantity_to_fill = self.context.positions[exchange_role].get_remaining_qty(self._symbol_info[exchange_role].min_base_quantity)
        if max_quantity_to_fill == 0:
            return

        curr_book_ticker = self._get_book_ticker(exchange_role)
        settings = self.context.settings[exchange_role]
        offset_ticks = settings.ticks_offset
        side = Side.BUY if exchange_role == 'source' else Side.SELL

        if settings.use_market:
            hedge_book_ticker = self._get_book_ticker('hedge')

            max_hedge_top_qty = hedge_book_ticker.bid_quantity if side == Side.BUY else hedge_book_ticker.ask_quantity
            max_curr_top_qty = curr_book_ticker.ask_quantity if side == Side.BUY else curr_book_ticker.bid_quantity
            market_order_qty = min(max_hedge_top_qty, max_curr_top_qty, max_quantity_to_fill)

            if market_order_qty < self._get_min_base_qty(exchange_role):
                self.logger.info(f"⚠️ Not enough top order book quantity to place market order on {exchange_role}",
                                 available_qty=market_order_qty,
                                 min_required=self._get_min_base_qty(exchange_role))
                return

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
            self.context.set_save_flag()

    # Enhanced state machine handlers
    async def _sync_positions(self):
        """Sync order status from exchanges in parallel."""
        sync_tasks = [
            self._sync_exchange_order(exchange_role) for exchange_role in self.context.positions.keys()
        ]
        await asyncio.gather(*sync_tasks)

    def _is_allowed_by_position_balance(self, exchange_role: PrimaryExchangeRole) -> bool:
        """Check if trading is allowed based on position balances."""
        source_pos = self.context.positions['source']
        dest_pos = self.context.positions['dest']

        if source_pos.qty == dest_pos.qty == 0:
            return True

        if exchange_role == 'source':
            return source_pos.qty < dest_pos.qty
        else:
            return dest_pos.qty < source_pos.qty

    async def _manage_position(self, exchange_role: PrimaryExchangeRole):
        """Manage limit orders for one side."""
        # Skip if no quantity to fill
        allowed_to_trade = self._exchange_trading_allowed[exchange_role]
        is_fulfilled = self.context.positions[exchange_role].is_fulfilled(self._get_min_base_qty(exchange_role))
        # allowed_by_balance = self._is_allowed_by_position_balance(exchange_role)

        if not allowed_to_trade or is_fulfilled: #  or not allowed_by_balance
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

    async def _manage_transfer_between_exchanges(self) -> bool:
        try:
            request = self.transfer_request

            symbol = self.context.symbol
            source = self.context.settings['source'].exchange
            dest = self.context.settings['dest'].exchange
            dest_pos = self.context.positions['dest']
            source_pos = self.context.positions['source']

            if request: # has active transfer
                if request.in_progress:
                    return True
                else: # has completed or failed
                    if request.completed:
                        self.logger.info(f"🔄 Transfer completed: {request.qty} {request.asset}, resuming trading")
                        if request.asset == symbol.base:
                            dest_pos.reset(request.qty)
                            source_pos.reset(self.context.total_quantity)
                        else:
                            source_pos.reset(self.context.total_quantity)
                            dest_pos.reset(0.0)

                    else:
                        self.logger.error(f"❌ Transfer failed, check manually {request}")


                    self.transfer_request = None
                    self.context.active_transfer = None
                    self.context.set_save_flag()
                    await self._stop_transfer_monitor()
                    return False
            else:

                transfer_request = None
                transfer_exchange_enum = None
                curr_side = None

                if source_pos.is_fulfilled(self._get_min_base_qty('source')):
                    base_balance = await self._exchanges['source'].private.get_asset_balance(symbol.base, force=True)

                    transfer_exchange_enum = source
                    curr_side = 'source'

                    qty = min(source_pos.qty, base_balance.available)

                    transfer_request = await self._transfer_module.transfer_asset(symbol.base, source, dest, qty)

                    self.logger.info(f"🚀 Starting transfer of {qty} {symbol.base} from {source.name} to {dest.name}")
                elif dest_pos.is_fulfilled(self._get_min_base_qty('dest')):
                    quote_balance = await self._exchanges['dest'].private.get_asset_balance(symbol.quote, force=True)

                    transfer_exchange_enum = dest
                    curr_side = 'dest'

                    qty = min(dest_pos.acc_quote_qty, quote_balance.available)

                    transfer_request = await self._transfer_module.transfer_asset(symbol.quote, dest, source, qty)

                    self.logger.info(f"🚀 Started transfer of {qty} {symbol.quote} from {dest.name} to {source.name}")

                if transfer_request and curr_side:
                    self.transfer_request = transfer_request
                    self.context.active_transfer = ActiveTransferState(
                        transfer_id=self.transfer_request.withdrawal_id,
                        exchange_enum=transfer_exchange_enum
                    )

                    if curr_side == 'source':
                        source_pos.reset()
                    else:
                        dest_pos.reset()


                    self.context.set_save_flag()
                    await self._start_transfer_monitor()
                    return True

        except Exception as e:
            self.logger.error(f"❌ Error managing transfer between exchanges: {e}")
        finally:
            return False

    async def step(self):
        if self.context.status != 'active':
            await asyncio.sleep(1)
            return
        # Check transfer completion first
        if await self._manage_transfer_between_exchanges():
            return

        await self._sync_positions()

        await self._manage_arbitrage_signals()

        await self._manage_positions()

        await self._rebalance_hedge()

    async def cleanup(self):
        await super().cleanup()

        # Cleanup TA module
        await self._ta_module.cleanup()

        # Close exchange connections
        close_tasks = []
        for exchange in self._exchanges.values():
            close_tasks.append(exchange.close())
        await asyncio.gather(*close_tasks, self._stop_transfer_monitor())
