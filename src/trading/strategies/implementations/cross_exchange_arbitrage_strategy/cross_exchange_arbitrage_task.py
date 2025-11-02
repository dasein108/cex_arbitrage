import asyncio
from typing import Optional, Type, Dict, Literal, TypeAlias
import msgspec
from msgspec import Struct
import numpy as np
from exchanges.dual_exchange import DualExchange
from config.config_manager import get_exchange_config
from exchanges.structs import Order, SymbolInfo, ExchangeEnum, Symbol, OrderId, BookTicker
from exchanges.structs.common import Side
from infrastructure.exceptions.exchange import OrderNotFoundError, InsufficientBalanceError
from infrastructure.logging import HFTLoggerInterface, get_logger
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, PrivateWebsocketChannelType
from trading.research.cross_arbitrage.arbitrage_analyzer import AnalyzerKeys

from utils.math_utils import get_decrease_vector
from trading.strategies.implementations.cross_exchange_arbitrage_strategy.asset_transfer_module import AssetTransferModule, TransferRequest
from trading.strategies.implementations.base_strategy.unified_position import Position, PositionError

from trading.strategies.implementations.base_strategy.base_strategy import BaseStrategyContext, BaseStrategyTask
from trading.analysis.arbitrage_signals import calculate_arb_signals, ArbSignal
from trading.analysis.structs import Signal

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
    
    # Spread validation parameters
    min_profit_margin: float = 0.1  # Minimum required profit margin in percentage (0.1%)
    max_acceptable_spread: float = 0.2  # Maximum acceptable total spread across exchanges in percentage (0.2%)

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

    def __init__(self,
                 context: CrossExchangeArbitrageTaskContext,
                 logger: HFTLoggerInterface = None,
                 **kwargs):
        """Initialize cross-exchange hedged arbitrage task.
        """
        super().__init__(context, logger, **kwargs)
        self.logger = get_logger(self.context.tag) if logger is None else logger
        # DualExchange instances for each side (unified public/private)
        self._exchanges: Dict[ExchangeRoleType, DualExchange] = self.create_exchanges()

        self._current_order: Dict[ExchangeRoleType, Optional[Order]] = {'source': None, 'dest': None, 'hedge': None}
        self._symbol_info: Dict[ExchangeRoleType, Optional[SymbolInfo]] = {'source': None, 'dest': None, 'hedge': None}
        self._exchange_trading_allowed: Dict[ExchangeRoleType, bool] = {'source': False, 'dest': False}

        # Use unified signal generator with proven backtest logic
        from trading.research.cross_arbitrage.arbitrage_analyzer import ArbitrageAnalyzer

        # Initialize candle-based analyzer like in hedged backtest
        self.analyzer = ArbitrageAnalyzer()
        
        # Initialize historical spreads for signal generation with numpy arrays
        self.historical_spreads = {
            'mexc_vs_gateio_futures': np.array([], dtype=np.float64),
            'gateio_spot_vs_futures': np.array([], dtype=np.float64)
        }
        
        # Initialize signal generator (will be populated from candles)
        self._signal_generator = None
        self._candle_data_loaded = False
        
        # Spread monitoring
        self._spread_check_counter = 0
        self._spread_rejection_counter = 0
        self._last_spread_log_time = asyncio.get_event_loop().time()
        
        # Historical spread updates (every 5 minutes)
        self._last_spread_update_time = asyncio.get_event_loop().time()
        self._spread_update_interval = 300  # 5 minutes in seconds

        self.round_trip_fees = 0.0

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
                             self._load_initial_balances(),
                             self._load_historical_spreads())

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

        # setup roundtrip fees
        self.round_trip_fees = (self._get_fees('source').taker_fee +
                                self._get_fees('dest').taker_fee +
                                self._get_fees('hedge').taker_fee * 2)

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

            book_ticker = self._get_book_ticker(exchange_role)
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

    async def _check_arbitrage_signal(self) -> Signal:
        """
        Check for arbitrage entry/exit signals using dynamic thresholds with integrated spread validation.
        
        Returns:
            Signal enum (ENTER, EXIT, or HOLD) - HOLD if spreads fail validation
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
            
            # Update historical spreads periodically
            await self._update_historical_spreads_if_needed()
            
            # Generate signal using current market data with historical context
            signal_result = self._generate_signal_from_current_data()
            
            # Validate spreads for the generated signal (integrated validation)
            validated_signal = self._validate_spread_profitability(signal_result)
            
            # Log signal for monitoring
            if validated_signal != Signal.HOLD:
                self.logger.info("🎯 Arbitrage signal generated and validated",
                                 signal=validated_signal.value)
            else:
                self.logger.debug("⏸ No signal or validation failed")

            return validated_signal

        except Exception as e:
            self.logger.error(f"❌ Error checking arbitrage signal: {e}")
            return Signal.HOLD

    async def _load_historical_spreads(self):
        """Load candle data and populate historical spreads for signal generation."""
        if self._candle_data_loaded:
            return
            
        try:
            self.logger.info("📥 Loading candle data for signal generation...")
            
            # Load 7 days of candle data like in hedged backtest
            df, _ = await self.analyzer.run_analysis(self.context.symbol, days=7)
            
            if df.empty:
                self.logger.warning("⚠️ No candle data received from analyzer")
                return
            
            # Validate required columns exist
            required_columns = [AnalyzerKeys.mexc_vs_gateio_futures_arb, AnalyzerKeys.gateio_spot_vs_futures_arb]
            missing_columns = [col for col in required_columns if col not in df.columns]

            if missing_columns:
                self.logger.error(f"❌ Missing required columns in candle data: {missing_columns}")
                return
            
            # Populate historical spreads with numpy arrays for better performance
            self.historical_spreads['mexc_vs_gateio_futures'] = df[AnalyzerKeys.mexc_vs_gateio_futures_arb].values.astype(np.float64)
            self.historical_spreads['gateio_spot_vs_futures'] = df[AnalyzerKeys.gateio_spot_vs_futures_arb].values.astype(np.float64)
            
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

    async def _update_historical_spreads_if_needed(self):
        """Update historical spreads with current market data every 5 minutes."""
        current_time = asyncio.get_event_loop().time()
        
        # Check if it's time to update (every 5 minutes)
        if current_time - self._last_spread_update_time < self._spread_update_interval:
            return
        
        try:
            # Only update if we have loaded candle data and sufficient history
            if not self._candle_data_loaded or len(self.historical_spreads['mexc_vs_gateio_futures']) < 50:
                return
            
            # Calculate current spreads
            current_mexc_spread = self.mexc_vs_gateio_futures_spread
            current_gateio_spread = self.gateio_spot_vs_futures_spread
            
            # Append current spreads to historical data
            self.historical_spreads['mexc_vs_gateio_futures'] = np.append(
                self.historical_spreads['mexc_vs_gateio_futures'], 
                current_mexc_spread
            )
            self.historical_spreads['gateio_spot_vs_futures'] = np.append(
                self.historical_spreads['gateio_spot_vs_futures'], 
                current_gateio_spread
            )
            
            # Keep rolling window (maintain last 2016 points = 7 days * 24 hours * 12 five-minute intervals)
            max_history_points = 2016
            if len(self.historical_spreads['mexc_vs_gateio_futures']) > max_history_points:
                self.historical_spreads['mexc_vs_gateio_futures'] = self.historical_spreads['mexc_vs_gateio_futures'][-max_history_points:]
                self.historical_spreads['gateio_spot_vs_futures'] = self.historical_spreads['gateio_spot_vs_futures'][-max_history_points:]
            
            # Update timestamp
            self._last_spread_update_time = current_time
            
            self.logger.debug(
                f"📊 Updated historical spreads: "
                f"mexc={current_mexc_spread:.4f}%, gateio={current_gateio_spread:.4f}%, "
                f"total_points={len(self.historical_spreads['mexc_vs_gateio_futures'])}"
            )
            
        except Exception as e:
            self.logger.error(f"❌ Failed to update historical spreads: {e}")

    def _generate_signal_from_current_data(self):
        """Generate signals using current market data with historical candle context."""
        
        # Ensure we have enough historical data
        if len(self.historical_spreads['mexc_vs_gateio_futures']) < 50:
            from trading.analysis.arbitrage_signals import ArbSignal, ArbStats
            return ArbSignal(
                signal=Signal.HOLD,
                mexc_vs_gateio_futures=ArbStats(0, 0, 0, self.mexc_vs_gateio_futures_spread),
                gateio_spot_vs_futures=ArbStats(0, 0, 0, self.gateio_spot_vs_futures_spread)
            )
        
        arb_signal_result = calculate_arb_signals(
            mexc_vs_gateio_futures_history=self.historical_spreads['mexc_vs_gateio_futures'],
            gateio_spot_vs_futures_history=self.historical_spreads['gateio_spot_vs_futures'],
            current_mexc_vs_gateio_futures=self.mexc_vs_gateio_futures_spread,
            current_gateio_spot_vs_futures=self.gateio_spot_vs_futures_spread
        )

        return arb_signal_result

    @property
    def mexc_vs_gateio_futures_spread(self) -> float:
        mexc_ticker = self._get_book_ticker('source')  # MEXC
        gateio_futures_ticker = self._get_book_ticker('hedge')  # Gate.io futures

        # Use exact backtest formula for consistency
        spread = (gateio_futures_ticker.bid_price - mexc_ticker.ask_price) / gateio_futures_ticker.bid_price * 100
        return spread

    @property
    def gateio_spot_vs_futures_spread(self) -> float:
        gateio_spot_ticker = self._get_book_ticker('dest')  # Gate.io spot
        gateio_futures_ticker = self._get_book_ticker('hedge')  # Gate.io futures

        # Use exact backtest formula for consistency
        spread = (gateio_spot_ticker.bid_price - gateio_futures_ticker.ask_price) / gateio_spot_ticker.bid_price * 100
        return spread
    
    def _calculate_execution_spreads(self) -> Dict[str, float]:
        """Calculate current bid-ask spreads for each exchange in percentage."""
        spreads = {}
        
        # Source exchange (MEXC) spread
        source_ticker = self._get_book_ticker('source')
        source_spread = ((source_ticker.ask_price - source_ticker.bid_price) / 
                        source_ticker.ask_price * 100)
        spreads['source'] = source_spread
        
        # Destination exchange (Gate.io spot) spread
        dest_ticker = self._get_book_ticker('dest')
        dest_spread = ((dest_ticker.ask_price - dest_ticker.bid_price) / 
                      dest_ticker.ask_price * 100)
        spreads['dest'] = dest_spread
        
        # Hedge exchange (Gate.io futures) spread
        hedge_ticker = self._get_book_ticker('hedge')
        hedge_spread = ((hedge_ticker.ask_price - hedge_ticker.bid_price) / 
                       hedge_ticker.ask_price * 100)
        spreads['hedge'] = hedge_spread
        
        # Total execution spread (entry + exit costs)
        spreads['total'] = source_spread + dest_spread + hedge_spread
        
        return spreads
    
    def _validate_spread_profitability(self, arb_signal_result: ArbSignal) -> Signal:
        """
        Enhanced spread validation using ArbStats for dynamic thresholds and entry/exit specific logic.
        
        Args:
            arb_signal_result: ArbSignal result from calculate_arb_signals with signal and stats
            
        Returns:
            Signal enum (ENTER, EXIT, or HOLD) - original signal if valid, HOLD if validation fails
        """
        # Track validation attempts
        self._spread_check_counter += 1
        
        signal = arb_signal_result.signal
        
        # Get current execution spreads and fees
        execution_spreads = self._calculate_execution_spreads()
        total_spread_cost = execution_spreads['total']
        is_enter_mode = self.context.current_role == 'source'
        # Entry/Exit specific validation
        if signal == Signal.ENTER and is_enter_mode:
            validation_result = self._validate_entry_spreads(
                arb_signal_result, total_spread_cost, execution_spreads
            )
        elif signal == Signal.EXIT and not is_enter_mode:
            validation_result = self._validate_exit_spreads(
                arb_signal_result, total_spread_cost, execution_spreads
            )
        else:  # HOLD
            return Signal.HOLD  # Pass through HOLD signals
        
        # Update rejection counter
        if not validation_result:
            self._spread_rejection_counter += 1
        
        # Periodic spread monitoring (every 60 seconds)
        current_time = asyncio.get_event_loop().time()
        if current_time - self._last_spread_log_time > 60:
            self._last_spread_log_time = current_time
            rejection_rate = (self._spread_rejection_counter / max(1, self._spread_check_counter)) * 100
            self.logger.info(
                f"📊 Spread monitoring stats: checks={self._spread_check_counter}, "
                f"rejections={self._spread_rejection_counter} ({rejection_rate:.1f}%), "
                f"current_spreads={total_spread_cost:.3f}%",
                mexc_spread=f"{execution_spreads['source']:.3f}%",
                gateio_spot_spread=f"{execution_spreads['dest']:.3f}%",
                gateio_futures_spread=f"{execution_spreads['hedge']:.3f}%"
            )
        
        # Return original signal if validation passed, HOLD if failed
        return signal if validation_result else Signal.HOLD

    def _validate_entry_spreads(self, arb_signal_result, total_spread_cost: float, execution_spreads: dict) -> bool:
        """
        Validate spreads for ENTRY signals using dynamic ArbStats thresholds.
        
        For entries, we care most about:
        1. The arbitrage opportunity exceeds statistical entry threshold
        2. Total costs (spreads + fees) don't consume too much of the edge
        3. Current spreads aren't abnormally high
        """
        actual_fees = self.round_trip_fees * 100  # Convert to percentage

        # Extract ArbStats for dynamic thresholds
        mexc_stats = arb_signal_result.mexc_vs_gateio_futures
        
        # 1. Check if opportunity exceeds dynamic entry threshold (25th percentile of mins)
        entry_edge = abs(mexc_stats.current - mexc_stats.min_25pct)
        
        # 2. Calculate total trading costs
        total_costs = total_spread_cost + actual_fees
        
        # 3. Ensure sufficient profit margin after costs
        net_edge = abs(mexc_stats.current) - total_costs
        required_profit = self.context.min_profit_margin
        
        # Entry validation logic
        if net_edge < required_profit:
            self.logger.debug(
                f"⚠️ Entry validation failed: net_edge={net_edge:.3f}% < "
                f"required={required_profit:.3f}% | "
                f"opportunity={abs(mexc_stats.current):.3f}%, costs={total_costs:.3f}%",
                entry_threshold=f"{mexc_stats.min_25pct:.3f}%",
                mexc_spread=f"{execution_spreads['source']:.3f}%",
                gateio_spot_spread=f"{execution_spreads['dest']:.3f}%",
                gateio_futures_spread=f"{execution_spreads['hedge']:.3f}%",
                fees=f"{actual_fees:.3f}%"
            )
            return False
        
        # 4. Check if current spreads are within acceptable range (relaxed for good opportunities)
        max_spread_multiplier = 2.0 if abs(mexc_stats.current) > abs(mexc_stats.mean) * 1.5 else 1.0
        adjusted_max_spread = self.context.max_acceptable_spread * max_spread_multiplier
        
        if total_spread_cost > adjusted_max_spread:
            self.logger.debug(
                f"⚠️ Entry validation failed: spreads={total_spread_cost:.3f}% > "
                f"adjusted_max={adjusted_max_spread:.3f}% (multiplier={max_spread_multiplier:.1f})",
                opportunity_quality=f"{abs(mexc_stats.current):.3f}% vs mean {abs(mexc_stats.mean):.3f}%"
            )
            return False
        
        # Success logging
        self.logger.info(
            f"✅ Entry validation passed: net_edge={net_edge:.3f}% > required={required_profit:.3f}%",
            opportunity=f"{abs(mexc_stats.current):.3f}%",
            entry_threshold=f"{mexc_stats.min_25pct:.3f}%",
            costs=f"{total_costs:.3f}%",
            spreads=f"{total_spread_cost:.3f}%",
            fees=f"{actual_fees:.3f}%"
        )
        return True

    def _validate_exit_spreads(self, arb_signal_result, total_spread_cost: float, execution_spreads: dict) -> bool:
        """
        Validate spreads for EXIT signals using dynamic ArbStats thresholds.
        
        For exits, we care most about:
        1. We're in a profitable exit zone (above 25th percentile of maxes)
        2. Exit costs don't erode existing profit too much
        3. Better to exit with lower costs than wait for perfect opportunity
        """
        # Extract ArbStats for dynamic thresholds
        gateio_stats = arb_signal_result.gateio_spot_vs_futures
        
        actual_fees = self.round_trip_fees * 100  # Convert to percentage
        
        # For exits, be more permissive on spreads since timing is critical
        exit_edge = gateio_stats.current - gateio_stats.max_25pct
        
        # Calculate exit costs (generally should be lower threshold than entry)
        total_costs = total_spread_cost + actual_fees
        
        # For exits, allow higher spread costs if we're in good exit territory
        exit_spread_tolerance = self.context.max_acceptable_spread * 1.5  # 50% more permissive
        
        if total_spread_cost > exit_spread_tolerance:
            self.logger.warning(
                f"⚠️ Exit validation failed: spreads={total_spread_cost:.3f}% > "
                f"exit_tolerance={exit_spread_tolerance:.3f}%",
                exit_signal_strength=f"{exit_edge:.3f}%",
                exit_threshold=f"{gateio_stats.max_25pct:.3f}%"
            )
            return False
        
        # More permissive profit check for exits (preserve capital, don't optimize for max profit)
        min_exit_profit = self.context.min_profit_margin * 0.5  # Half the entry requirement
        if exit_edge < min_exit_profit:
            self.logger.warning(
                f"⚠️ Exit validation failed: exit_edge={exit_edge:.3f}% < "
                f"min_exit_profit={min_exit_profit:.3f}%",
                current_signal=f"{gateio_stats.current:.3f}%",
                exit_threshold=f"{gateio_stats.max_25pct:.3f}%"
            )
            return False
        
        # Success logging
        self.logger.info(
            f"✅ Exit validation passed: exit_edge={exit_edge:.3f}% > min={min_exit_profit:.3f}%",
            exit_signal=f"{gateio_stats.current:.3f}%",
            exit_threshold=f"{gateio_stats.max_25pct:.3f}%",
            costs=f"{total_costs:.3f}%",
            spread_tolerance=f"{exit_spread_tolerance:.3f}%"
        )

        return True

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

            self.logger.error(f"🚫 Insufficient balance to place order {tag_str} |"
                              f" pos: {pos}, order: {side} {quantity} @ {price}",
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
        # Check arbitrage signals with integrated spread validation
        validated_signal = await self._check_arbitrage_signal()
        
        # Set trading permissions based on validated signal
        source_allowed = (validated_signal == Signal.ENTER)
        dest_allowed = (validated_signal == Signal.EXIT)

        if self._exchange_trading_allowed['source'] != source_allowed:
            self._exchange_trading_allowed['source'] = source_allowed
            state = "🟢 enabled" if source_allowed else "⛔️ disabled"
            self.logger.info(f"🔔 Source trading {state} based on validated signal")

        if self._exchange_trading_allowed['dest'] != dest_allowed:
            self._exchange_trading_allowed['dest'] = dest_allowed
            state = "🟢 enabled" if dest_allowed else "⛔️ disabled"
            self.logger.info(f"🔔 Dest trading {state} based on validated signal")

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
                else:
                    return False

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
