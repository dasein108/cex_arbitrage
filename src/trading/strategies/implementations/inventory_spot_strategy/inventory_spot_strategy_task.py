import asyncio
from typing import Optional, Type, Dict, Literal, TypeAlias

from exchanges.structs import Order, SymbolInfo, ExchangeEnum, Symbol, OrderId, BookTicker
from exchanges.structs.common import Side
from infrastructure.exceptions.exchange import OrderNotFoundError, InsufficientBalanceError
from infrastructure.logging import HFTLoggerInterface, get_logger, LoggerFactory
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, PrivateWebsocketChannelType

from utils.math_utils import get_decrease_vector

from trading.strategies.implementations.base_strategy.base_multi_spot_futures_strategy import (
    BaseMultiSpotFuturesArbitrageTask,
    BaseMultiSpotFuturesTaskContext)
from trading.signals_v2.implementation.inventory_spot_strategy_signal import InventorySpotStrategySignal, \
    InventorySignalWithLimitEnum
from utils.logging_utils import disable_default_exchange_logging


class InventorySpotStrategyTask(BaseMultiSpotFuturesArbitrageTask):
    name = "inventory_spot_strategy"

    def __init__(self,
                 context: BaseMultiSpotFuturesTaskContext,
                 logger: HFTLoggerInterface = None,
                 **kwargs):
        """Initialize spot-futures arbitrage task.
        """
        super().__init__(context, logger, **kwargs)
        params = kwargs.get("strategy_params", {'mexc_spread_threshold_bps': 30,
                                                'gateio_spread_threshold_bps': 30})
        self.signal = InventorySpotStrategySignal(params=params)

        # disable logging from exchange modules to reduce noise
        disable_default_exchange_logging()

    def get_spot_book_ticker(self, index: int) -> BookTicker:
        return self._spot_ex[index].public.book_ticker[self.context.symbol]

    @property
    def is_opened(self):
        return self.hedge_pos.qty > 0 and self.total_spot_qty > 0

    async def init_with_hedge_position(self, signal: InventorySignalWithLimitEnum):
        pass

    async def manage_delta_hedge(self):
        delta = self.total_spot_qty - self.hedge_pos.qty  # futures_qty is negative for short positions

        if abs(delta) < self._hedge_ex.public.get_min_base_quantity(self.context.symbol):
            return False

        self.logger.info(f"⚖️ Detected position imbalance: delta={delta:.8f}, "
                         f"spot={self.total_spot_qty}, futures={self.hedge_pos.qty}")

        book_ticker = self._hedge_ex.public.book_ticker[self.context.symbol]
        price = book_ticker.ask_price if delta < 0 else book_ticker.bid_price
        side = Side.SELL if delta > 0 else Side.BUY
        self.logger.info(f"⚖️ Re-balance futures: side={side.name}, qty={abs(delta):.8f} at price={price:.8f}")

        await self.hedge_manager.place_order(side=side, price=price, quantity=abs(delta), is_market=True)

    async def manage_arbitrage(self, signal: InventorySignalWithLimitEnum):
        pass

    async def _manage_positions(self):
        index_mexc = self._spot_ex_map[ExchangeEnum.MEXC]
        index_gateio = self._spot_ex_map[ExchangeEnum.GATEIO]

        book_tickers = {ExchangeEnum.MEXC: self.get_spot_book_ticker(index_mexc),
                        ExchangeEnum.GATEIO: self.get_spot_book_ticker(index_gateio)}

        signal = self.signal.get_live_signal_book_ticker(book_tickers)

        if signal != InventorySignalWithLimitEnum.HOLD:
            if not self.is_opened:
                await self.init_with_hedge_position(signal)
            else:
                await self.manage_arbitrage(signal)

        await self.manage_delta_hedge()
