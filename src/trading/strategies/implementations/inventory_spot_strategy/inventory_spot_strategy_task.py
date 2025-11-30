import asyncio
import copy
from typing import Dict, Tuple, Optional, Type, List

from db.models import Symbol
from exchanges.structs import ExchangeEnum, BookTicker, Order
from exchanges.structs.common import Side
from infrastructure.logging import HFTLoggerInterface
from trading.strategies.implementations.base_strategy.pnl_tracker import PositionChange
from trading.strategies.implementations.base_strategy.position_manager import PositionManager
from trading.strategies.structs import MarketData

from trading.strategies.implementations.base_strategy.base_multi_spot_futures_strategy import (
    BaseMultiSpotFuturesArbitrageTask,
    BaseMultiSpotFuturesTaskContext)
from trading.signals_v2.implementation.inventory_spot_strategy_signal import InventorySpotStrategySignal, \
    InventorySignalPairType, ArbitrageLegType, ArbitrageSetup, ExchangeSideAllowanceType
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
        self._opo_pos: Dict[ExchangeEnum, PositionManager] = {}

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

        # await self._pos[ExchangeEnum.MEXC].cancel_order()
        # self.primary_exchange = ExchangeEnum.MEXC
        #
        # if self._pos[ExchangeEnum.MEXC].qty >= self._pos[ExchangeEnum.GATEIO].qty:
        #     self.primary_side = Side.SELL
        # else:
        #     self.primary_side = Side.BUY

    async def stop(self):
        await super().stop()

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
        self.logger.info(f"✅ {order.exchange.name} Order filled: {order} -> {self.status()}")
        # skip hedge fills

        if order.exchange in [ExchangeEnum.GATEIO_FUTURES]:
            return

        curr_setup = self.current_setup
        if not curr_setup:
            await self._adjust_spot_delta()
        else:
            if curr_setup.all_market:
                self.logger.info(" ⚪️ Both legs are market orders, no action needed on fill")
                await self._finish_arb_trade()
                return
            elif order.exchange == curr_setup.market_leg:
                # do nothing
                return
            else:
                await self._execute_market_leg(self.current_setup)
            # await self._execute_market_leg(order)

        # _execute_market_leg
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

    async def _execute_both_market(self, setup: ArbitrageSetup, qty: float) -> Optional[Tuple[Order, Order]]:
        try:
            tasks = []
            for e, params in setup.leg.items():
                pos = self._pos[e]
                if params.side == Side.SELL:
                    qty = min(pos.qty, qty)
                    if qty < pos.get_min_base_qty(params.side):
                        self.logger.info(f" ⚪️ {e.name} {qty} position too small to execute market order, skipping")
                        continue
                elif qty > self.context.total_quantity and params.side == Side.BUY:
                    self.logger.info(f" ⚪️ {e.name} {qty} position too big to execute market order, skipping")
                    continue

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

    async def _execute_primary_leg(self, arb_setup: ArbitrageSetup, arb_qty: float) -> Optional[Tuple[Order, Order]]:
        try:
            exchange_leg = list(arb_setup.leg.keys())[0] if len(arb_setup.leg) == 1 else arb_setup.limit_leg
            side = arb_setup.leg[exchange_leg].side
            is_market = arb_setup.leg[exchange_leg].is_market

            if is_market:
                await self._pos[exchange_leg].place_market_order(
                    side=side,
                    quantity=arb_qty,
                )
                return None

            await self._pos[arb_setup.limit_leg].place_trailing_limit_order(
                side=side,
                quantity=arb_qty,  # slightly over to ensure full fill
            )
            return None
        except Exception as e:
            self.logger.error(f"❌ Error executing both market orders: {e}")
            return None

    async def _finish_arb_trade(self):
        if self._pos[ExchangeEnum.MEXC].pnl.pnl_usdt > 0 and self._pos[ExchangeEnum.GATEIO].pnl.pnl_usdt > 0:
            self.logger.info(f"✅ Arbitrage trade completed for setup: {self.current_setup}")

        pass

    async def _adjust_spot_delta(self) -> Optional[ExchangeEnum]:
        sell_exchange = None

        # detect spot with max qty
        max_qty = max([p.qty for p in self._pos.values()])
        for exchange, pos in self._pos.items():
            # skip futures hedge
            if exchange == ExchangeEnum.GATEIO_FUTURES:
                continue

            if pos.qty == max_qty and max_qty > 0:
                sell_exchange = exchange

        if not sell_exchange:
            return None

        sell_pos = self._pos[sell_exchange]
        buy_pos = self._opo_pos[sell_exchange]

        delta_qty = sell_pos.qty - buy_pos.qty
        if delta_qty >= buy_pos.get_min_base_qty():
            # no arbitrage setup, and limit leg has more qty than market leg
            self.logger.info(" ⚪️ No arbitrage setup and spot disbalance detected, executing market order to rebalance")
            await buy_pos.place_market_order(
                side=Side.BUY,
                quantity=delta_qty
            )
            return None

        return sell_exchange

    async def _execute_market_leg(self, arb_setup: ArbitrageSetup):
        if not arb_setup.market_leg:
            return None

        # market_pos = self._pos[arb_setup.market_leg]
        # limit_pos = self._pos[arb_setup.limit_leg]
        market_pos = self._pos[arb_setup.market_leg]

        sell_pos = self._pos[arb_setup.get_leg_by_side(Side.SELL)]
        buy_pos = self._pos[arb_setup.get_leg_by_side(Side.BUY)]

        delta_qty = sell_pos.qty - buy_pos.qty if market_pos.position.side == Side.BUY else buy_pos.qty - sell_pos.qty

        side = arb_setup.market_side
        min_qty = market_pos.get_min_base_qty(side)

        if delta_qty <= min_qty:
            # self.logger.info(f" ⚪️ Arbitrage quantity {delta_qty} less than min market leg qty {min_qty}, skipping")
            return None

        if side == Side.SELL and market_pos.qty < min_qty:
            self.logger.info(
                f" 🚫️ {buy_pos.exchange.name} market leg position too small to execute market order, skipping")
            return None

        await market_pos.place_market_order(
            side=side,
            quantity=delta_qty
        )

        # accomplish when sold all, or market leg qty is less than min qty
        if sell_pos.qty == 0:
            print(f'PROFIT: {buy_pos.position} {sell_pos.position}')
            await self._finish_arb_trade()

    def get_best_setup(self, setups: List[ArbitrageSetup]) -> Optional[ArbitrageSetup]:
        best = None
        for setup in setups:
            if setup is None:
                continue
            if not best or setup.spread_bps > best.spread_bps:
                best = setup
        return best

    def _get_exchange_availability(self) -> ExchangeSideAllowanceType:
        """Get position availability for each exchange and side.
        
        Returns:
            Dict mapping exchange -> {Side.BUY: bool, Side.SELL: bool}
            where bool indicates if exchange has sufficient position for that side.
        """
        mexc_pos = self._pos[ExchangeEnum.MEXC]
        gateio_pos = self._pos[ExchangeEnum.GATEIO]

        # BUY operations require position < total_qty (room to buy more)
        # SELL operations require position > 0 (inventory to sell)
        mexc_can_buy = mexc_pos.qty < self.context.total_quantity - mexc_pos.get_min_base_qty(Side.BUY)
        mexc_can_sell = mexc_pos.qty > mexc_pos.get_min_base_qty(Side.SELL)

        gateio_can_buy = gateio_pos.qty < self.context.total_quantity - gateio_pos.get_min_base_qty(Side.SELL)
        gateio_can_sell = gateio_pos.qty > gateio_pos.get_min_base_qty(Side.SELL)

        return {
            ExchangeEnum.MEXC: {Side.BUY: mexc_can_buy, Side.SELL: mexc_can_sell},
            ExchangeEnum.GATEIO: {Side.BUY: gateio_can_buy, Side.SELL: gateio_can_sell}
        }

    async def _manage_arbitrage(self) -> Optional[Order]:

        try:
            threshold_bps = 5

            # default qty
            arb_qty = self.context.order_qty
            mexc_pos = self._pos[ExchangeEnum.MEXC]
            gateio_pos = self._pos[ExchangeEnum.GATEIO]

            min_qty = min(mexc_pos.get_min_base_qty(Side.SELL), gateio_pos.get_min_base_qty(Side.SELL))

            # edge cases
            # both empty: buy with lower price exchange
            trading_setup = None
            if self.total_spot_qty < min_qty:
                buy_leg = ExchangeEnum.MEXC if mexc_pos.book_ticker.bid_price < gateio_pos.book_ticker.bid_price else ExchangeEnum.GATEIO
                trading_setup = ArbitrageSetup(leg={buy_leg: ArbitrageLegType(side=Side.BUY, is_market=False)},
                                               id=f"single_{buy_leg}_BUY")
            elif mexc_pos.qty > self.context.total_quantity and gateio_pos.qty > self.context.total_quantity:
                sell_leg = ExchangeEnum.MEXC if mexc_pos.book_ticker.ask_price > gateio_pos.book_ticker.ask_price else ExchangeEnum.GATEIO
                trading_setup = ArbitrageSetup(leg={sell_leg: ArbitrageLegType(side=Side.SELL, is_market=False)},
                                               id=f"single_{sell_leg}_SELL")
            else:
                # Get position availability for filtering signals
                availability = self._get_exchange_availability()
                trading_setup = self.signal.get_signals(availability, threshold_bps)
                pass

            if self.current_setup != trading_setup:
                self.logger.info(self.status())
                prev_setup = copy.deepcopy(self.current_setup)
                self.logger.info(f" 🔄 New trading setup detected {trading_setup} prev {prev_setup}")
                self.current_setup = trading_setup

                # cancel trailing limit orders on setup change
                await asyncio.gather(*[pos.cancel_order() for pos in self._pos.values()])

                if trading_setup:
                    is_changed = False
                    if len(trading_setup.leg) == 1:
                        leg, item = list(trading_setup.leg.items())[0]
                        if self._pos[leg].position.side != item.side:
                            self._pos[leg].set_side(item.side)
                            opo_side = Side.BUY if item.side == Side.SELL else Side.SELL
                            self._pos[self.opo_exchange[leg]].set_side(opo_side)
                            is_changed = True
                    else:
                        for leg, item in trading_setup.leg.items():
                            if self._pos[leg].position.side != item.side:
                                self._pos[leg].set_side(item.side)
                                is_changed = True

                    if is_changed:
                        await self._finish_arb_trade()

                    # if is_accomplished:
                    #     await self._finish_arb_trade()

            if not trading_setup:
                return None

            if trading_setup.all_market:
                await self._execute_both_market(trading_setup, arb_qty)
                # finish after both market legs
                await self._finish_arb_trade()
            else:
                await self._execute_primary_leg(trading_setup, arb_qty)

            # check market leg regardless setup, to handle when setup is gone
            # and limit order was executed in between signals
            # if not trading_setup:
            #     await self._adjust_spot_delta()
            # else:
            #     await self._execute_market_leg(trading_setup)

            return None
        except Exception as e:
            self.logger.error(f"❌ Error managing spot position: {e}")
            import traceback
            traceback.print_exc()
            return None

    # async def _manage_arbitrage(self) -> Optional[Order]:
    #
    #     try:
    #         threshold_bps = 5
    #
    #         # default qty
    #         arb_qty = self.context.order_qty
    #         mexc_pos = self._pos[ExchangeEnum.MEXC]
    #         gateio_pos = self._pos[ExchangeEnum.GATEIO]
    #
    #         abs_delta = abs(mexc_pos.qty - gateio_pos.qty)
    #         min_qty = min(mexc_pos.get_min_base_qty(Side.SELL), gateio_pos.get_min_base_qty(Side.SELL))
    #
    #         # Get position availability for filtering signals
    #         availability = self._get_exchange_availability()
    #
    #         # both have zero position
    #         if self.total_spot_qty < min_qty:
    #             # Only request BUY signals from exchanges that can actually buy
    #             possible_setups = []
    #             if availability[ExchangeEnum.MEXC][Side.BUY]:
    #                 mexc_setup = self.signal.get_best_setup(exchange=ExchangeEnum.MEXC, side=Side.BUY, threshold_bps=threshold_bps)
    #                 if mexc_setup:
    #                     possible_setups.append(mexc_setup)
    #
    #             if availability[ExchangeEnum.GATEIO][Side.BUY]:
    #                 gateio_setup = self.signal.get_best_setup(exchange=ExchangeEnum.GATEIO, side=Side.BUY, threshold_bps=threshold_bps)
    #                 if gateio_setup:
    #                     possible_setups.append(gateio_setup)
    #
    #             trading_setup = self.get_best_setup(possible_setups)
    #         else:
    #             # have no imbalance, but both have balance
    #             if abs_delta > min_qty and mexc_pos.qty > 0 and gateio_pos.qty > 0:
    #                 # Only request SELL signals from exchanges that can actually sell
    #                 possible_setups = []
    #                 if availability[ExchangeEnum.MEXC][Side.SELL]:
    #                     mexc_setup = self.signal.get_best_setup(exchange=ExchangeEnum.MEXC, side=Side.SELL, threshold_bps=threshold_bps)
    #                     if mexc_setup:
    #                         possible_setups.append(mexc_setup)
    #
    #                 if availability[ExchangeEnum.GATEIO][Side.SELL]:
    #                     gateio_setup = self.signal.get_best_setup(exchange=ExchangeEnum.GATEIO, side=Side.SELL, threshold_bps=threshold_bps)
    #                     if gateio_setup:
    #                         possible_setups.append(gateio_setup)
    #
    #                 trading_setup = self.get_best_setup(possible_setups)
    #                 arb_qty = min(mexc_pos.qty, gateio_pos.qty)
    #             else:
    #                 primary_exchange = ExchangeEnum.GATEIO if mexc_pos.qty - gateio_pos.qty > 0 else ExchangeEnum.MEXC
    #                 # Only request BUY signal if primary exchange can actually buy
    #                 if availability[primary_exchange][Side.BUY]:
    #                     trading_setup = self.signal.get_best_setup(primary_exchange, Side.BUY, threshold_bps=threshold_bps)
    #                 else:
    #                     trading_setup = None
    #                 arb_qty = abs_delta if abs_delta > min_qty else self.context.order_qty
    #
    #         if self.current_setup != trading_setup:
    #             self.logger.info(self.status())
    #             self.logger.info(f" 🔄 New trading setup detected on {trading_setup}")
    #             self.current_setup = trading_setup
    #
    #             # cancel trailing limit orders on setup change
    #             await asyncio.gather(*[pos.cancel_order() for pos in self._pos.values()])
    #
    #             if trading_setup:
    #                 is_accomplished = False
    #                 for leg, item in trading_setup.leg.items():
    #                     if self._pos[leg].position.side != item.side:
    #                         is_accomplished = True
    #                     self._pos[leg].set_side(item.side)
    #
    #                 if is_accomplished:
    #                     await self._finish_arb_trade()
    #
    #         if not trading_setup:
    #             return None
    #
    #         if trading_setup.all_market:
    #             return await self._execute_both_market(trading_setup, arb_qty)
    #         else:
    #             await self._execute_limit_leg(trading_setup, arb_qty)
    #
    #         # check market leg regardless setup, to handle when setup is gone
    #         # and limit order was executed in between signals
    #         # if not trading_setup:
    #         #     await self._adjust_spot_delta()
    #         # else:
    #         #     await self._execute_market_leg(trading_setup)
    #
    #         return None
    #     except Exception as e:
    #         self.logger.error(f"❌ Error managing spot position: {e}")
    #         import traceback
    #         traceback.print_exc()
    #         return None

    async def _manage_positions(self):
        # if await self._manage_transfer_between_exchanges():
        #     return

        book_tickers = {ExchangeEnum.MEXC: self._pos[ExchangeEnum.MEXC].book_ticker,
                        ExchangeEnum.GATEIO: self._pos[ExchangeEnum.GATEIO].book_ticker,
                        ExchangeEnum.GATEIO_FUTURES: self.hedge_manager.book_ticker}

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
                                          gateio_spread_threshold_bps: Optional[
                                              float] = 30) -> InventorySpotStrategyTask:
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
