import asyncio
from typing import Dict, Tuple, Optional, Type, List

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
    InventorySignalPairType, InventorySignalType, ArbitrageSetup
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

        self.current_setup: Optional[ArbitrageSetup] = None
        self.primary_exchange: Optional[ExchangeEnum] = None
        self.primary_side: Side = Side.BUY

    async def start(self):
        await super().start()
        self._pos = {self._spot_ex_map[i]: spot_man for i, spot_man in enumerate(self._spot_managers)}
        self._opo_pos = {exchange: self._pos[self.opo_exchange[exchange]] for exchange in self._pos}

        self._pos[ExchangeEnum.GATEIO_FUTURES] = self.hedge_manager

        await self._pos[ExchangeEnum.MEXC].cancel_order()
        # self.primary_exchange = ExchangeEnum.MEXC
        #
        # if self._pos[ExchangeEnum.MEXC].qty >= self._pos[ExchangeEnum.GATEIO].qty:
        #     self.primary_side = Side.SELL
        # else:
        #     self.primary_side = Side.BUY

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

    async def _on_order_filled_callback(self, order: Order, change: PositionChange):
        self.logger.info(f"✅ {order.exchange} Order filled: {order}")
        pass
        #
        # if order.exchange == ExchangeEnum.MEXC:
        #     # switch mexc side
        #     gateio_side = Side.BUY if order.side == Side.SELL else Side.SELL
        #     gateio_pos = self._pos[ExchangeEnum.GATEIO]
        #     qty_executed = self._pos[ExchangeEnum.MEXC].get_filled_qty(order.side)
        #
        #     qty = min(gateio_pos.qty, qty_executed) if gateio_side == Side.SELL else qty_executed
        #
        #     if qty <= gateio_pos.get_min_base_qty():
        #         return
        #
        #     return await self._pos[ExchangeEnum.GATEIO].place_market_order(
        #         side=gateio_side,
        #         quantity=qty,
        #     )

    async def _execute_both_market(self, setup: ArbitrageSetup)-> Optional[Tuple[Order, Order]]:
        try:
            qty = min(self._pos[ExchangeEnum.MEXC].qty, self._pos[ExchangeEnum.GATEIO].qty)
            tasks = []
            for e, params in setup.leg.items():
                pos = self._pos[e]
                if qty < pos.get_min_base_qty(params.side):
                    self.logger.info(f" ⚪️ {e.name} position too small to execute market order, skipping")
                    return None
                tasks.append(self._pos[e].place_market_order(
                    side=params.side,
                    quantity=qty,
                ))
            await asyncio.gather(*tasks)
            await self._finish_arb_trade()
            return None
        except Exception as e:
            self.logger.error(f"❌ Error executing both market orders: {e}")
            return None

    async def _execute_limit_leg(self, arb_setup: ArbitrageSetup)-> Optional[Tuple[Order, Order]]:
        try:
            side = arb_setup.leg[arb_setup.limit_leg].side
            if side == Side.BUY:
                opo_qty = self._opo_pos[arb_setup.limit_leg].qty

                min_arb_qty = max(self._pos[arb_setup.limit_leg].get_min_base_qty(),
                                  self._opo_pos[arb_setup.limit_leg].get_min_base_qty(Side.SELL))
                if opo_qty < min_arb_qty:
                    qty = self.context.order_qty
                else:
                    if self._pos[ExchangeEnum.MEXC].qty > 0:
                        qty = min(self._pos[ExchangeEnum.MEXC].qty, self._pos[ExchangeEnum.GATEIO].qty)
                    else:
                        qty = self._pos[ExchangeEnum.GATEIO].qty
            else:
                qty = self._pos[arb_setup.limit_leg].qty
                # limit_pos = self._pos[arb_setup.limit_leg]
                # if limit_pos.qty > limit_pos.get_min_base_qty(limit_side=Side.SELL):
                # # qty = min(self._pos[ExchangeEnum.MEXC].qty, self._pos[ExchangeEnum.GATEIO].qty)
                #     qty = self._pos[arb_setup.limit_leg].qty
                # else:

            await self._pos[arb_setup.limit_leg].place_trailing_limit_order(
                side=side,
                quantity=qty
            )
            return None
        except Exception as e:
            self.logger.error(f"❌ Error executing both market orders: {e}")
            return None

    async def _finish_arb_trade(self):
        pass

    async def _sync_spot_legs(self):
        market_pos = self._pos[self.current_setup.market_leg]
        limit_pos = self._pos[self.current_setup.limit_leg]
        limit_side = self.current_setup.leg[self.current_setup.limit_leg].side
        market_side = self.current_setup.leg[self.current_setup.market_leg].side
        market_qty = limit_pos.get_filled_qty(limit_side) - market_pos.get_filled_qty(market_side)
        both_filled = limit_pos.get_filled_qty(limit_side) > 0 and market_pos.get_filled_qty(market_side) > 0
        if market_qty >= market_pos.get_min_base_qty():
            await market_pos.place_market_order(
                side=market_side,
                quantity=market_qty
            )

        sell_pos = market_pos if market_side == Side.SELL else limit_pos
        # accomplish when sold all, or market leg qty is less than min qty
        if both_filled and (sell_pos.qty == 0  or market_qty < market_pos.get_min_base_qty()):
            await self._finish_arb_trade()

    def get_best_setup(self, setups: List[ArbitrageSetup]) -> Optional[ArbitrageSetup]:
        best = None
        for setup in setups:
            if setup is None:
                continue
            if not best or setup.spread_bps > best.spread_bps:
                best = setup
        return best

    async def _manage_arbitrage(self) -> Optional[Order]:

        try:
            threshold_bps = 5
            # if not opened choose the best opportunity to initial buy
            if self.total_spot_qty == 0:
                # trading_setup = self.get_best_setup([
                #     self.signal.get_best_setup(exchange=ExchangeEnum.MEXC, side=Side.BUY),
                #     self.signal.get_best_setup(exchange=ExchangeEnum.GATEIO, side=Side.BUY)
                # ])
                # if not trading_setup and trading_setup.limit_side != Side.BUY:
                trading_setup = self.get_best_setup([
                    self.signal.get_best_setup(exchange=ExchangeEnum.MEXC, side=Side.BUY, is_market=False,
                                               threshold_bps=threshold_bps),
                    self.signal.get_best_setup(exchange=ExchangeEnum.GATEIO, side=Side.BUY, is_market=False,
                                               threshold_bps=threshold_bps)
                ])
                pass
            else:
                mexc_pos = self._pos[ExchangeEnum.MEXC]
                gateio_pos = self._pos[ExchangeEnum.GATEIO]
                primary_side = Side.SELL

                if gateio_pos.qty == 0 and mexc_pos.qty > 0:
                    primary_exchange = ExchangeEnum.GATEIO
                    primary_side = Side.BUY
                elif mexc_pos.qty == 0 and gateio_pos.qty > 0:
                    primary_exchange = ExchangeEnum.MEXC
                    primary_side = Side.BUY
                else:
                    primary_exchange = ExchangeEnum.MEXC if mexc_pos.qty >= gateio_pos.qty else ExchangeEnum.GATEIO

                trading_setup = self.signal.get_best_setup(primary_exchange, primary_side, is_market=False,
                                                           threshold_bps=threshold_bps)


            if self.current_setup != trading_setup:
                self.logger.info(f" 🔄 New trading setup detected on {trading_setup}")
                # TODO: cancel trailing limit orders on setup change
                self.current_setup = trading_setup
                await asyncio.gather(*[pos.cancel_order() for pos in self._pos.values()])

            if not trading_setup:
                return None

            if trading_setup.all_market:
                return await self._execute_both_market(trading_setup)

            await self._execute_limit_leg(trading_setup)
            await self._sync_spot_legs()
            return None
        except Exception as e:
            self.logger.error(f"❌ Error managing spot position on MEXC: {e}")
            return None

    async def _manage_positions(self):
        # if await self._manage_transfer_between_exchanges():
        #     return

        book_tickers = {ExchangeEnum.MEXC: self._pos[ExchangeEnum.MEXC].book_ticker,
                        ExchangeEnum.GATEIO: self._pos[ExchangeEnum.GATEIO].book_ticker}

        # signals: InventorySignalPairType = self.signal.get_live_signal_book_ticker(book_tickers, threshold=15)
        # await asyncio.gather(*[self._manage_spot_position(signals, exchange) for exchange in signals])
        self.signal.get_live_signal_book_ticker(book_tickers, threshold=15)
        await self._manage_arbitrage()
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
