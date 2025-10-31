import asyncio
from typing import Optional, Type, Dict, Literal, List, TypeAlias
import msgspec
from msgspec import Struct
import numpy as np
from exchanges.dual_exchange import DualExchange
from config.config_manager import get_exchange_config
from exchanges.structs import Order, SymbolInfo, ExchangeEnum, Symbol, OrderId, BookTicker
from exchanges.structs.common import Side
from infrastructure.exceptions.exchange import OrderNotFoundError, InsufficientBalanceError
from infrastructure.logging import HFTLoggerInterface, get_logger
from utils.exchange_utils import is_order_filled
from .base_strategy import BaseStrategyContext, BaseStrategyTask
from .unified_position import Position, PositionError
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, PrivateWebsocketChannelType

MarketType: TypeAlias = Literal['spot', 'futures']

BASE_SPOT_FUTURES_STRATEGY_TASK_TYPE = "base_spot_futures_strategy"


class MarketData(Struct):
    exchange: Optional[ExchangeEnum] = None
    tick_tolerance: int = 0
    ticks_offset: int = 0
    use_market: bool = False
    order_id: Optional[OrderId] = None

class BaseSpotFuturesTaskContext(BaseStrategyContext, kw_only=True):
    """Context for cross-exchange spot-futures arbitrage execution.

    Manages delta-neutral positions between spot and futures markets across different exchanges
    to capture basis spread opportunities (e.g., MEXC spot vs Gate.io futures).
    """
    # Required fields
    symbol: Symbol

    # Override default task type
    task_type: str = BASE_SPOT_FUTURES_STRATEGY_TASK_TYPE
    # Optional fields with defaults
    total_quantity: Optional[float] = None
    order_qty: Optional[float] = None  # size of each order for limit orders

    # Spread validation parameters
    min_profit_margin: float = 0.1  # Minimum required profit margin in percentage (0.1%)

    # Complex fields with factory defaults
    positions: Dict[MarketType, Position] = msgspec.field(
        default_factory=lambda: {'spot': Position(side=Side.BUY, mode='accumulate'),
                                 'futures': Position(side=Side.SELL, mode='hedge')})
    settings: Dict[MarketType, MarketData] = msgspec.field(
        default_factory=lambda: {'spot': MarketData(), 'futures': MarketData()})


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
    def from_json(json_bytes: str) -> 'BaseSpotFuturesTaskContext':
        """Deserialize context from dict data."""
        return msgspec.json.decode(json_bytes, type=BaseSpotFuturesTaskContext)


class BaseSpotFuturesArbitrageTask(BaseStrategyTask[BaseSpotFuturesTaskContext]):
    """State machine for executing cross-exchange spot-futures arbitrage strategies.

    Executes simultaneous spot positions on one exchange and futures positions on another
    to capture basis spread opportunities while maintaining market-neutral exposure.
    Examples: MEXC spot vs Gate.io futures, Binance spot vs Gate.io futures.
    """

    name: str = "SpotFuturesArbitrageTask"

    @property
    def context_class(self) -> Type[BaseSpotFuturesTaskContext]:
        """Return the spot-futures arbitrage context class."""
        return BaseSpotFuturesTaskContext

    @property
    def has_position(self):
        return self.context.positions['spot'].qty > 0 and self.context.positions['futures'].qty > 0

    @property
    def spot_pos(self):
        """Shortcut to spot position."""
        return self.context.positions['spot']

    @property
    def futures_pos(self):
        """Shortcut to futures position."""
        return self.context.positions['futures']

    def __init__(self,
                 context: BaseSpotFuturesTaskContext,
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

        self._entry_time = None
        self._entry_spread = None

        self.round_trip_fees = 0.0

        self.context.status = 'inactive'

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
                             self._load_initial_positions())

        # Setup roundtrip fees
        self.round_trip_fees = ((self._get_fees('spot').maker_fee +
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
        finally:
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


    def _track_order_execution(self, market_type: MarketType, order: Optional[Order] = None):
        """Process filled order and update context for specific market."""
        if not order:
            self.context.positions[market_type].last_order = None
            return

        try:
            pos = self.context.positions[market_type]
            pos_change = pos.update_position_with_order(order, fee=self._get_fees(market_type).taker_fee)
            if is_order_filled(order):
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


    async def _manage_positions(self):
        """Manage positions for both spot and futures markets."""

        raise NotImplemented("Should be overridden in subclass")


    async def step(self):
        try:
            if self.context.status != 'active':
                await asyncio.sleep(1)
                return

            await self._sync_positions()

            await self._manage_positions()

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