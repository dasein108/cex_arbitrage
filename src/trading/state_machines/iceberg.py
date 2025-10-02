
from enum import IntEnum
from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Literal, Optional
from infrastructure.logging import HFTLoggerInterface
from exchanges.structs.common import Symbol, Side

# BaseStrategyState = Literal["idle", "error", "active", "completed", "paused"]

class BaseStrategyState(IntEnum):
    """Base states for all trading strategies."""
    IDLE = 1
    EXECUTING = 2
    MONITORING = 3
    COMPLETED = 100
    PAUSED = 0
    ERROR = -1


class TradingTaskContext:
    def __init__(self, symbol: Symbol, side: Optional[Side] = None):
        self.symbol = symbol
        self.side = side

T = TypeVar('T', bound=TradingTaskContext)

class BaseTradingTask(Generic[T], ABC):
    def __init__(self, logger: HFTLoggerInterface):
        self.state = BaseStrategyState.IDLE
        self.context: Optional[T] = None
        self.logger = logger

    def start(self, *args, **kwargs):
        self.logger.info(f"Starting task in state {self.state.name}")
        # self.state = BaseStrategyState.EXECUTING

    def pause(self):
        self.logger.info(f"Pausing task from state {self.state.name}")
        self.state = BaseStrategyState.PAUSED

    def update(self, *args, **kwargs):
        self.logger.info(f"Updating task in state {self.state.name}")


class IcebergTaskContext(TradingTaskContext):
    def __init__(self, symbol: Symbol, side: Side, total_quantity: float, order_quantity: float):
        super().__init__(symbol, side)
        self.total_quantity = total_quantity
        self.order_quantity = order_quantity
        self.quantity_filled = 0.0
        self.avg_price = 0.0


class IcebergTask(BaseTradingTask[TradingTaskContext]):
    """ State machine for executing iceberg orders."""

    def __init__(self, logger: HFTLoggerInterface):
        super().__init__(logger)
        self.total_quantity: float = 0.0