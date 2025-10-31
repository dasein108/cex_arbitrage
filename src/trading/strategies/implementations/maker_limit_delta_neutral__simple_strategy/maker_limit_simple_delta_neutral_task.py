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


    async def _adjust_futures_position(self):
        """Manage limit orders for one market."""
        # Skip if no quantity to fill
        spot_qty = self.spot_pos.qty if self.spot_pos.qty > self._get_min_base_qty('spot') else 0
        delta = spot_qty - self.futures_pos.qty
        if abs(delta) < self._get_min_base_qty('futures'):
            return

        quantity_to_fill = abs(delta)
        side = Side.BUY if delta > 0 else Side.SELL
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
        return self._exchanges['spot'].balances[self.context.symbol.base].available

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

        top_price = book_ticker.bid_price if side == Side.BUY else book_ticker.ask_price
        tick_difference = abs((order_price - top_price) / self._symbol_info['spot'].tick)
        should_cancel = tick_difference > settings.tick_tolerance

        if should_cancel:
            self.logger.info(
                f"⚠️ Price moved significantly on SPOT. Current {side.name}: {top_price}, "
                f"Our price: {order_price}")

            await self._cancel_order_safe('spot', order_id=curr_order.order_id)

        return should_cancel

    def handle_spot_mode(self):
        if self.spot_pos.is_fulfilled(self._get_min_base_qty('spot')):
            if self.spot_pos.mode == 'accumulate':
                self.logger.info("Switching SPOT position mode to 'release'")
                self.spot_pos.set_mode('release')
            else:
                self.logger.info("Switching SPOT position mode to 'accumulate'")

                spot_pnl = self.spot_pos.pnl_tracker
                fut_pnl = self.futures_pos.pnl_tracker
                total_pnl = spot_pnl.pnl_usdt + fut_pnl.pnl_usdt
                icon = "💰" if total_pnl > 0 else "🔻"
                self.logger.info(f"{icon} SPOT PnL: {spot_pnl.pnl_usdt:.4f}$ (net: {spot_pnl.pnl_usdt_net:.4f}$), "
                                 f"{self.spot_pos.entry_price} -> {self.spot_pos.price} ({self.spot_pos.entry_price - self.spot_pos.price:.4}) | "
                                 f"FUTURES PnL: {fut_pnl.pnl_usdt:.4f}$ (net: {fut_pnl.pnl_usdt_net:.4f}$), "
                                 f"{self.futures_pos.entry_price} -> {self.futures_pos.price}  ({self.futures_pos.entry_price - self.futures_pos.price:.4})| "
                                 f"Total PnL: {total_pnl:.4f}$ ")

                self.spot_pos.reset(self.context.total_quantity, reset_pnl=True)
                self.futures_pos.reset(self.context.total_quantity, reset_pnl=True)

                self.spot_pos.set_mode('accumulate')

    async def _manage_positions(self):
        """Manage both spot and futures positions."""
        await self._manage_spot_limit_order_place()
        await self._manage_spot_order_cancel()
        await self._adjust_futures_position()
        self.handle_spot_mode()


