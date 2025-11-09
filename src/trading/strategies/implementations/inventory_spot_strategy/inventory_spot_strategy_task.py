import asyncio
from typing import Dict, Tuple, Optional, Type

from db.models import Symbol
from exchanges.structs import ExchangeEnum, BookTicker
from exchanges.structs.common import Side
from infrastructure.logging import HFTLoggerInterface
from trading.strategies.implementations.base_strategy.position_manager import PositionManager
from trading.strategies.structs import MarketData

from utils.math_utils import get_decrease_vector

from trading.strategies.implementations.base_strategy.base_multi_spot_futures_strategy import (
    BaseMultiSpotFuturesArbitrageTask,
    BaseMultiSpotFuturesTaskContext)
from trading.signals_v2.implementation.inventory_spot_strategy_signal import InventorySpotStrategySignal, \
    InventorySignalWithLimitEnum
from utils.logging_utils import disable_default_exchange_logging


class InventorySpotTaskContext(BaseMultiSpotFuturesTaskContext, kw_only=True):
    name: str = "inventory_spot_strategy"
    mexc_spread_threshold_bps: Optional[float] = 30,
    gateio_spread_threshold_bps: Optional[float] = 30


class InventorySpotStrategyTask(BaseMultiSpotFuturesArbitrageTask[InventorySpotTaskContext]):
    name = "inventory_spot_strategy"

    @property
    def context_class(self) -> Type[InventorySpotTaskContext]:
        """Return the spot-futures arbitrage context class."""
        return InventorySpotTaskContext

    def __init__(self,
                 context: InventorySpotTaskContext,
                 logger: HFTLoggerInterface = None,
                 **kwargs):
        """Initialize spot-futures arbitrage task.
        """
        super().__init__(context, logger, **kwargs)

        params = {'mexc_spread_threshold_bps': self.context.mexc_spread_threshold_bps,
                  'gateio_spread_threshold_bps': self.context.gateio_spread_threshold_bps}
        self.signal = InventorySpotStrategySignal(params=params)

        # disable logging from exchange modules to reduce noise
        disable_default_exchange_logging()

        self._pos: Dict[ExchangeEnum, PositionManager] = {}

    async def start(self):
        await super().start()
        self._pos = {self._spot_ex_map[i]: spot_man for i, spot_man in enumerate(self._spot_managers)}
        self._pos[ExchangeEnum.GATEIO_FUTURES] = self.hedge_manager

    def get_spot_book_ticker(self, index: int) -> BookTicker:
        return self._spot_ex[index].public.book_ticker[self.context.symbol]

    @property
    def is_opened(self):
        return self.hedge_pos.qty > 0 and self.total_spot_qty > 0

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
        pos_mexc = self._pos[ExchangeEnum.MEXC]
        pos_gateio = self._pos[ExchangeEnum.GATEIO]
        qty = self.context.order_qty

        # MEXC, GATEIO params mapping
        signal_mapping = {
            InventorySignalWithLimitEnum.MARKET_MEXC_SELL_LIMIT_GATEIO_BUY: ((Side.SELL, True), (Side.BUY, False)),
            InventorySignalWithLimitEnum.LIMIT_MEXC_SELL_MARKET_GATEIO_BUY: ((Side.SELL, False), (Side.BUY, True)),
            InventorySignalWithLimitEnum.LIMIT_GATEIO_SELL_MARKET_MEXC_BUY: ((Side.BUY, True), (Side.SELL, False)),
            InventorySignalWithLimitEnum.MARKET_GATEIO_SELL_LIMIT_MEXC_BUY: ((Side.BUY, True), (Side.SELL, False)),
            InventorySignalWithLimitEnum.MARKET_GATEIO_SELL_MARKET_MEXC_BUY: ((Side.BUY, True), (Side.SELL, True)),
            InventorySignalWithLimitEnum.MARKET_MEXC_SELL_MARKET_GATEIO_BUY: ((Side.SELL, True), (Side.BUY, True))
        }

        mexc_params, gateio_params = signal_mapping.get(signal)
        mexc_sell_allowed = pos_mexc.is_fulfilled() or mexc_params[0] == Side.BUY
        gateio_sell_allowed = pos_gateio.is_fulfilled() or gateio_params[0] == Side.BUY

        if not mexc_sell_allowed or not gateio_sell_allowed:
            self.logger.info(f"⚠️ {signal.name} Sell not allowed - MEXC {pos_mexc} GATEIO {pos_gateio}")
            return

        tasks = []

        if mexc_params[1]:
            if not self.is_opened:  # workaround to open with limit one side if position not persisted
                tasks.append(pos_mexc.place_market_order(
                    side=mexc_params[0],
                    quantity=qty,
                ))
        else:
            tasks.append(pos_mexc.place_trailing_limit_order(
                side=mexc_params[0],
                quantity=qty,
            ))

        if gateio_params[1]:
            if not self.is_opened:  # workaround to open with limit one side if position not persisted
                tasks.append(pos_gateio.place_market_order(
                    side=gateio_params[0],
                    quantity=qty,
                ))
        else:
            tasks.append(pos_mexc.place_trailing_limit_order(
                side=gateio_params[0],
                quantity=qty,
            ))

        await asyncio.gather(*tasks)

    async def _manage_positions(self):

        book_tickers = {ExchangeEnum.MEXC: self._pos[ExchangeEnum.MEXC].book_ticker,
                        ExchangeEnum.GATEIO: self._pos[ExchangeEnum.GATEIO].book_ticker}

        signal = self.signal.get_live_signal_book_ticker(book_tickers)

        if signal != InventorySignalWithLimitEnum.HOLD:
            self.logger.info(f"Live Signal: {signal.name} MEXC: {self._pos[ExchangeEnum.MEXC].book_ticker},"
                             f" GATEIO: {self._pos[ExchangeEnum.GATEIO].book_ticker}")

            await self.manage_arbitrage(signal)
        else:
            await asyncio.gather(*[p.cancel_order() for p in self._spot_managers])

        await self.manage_delta_hedge()


def create_inventory_spread_strategy_task(symbol: Symbol, order_qty: float, total_qty: float,
                mexc_spread_threshold_bps: Optional[float] = 30,
                gateio_spread_threshold_bps: Optional[float] = 30) -> InventorySpotStrategyTask:
    spot_settings = [MarketData(
        exchange=ExchangeEnum.MEXC,
    ),
        MarketData(
            exchange=ExchangeEnum.GATEIO,
        )]

    hedge_settings = MarketData(exchange=ExchangeEnum.GATEIO_FUTURES)

    context = InventorySpotTaskContext(
        symbol=symbol,
        order_qty=order_qty,
        total_quantity=total_qty,
        spot_settings=spot_settings,
        hedge_settings=hedge_settings,
        mexc_spread_threshold_bps=mexc_spread_threshold_bps,
        gateio_spread_threshold_bps=gateio_spread_threshold_bps

    )
    return InventorySpotStrategyTask(context=context)
