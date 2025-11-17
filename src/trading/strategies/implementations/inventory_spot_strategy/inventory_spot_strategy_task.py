import asyncio
from typing import Dict, Tuple, Optional, Type

from db.models import Symbol
from exchanges.structs import ExchangeEnum, BookTicker, Order
from exchanges.structs.common import Side
from infrastructure.logging import HFTLoggerInterface
from trading.strategies.implementations.base_strategy.pnl_tracker import PositionChange
from trading.strategies.implementations.base_strategy.position_manager import PositionManager
from trading.strategies.implementations.cross_exchange_arbitrage_strategy.asset_transfer_module import \
    AssetTransferModule, TransferRequest
from trading.strategies.structs import MarketData

from trading.strategies.implementations.base_strategy.base_multi_spot_futures_strategy import (
    BaseMultiSpotFuturesArbitrageTask,
    BaseMultiSpotFuturesTaskContext)
from trading.signals_v2.implementation.inventory_spot_strategy_signal import InventorySpotStrategySignal, \
    InventorySignalPairType, InventorySignalType
from utils.logging_utils import disable_default_exchange_logging

TRANSFER_REFRESH_SECONDS = 30

class InventorySpotTaskContext(BaseMultiSpotFuturesTaskContext, kw_only=True):
    name: str = "inventory_spot_strategy"
    mexc_spread_threshold_bps: Optional[float] = 30,
    gateio_spread_threshold_bps: Optional[float] = 30
    transfer_request: Optional[TransferRequest] = None



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
        self._opo_pos: Dict[ExchangeEnum, PositionManager] = {}

        self._transfer_module: Optional[AssetTransferModule] = None
        self.opo_exchange = {
                ExchangeEnum.MEXC: ExchangeEnum.GATEIO,
                ExchangeEnum.GATEIO: ExchangeEnum.MEXC
            }

        self.mexc_side: Side = Side.BUY

    async def start(self):
        await super().start()
        self._pos = {self._spot_ex_map[i]: spot_man for i, spot_man in enumerate(self._spot_managers)}
        self._opo_pos = {exchange: self._pos[self.opo_exchange[exchange]] for exchange in self._pos}

        self._pos[ExchangeEnum.GATEIO_FUTURES] = self.hedge_manager

        await self._pos[ExchangeEnum.MEXC].cancel_order()

        if self._pos[ExchangeEnum.MEXC].qty >= self._pos[ExchangeEnum.GATEIO].qty:
            self.mexc_side = Side.SELL
        else:
            self.mexc_side = Side.BUY

        self._transfer_module = AssetTransferModule(
            exchanges={exchange: e.private for exchange, e in self._exchanges.items()},
            logger=self.logger
        )

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

    async def stop(self):
        await super().stop()
        await self._stop_transfer_monitor()

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

    async def _initiate_new_transfer(self) -> Optional[TransferRequest]:
        try:
            """Initiate a new transfer if position is fulfilled."""
            symbol = self.context.symbol
            from_exchange = to_exchange = None
            qty = 0.0
            asset = None

            for exchange, pos in self._pos.items():
                if pos.is_fulfilled():
                    from_exchange = exchange
                    to_exchange =self.opo_exchange[exchange]
                    qty = pos.position.qty
                    asset = symbol.base
                    break

            # nothing to transfer on base, check quote unrealized pnl
            if not asset:
                for exchange, pos in self._pos.items():
                    if pos.balance_usdt > self._pos[self.opo_exchange[exchange]].balance_usdt:
                        qty = self.context.total_quantity * pos.book_ticker.bid_price
                        asset = symbol.quote
                        from_exchange = exchange
                        to_exchange = self.opo_exchange[exchange]
                        break

            if asset and qty > 0:
                transfer_request = await self._transfer_module.transfer_asset(
                    symbol.base, from_exchange, to_exchange, qty, buy_price=0
                )

                self.logger.info(
                    f"🚀 Starting transfer of {qty} {symbol.base} from {from_exchange.name} to {to_exchange.name}")

                return transfer_request

            return None
        except Exception as e:
            self.logger.error(f"❌ Error initiating new transfer: {e}")
            return None


    async def _handle_completed_transfer(self, request: TransferRequest) -> None:
        """Handle a completed transfer and update positions accordingly."""
        self.logger.info(f"🔄 Transfer completed: {request.qty} {request.asset}: {request} resuming trading")
        await asyncio.gather(*[p.load_position_from_exchange() for p in self._spot_managers])


        # from infrastructure.networking.telegram import send_to_telegram
        # await send_to_telegram(msg)
        #
        # source_pos.reset(self.context.total_quantity)
        # dest_pos.reset(0.0)
        # hedge_pos.reset()

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
                    for p in self.context.positions:
                        p.reset(target_qty=self.context.total_quantity, reset_pnl=False)

                    self.context.set_save_flag()
                    await self._start_transfer_monitor()
                    return True
                else:
                    return False

        except Exception as e:
            self.logger.error(f"❌ Error managing transfer between exchanges: {e}")
            return False


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

    # async def _manage_spot_position(self, signals: InventorySignalPairType, exchange: ExchangeEnum) -> Optional[Order]:
    #     try:
    #         signal = signals.get(exchange)
    #         pos = self._pos[exchange]
    #         if not signal or pos.is_fulfilled():
    #             return None
    #
    #         opo_signal = signals.get(self.opo_exchange[exchange])
    #         opo_pos = self._opo_pos[exchange]
    #
    #         qty = min(self.context.order_qty, opo_pos.qty - pos.qty)
    #
    #         # avoid overfilling position
    #         if qty <= pos.get_min_base_qty():
    #             return None
    #
    #         if signal.is_market:
    #             # if exchange not market or opo position zero, market orders not allowed
    #             if not opo_signal and opo_signal.is_market and opo_pos.qty == 0:
    #                 return None
    #
    #             return await pos.place_market_order(
    #                 side=signal.side,
    #                 quantity=qty,
    #             )
    #
    #         return await pos.place_trailing_limit_order(
    #             side=signal.side,
    #             quantity=qty,
    #         )
    #     except Exception as e:
    #         self.logger.error(f"❌ Error managing spot position on {exchange.name}: {e}")
    #         return None
    async def _on_order_filled_callback(self, order: Order, change: PositionChange):
        self.logger.info(f"✅ {order.exchange} Order filled: {order}")
        if order.exchange == ExchangeEnum.MEXC:
            # switch mexc side
            self.mexc_side = Side.SELL if order.side == Side.BUY else Side.BUY
            gateio_side = Side.BUY if order.side == Side.SELL else Side.SELL
            gateio_pos = self._pos[ExchangeEnum.GATEIO]
            qty = min(gateio_pos.qty, change.delta_qty) if gateio_side == Side.SELL else change.delta_qty
            return await self._pos[ExchangeEnum.GATEIO].place_market_order(
                side=gateio_side,
                quantity=qty,
            )
    async def _manage_mexc_position(self) -> Optional[Order]:
        try:
            pos = self._pos[ExchangeEnum.MEXC]
            opo_pos = self._opo_pos[ExchangeEnum.MEXC]
            side =self.mexc_side

            if side == Side.BUY:
                if pos.is_fulfilled() and opo_pos.is_fulfilled():
                    self.mexc_side = Side.SELL
                    return None
                # qty = min(self.context.order_qty, opo_pos.qty - pos.qty) if is_opo_greater else self.context.order_qty
                qty = self.context.order_qty
            else:
                if pos.qty <= pos.get_min_base_qty():
                    # switch to BUY mode
                    self.logger.info(f" 🔄 MEXC position zero, switching to BUY mode")
                    self.mexc_side = Side.BUY

                    return None
                qty = min(self.context.order_qty, pos.qty)


            return await pos.place_trailing_limit_order(
                side=side,
                quantity=qty,
                top_offset_pct=0.1,
                trail_pct=0.2
            )
        except Exception as e:
            self.logger.error(f"❌ Error managing spot position on MEXC: {e}")
            return None
    # async def _manage_spot_position(self, exchange: ExchangeEnum) -> Optional[Order]:
    #     try:
    #         pos = self._pos[exchange]
    #
    #
    #
    #         opo_pos = self._opo_pos[exchange]
    #         is_opo_greater = opo_pos.qty > pos.qty
    #         qty = min(self.context.order_qty, opo_pos.qty - pos.qty) if is_opo_greater else self.context.order_qty
    #
    #
    #         # refuse to place order if opo position has an active order
    #         if opo_pos.has_order:
    #             return None
    #
    #         if exchange == ExchangeEnum.GATEIO:
    #             side = Side.BUY if pos.qty < opo_pos.qty else Side.SELL
    #
    #             restricted = pos.is_fulfilled() if side == Side.BUY else qty <= pos.get_min_base_qty()
    #             if not restricted:
    #                 return None
    #
    #             # if exchange not market or opo position zero, market orders not allowed
    #             if not is_opo_greater or opo_pos.qty == 0:
    #                 return None
    #
    #             return await pos.place_market_order(
    #                 side=side,
    #                 quantity=qty,
    #             )
    #
    #         side = Side.BUY if pos.qty == 0 or pos.qty < opo_pos.qty else Side.SELL
    #
    #         restricted = pos.is_fulfilled() if side == Side.BUY else qty <= pos.get_min_base_qty()
    #         if not restricted:
    #             return None
    #
    #         return await pos.place_trailing_limit_order(
    #             side=side,
    #             quantity=qty,
    #         )
    #     except Exception as e:
    #         self.logger.error(f"❌ Error managing spot position on {exchange.name}: {e}")
    #         return None

    async def _manage_positions(self):
        # if await self._manage_transfer_between_exchanges():
        #     return

        book_tickers = {ExchangeEnum.MEXC: self._pos[ExchangeEnum.MEXC].book_ticker,
                        ExchangeEnum.GATEIO: self._pos[ExchangeEnum.GATEIO].book_ticker}

        # signals: InventorySignalPairType = self.signal.get_live_signal_book_ticker(book_tickers, threshold=15)
        # await asyncio.gather(*[self._manage_spot_position(signals, exchange) for exchange in signals])
        self.signal.get_live_signal_book_ticker(book_tickers, threshold=15)
        await self._manage_mexc_position()
        await self.manage_delta_hedge()

    def status(self):
        return (f"HEDGE: {self.hedge_pos}, MEXC SPOT: {self._pos[ExchangeEnum.MEXC].position}, "
                f"GATEIO SPOT: {self._pos[ExchangeEnum.GATEIO].position}")

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
