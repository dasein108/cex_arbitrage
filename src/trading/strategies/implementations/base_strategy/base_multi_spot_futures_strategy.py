import asyncio
from typing import Optional, Type, Dict, Literal, List, TypeAlias, TypeVar, Generic
import msgspec
from dill import settings
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
from .position_data import PositionData
from .exchange_position import PositionError
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, PrivateWebsocketChannelType
from .position_manager import PositionManager

MarketType: TypeAlias = Literal['spot', 'futures']

BASE_MULTI_SPOT_FUTURES_STRATEGY_TASK_TYPE = "base_multi_spot_futures_strategy"


class MarketData(Struct):
    exchange: Optional[ExchangeEnum] = None
    tick_tolerance: int = 0
    ticks_offset: int = 0
    use_market: bool = False


class BaseMultiSpotFuturesTaskContext(BaseStrategyContext, kw_only=True):
    """Context for cross-exchange spot-futures arbitrage execution.

    Manages delta-neutral positions between spot and futures markets across different exchanges
    to capture basis spread opportunities (e.g., MEXC spot vs Gate.io futures).
    """
    # Required fields
    symbol: Symbol

    # Override default task type
    task_type: str = BASE_MULTI_SPOT_FUTURES_STRATEGY_TASK_TYPE
    # Optional fields with defaults
    total_quantity: Optional[float] = None
    order_qty: Optional[float] = None  # size of each order for limit orders

    hedge: Optional[PositionData] = None

    # Complex fields with factory defaults
    positions: List[PositionData] = msgspec.field(default_factory=lambda: [])

    spot_settings: List[MarketData] = msgspec.field(default_factory=lambda: [])

    hedge_settings: MarketData = msgspec.field(default_factory=lambda: MarketType())

    @property
    def tag(self) -> str:
        """Generate logging tag based on task_id and symbol."""
        return f"{self.task_type}.{self.symbol}"

    @staticmethod
    def from_json(json_bytes: str) -> 'BaseMultiSpotFuturesTaskContext':
        """Deserialize context from dict data."""
        return msgspec.json.decode(json_bytes, type=BaseMultiSpotFuturesTaskContext)


T = TypeVar("T", bound=BaseMultiSpotFuturesTaskContext)

class BaseMultiSpotFuturesArbitrageTask(BaseStrategyTask[T], Generic[T]):
# class BaseMultiSpotFuturesArbitrageTask(BaseStrategyTask[BaseMultiSpotFuturesTaskContext]):
    """State machine for executing cross-exchange spot-futures arbitrage strategies.

    Executes simultaneous spot positions on one exchange and futures positions on another
    to capture basis spread opportunities while maintaining market-neutral exposure.
    Examples: MEXC spot vs Gate.io futures, Binance spot vs Gate.io futures.
    """

    @property
    def context_class(self) -> T:
        """Return the spot-futures arbitrage context class."""
        return T

    @property
    def total_spot_qty(self):
        return sum([p.qty for p in self.context.positions])

    def get_spot_pos(self, index: int):
        return self.context.positions[index]

    @property
    def hedge_pos(self):
        """Shortcut to futures position."""
        return self.context.hedge

    @property
    def hedge_manager(self) -> Optional[PositionManager]:
        """Shortcut to hedge position manager."""
        return self._hedge_manager

    @property 
    def spot_managers(self) -> List[PositionManager]:
        """Shortcut to spot position managers."""
        return self._spot_managers

    def get_spot_manager(self, index: int) -> Optional[PositionManager]:
        """Get spot manager by index."""
        if 0 <= index < len(self._spot_managers):
            return self._spot_managers[index]
        return None

    def __init__(self,
                 context: T,
                 logger: HFTLoggerInterface = None,
                 **kwargs):
        """Initialize spot-futures arbitrage task.
        """
        super().__init__(context, logger, **kwargs)
        self.logger = get_logger(str(self.context.tag)) if logger is None else logger
        self._hedge_ex = DualExchange.get_instance(get_exchange_config(context.hedge_settings.exchange), self.logger)

        # DualExchange instances for spot and futures markets
        self._spot_ex: List[DualExchange] = [DualExchange.get_instance(get_exchange_config(
            setting.exchange), self.logger) for setting in self.context.spot_settings]

        self._spot_ex_map: [int, ExchangeEnum] = {}
        # Single position managers - one per position
        self._hedge_manager: Optional[PositionManager] = None
        self._spot_managers: List[PositionManager] = []

        self.context.status = 'inactive'

    def save_context(self, position_data: PositionData, index: Optional[int] = None,
                     is_hedge: bool = False):
        """Save context callback for position managers."""
        if is_hedge:
            self.context.hedge = position_data
        else:
            self.context.positions[index] = position_data
        # This can be overridden by subclasses if needed

        self.context.set_save_flag()
        pass

    async def _start_hedge_exchange(self):
        await self._hedge_ex.initialize(
            [self.context.symbol],
            public_channels=[PublicWebsocketChannelType.BOOK_TICKER],
            private_channels=[PrivateWebsocketChannelType.ORDER, PrivateWebsocketChannelType.POSITION]
        )

    async def _start_spot_exchanges(self, index: int):
        # setting = self.context.settings[index]
        exchange = self._spot_ex[index]

        self._spot_ex_map[index] = exchange.exchange_enum

        await exchange.initialize(
            [self.context.symbol],
            public_channels=[PublicWebsocketChannelType.BOOK_TICKER],
            private_channels=[PrivateWebsocketChannelType.ORDER, PrivateWebsocketChannelType.BALANCE]
        )

    async def start(self):
        if self.context is None:
            raise ValueError("Cannot start task: context is None (likely deserialization failed)")

        await super().start()

        self.context.status = 'inactive'  # prevent step() while not loaded

        # Initialize DualExchanges
        init_tasks = [self._start_hedge_exchange()]
        for i in range(len(self.context.spot_settings)):
            init_tasks.append(self._start_spot_exchanges(i))

        await asyncio.gather(*init_tasks)

        # create hedge if not exists
        if not self.context.hedge:
            self.context.hedge = PositionData(
                symbol=self.context.symbol,
                side=Side.SELL)

        # create spot positions if not exists
        if not self.context.positions:
            for setting in self.context.spot_settings:
                pos = PositionData(
                    symbol=self.context.symbol,
                    side=Side.BUY)
                self.context.positions.append(pos)

        # Create position managers - one per position
        self._hedge_manager = PositionManager(
            position_data=self.context.hedge,
            exchange=self._hedge_ex,
            logger=self.logger,
            save_context=lambda pd: self.save_context(position_data=pd, is_hedge=True)
        )

        self._spot_managers = []
        for i, pos in enumerate(self.context.positions):
            manager = PositionManager(
                position_data=pos,
                exchange=self._spot_ex[i],
                logger=self.logger,
                save_context=lambda pd: self.save_context(index=i, position_data=pd, is_hedge=False)
            )
            self._spot_managers.append(manager)

        # Initialize all position managers
        init_tasks = [self._hedge_manager.initialize(self.context.total_quantity)]
        for manager in self._spot_managers:
            init_tasks.append(manager.initialize(self.context.total_quantity))

        # Initialize all positions
        await asyncio.gather(*init_tasks)

        self.context.status = 'active'

    async def pause(self):
        """Pause task and cancel any active order."""
        await super().pause()
        await self._cancel_all()

    async def cancel(self):
        """Handle cancelled state."""
        await super().cancel()
        await self._cancel_all()

    async def stop(self):
        """Handle stopped state."""
        await super().stop()
        await self._cancel_all()

    async def _cancel_all(self):
        cancel_tasks = []
        
        # Cancel hedge order
        if self._hedge_manager:
            cancel_tasks.append(self._hedge_manager.cancel_order())
        
        # Cancel spot orders
        for manager in self._spot_managers:
            cancel_tasks.append(manager.cancel_order())
        
        if cancel_tasks:
            canceled = await asyncio.gather(*cancel_tasks, return_exceptions=True)
            self.logger.info(f"🛑 Canceled all orders", orders=str(canceled))

    async def _sync_positions(self):
        """Sync order status from exchanges in parallel."""
        sync_tasks = []
        
        # Sync hedge position
        if self._hedge_manager:
            sync_tasks.append(self._hedge_manager.sync_with_exchange())
        
        # Sync spot positions
        for manager in self._spot_managers:
            sync_tasks.append(manager.sync_with_exchange())
        
        if sync_tasks:
            await asyncio.gather(*sync_tasks, return_exceptions=True)

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
        close_tasks = [self._hedge_ex.close()]
        for exchange in self._spot_ex:
            close_tasks.append(exchange.close())

        await asyncio.gather(*close_tasks)
