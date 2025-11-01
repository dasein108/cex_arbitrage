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
from infrastructure.logging import HFTLoggerInterface, get_logger, LoggerFactory
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, PrivateWebsocketChannelType

from utils import get_decrease_vector

from trading.strategies.implementations.base_strategy.base_spot_futures_strategy import (BaseSpotFuturesArbitrageTask,
                                                                                         BaseSpotFuturesTaskContext, MarketType)

# Import indicators for market intelligence
from .indicators import (
    SimpleMarketDataLoader,
    SimpleMarketState,
    SafetyIndicators,
    DynamicParameters
)

MAKER_LIMIT_DELTA_NEUTRAL_TASK_TYPE = "maker_limit_delta_neutral_strategy"

class MakerLimitDeltaNeutralTaskContext(BaseSpotFuturesTaskContext, kw_only=True):
    # Override default task type
    task_type: str = MAKER_LIMIT_DELTA_NEUTRAL_TASK_TYPE


class MakerLimitDeltaNeutralTask(BaseSpotFuturesArbitrageTask):
    """State machine for executing cross-exchange spot-futures arbitrage strategies.

    Executes simultaneous spot positions on one exchange and futures positions on another
    to capture basis spread opportunities while maintaining market-neutral exposure.
    Examples: MEXC spot vs Gate.io futures, Binance spot vs Gate.io futures.
    """

    @property
    def context_class(self) -> Type[MakerLimitDeltaNeutralTaskContext]:
        """Return the spot-futures arbitrage context class."""
        return MakerLimitDeltaNeutralTaskContext

    def __init__(self,
                 context: MakerLimitDeltaNeutralTaskContext,
                 logger: HFTLoggerInterface = None,
                 **kwargs):
        """Initialize spot-futures arbitrage task.
        """
        super().__init__(context, logger, **kwargs)
        self.logger = get_logger(self.context.tag) if logger is None else logger

        # Reduce noisy exchange logs
        logger_names = [
            "GATEIO_SPOT.ws.private", "GATEIO_SPOT.ws.public",
            "GATEIO_FUTURES.ws.private", "GATEIO_FUTURES.ws.public",
            "MEXC_SPOT.ws.private", "MEXC_SPOT.ws.public",
            "MEXC_SPOT.MEXC_SPOT_private", "GATEIO_FUTURES.GATEIO_FUTURES_private"
                                           "rest.client.gateio", "rest.client.mexc", "rest.client.mexc_spot"
        ]

        for logger_name in logger_names:
            LoggerFactory.override_logger(logger_name, min_level="ERROR")

        # Initialize market intelligence indicators
        self.market_state = None
        self.safety_indicators = None
        self.dynamic_params = None
        self.indicators_initialized = False

    async def _initialize_indicators(self):
        """Initialize market data and indicators system."""
        

        try:
            self.logger.info("🧠 Initializing market intelligence indicators...")
            
            # Load initial historical data
            data_loader = SimpleMarketDataLoader()
            exchanges = [
                self.context.spot_exchange_enum,
                self.context.futures_exchange_enum
            ]
            
            # Load 12 hours of historical data
            initial_data = await data_loader.load_initial_data(
                exchanges=exchanges,
                symbol=self.context.symbol,
                hours=12
            )
            
            # Initialize market state tracker
            self.market_state = SimpleMarketState(max_history_minutes=120)  # 2 hours rolling
            self.market_state.load_initial_data(initial_data)
            
            # Initialize safety indicators
            safety_config = {
                'max_volatility_pct': 2.0,      # 2% volatility threshold
                'max_spread_ratio': 1.5,        # futures spread <= 1.5x spot spread
                'min_data_points': 10
            }
            self.safety_indicators = SafetyIndicators(self.market_state, safety_config)
            
            # Initialize dynamic parameters optimizer
            base_config = {
                'ticks_offset': self.context.settings['spot'].ticks_offset,
                'tick_tolerance': self.context.settings['spot'].tick_tolerance
            }
            self.dynamic_params = DynamicParameters(self.market_state, base_config)
            
            self.indicators_initialized = True
            
            # Log initialization status
            if data_loader.has_historical_data:
                self.logger.info("✅ Market intelligence initialized with historical data")
            else:
                self.logger.info("⚠️ Market intelligence initialized in real-time only mode")
                
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize indicators: {e}")
            # Continue without indicators (graceful fallback)
            self.indicators_initialized = False

    async def _cancel_all_orders(self):
        """Cancel all active orders for safety."""
        try:
            # Cancel spot orders
            if hasattr(self.spot_pos, 'last_order') and self.spot_pos.last_order:
                await self._cancel_order_safe('spot', order_id=self.spot_pos.last_order.order_id)
            
            # Cancel futures orders if any (implementation depends on your base class)
            # This is a placeholder - implement based on your futures order tracking
            
            self.logger.info("🛑 All orders cancelled for safety")
            
        except Exception as e:
            self.logger.error(f"Error cancelling orders: {e}")

    async def _adjust_futures_position(self):
        """Manage limit orders for one market."""
        # Skip if no quantity to fill
        spot_qty = self.spot_pos.qty if self.spot_pos.qty > self._get_min_base_qty('spot') else 0
        delta = spot_qty - self.futures_pos.qty
        if abs(delta) < self._get_min_base_qty('futures'):
            return

        quantity_to_fill = abs(delta)
        side = Side.BUY if delta < 0 else Side.SELL
        book_ticker = self._get_book_ticker('futures')
        order_price = book_ticker.bid_price if side == Side.SELL else book_ticker.ask_price

        order = await self._place_order_safe(
            'futures',
            side,
            quantity_to_fill,
            order_price,
            is_market=False,
            tag=f"futures:{side.name}:market"
        )

        pass

    def _get_limit_order_side(self)-> Side:
        """Determine side for limit order based on current position delta."""

        return Side.BUY if self.spot_pos.mode == 'accumulate' else Side.SELL

    @property
    def spot_balance(self):
        return self._exchanges['spot'].balances[self.context.symbol.base].total

    async def start(self):
        await super().start()
        await self._initialize_indicators()

    async def _manage_spot_limit_order_place(self):
        """Place limit order to top-offset price or market order."""
        if self.spot_pos.last_order:
            return

        max_qty = self.spot_pos.get_remaining_qty(self._get_min_base_qty('spot'))
        max_quantity_to_fill = max_qty - max_qty * self._get_fees('spot').taker_fee * 2

        if max_quantity_to_fill == 0:
            return

        book_ticker = self._get_book_ticker('spot')
        settings = self.context.settings['spot']
        
        # Use dynamic offset if indicators are available
        if self.dynamic_params:
            offset_ticks = self.dynamic_params.get_dynamic_tick_offset()
        else:
            offset_ticks = settings.ticks_offset

        side = self._get_limit_order_side()

        top_price = book_ticker.bid_price if side == Side.BUY else book_ticker.ask_price

        # Get fresh price for order
        vector_ticks = get_decrease_vector(side, offset_ticks)
        order_price = top_price + vector_ticks * self._symbol_info['spot'].tick

        # Adjust to rest unfilled total amount
        limit_order_qty = min(self.context.order_qty, max_quantity_to_fill)
        if side == Side.SELL:
            limit_order_qty = min(limit_order_qty, self.spot_balance)

        order = await self._place_order_safe(
            'spot',
            side,
            limit_order_qty,
            order_price,
            is_market=False,
            tag=f"spot:{side.name}:limit"
        )
        pass

    async def _manage_spot_order_cancel(self) -> bool:
        """Determine if current order should be cancelled due to price movement."""
        curr_order = self.spot_pos.last_order
        settings = self.context.settings['spot']

        if not curr_order:
            return False

        side = curr_order.side
        book_ticker = self._get_book_ticker('spot')
        order_price = curr_order.price

        # Use dynamic tolerance if indicators are available
        if self.dynamic_params:
            tick_tolerance = self.dynamic_params.get_dynamic_tick_tolerance()
        else:
            tick_tolerance = settings.tick_tolerance

        top_price = book_ticker.bid_price if side == Side.BUY else book_ticker.ask_price
        tick_difference = abs((order_price - top_price) / self._symbol_info['spot'].tick)
        should_cancel = tick_difference - settings.ticks_offset > tick_tolerance

        if should_cancel:
            self.logger.info(
                f"⚠️ Price moved significantly on SPOT. Current {side.name}: {top_price}, "
                f"Our price: {order_price} (tolerance: {tick_tolerance} ticks)")

            await self._cancel_order_safe('spot', order_id=curr_order.order_id)

        return should_cancel

    async def handle_spot_mode(self):
        if self.spot_pos.is_fulfilled(self._get_min_base_qty('spot')):
            if self.spot_pos.mode == 'accumulate':
                self.logger.info("Switching SPOT position mode to 'release'")
                self.spot_pos.set_mode('release')
                await self._exchanges['spot'].private.load_balances()
            else:
                self.logger.info("Switching SPOT position mode to 'accumulate'")

                spot_pnl = self.spot_pos.pnl_tracker
                fut_pnl = self.futures_pos.pnl_tracker
                total_pnl = spot_pnl.pnl_usdt + fut_pnl.pnl_usdt
                icon = "💰" if total_pnl > 0 else "🔻"
                self.logger.info(f"{icon} SPOT PnL: {spot_pnl.pnl_usdt:.4f}$ (net: {spot_pnl.pnl_usdt_net:.4f}$), "
                                 f"{spot_pnl.avg_entry_price:.6f} -> {spot_pnl.avg_exit_price:.6f} ({spot_pnl.avg_entry_price - spot_pnl.avg_exit_price:.4}) | "
                                 f"FUTURES PnL: {fut_pnl.pnl_usdt:.4f}$ (net: {fut_pnl.pnl_usdt_net:.4f}$), "
                                 f"{fut_pnl.avg_entry_price:.6f} -> {fut_pnl.avg_exit_price:.6f}  ({fut_pnl.avg_entry_price - fut_pnl.avg_exit_price:.4})| "
                                 f"Total PnL: {total_pnl:.4f}$ ")

                self.spot_pos.reset(self.context.total_quantity, reset_pnl=True)
                self.futures_pos.reset(self.context.total_quantity, reset_pnl=True)

                self.spot_pos.set_mode('accumulate')

    async def _manage_positions(self):
        """Manage both spot and futures positions with market intelligence."""
        if not self.indicators_initialized:
            return
        # spot_spread = self._get_book_ticker('spot').spread
        # fut_spread = self._get_book_ticker('futures').spread
        # delta = spot_spread - fut_spread
        # self.logger.info(f"spot {spot_spread:.6f} futures {fut_spread:.6f} delta {delta:.6f}")
        # Update market state with real-time data
        if self.market_state:
            try:
                spot_book = self._get_book_ticker('spot')
                futures_book = self._get_book_ticker('futures')
                self.market_state.update_real_time(spot_book, futures_book)
                
                # Safety check - halt trading if unsafe conditions detected
                if self.safety_indicators:
                    is_safe, reason = self.safety_indicators.is_safe_to_trade()
                    if not is_safe:
                        await self._cancel_all_orders()
                        self.logger.warning(f"🛑 Trading halted: {reason}")
                        return
                        
            except Exception as e:
                self.logger.error(f"Error updating market intelligence: {e}")
                # Continue with trading if indicators fail (graceful fallback)
        
        # Execute normal position management with enhanced parameters
        await self._manage_spot_limit_order_place()
        await self._manage_spot_order_cancel()
        await self._adjust_futures_position()
        await self.handle_spot_mode()


