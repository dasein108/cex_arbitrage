import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Coroutine

from config import MEXC_KEY, MEXC_SECRET
from exchanges.common.entities import AccountBalance, Deal, Kline, Order, SymbolInfo, SymbolStr, Ticker24
from exchanges.common.enums import Action, Interval, StreamInterval, from_interval, from_stream_interval
from exchanges.common.exceptions import apply_exception_handler
from exchanges.common.interfaces import BaseSyncExchange
from exchanges.mexc_api.rest_api import MexcRestApi, mexc_exception_handler
from exchanges.mexc_api.websocket.mexc_ws import MexcWebSocketBase
from strategies.modules.OrderBook import AlgoOrderbook
from utils.date import now
from utils.decorators import repeat_every
from utils.exceptions import with_traceback

# Import moved to avoid circular import - will be imported locally where needed


TRUNC_DEALS = 100
TRUNC_ORDERS = 100

PUBLIC_STREAMS = ["spot@private.account.v3.api.protobuf", "spot@private.deals.v3.api.protobuf", "spot@private.orders.v3.api.protobuf"]

# apply interceptors for exceptions
apply_exception_handler(MexcRestApi, mexc_exception_handler)


class MexcSyncExchange(BaseSyncExchange):
    tag = "mexc"
    _symbol_info: Dict[SymbolStr, SymbolInfo] = {}

    def __init__(self, on_trade: Optional[Callable[[SymbolStr, Deal], Coroutine]] = None):
        super().__init__()
        self.on_trade = on_trade

        self.wsb = MexcWebSocketBase(f"WS_MEXC", self._on_message, streams=PUBLIC_STREAMS)

        self.deals: Dict[SymbolStr, List[Deal]] = {}
        self.orders: Dict[SymbolStr, Dict[str, Order]] = {}
        self.klines: Dict[SymbolStr, Dict[Interval, List[Kline]]] = {}
        self._ob: Dict[SymbolStr, Optional[AlgoOrderbook]] = {}  # AlgoOrderbook - imported locally
        self.streams: Dict[SymbolStr, List[str]] = {}
        self._balance: Dict[str, AccountBalance] = {}
        self._symbol_info: Dict[SymbolStr, SymbolInfo] = {}
        self.ticker_24h: Dict[SymbolStr, Ticker24] = {}
        self.last_update = now()
        self.last_symbol_update: Dict[SymbolStr, datetime] = {}
        self._rest_api = MexcRestApi(MEXC_KEY, MEXC_SECRET)

    @property
    def ob(self) -> Dict[SymbolStr, AlgoOrderbook]:  # AlgoOrderbook
        return self._ob

    @property
    def symbol_info(self) -> Dict[SymbolStr, SymbolInfo]:
        return self._symbol_info

    @property
    def balance(self) -> Dict[str, AccountBalance]:
        return self._balance

    @property
    def rest_api(self) -> MexcRestApi:
        return self._rest_api

    @property
    def balance_free_usdt(self):
        return self._balance.get("USDT", AccountBalance("USDT", 0, 0)).free

    @repeat_every(15)
    async def refresh_tickers(self):
        await self.force_update_tickers()

    @repeat_every(30)
    async def refresh_balances(self):
        await self.force_update_balances()

    @repeat_every(60 * 5)
    async def _prune(self):
        legacy_timestamp = now() - timedelta(minutes=10)
        for symbol in self.orders:
            ids = list([k for k, v in self.orders[symbol].items() if v.timestamp < legacy_timestamp])
            for id in ids:
                del self.orders[symbol][id]

    async def force_update_tickers(self):
        tickers = await self.rest_api.get_usdt_ticker_24()
        self.ticker_24h = {s: t for s, t in tickers.items()}

    async def init(self):
        asyncio.create_task(self.refresh_tickers())
        asyncio.create_task(self.refresh_balances())

        self._symbol_info = await self.rest_api.load_symbol_info()
        await self.force_update_tickers()
        await self.force_update_balances()
        asyncio.create_task(self._prune())
        return self

    def get_last_price(self, symbol: SymbolStr):
        deals = self.deals.get(symbol)

        return deals[-1].price

    async def start_symbol(self, symbol: SymbolStr, with_deals=False):
        # Import locally to avoid circular import
        from strategies.modules.OrderBook import AlgoOrderbook

        kline_intervals = [Interval.ONE_MIN, Interval.FIVE_MIN]  # Interval.ONE_MIN

        orders = await self.rest_api.get_all_orders(symbol, TRUNC_ORDERS)
        self.orders[symbol] = {o.order_id: o for o in orders}

        coin = symbol.split("USDT")[0]

        self._balance[coin] = self._balance.get(coin, AccountBalance(coin, 0, 0))
        self.klines[symbol] = {}
        for k in kline_intervals:
            self.klines[symbol][k] = await self.rest_api.get_last_candles(symbol, k, 100)

        depth = await self.rest_api.get_order_book(symbol)

        self._ob[symbol] = AlgoOrderbook(symbol, self._symbol_info[symbol])
        self._ob[symbol].update(depth)
        self.last_symbol_update[symbol] = now()
        if with_deals:
            self.deals[symbol] = await self.rest_api.get_last_deals(symbol, TRUNC_DEALS)
            # 10ms 100ms
            streams = [
                f"spot@public.aggre.deals.v3.api.protobuf@10ms@{symbol.upper()}",
                f"spot@public.limit.depth.v3.api.protobuf@{symbol.upper()}@5",
            ]
        else:
            self.deals[symbol] = []
            streams = [f"spot@public.limit.depth.v3.api.protobuf@{symbol.upper()}@5"]

        streams += [f"spot@public.kline.v3.api.protobuf@{symbol.upper()}@{from_interval(k).value}" for k in kline_intervals]

        self.streams[symbol] = streams

        await self.wsb.subscribe(streams)

        logging.info(f"Websocket {symbol} started")

    async def stop_symbol(self, symbol: SymbolStr):
        await self.wsb.subscribe(self.streams[symbol], Action.UNSUBSCRIBE)
        # TODO: tmp disabled to avoid errors on stop
        # del self.orders[symbol]
        # del self.deals[symbol]
        # del self.klines[symbol]
        # del self.ob[symbol]
        del self.streams[symbol]
        logging.info(f"Websocket for {symbol} stopped")

    async def force_update_orderbook(self, symbol: SymbolStr, depth_size=5):
        try:
            depth = await self.rest_api.get_order_book(symbol, depth_size)
            self._ob[symbol].update(depth)
        except Exception as e:
            logging.warning(f"force update orderbook: {e}")

    async def force_update_balances(self):
        self._balance = await self.rest_api.get_balance()

    async def stop(self):
        await self.wsb.stop()
        logging.info("Websocket stopped")

    async def restart(self):
        logging.info("Restarting websocket...")
        await self.wsb.restart()

    # def open_orders(self):
    #     return get_open_orders(self.symbol)
    #
    async def get_order_cache(self, order: Order, force=False):
        o = self.orders[order.symbol].get(order.order_id, order)
        if not o.is_done() and force:
            return await self._rest_api.get_order_info(o)
        return o

    def get_change_24h(self, symbol: SymbolStr):
        return self.ticker_24h.get(symbol, Ticker24(0, 0))

    def get_ticker_price(self, symbol: SymbolStr):
        return float(self.ticker_24h.get(symbol, Ticker24(0, 0)).last_price)

    async def _on_message(self, msg):
        try:
            channel = msg.get("channel", "unknown")
            # data = msg.get('d', None)
            # if data is None:
            #     logging.info(f'No data in message: {msg}')
            #     return

            if channel == "spot@private.orders.v3.api.protobuf":
                self.last_update = now()

                symbol = msg["symbol"]
                o = Order.from_ws(symbol, msg["privateOrders"])  # , msg['t']
                if symbol in self.orders:
                    self.orders[symbol][o.order_id] = o

                # self.orders[symbol] = self.orders[symbol][-TRUNC_ORDERS:]
            elif channel == "spot@private.account.v3.api.protobuf":
                self.last_update = now()
                data = msg["privateAccount"]
                coin = data["vcoinName"]
                self._balance[coin] = AccountBalance(coin, float(data["balanceAmount"]), float(data["frozenAmount"]))
            elif channel == "spot@private.deals.v3.api.protobuf":
                # https://mexcdevelop.github.io/apidocs/spot_v3_en/#spot-account-deals
                # symbol = msg['s']
                # deal = Deal.from_ws(data['d'])
                pass
            elif channel.startswith("spot@public.aggre.deals.v3.api.protobuf"):
                _, __, ___, symbol = channel.split("@")
                data = msg["publicAggreDeals"]
                new_deals = [Deal.from_ws(d) for d in data["deals"]]
                for d in new_deals:
                    if self.on_trade:
                        await self.on_trade(symbol, d)

                if symbol in self.deals:
                    # self.deals[symbol] = []
                    self.deals[symbol] = self.deals[symbol][-TRUNC_DEALS:] + new_deals

            elif channel.startswith("spot@public.kline.v3.api.protobuf"):
                _, __, symbol, interval = channel.split("@")
                data = msg["publicSpotKline"]
                k_interval = from_stream_interval(StreamInterval(interval))
                self.klines[symbol][k_interval] = self.klines[symbol][k_interval][-100:] + [
                    Kline.from_mexc_ws(data)
                ]

            elif channel.startswith("spot@public.limit.depth.v3.api.protobuf"):
                symbol = channel.split("@")[2]

                self.last_symbol_update[symbol] = now()
                data = msg["publicLimitDepths"]
                depth = (
                    [[float(x["price"]), float(x["quantity"])] for x in data["bids"]],
                    [[float(x["price"]), float(x["quantity"])] for x in data["asks"]],
                )
                self._ob[symbol].update(depth)
            else:
                logging.warning(f"Unknown message: {msg}")
        except Exception as e:
            logging.error(f"WS Error: {with_traceback(e)} {msg}")
            # traceback.print_exc()


if __name__ == "__main__":

    async def main():
        pass

    asyncio.run(main())
