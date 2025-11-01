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

from utils import get_decrease_vector
from trading.strategies.implementations.base_strategy.unified_position import Position, PositionError

from trading.strategies.implementations.base_strategy.base_strategy import BaseStrategyContext, BaseStrategyTask
from trading.analysis.arbitrage_signals import ArbSignal, ArbStats

from trading.analysis.structs import Signal

MarketType: TypeAlias = Literal['spot', 'futures']

TRANSFER_REFRESH_SECONDS = 30

SPOT_FUTURES_ARBITRAGE_TASK_TYPE = "spot_futures_arbitrage_strategy"


class MarketData(Struct):
    exchange: Optional[ExchangeEnum] = None
    tick_tolerance: int = 0
    ticks_offset: int = 0
    use_market: bool = False
    order_id: Optional[OrderId] = None



class SpotFuturesArbitrageTaskContext(BaseStrategyContext, kw_only=True):
    """Context for cross-exchange spot-futures arbitrage execution.

    Manages delta-neutral positions between spot and futures markets across different exchanges
    to capture basis spread opportunities (e.g., MEXC spot vs Gate.io futures).
    """
    # Required fields  
    symbol: Symbol

    # Override default task type
    task_type: str = SPOT_FUTURES_ARBITRAGE_TASK_TYPE
    # Optional fields with defaults
    total_quantity: Optional[float] = None
    order_qty: Optional[float] = None  # size of each order for limit orders

    # Spread validation parameters
    min_profit_margin: float = 0.1  # Minimum required profit margin in percentage (0.1%)
    max_acceptable_spread: float = 0.2  # Maximum acceptable total spread across markets in percentage (0.2%)

    # Complex fields with factory defaults
    positions: Dict[MarketType, Position] = msgspec.field(
        default_factory=lambda: {'spot': Position(side=Side.BUY, mode='accumulate'),
                                 'futures': Position(side=Side.SELL, mode='hedge')})
    settings: Dict[MarketType, MarketData] = msgspec.field(
        default_factory=lambda: {'spot': MarketData(), 'futures': MarketData()})

    # Cross-exchange transfer management
    signal: Signal = Signal.HOLD

    @property
    def tag(self) -> str:
        """Generate logging tag based on task_id and symbol."""
        return f"{self.task_type}.{self.symbol.base}_{self.symbol.quote}"

    @property
    def spot_exchange_enum(self):
        return self.settings['spot'].exchange

    @property
    def futures_exchange_enum(self):
        return self.settings['futures'].exchange

    @staticmethod
    def from_json(json_bytes: str) -> 'SpotFuturesArbitrageTaskContext':
        """Deserialize context from dict data."""
        return msgspec.json.decode(json_bytes, type=SpotFuturesArbitrageTaskContext)


class SpotFuturesArbitrageTask(BaseStrategyTask[SpotFuturesArbitrageTaskContext]):
    """State machine for executing cross-exchange spot-futures arbitrage strategies.

    Executes simultaneous spot positions on one exchange and futures positions on another
    to capture basis spread opportunities while maintaining market-neutral exposure.
    Examples: MEXC spot vs Gate.io futures, Binance spot vs Gate.io futures.
    """

    name: str = "SpotFuturesArbitrageTask"

    @property
    def context_class(self) -> Type[SpotFuturesArbitrageTaskContext]:
        """Return the spot-futures arbitrage context class."""
        return SpotFuturesArbitrageTaskContext

    @property
    def has_position(self):
        return self.context.positions['spot'].qty > 0 and self.context.positions['futures'].qty > 0


    def __init__(self,
                 context: SpotFuturesArbitrageTaskContext,
                 logger: HFTLoggerInterface = None,
                 **kwargs):
        """Initialize spot-futures arbitrage task.
        """
        super().__init__(context, logger, **kwargs)
        self.logger = get_logger(self.context.tag) if logger is None else logger
        
        # DualExchange instances for spot and futures markets
        self._exchanges: Dict[MarketType, DualExchange] = {
            'spot': self.create_exchange('spot'),
            'futures': self.create_exchange('futures')
        }

        self._symbol_info: Dict[MarketType, Optional[SymbolInfo]] = {'spot': None, 'futures': None}

        # Initialize historical spreads for signal generation with numpy arrays
        self.historical_spreads = {
            'spot_vs_futures': np.array([], dtype=np.float64),
            'execution_spreads': np.array([], dtype=np.float64)
        }
        
        # Spread monitoring
        self._spread_check_counter = 0
        self._spread_rejection_counter = 0
        self._last_spread_log_time = asyncio.get_event_loop().time()
        
        # Historical spread updates (every 5 minutes)
        self._last_spread_update_time = asyncio.get_event_loop().time()
        self._spread_update_interval = 300  # 5 minutes in seconds

        # Entry tracking for exit conditions (from analyzer logic)
        self._entry_time = None
        self._entry_spread = None

        self.round_trip_fees = 0.0

        self.context.status = 'inactive'
        self.fut_min_spread = 999
        self.fut_max_spread = -999
        self.spot_min_spread = 999
        self.spot_max_spread = -999


    def create_exchange(self, market_type: MarketType) -> DualExchange:
        """Create exchanges with optimized config loading for HFT performance."""

        exchange_name = str(self.context.settings[market_type].exchange.value)
        exchange_config = get_exchange_config(exchange_name)

        return DualExchange.get_instance(exchange_config, self.logger)

    async def start(self):
        if self.context is None:
            raise ValueError("Cannot start task: context is None (likely deserialization failed)")

        await super().start()

        self.context.status = 'inactive'  # prevent step() while not loaded

        # Initialize DualExchanges in parallel for HFT performance
        init_tasks = []
        for market_type, exchange in self._exchanges.items():
            private_channels = [PrivateWebsocketChannelType.POSITION] if exchange.is_futures else [
                PrivateWebsocketChannelType.BALANCE]
            init_tasks.append(
                exchange.initialize(
                    [self.context.symbol],
                    public_channels=[PublicWebsocketChannelType.BOOK_TICKER],
                    private_channels=[PrivateWebsocketChannelType.ORDER] + private_channels
                )
            )
        await asyncio.gather(*init_tasks)
        
        # Initialize symbol info and load active orders and balances
        await asyncio.gather(self._load_symbol_info(),
                             self._force_load_active_orders(),
                             self._load_initial_positions(),
                             self._load_historical_spreads())

        # Log the status of data loading
        if len(self.historical_spreads['spot_vs_futures']) >= 20:
            self.logger.info("✅ Z-score based signal generation initialized with analyzer logic - ready for signal generation")
        else:
            self.logger.info("✅ Z-score based signal generation initialized with analyzer logic - accumulating historical data")

        # Setup roundtrip fees
        self.round_trip_fees = ((self._get_fees('spot').taker_fee +
                                self._get_fees('futures').taker_fee) * 2)

        self.context.status = 'active'

    def _get_fees(self, market_type: MarketType):
        return self._exchanges[market_type].private.get_fees(self.context.symbol)

    async def _load_initial_positions(self):
        """Load initial positions for both spot and futures."""
        # Load futures position
        fut_position = self.context.positions['futures']
        futures_exchange = self._exchanges['futures']

        # Load real futures position
        position = await futures_exchange.private.get_position(self.context.symbol, force=True)

        if position:
            fut_position.qty = position.qty_base
            fut_position.price = position.entry_price
            self.logger.info(f"🔄 Loaded initial futures position {fut_position}")
        else:
            self.logger.info(f"ℹ️ No existing futures position")
            fut_position.reset(reset_pnl=False)

        # Load spot position (based on balance)
        spot_exchange = self._exchanges['spot']
        await spot_exchange.private.load_balances()
        balance = await spot_exchange.private.get_asset_balance(self.context.symbol.base)

        book_ticker = self._get_book_ticker('spot')
        min_qty = self._symbol_info['spot'].get_abs_min_quantity(book_ticker.bid_price)
        spot_pos = self.context.positions['spot']
        self.paper_position = None

        if balance.available > min_qty:
            spot_pos.qty = balance.available

        # Fix price if not set
        if spot_pos.qty > 0 and spot_pos.price == 0:
            self.logger.info(f"⚠️ Price was not set for spot position, guessing from order book")
            spot_pos.price = book_ticker.bid_price

        self.logger.info(f"🔄 Loaded initial spot position {spot_pos}")

        spot_pos.target_qty = fut_position.target_qty = self.context.total_quantity

    async def pause(self):
        """Pause task and cancel any active order."""
        await super().pause()
        await self.cancel_all()

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
        for market_type, pos in self.context.positions.items():
            if pos.last_order:
                cancel_tasks.append(self._cancel_order_safe(market_type,
                                                            pos.last_order.order_id,
                                                            f"cancel_all"))

        canceled = await asyncio.gather(*cancel_tasks)
        self.logger.info(f"🛑 Canceled all orders", orders=str(canceled))

    async def _force_load_active_orders(self):
        for market_type, exchange in self._exchanges.items():
            last_order = self.context.positions[market_type].last_order
            if last_order:
                try:
                    order = await exchange.private.fetch_order(last_order.symbol, last_order.order_id)
                except OrderNotFoundError as e:
                    self.logger.warning(f"⚠️ Could not find existing order '{last_order}' on {market_type} "
                                        f"during reload: {e}")
                    order = None

                self._track_order_execution(market_type, order)

    async def _sync_exchange_order(self, market_type: MarketType) -> Order | None:
        """Get current order from exchange, track updates."""
        pos = self.context.positions[market_type]

        if pos.last_order:
            updated_order = await self._exchanges[market_type].private.get_active_order(
                self.context.symbol, pos.last_order.order_id
            )
            self._track_order_execution(market_type, updated_order)

    async def _load_symbol_info(self, force=False):
        for market_type, exchange in self._exchanges.items():
            if force:
                await exchange.public.load_symbols_info()

            self._symbol_info[market_type] = exchange.public.symbols_info[self.context.symbol]
            await exchange.public.get_book_ticker(self.context.symbol)

    def _get_book_ticker(self, market_type: MarketType) -> BookTicker:
        """Get current best price from public exchange."""
        book_ticker = self._exchanges[market_type].public.book_ticker[self.context.symbol]
        return book_ticker

    async def _check_arbitrage_signal(self) -> Signal:
        """
        Check for spot-futures arbitrage entry/exit signals using dynamic thresholds.
        
        Returns:
            Signal enum (ENTER, EXIT, or HOLD) - HOLD if spreads fail validation
        """
        try:
            # Get current order books from both markets
            spot_book = self._get_book_ticker('spot')
            futures_book = self._get_book_ticker('futures')
            
            # Log current prices for debugging
            self.logger.debug("📊 Current prices",
                            spot_bid=spot_book.bid_price,
                            spot_ask=spot_book.ask_price,
                            futures_bid=futures_book.bid_price,
                            futures_ask=futures_book.ask_price)
            
            # Update historical spreads periodically
            await self._update_historical_spreads_if_needed()
            
            # Generate signal using current market data with historical context
            signal_result = self._generate_signal_from_current_data()
            
            # Validate spreads for the generated signal
            validated_signal = self._validate_spread_profitability(signal_result)
            
            # Log signal for monitoring
            if validated_signal != Signal.HOLD:
                self.logger.info("🎯 Spot-futures arbitrage signal generated and validated",
                                 signal=validated_signal.value)
            else:
                self.logger.debug("⏸ No signal or validation failed")

            # Update trading permissions
            if self.context.signal != validated_signal:
                self.logger.info(f"🔔 Trading signal {validated_signal}")

            self.context.signal = validated_signal

            return validated_signal

        except Exception as e:
            self.logger.error(f"❌ Error checking arbitrage signal: {e}")
            return Signal.HOLD

    async def _load_historical_spreads(self):
        """Load candle data and pre-calculate spot_vs_futures spread history for z-score analysis."""

        try:
            self.logger.info("📊 Loading historical candles for z-score based signal generation...")
            
            # Import candle loading capability
            from trading.analysis.data_sources import CandlesLoader
            from exchanges.structs.enums import KlineInterval
            from datetime import datetime, timedelta, timezone
            
            candles_loader = CandlesLoader()
            
            # Load last 24 hours of 5-minute candles for both spot and futures
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(hours=24)

            spot_exchange = self.context.settings['spot'].exchange
            futures_exchange = self.context.settings['futures'].exchange
            
            # Load candles for both exchanges
            spot_task = candles_loader.download_candles(
                exchange=spot_exchange,
                symbol=self.context.symbol,
                timeframe=KlineInterval.MINUTE_5,
                start_date=start_time,
                end_date=end_time
            )
            
            futures_task = candles_loader.download_candles(
                exchange=futures_exchange,
                symbol=self.context.symbol,
                timeframe=KlineInterval.MINUTE_5,
                start_date=start_time,
                end_date=end_time
            )
            
            # Get both candle datasets
            spot_df, futures_df = await asyncio.gather(spot_task, futures_task)
            
            if spot_df is None or futures_df is None or spot_df.empty or futures_df.empty:
                self.logger.warning("⚠️ No historical candle data available, using empty arrays")
                self.historical_spreads['spot_vs_futures'] = np.array([], dtype=np.float64)
                self.historical_spreads['execution_spreads'] = np.array([], dtype=np.float64)
            else:
                # Merge candle data on timestamp
                merged_df = self._merge_and_calculate_spreads(spot_df, futures_df)
                
                if len(merged_df) > 0:
                    # Populate historical spreads arrays
                    self.historical_spreads['spot_vs_futures'] = merged_df['basis_spread'].values.astype(np.float64)
                    self.historical_spreads['execution_spreads'] = merged_df['execution_spread'].values.astype(np.float64)
                    
                    self.logger.info(f"✅ Loaded {len(merged_df)} historical spread data points")
                    self.logger.info(f"📈 Spread range: {merged_df['basis_spread'].min():.4f}% to {merged_df['basis_spread'].max():.4f}%")
                else:
                    self.logger.warning("⚠️ No merged candle data available")
                    self.historical_spreads['spot_vs_futures'] = np.array([], dtype=np.float64)
                    self.historical_spreads['execution_spreads'] = np.array([], dtype=np.float64)
            
            self.logger.info("✅ Z-score based signal generation initialized with historical data")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to load historical spreads: {e}")
            import traceback
            self.logger.debug(f"Full error traceback: {traceback.format_exc()}")
            
            # Fallback to empty arrays
            self.historical_spreads['spot_vs_futures'] = np.array([], dtype=np.float64)
            self.historical_spreads['execution_spreads'] = np.array([], dtype=np.float64)

    def candles_to_bid_ask_spread(self, df, exchange_enum: ExchangeEnum):
        # df = df[['close', 'high', 'low']].copy()
        #
        # cols = {
        #     'high': f'{exchange_enum.value}_high',
        #     'low': f'{exchange_enum.value}_low',
        #     'close': f'{exchange_enum.value}_close',
        # }
        #
        # df.rename(columns=cols, inplace=True)
        #  Use bid-ask spread estimate: (high - low) / close * 100
        df['spread'] = ((df['high'] - df[f'low']) / df['close']) * 100
        # ((df[f'{spot_exchange.value}_high'] - df[f'{spot_exchange.value}_low']) / df[spot_col]) * 100
        df = df[['close', 'spread', 'timestamp']]
        df.rename(columns={
            'spread': f'{exchange_enum.value}_spread',
            'close': f'{exchange_enum.value}_close'
        }, inplace=True)

        return df



    def _merge_and_calculate_spreads(self, spot_df, futures_df):
        """Merge spot and futures candle data and calculate basis spreads (from analyzer logic)."""
        import pandas as pd
        
        # Create copies to avoid modifying original data
        spot_df = spot_df.copy()
        futures_df = futures_df.copy()
        
        # spot_exchange = self.context.settings['spot'].exchange
        # futures_exchange = self.context.settings['futures'].exchange

        spot_df = self.candles_to_bid_ask_spread(spot_df, self.context.spot_exchange_enum)
        futures_df = self.candles_to_bid_ask_spread(futures_df, self.context.futures_exchange_enum)

        # # Rename columns to match analyzer pattern
        # spot_cols = {
        #     'open': f'{spot_exchange.value}_open',
        #     'high': f'{spot_exchange.value}_high',
        #     'low': f'{spot_exchange.value}_low',
        #     'close': f'{spot_exchange.value}_close',
        #     'volume': f'{spot_exchange.value}_volume'
        # }
        #
        # futures_cols = {
        #     'open': f'{futures_exchange.value}_open',
        #     'high': f'{futures_exchange.value}_high',
        #     'low': f'{futures_exchange.value}_low',
        #     'close': f'{futures_exchange.value}_close',
        #     'volume': f'{futures_exchange.value}_volume'
        # }
        #
        # spot_df.rename(columns=spot_cols, inplace=True)
        # futures_df.rename(columns=futures_cols, inplace=True)
        
        # Merge on timestamp
        df = pd.merge(spot_df, futures_df, on='timestamp', how='inner')
        df.sort_values('timestamp', inplace=True)
        
        if df.empty:
            return df
        
        # Convert timestamp to datetime
        # df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
        # df.reset_index(drop=True, inplace=True)
        
        # Calculate basis spread using close prices (same as analyzer)
        spot_col = f'{self.context.spot_exchange_enum.value}_close'
        futures_col = f'{self.context.futures_exchange_enum.value}_close'
        
        # Basis spread: (futures - spot) / spot * 100
        df['basis_spread'] = ((df[futures_col] - df[spot_col]) / df[spot_col]) * 100
        
        # Calculate execution spreads (simplified)
        # Use bid-ask spread estimate: (high - low) / close * 100
        # spot_spread = ((df[f'{spot_exchange.value}_high'] - df[f'{spot_exchange.value}_low']) / df[spot_col]) * 100
        # futures_spread = ((df[f'{futures_exchange.value}_high'] - df[f'{futures_exchange.value}_low']) / df[futures_col]) * 100

        df['execution_spread'] = df[f'{self.context.spot_exchange_enum.value}_spread'] + df[f'{self.context.futures_exchange_enum.value}_spread']

        # Fill any NaN values
        df['basis_spread'].fillna(0, inplace=True)
        df['execution_spread'].fillna(0.1, inplace=True)  # Default 0.1% execution cost
        
        return df

    async def _update_historical_spreads_if_needed(self):
        """Update historical spreads with current market data every 5 minutes."""
        current_time = asyncio.get_event_loop().time()
        
        # Check if it's time to update (every 5 minutes)
        if current_time - self._last_spread_update_time < self._spread_update_interval:
            return
        
        try:
            # Calculate current spreads
            current_spot_futures_spread = self.spot_vs_futures_spread
            current_execution_spread = self._calculate_execution_spreads()['total']
            
            # Append current spreads to historical data
            self.historical_spreads['spot_vs_futures'] = np.append(
                self.historical_spreads['spot_vs_futures'], 
                current_spot_futures_spread
            )
            self.historical_spreads['execution_spreads'] = np.append(
                self.historical_spreads['execution_spreads'], 
                current_execution_spread
            )
            
            # Keep rolling window (maintain last 2016 points = 7 days * 24 hours * 12 five-minute intervals)
            max_history_points = 2016
            if len(self.historical_spreads['spot_vs_futures']) > max_history_points:
                self.historical_spreads['spot_vs_futures'] = self.historical_spreads['spot_vs_futures'][-max_history_points:]
                self.historical_spreads['execution_spreads'] = self.historical_spreads['execution_spreads'][-max_history_points:]
            
            # Update timestamp
            self._last_spread_update_time = current_time
            
            self.logger.debug(
                f"📊 Updated historical spreads: "
                f"spot_futures={current_spot_futures_spread:.4f}%, execution={current_execution_spread:.4f}%, "
                f"total_points={len(self.historical_spreads['spot_vs_futures'])}"
            )
            
        except Exception as e:
            self.logger.error(f"❌ Failed to update historical spreads: {e}")

    def _generate_signal_from_current_data(self):
        """Generate signals using z-score based analysis from analyzer logic."""
        
        # Ensure we have enough historical data (need at least 20 for rolling stats)

        # Calculate z-score based signal using analyzer logic
        current_spread = self.spot_vs_futures_spread
        historical_spreads = self.historical_spreads['spot_vs_futures']
        
        # Rolling statistics (last 20 periods)
        window = 20
        recent_spreads = historical_spreads[-window:]
        basis_mean = np.mean(recent_spreads)
        basis_std = np.std(recent_spreads)
        
        # Avoid division by zero
        if basis_std == 0:
            z_score = 0
        else:
            z_score = (current_spread - basis_mean) / basis_std
        
        # Calculate total fees for validation
        total_fees = self.round_trip_fees
        
        # Entry/Exit logic based on analyzer
        signal = Signal.HOLD
        # self.fut_max_spread = max(self.fut_max_spread, self.futures_vs_spot_spread)
        # self.fut_min_spread = min(self.fut_min_spread, self.futures_vs_spot_spread)
        # self.spot_max_spread = max(self.spot_max_spread, self.spot_vs_futures_spread)
        # self.spot_min_spread = min(self.spot_min_spread, self.spot_vs_futures_spread)
        # spot_vs_futures = self.spot_vs_futures_spread
        # futures_vs_spot = self.futures_vs_spot_spread
        # diff_fut_vs_spot = self.fut_max_spread - self.spot_min_spread
        # diff_spot_vs_fut = self.spot_max_spread - self.fut_min_spread
        # spot_bid_ask = self._get_book_ticker('spot')
        # futures_bid_ask = self._get_book_ticker('futures')
        # if spot_vs_futures < -0.4 and not self.paper_position:
        #     self.paper_position = {'enter_spot': spot_bid_ask.ask_price,
        #                            'enter_futures': futures_bid_ask.bid_price}
        #     self.logger.info(f"📋 Paper position ENTER: {self.paper_position}")
        # elif futures_vs_spot > -0.1 and self.paper_position:
        #     enter_spot = self.paper_position['enter_spot']
        #     enter_futures = self.paper_position['enter_futures']
        #     exit_spot = spot_bid_ask.bid_price
        #     exit_futures = futures_bid_ask.ask_price
        #     spot_return = (exit_spot - enter_spot) / enter_spot * 100
        #     futures_return = (enter_futures - exit_futures) / enter_futures * 100
        #     total_return = spot_return + futures_return - total_fees
        #     self.logger.info(f"📋 Paper position EXIT: {{'exit_spot': {exit_spot}, 'exit_futures': {exit_futures}}} "
        #                      f"Returns: spot={spot_return:.4f}%, futures={futures_return:.4f}%, "
        #                      f"total={total_return:.4f}% after fees={total_fees:.4f}%")
        #     self.paper_position = None
        #
        # if spot_vs_futures < -0.4 or futures_vs_spot > 0.1:
        #     self.logger.info(f"enter: {spot_vs_futures:.4f} ({self.spot_min_spread:.4f}, {self.spot_max_spread:.4f}) diff: {diff_spot_vs_fut:.4f}   "
        #                      f"exit: {futures_vs_spot:.4f}  ({self.fut_min_spread:.4f}, {self.fut_max_spread:.4f}) diff: {diff_fut_vs_spot:.4f}")
        #
        # if futures_bid_ask.ask_price - spot_bid_ask.bid_price < 0:
        #     self.logger.info(f"arb opportunity: spot_bid {spot_bid_ask.bid_price}  futures_ask {futures_bid_ask.ask_price} "
        #                      f"diff: {futures_bid_ask.ask_price - spot_bid_ask.bid_price:.4f}")
        # if futures_bid_ask.bid_price - spot_bid_ask.ask_price > 0:
        #     self.logger.info(f"arb opportunity: spot_ask {spot_bid_ask.ask_price}  futures_bid {futures_bid_ask.bid_price} "
        #                      f"diff: {futures_bid_ask.bid_price - spot_bid_ask.ask_price:.4f}")
        #
        #  # Entry/Exit logic from analyzer:
         # Entry condition: no position and abs(z_score) > 2 and spread > fees
         # Exit conditions handled in separate method
        if not self.has_position:
            # Entry logic: abs(z_score) > 2 and spread > fees
            if abs(z_score) > 2 and abs(current_spread) > total_fees * 100:
                signal = Signal.ENTER
        elif self.has_position:
            # Exit logic: mean reversion, max holding time, or sign flip
            signal = self._check_exit_conditions(z_score, current_spread)

        # Log signal for monitoring
        self.logger.debug("📊 Z-score based signal analysis",
                         current_spread=current_spread,
                         z_score=z_score,
                         basis_mean=basis_mean,
                         basis_std=basis_std,
                         signal=signal.value)
        
        # Return signal in ArbSignal format for compatibility
        return ArbSignal(
            signal=signal,
            mexc_vs_gateio_futures=ArbStats(basis_mean, basis_std, z_score, current_spread),
            gateio_spot_vs_futures=ArbStats(0, 0, 0, self._calculate_execution_spreads()['total'])
        )
    
    def _check_exit_conditions(self, z_score: float, current_spread: float) -> Signal:
        """Check exit conditions based on analyzer logic."""
        
        # Get entry spread for sign flip check
        entry_spread = getattr(self, '_entry_spread', None)
        
        # Calculate holding time
        entry_time = getattr(self, '_entry_time', None)
        if entry_time:
            current_time = asyncio.get_event_loop().time()
            holding_time_minutes = (current_time - entry_time) / 60
        else:
            holding_time_minutes = 0
        
        # Exit conditions from analyzer:
        # 1. Mean reversion: abs(z_score) < 0.5
        if abs(z_score) < 0.5:
            self.logger.info(f"🔄 Exit signal: Mean reversion (z_score={z_score:.2f})")
            return Signal.EXIT
        
        # 2. Maximum holding time: 4 hours (240 minutes)
        if holding_time_minutes > 240:
            self.logger.info(f"⏰ Exit signal: Max holding time reached ({holding_time_minutes:.1f} min)")
            return Signal.EXIT
        
        # 3. Sign flip: spread changed direction
        if entry_spread is not None and current_spread * entry_spread < 0:
            self.logger.info(f"🔄 Exit signal: Spread sign flip (entry={entry_spread:.4f}%, current={current_spread:.4f}%)")
            return Signal.EXIT
        
        return Signal.HOLD
    
    def _track_position_entry(self):
        """Track when we enter a position for exit condition analysis."""
        self._entry_time = asyncio.get_event_loop().time()
        self._entry_spread = self.spot_vs_futures_spread
        self.logger.info(f"📈 Position entry tracked: spread={self._entry_spread:.4f}%, time={self._entry_time}")
    
    def _try_restore_entry_tracking(self):
        """Try to restore entry tracking when resuming in exit mode."""
        # In a real implementation, this could load from persistent state
        # For now, we'll estimate based on position entry prices
        spot_pos = self.context.positions['spot']
        if spot_pos.qty > 0:
            # Estimate entry spread based on current prices vs position price
            current_spot_price = self._get_book_ticker('spot').bid_price
            if spot_pos.price > 0:
                # Use position price difference as proxy for entry spread
                self._entry_spread = ((current_spot_price - spot_pos.price) / spot_pos.price) * 100
                self._entry_time = asyncio.get_event_loop().time() - 300  # Assume 5 minutes ago
                self.logger.info(f"🔄 Estimated entry tracking restored: spread≈{self._entry_spread:.4f}%")

    @property
    def spot_vs_futures_spread(self) -> float:
        """Calculate cross-exchange spot vs futures basis spread."""
        spot_ticker = self._get_book_ticker('spot')
        futures_ticker = self._get_book_ticker('futures')

        # Cross-exchange basis spread calculation
        # For MEXC spot vs Gate.io futures arbitrage:
        # - Enter when MEXC spot is cheaper than Gate.io futures (negative spread)
        # - Exit when spread normalizes or reverses
        # Formula: (futures_bid - spot_ask) / futures_bid * 100
        # Positive spread = opportunity to buy spot and sell futures
        spread = (futures_ticker.bid_price - spot_ticker.ask_price) / futures_ticker.bid_price * 100
        return spread

    @property
    def futures_vs_spot_spread(self) -> float:
        """Calculate cross-exchange spot vs futures basis spread."""
        spot_ticker = self._get_book_ticker('spot')
        futures_ticker = self._get_book_ticker('futures')

        spread = (futures_ticker.ask_price - spot_ticker.bid_price) / futures_ticker.ask_price * 100
        return spread
    
    def _calculate_execution_spreads(self) -> Dict[str, float]:
        """Calculate current bid-ask spreads for each market in percentage."""
        spreads = {}
        
        # Spot market spread
        spot_ticker = self._get_book_ticker('spot')
        spot_spread = ((spot_ticker.ask_price - spot_ticker.bid_price) / 
                      spot_ticker.ask_price * 100)
        spreads['spot'] = spot_spread
        
        # Futures market spread
        futures_ticker = self._get_book_ticker('futures')
        futures_spread = ((futures_ticker.ask_price - futures_ticker.bid_price) / 
                         futures_ticker.ask_price * 100)
        spreads['futures'] = futures_spread
        
        # Total execution spread (entry + exit costs)
        spreads['total'] = spot_spread + futures_spread
        
        return spreads
    
    def _validate_spread_profitability(self, arb_signal_result: ArbSignal) -> Signal:
        """
        Enhanced spread validation using ArbStats for dynamic thresholds.
        
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

        # Entry/Exit specific validation
        if signal == Signal.ENTER and not self.has_position:
            validation_result = self._validate_entry_spreads(
                arb_signal_result, total_spread_cost, execution_spreads
            )
        elif signal == Signal.EXIT and self.has_position:
            validation_result = self._validate_exit_spreads(
                arb_signal_result, total_spread_cost, execution_spreads
            )
        else:  # HOLD or wrong mode
            return Signal.HOLD
        
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
                spot_spread=f"{execution_spreads['spot']:.3f}%",
                futures_spread=f"{execution_spreads['futures']:.3f}%"
            )
        
        # Return original signal if validation passed, HOLD if failed
        return signal if validation_result else Signal.HOLD

    def _validate_entry_spreads(self, arb_signal_result, total_spread_cost: float, execution_spreads: dict) -> bool:
        """Validate spreads for ENTRY signals using dynamic ArbStats thresholds."""
        actual_fees = self.round_trip_fees * 100  # Convert to percentage

        # Extract ArbStats for dynamic thresholds (using spot-futures as main signal)
        spot_futures_stats = arb_signal_result.mexc_vs_gateio_futures  # Reusing structure
        
        # Check if opportunity exceeds dynamic entry threshold
        entry_edge = abs(spot_futures_stats.current - spot_futures_stats.min_25pct)
        
        # Calculate total trading costs
        total_costs = total_spread_cost + actual_fees
        
        # Ensure sufficient profit margin after costs
        net_edge = abs(spot_futures_stats.current) - total_costs
        required_profit = self.context.min_profit_margin
        
        # Entry validation logic
        if net_edge < required_profit:
            self.logger.debug(
                f"⚠️ Entry validation failed: net_edge={net_edge:.3f}% < "
                f"required={required_profit:.3f}% | "
                f"opportunity={abs(spot_futures_stats.current):.3f}%, costs={total_costs:.3f}%",
                entry_threshold=f"{spot_futures_stats.min_25pct:.3f}%",
                spot_spread=f"{execution_spreads['spot']:.3f}%",
                futures_spread=f"{execution_spreads['futures']:.3f}%",
                fees=f"{actual_fees:.3f}%"
            )
            return False
        
        # Check if current spreads are within acceptable range
        max_spread_multiplier = 2.0 if abs(spot_futures_stats.current) > abs(spot_futures_stats.mean) * 1.5 else 1.0
        adjusted_max_spread = self.context.max_acceptable_spread * max_spread_multiplier
        
        if total_spread_cost > adjusted_max_spread:
            self.logger.debug(
                f"⚠️ Entry validation failed: spreads={total_spread_cost:.3f}% > "
                f"adjusted_max={adjusted_max_spread:.3f}% (multiplier={max_spread_multiplier:.1f})",
                opportunity_quality=f"{abs(spot_futures_stats.current):.3f}% vs mean {abs(spot_futures_stats.mean):.3f}%"
            )
            return False
        
        # Success logging
        self.logger.info(
            f"✅ Entry validation passed: net_edge={net_edge:.3f}% > required={required_profit:.3f}%",
            opportunity=f"{abs(spot_futures_stats.current):.3f}%",
            entry_threshold=f"{spot_futures_stats.min_25pct:.3f}%",
            costs=f"{total_costs:.3f}%",
            spreads=f"{total_spread_cost:.3f}%",
            fees=f"{actual_fees:.3f}%"
        )
        return True

    def _validate_exit_spreads(self, arb_signal_result, total_spread_cost: float, execution_spreads: dict) -> bool:
        """Validate spreads for EXIT signals using dynamic ArbStats thresholds."""
        # Extract ArbStats for dynamic thresholds (using execution costs as exit signal)
        execution_stats = arb_signal_result.gateio_spot_vs_futures  # Reusing structure
        
        actual_fees = self.round_trip_fees * 100  # Convert to percentage
        
        # For exits, be more permissive on spreads since timing is critical
        exit_edge = execution_stats.current - execution_stats.max_25pct
        
        # Calculate exit costs
        total_costs = total_spread_cost + actual_fees
        
        # For exits, allow higher spread costs if we're in good exit territory
        exit_spread_tolerance = self.context.max_acceptable_spread * 1.5  # 50% more permissive
        
        if total_spread_cost > exit_spread_tolerance:
            self.logger.warning(
                f"⚠️ Exit validation failed: spreads={total_spread_cost:.3f}% > "
                f"exit_tolerance={exit_spread_tolerance:.3f}%",
                exit_signal_strength=f"{exit_edge:.3f}%",
                exit_threshold=f"{execution_stats.max_25pct:.3f}%"
            )
            return False
        
        # More permissive profit check for exits
        min_exit_profit = self.context.min_profit_margin * 0.5  # Half the entry requirement
        if exit_edge < min_exit_profit:
            self.logger.warning(
                f"⚠️ Exit validation failed: exit_edge={exit_edge:.3f}% < "
                f"min_exit_profit={min_exit_profit:.3f}%",
                current_signal=f"{execution_stats.current:.3f}%",
                exit_threshold=f"{execution_stats.max_25pct:.3f}%"
            )
            return False
        
        # Success logging
        self.logger.info(
            f"✅ Exit validation passed: exit_edge={exit_edge:.3f}% > min={min_exit_profit:.3f}%",
            exit_signal=f"{execution_stats.current:.3f}%",
            exit_threshold=f"{execution_stats.max_25pct:.3f}%",
            costs=f"{total_costs:.3f}%",
            spread_tolerance=f"{exit_spread_tolerance:.3f}%"
        )

        return True

    async def _cancel_order_safe(
            self,
            market_type: MarketType,
            order_id: OrderId,
            tag: str = ""
    ) -> Optional[Order]:
        """Safely cancel order with consistent error handling."""
        tag_str = f"'{market_type.upper()}' {tag}".strip()
        symbol = self.context.symbol
        exchange = self._exchanges[market_type].private
        try:
            order = await exchange.cancel_order(symbol, order_id)
            self.logger.info(f"🛑 Cancelled {tag_str}", order=str(order), order_id=order_id)
        except Exception as e:
            self.logger.error(f"🚫 Failed to cancel {tag_str} order", error=str(e))
            # Try to fetch order status instead
            order = await exchange.fetch_order(symbol, order_id)

        self._track_order_execution(market_type, order)
        return order

    async def _place_order_safe(
            self,
            market_type: MarketType,
            side: Side,
            quantity: float,
            price: float,
            is_market: bool = False,
            tag: str = ""
    ) -> Optional[Order]:
        """Place limit order with validation and error handling."""
        tag_str = f"'{market_type}' {side.name} {tag}"
        symbol = self.context.symbol

        try:
            exchange = self._exchanges[market_type].private
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

            self._track_order_execution(market_type, order)

            self.logger.info(f"📈 Placed {tag_str} order",
                             order_id=order.order_id,
                             order=str(order))

            return order
        except InsufficientBalanceError as ife:
            pos = self.context.positions[market_type]
            pos.acc_qty = pos.target_qty

            self.logger.error(f"🚫 Insufficient balance to place order {tag_str} "
                              f"| pos: {pos}, order: {quantity} @ {price}  adjust position amount",
                              error=str(ife))
            return None
        except Exception as e:
            self.logger.error(f"🚫 Failed to place order {tag_str}", error=str(e))
            return None

    def _get_min_base_qty(self, market_type: MarketType) -> float:
        price = self._get_book_ticker(market_type).bid_price
        return self._symbol_info[market_type].get_abs_min_quantity(price)

    async def _rebalance_positions(self) -> bool:
        """Rebalance spot and futures positions to maintain delta neutrality."""
        spot_qty = self.context.positions['spot'].qty
        futures_qty = self.context.positions['futures'].qty

        # Calculate delta (should be close to zero for delta neutral)
        delta = spot_qty - futures_qty  # futures_qty is negative for short positions

        if abs(delta) < self._get_min_base_qty('futures'):
            return False

        self.logger.info(f"⚖️ Detected position imbalance: delta={delta:.8f}, "
                         f"spot={spot_qty}, futures={futures_qty}")
        
        if delta > 0:
            # Too much long exposure - increase futures short
            await self._place_order_safe('futures', Side.SELL, abs(delta),
                                         self._get_book_ticker('futures').bid_price,
                                         is_market=True, tag="⏬ Increase Futures Short")
        else:
            # Too much short exposure - decrease futures short
            await self._place_order_safe('futures', Side.BUY, abs(delta),
                                         self._get_book_ticker('futures').ask_price,
                                         is_market=True, tag="⏫ Decrease Futures Short")

        return True

    async def _manage_order_place(self, market_type: MarketType):
        """Place limit order to top-offset price or market order."""
        pos = self.context.positions[market_type]
        max_qty = pos.get_remaining_qty(self._symbol_info[market_type].min_base_quantity)
        max_quantity_to_fill = max_qty - max_qty * self._get_fees(market_type).taker_fee * 2
        
        if max_quantity_to_fill == 0:
            return

        curr_book_ticker = self._get_book_ticker(market_type)
        settings = self.context.settings[market_type]
        offset_ticks = settings.ticks_offset
        
        # Determine side based on market type and current mode
        if market_type == 'spot':
            side = Side.BUY if self.context.signal == Signal.ENTER else Side.SELL
        else:  # futures
            side = Side.SELL if self.context.signal == Signal.ENTER else Side.BUY

        if settings.use_market:
            max_top_qty = curr_book_ticker.ask_quantity if side == Side.BUY else curr_book_ticker.bid_quantity
            market_order_qty = min(max_top_qty, max_quantity_to_fill)

            if market_order_qty < self._get_min_base_qty(market_type):
                self.logger.info(f"⚠️ Not enough top order book quantity to place market order on {market_type}",
                                 available_qty=market_order_qty,
                                 min_required=self._get_min_base_qty(market_type))
                return

            order_price = curr_book_ticker.ask_price if side == Side.BUY else curr_book_ticker.bid_price

            await self._place_order_safe(
                market_type,
                side,
                market_order_qty,
                order_price,
                is_market=True,
                tag=f"{market_type}:{side.name}:market"
            )
        else:
            top_price = curr_book_ticker.bid_price if side == Side.BUY else curr_book_ticker.ask_price

            # Get fresh price for order
            vector_ticks = get_decrease_vector(side, offset_ticks)
            order_price = top_price + vector_ticks * self._symbol_info[market_type].tick

            # Adjust to rest unfilled total amount
            limit_order_qty = min(self.context.order_qty, max_quantity_to_fill)

            await self._place_order_safe(
                market_type,
                side,
                limit_order_qty,
                order_price,
                is_market=False,
                tag=f"{market_type}:{side.name}:limit"
            )

    async def _manage_order_cancel(self, market_type: MarketType) -> bool:
        """Determine if current order should be cancelled due to price movement."""
        curr_order = self.context.positions[market_type].last_order
        settings = self.context.settings[market_type]

        if not curr_order or settings.use_market:
            return False

        side = curr_order.side
        book_ticker = self._get_book_ticker(market_type)
        order_price = curr_order.price

        top_price = book_ticker.bid_price if side == Side.BUY else book_ticker.ask_price
        tick_difference = abs((order_price - top_price) / self._symbol_info[market_type].tick)
        should_cancel = tick_difference > settings.tick_tolerance

        if should_cancel:
            self.logger.info(
                f"⚠️ Price moved significantly on {market_type}. Current {side.name}: {top_price}, "
                f"Our price: {order_price}")

            await self._cancel_order_safe(market_type, order_id=curr_order.order_id)

        return should_cancel

    def _track_order_execution(self, market_type: MarketType, order: Optional[Order] = None):
        """Process filled order and update context for specific market."""
        if not order:
            return

        try:
            pos = self.context.positions[market_type]
            pos_change = pos.update_position_with_order(order, fee=self._get_fees(market_type).taker_fee)

            self.logger.info(f"📊 Updated position on {market_type}",
                             side=order.side.name,
                             qty_before=pos_change.qty_before,
                             price_before=pos_change.price_before,
                             qty_after=pos_change.qty_after,
                             price_after=pos_change.price_after)

        except PositionError as pe:
            self.logger.error(f"🚫 Position update error on {market_type} after order fill",
                              error=str(pe))

        finally:
            self.context.set_save_flag()

    async def _sync_positions(self):
        """Sync order status from exchanges in parallel."""
        sync_tasks = [
            self._sync_exchange_order(market_type) for market_type in self.context.positions.keys()
        ]
        await asyncio.gather(*sync_tasks)

    async def _manage_position(self, market_type: MarketType):
        """Manage limit orders for one market."""
        # Skip if no quantity to fill
        if self.context.signal == Signal.HOLD:
            return

        is_fulfilled = self.context.positions[market_type].is_fulfilled(self._get_min_base_qty(market_type))
        
        if is_fulfilled:
            return

        # Cancel if price moved too much
        is_cancelled = await self._manage_order_cancel(market_type)
        if is_cancelled:
            return

        # Place order if none exists
        await self._manage_order_place(market_type)

    async def _manage_positions(self):
        """Manage positions for both spot and futures markets."""

        # Manage both markets simultaneously
        await asyncio.gather(
            self._manage_position('spot'),
            self._manage_position('futures')
        )

    async def step(self):
        try:
            if self.context.status != 'active':
                await asyncio.sleep(1)
                return

            await self._sync_positions()
            await self._check_arbitrage_signal()

            await self._manage_positions()
            await self._rebalance_positions()

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
