import asyncio
from typing import Optional, Type, Dict, Literal, List, TypeAlias
import msgspec
from msgspec import Struct
from exchanges.dual_exchange import DualExchange
from config.config_manager import get_exchange_config
from exchanges.structs import Order, SymbolInfo, ExchangeEnum, Symbol, OrderId, BookTicker
from exchanges.structs.common import Side
from infrastructure.exceptions.exchange import OrderNotFoundError, InsufficientBalanceError
from infrastructure.logging import HFTLoggerInterface
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, PrivateWebsocketChannelType

from utils import get_decrease_vector
from trading.strategies.implementations.cross_exchange_arbitrage_strategy.asset_transfer_module import AssetTransferModule, TransferRequest
from trading.strategies.implementations.cross_exchange_arbitrage_strategy.unified_position import Position, PositionError

from trading.strategies.implementations.base_strategy.base_strategy import BaseStrategyContext, BaseStrategyTask

PrimaryExchangeRole: TypeAlias = Literal['source', 'dest']

ExchangeRoleType: TypeAlias = PrimaryExchangeRole | Literal['hedge']

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

    current_role: Optional[PrimaryExchangeRole] = None

    # Complex fields with factory defaults
    positions: Dict[ExchangeRoleType, Position] = msgspec.field(
        default_factory=lambda: {'source': Position(side=Side.BUY, mode='accumulate'),
                                 'dest': Position(side=Side.BUY, mode='release'),
                                 'hedge': Position(side=Side.SELL, mode='hedge')})
    settings: Dict[ExchangeRoleType, ExchangeData] = msgspec.field(
        default_factory=lambda: {'source': ExchangeData(), 'dest': ExchangeData(), 'hedge': ExchangeData()})


    transfer_request: Optional[TransferRequest] = None

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

        # Use unified signal generator with proven backtest logic
        from trading.research.cross_arbitrage.arbitrage_analyzer import ArbitrageAnalyzer

        # Initialize candle-based analyzer like in hedged backtest
        self.analyzer = ArbitrageAnalyzer()
        
        # Initialize historical spreads for signal generation
        self.historical_spreads = {
            'mexc_vs_gateio_futures': [],
            'gateio_spot_vs_futures': []
        }
        
        # Initialize signal generator (will be populated from candles)
        self._signal_generator = None
        self._candle_data_loaded = False

        source_exchange = self.context.settings['source'].exchange
        dest_exchange = self.context.settings['dest'].exchange
        # Create transfer module
        self._transfer_module = AssetTransferModule(
            exchanges={source_exchange: self._exchanges['source'].private,  # type: ignore
                       dest_exchange: self._exchanges['dest'].private},
            logger=self.logger
        )

        self._transfer_task: Optional[asyncio.Task] = None
        self.context.status = 'inactive'

    def create_exchanges(self):
        """Create exchanges with optimized config loading for HFT performance."""
        exchanges = {}
        
        # Pre-load all unique exchange configs to avoid redundant calls
        unique_exchanges = set(settings.exchange.value for settings in self.context.settings.values())
        exchange_configs = {
            exchange_name: get_exchange_config(exchange_name) 
            for exchange_name in unique_exchanges
        }
        
        # Create exchanges using cached configs
        for exchange_type, settings in self.context.settings.items():
            config = exchange_configs[settings.exchange.value]
            exchanges[exchange_type] = DualExchange.get_instance(config, self.logger)

        return exchanges

    async def start(self):
        if self.context is None:
            raise ValueError("Cannot start task: context is None (likely deserialization failed)")

        await super().start()

        self.context.status = 'inactive'  # prevent step() while not loaded

        # Initialize DualExchanges in parallel for HFT performance
        init_tasks = []
        for exchange_type, exchange in self._exchanges.items():
            private_channels = [PrivateWebsocketChannelType.POSITION] if exchange.is_futures else [
                PrivateWebsocketChannelType.BALANCE]
            init_tasks.append(
                exchange.initialize(
                    [self.context.symbol],
                    public_channels=[PublicWebsocketChannelType.BOOK_TICKER],
                    # all balance/position sync is synthetic based on order fills
                    private_channels=[PrivateWebsocketChannelType.ORDER] + private_channels
                )
            )
        await asyncio.gather(*init_tasks)
        # init symbol info, reload active orders
        await asyncio.gather(self._load_symbol_info(),
                             self._force_load_active_orders(),
                             self._load_initial_balances())

        # Signal generator is ready to use immediately (no initialization needed)

        # if there is an active transfer, restore state
        transfer_request = self.context.transfer_request
        if transfer_request:
            transfer_request = await self._transfer_module.update_transfer_request(transfer_request)

            if not transfer_request:
                self.logger.warning(f"⚠️ Could not restore active transfer - remove")
                self.context.transfer_request = None
                self.context.set_save_flag()
            else:
                self.context.transfer_request = transfer_request
                self.logger.warning(f"Waiting for active transfer to complete")
                await self._start_transfer_monitor()

        self.logger.info("✅ Candle-based signal generation initialized")

        self.context.status = 'active'

    def _get_fees(self, exchange_role: ExchangeRoleType):
        return self._exchanges[exchange_role].private.get_fees(self.context.symbol)

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
        transfer_request = self.context.transfer_request

        while transfer_request:
            if not transfer_request.in_progress:
                break
            try:
                transfer_request = await self._transfer_module.update_transfer_request(transfer_request)
                self.context.transfer_request = transfer_request
                if not transfer_request:
                    break
            except Exception as e:
                self.logger.error(f"❌ Error updating transfer status: {e}")
                break
            await asyncio.sleep(TRANSFER_REFRESH_SECONDS)

    async def _load_initial_balances(self):
        hedge_position = self.context.positions['hedge']
        hedge_exchange = self._exchanges['hedge']

        # load real position with real price
        position = await hedge_exchange.private.get_position(self.context.symbol, force=True)

        if position:
            hedge_position.qty = position.qty_base
            hedge_position.price = position.entry_price
            self.logger.info(f"🔄 Loaded initial futures position for HEDGE {hedge_position}")
        else:
            self.logger.info(f"ℹ️ No existing futures position for HEDGE")
            hedge_position.reset(reset_pnl=False)

        exchange_role: ExchangeRoleType

        for exchange_role in ['source', 'dest']:
            exchange = self._exchanges[exchange_role]
            await exchange.private.load_balances()
            balance = await exchange.private.get_asset_balance(self.context.symbol.base)

            book_ticker = exchange.public.book_ticker.get(self.context.symbol)
            min_qty = self._symbol_info[exchange_role].get_abs_min_quantity(book_ticker.bid_price)
            pos = self.context.positions[exchange_role]

            if balance.available > min_qty:
                pos.qty = balance.available

            # fix price if not set
            if pos.qty > 0 and pos.price == 0:
                self.logger.info(f"⚠️ Price was not set for {exchange_role} position, guessing from order book")
                pos.price = book_ticker.bid_price if pos.mode == "accumulate" else book_ticker.ask_price

            self.logger.info(f"🔄 Loaded initial spot position for {exchange_role.upper()} {pos}")

        source = self.context.positions['source']
        dest = self.context.positions['dest']

        # guess role based on balances if not set
        if not self.context.current_role:
            if dest.qty == source.qty:
                self.logger.info(f"⚠️ Both sides have equal quantity, defaulting to SOURCE role")
                self.context.current_role = 'source'
            elif source.qty > dest.qty:
                self.logger.info(f"ℹ️ SOURCE has higher quantity, setting role to SOURCE")
                self.context.current_role = 'source'
            else:
                self.logger.info(f"ℹ️ DEST has higher quantity, setting role to DEST")
                self.context.current_role = 'dest'

        if self.context.current_role == 'dest':
            dest.target_qty = min(self.context.total_quantity,
                                  exchange.balances[self.context.symbol.base].available)
        else:
            source.target_qty = self.context.total_quantity


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

    async def _check_arbitrage_signal(self) -> List[str]:
        """
        Check for arbitrage entry/exit signals using dynamic thresholds.
        
        Returns:
            List of signals ('enter', 'exit', or empty)
        """

        try:
            # Get current order books from all exchanges
            source_book = self._get_book_ticker('source')  # MEXC spot
            dest_book = self._get_book_ticker('dest')  # Gate.io spot
            hedge_book = self._get_book_ticker('hedge')  # Gate.io futures
            
            # Log current prices for debugging
            self.logger.debug("📊 Current prices",
                            mexc_ask=source_book.ask_price,
                            mexc_bid=source_book.bid_price,
                            gateio_bid=dest_book.bid_price,
                            gateio_ask=dest_book.ask_price,
                            futures_bid=hedge_book.bid_price,
                            futures_ask=hedge_book.ask_price)


            # Load candle data if not already loaded
            await self._load_candle_data_if_needed()
            
            # Generate signal using current market data with historical context
            signal_result = self._generate_signal_from_current_data()
            
            # Convert signal to list format expected by existing code
            if signal_result.signal.value == 'ENTER':
                signals = ['enter']
            elif signal_result.signal.value == 'EXIT':
                signals = ['exit']
            else:
                signals = []
            
            # Log signal with reason for monitoring
            if signals:
                self.logger.info("🎯 Arbitrage signal generated",
                                 signals=signals,
                                 reason=signal_result.reason)
            else:
                self.logger.debug("⏸ No signal", reason=signal_result.reason)

            return signals

        except Exception as e:
            self.logger.error(f"❌ Error checking arbitrage signal: {e}")
            return []

    async def _load_candle_data_if_needed(self):
        """Load candle data and populate historical spreads for signal generation."""
        if self._candle_data_loaded:
            return
            
        try:
            self.logger.info("📥 Loading candle data for signal generation...")
            
            # Extract symbol from context (e.g., "F/USDT" -> "F_USDT")
            symbol_str = str(self.context.symbol).replace('/', '_')
            
            # Load 7 days of candle data like in hedged backtest
            df, _ = await self.analyzer.run_analysis(symbol_str, days=7)
            
            if df.empty:
                self.logger.warning("⚠️ No candle data received from analyzer")
                return
            
            # Validate required columns exist
            required_columns = ['mexc_vs_gateio_futures_arb', 'gateio_spot_vs_futures_arb']
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                self.logger.error(f"❌ Missing required columns in candle data: {missing_columns}")
                return
            
            # Populate historical spreads
            self.historical_spreads['mexc_vs_gateio_futures'] = df['mexc_vs_gateio_futures_arb'].tolist()
            self.historical_spreads['gateio_spot_vs_futures'] = df['gateio_spot_vs_futures_arb'].tolist()
            
            loaded_count = len(self.historical_spreads['mexc_vs_gateio_futures'])
            
            if loaded_count < 50:
                self.logger.warning(f"⚠️ Insufficient historical data: {loaded_count} points (need at least 50)")
            else:
                self.logger.info(f"✅ Loaded {loaded_count} historical spread data points for signal generation")
            
            self._candle_data_loaded = True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to load candle data: {e}")
            import traceback
            self.logger.debug(f"Full error traceback: {traceback.format_exc()}")

    def _generate_signal_from_current_data(self):
        """Generate signals using current market data with historical candle context."""
        
        # Ensure we have enough historical data
        if len(self.historical_spreads['mexc_vs_gateio_futures']) < 50:
            from trading.analysis.arbitrage_signals import ArbSignal, ArbStats
            from trading.analysis.structs import Signal
            return ArbSignal(
                signal=Signal.HOLD,
                mexc_vs_gateio_futures=ArbStats(0, 0, 0, 0),
                gateio_spot_vs_futures=ArbStats(0, 0, 0, 0),
                reason="Insufficient historical data"
            )
        
        # Calculate current spreads from live market data
        current_mexc_vs_gateio_futures = self._calculate_current_mexc_futures_spread()
        current_gateio_spot_vs_futures = self._calculate_current_gateio_spread()
        
        return calculate_arb_signals(
            mexc_vs_gateio_futures_history=self.historical_spreads['mexc_vs_gateio_futures'],
            gateio_spot_vs_futures_history=self.historical_spreads['gateio_spot_vs_futures'],
            current_mexc_vs_gateio_futures=current_mexc_vs_gateio_futures,
            current_gateio_spot_vs_futures=current_gateio_spot_vs_futures
        )
    
    def _calculate_current_mexc_futures_spread(self) -> float:
        """Calculate current MEXC vs Gate.io futures spread from live market data."""
        try:
            mexc_ticker = self._get_book_ticker('source')  # MEXC
            gateio_futures_ticker = self._get_book_ticker('hedge')  # Gate.io futures
            
            # Use exact backtest formula for consistency
            spread = (gateio_futures_ticker.bid_price - mexc_ticker.ask_price) / gateio_futures_ticker.bid_price * 100
            return spread
        except Exception as e:
            self.logger.error(f"❌ Error calculating MEXC futures spread: {e}")
            return 0.0
    
    def _calculate_current_gateio_spread(self) -> float:
        """Calculate current Gate.io spot vs futures spread from live market data."""
        try:
            gateio_spot_ticker = self._get_book_ticker('dest')  # Gate.io spot
            gateio_futures_ticker = self._get_book_ticker('hedge')  # Gate.io futures
            
            # Use exact backtest formula for consistency
            spread = (gateio_spot_ticker.bid_price - gateio_futures_ticker.ask_price) / gateio_spot_ticker.bid_price * 100
            return spread
        except Exception as e:
            self.logger.error(f"❌ Error calculating Gate.io spread: {e}")
            return 0.0

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
        except InsufficientBalanceError as ife:
            pos = self.context.positions[exchange_role]
            pos.acc_qty = pos.target_qty

            self.logger.error(f"🚫 Insufficient balance to place order {tag_str} | adjust position amount",
                              error=str(ife))
            return None
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

        external_qty = 0.0  # qty that is being transferred between exchanges

        # has active transfer - inter exchange liquidity keep hedge
        transfer_request = self.context.transfer_request

        if transfer_request and transfer_request.asset == self.context.symbol.base:
            external_qty = transfer_request.qty

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
        pos = self.context.positions[exchange_role]
        max_qty = pos.get_remaining_qty(self._symbol_info[exchange_role].min_base_quantity)
        max_quantity_to_fill = max_qty - max_qty * self._get_fees(exchange_role).taker_fee * 2
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
            pos = self.context.positions[exchange_role]
            pos_change = pos.update_position_with_order(order, fee=self._get_fees(exchange_role).taker_fee)

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
        if not allowed_to_trade or is_fulfilled:
            return

        # Cancel if price moved too much,
        is_cancelled = await self._manage_order_cancel(exchange_role)
        if is_cancelled:
            # place order with new cycle
            return

        # place order if none exists
        await self._manage_order_place(exchange_role)

    async def _manage_positions(self):
        role = self.context.current_role
        if role:
            await self._manage_position(role)
        else:
            self.logger.error("❌ Current role is not set, cannot manage positions")

    async def _manage_arbitrage_signals(self):
        # Check arbitrage signals using dynamic thresholds
        signals = await self._check_arbitrage_signal()
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

    async def _handle_completed_transfer(self, request: TransferRequest) -> None:
        """Handle a completed transfer and update positions accordingly."""
        symbol = self.context.symbol
        dest_pos = self.context.positions['dest']
        source_pos = self.context.positions['source']
        hedge_pos = self.context.positions['hedge']
        
        self.logger.info(f"🔄 Transfer completed: {request.qty} {request.asset}: {request} resuming trading")

        if request.asset == symbol.base:
            self.context.current_role = 'dest'
            await self._load_initial_balances()
            
            dest_pos.reset(request.qty).update(Side.BUY, request.qty, request.buy_price, 0.0)
            dest_pos.acc_qty = 0.0
        else:
            self.context.current_role = 'source'
            await self._load_initial_balances()

            # Track PnL for completed arbitrage cycle
            total_pnl_net = (dest_pos.pnl_tracker.pnl_usdt_net +
                             hedge_pos.pnl_tracker.pnl_usdt_net +
                             source_pos.pnl_tracker.pnl_usdt_net)

            msg = (f"💰 {self.context.symbol} Completed arbitrage"
                   f"\\r\\n Spot:     {dest_pos.pnl_tracker}, "
                   f"\\r\\n Hedge:    {hedge_pos.pnl_tracker} "
                   f"\\r\\n Total PNL:   {total_pnl_net:.4f}$")

            self.logger.info(msg)
            from infrastructure.networking.telegram import send_to_telegram
            await send_to_telegram(msg)

            source_pos.reset(self.context.total_quantity)
            dest_pos.reset(0.0)
            hedge_pos.reset()

    async def _initiate_new_transfer(self) -> Optional[TransferRequest]:
        """Initiate a new transfer if position is fulfilled."""
        symbol = self.context.symbol
        current_role = self.context.current_role
        source_pos = self.context.positions['source']
        dest_pos = self.context.positions['dest']
        
        if current_role == 'source' and source_pos.is_fulfilled(self._get_min_base_qty('source')):
            source_exchange = self.context.settings['source'].exchange
            dest_exchange = self.context.settings['dest'].exchange
            base_balance = await self._exchanges['source'].private.get_asset_balance(symbol.base, force=True)
            qty = min(source_pos.qty, base_balance.available)
            
            transfer_request = await self._transfer_module.transfer_asset(
                symbol.base, source_exchange, dest_exchange, qty, buy_price=source_pos.price
            )
            
            self.logger.info(f"🚀 Starting transfer of {qty} {symbol.base} from {source_exchange.name} to {dest_exchange.name}")
            return transfer_request
            
        elif current_role == 'dest' and dest_pos.is_fulfilled(self._get_min_base_qty('dest')):
            source_exchange = self.context.settings['source'].exchange
            dest_exchange = self.context.settings['dest'].exchange
            quote_balance = await self._exchanges['dest'].private.get_asset_balance(symbol.quote, force=True)
            qty = min(dest_pos.acc_quote_qty, quote_balance.available)
            
            # Adjust qty to USDT if needed
            if qty * self._get_book_ticker('dest').bid_price < quote_balance.available:
                qty = quote_balance.available
            
            transfer_request = await self._transfer_module.transfer_asset(
                symbol.quote, dest_exchange, source_exchange, qty
            )
            
            self.logger.info(f"🚀 Started transfer of {qty} {symbol.quote} from {dest_exchange.name} to {source_exchange.name}")
            return transfer_request
            
        return None

    async def _manage_transfer_between_exchanges(self) -> bool:
        try:
            request = self.context.transfer_request

            if request:  # has active transfer
                if request.in_progress:
                    return True
                else:  # has completed or failed
                    if request.completed:
                        await self._handle_completed_transfer(request)

                    else:
                        self.logger.error(f"❌ Transfer failed, check manually {request}")

                    self.context.transfer_request = None
                    self.context.set_save_flag()
                    await self._stop_transfer_monitor()
                    return False
            else:
                # No active transfer, check if we should initiate one
                transfer_request = await self._initiate_new_transfer()
                
                if transfer_request:
                    self.context.transfer_request = transfer_request
                    
                    # Reset position tracking but keep PnL
                    current_role = self.context.current_role
                    if current_role == 'source':
                        self.context.positions['source'].reset(reset_pnl=False)
                    else:
                        self.context.positions['dest'].reset(reset_pnl=False)
                    
                    self.context.set_save_flag()
                    await self._start_transfer_monitor()
                    return True

        except Exception as e:
            self.logger.error(f"❌ Error managing transfer between exchanges: {e}")
            return False

    async def step(self):
        try:
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

        except Exception as e:
            self.logger.error(f"❌ Error in strategy step: {e}")
            import traceback
            traceback.print_exc()

    async def cleanup(self):
        await super().cleanup()

        # Close exchange connections
        close_tasks = []
        for exchange in self._exchanges.values():
            close_tasks.append(exchange.close())
        await asyncio.gather(*close_tasks, self._stop_transfer_monitor())
