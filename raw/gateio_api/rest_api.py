from exchange.entities import AccountBalance, SymbolInfo, Deal, Kline
from datetime import datetime
from exchanges.common import Interval, Side, OrderType, OrderStatus
from typing import Optional, List, Dict, Any
from exchanges.base.interfaces.rest_api_interface import RestApiInterface
from gate_api import ApiClient, Configuration, Order as GateioOrder, SpotApi, WalletApi
from exchange.entities import SymbolStr, Order, Ticker24
from config import GATEIO_KEY, GATEIO_SECRET
import asyncio
from utils.date import ts_to_datetime
import functools
from gate_api.exceptions import GateApiException

from exchanges.common.exceptions import ExchangeAPIError, TradingDisabled, SkipStepException, InsufficientPosition, \
    OversoldException, UnknownException, apply_exception_handler

def mexc_exception_handler(func):
    """Default decorator to handle exceptions in GateioRestApi methods."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ExchangeAPIError as e:
            # code = e.code
            msg = e.message
            if e.mexc_code in [10007]:  # 'symbol not support api'
                raise TradingDisabled(e.message, e)
            if e.mexc_code == 700003:  # 'Timestamp for this request is outside of the recvWindow.'
                raise SkipStepException(e.message, e)
            elif e.mexc_code == 30016:  # trading disabled
                raise TradingDisabled(e.message, e)
            elif e.mexc_code == 10203:
                raise SkipStepException(e.message, e)

            elif e.mexc_code == 30004:  # Insufficient position
                raise InsufficientPosition(e.message, e)
            elif e.mexc_code in [30005, 30002]:  # Oversold, minimum transaction volume < ...
                raise OversoldException(e.message, e)
            else:
                raise UnknownException(e.message, e)
        except Exception as e:
            raise  e
    return wrapper

def gateio_exception_handler(func):
    """Decorator to handle exceptions in GateioRestApi methods."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except GateApiException as e:
            # logging.error(f"Error in {func.__name__}: {e}", exc_info=True)
            if e.label == 'BALANCE_NOT_ENOUGH':
                raise OversoldException(e.message, e)
            else:
                raise UnknownException(e.message, e)
        except Exception as e:
            raise e
    return wrapper

def to_gateio_symbol(symbol: SymbolStr):
    coin = symbol.replace("USDT", "")
    return f'{coin}_USDT'


def from_gateio_symbol(symbol: str):
    return SymbolStr(symbol.replace("_", ""))


# - Unix timestamp with second precision
# - Trading volume in quote currency
# - Closing price
# - Highest price
# - Lowest price
# - Opening price
# - Trading volume in core currency
# - Whether the window is closed; true indicates the end of
def kline_from_rest(data: List[any]):
    return Kline(float(data[5]), float(data[3]), float(data[4]), float(data[2]), 0, int(data[0]),
                 0, float(data[1]))


def from_gateio_status(status: str) -> OrderStatus:
    if status == 'open':
        return OrderStatus.NEW
    elif status == 'closed':
        return OrderStatus.FILLED
    elif status == 'cancelled':
        return OrderStatus.CANCELED
    else:
        return OrderStatus.UNKNOWN

def order_from_gateio(o: GateioOrder):
    #         Order status  - `open`: to be filled - `closed`: filled - `cancelled`: cancelled  # noqa: E501

    price = o.price
    status = from_gateio_status(o.status)

    amount = o.amount
    amount_filled = o.filled_amount

    if o.type == 'market':
        amount = amount_filled

    return Order(symbol=from_gateio_symbol(o.currency_pair),
                 order_id=o.id, price=float(price),
                 amount=float(amount), amount_filled=float(amount_filled),
                 side=Side(o.side.upper()), order_type=OrderType(o.type.upper()), status=status,
                 timestamp=ts_to_datetime(int(o.create_time)), exchange='gateio')


class GateioRestApi(RestApiInterface):
    si: Dict[SymbolStr, SymbolInfo] = {}
    def __init__(self, api_key, secret_key):
        super().__init__(api_key, secret_key)
        self.configuration = Configuration()
        config = Configuration(key=api_key, secret=secret_key, host="https://api.gateio.ws/api/v4")
        self.spot_api = SpotApi(ApiClient(config))
        self.wallet_api = WalletApi(ApiClient(config))

    async def get_order_book(self, symbol: SymbolStr) -> (List[List[float]], List[List[float]]):
        ob = await asyncio.to_thread(self.spot_api.list_order_book(to_gateio_symbol(symbol),
                                                                   limit=5, async_req=True).get)
        return ([[float(x[0]), float(x[1])] for x in ob.bids],
                [[float(x[0]), float(x[1])] for x in ob.asks])

    async def get_open_orders(self, symbol: SymbolStr) -> List[Order]:
        data = await asyncio.to_thread(self.spot_api.list_orders(currency_pair=to_gateio_symbol(symbol),
                                                                 status='open', async_req=True).get)
        pass

    async def get_usdt_ticker_24(self) -> Dict[str, Any]:
        data = await asyncio.to_thread(self.spot_api.list_tickers(async_req=True).get)
        # todo use 'last'
        return {from_gateio_symbol(x.currency_pair): Ticker24(float(x.last), float(x.quote_volume),
                                                              symbol=from_gateio_symbol(x.currency_pair)) for x in data}

    async def fetch_order_updates(self, order: Order) -> Order:
        o = await asyncio.to_thread(self.spot_api.get_order(order.order_id, to_gateio_symbol(order.symbol),
                                                            async_req=True).get)
        return order_from_gateio(o)

    async def get_all_orders(self, symbol: SymbolStr, limit: int = 100,
                             end_timestamp: Optional[datetime] = None) -> List[Order]:
        print(f'before {symbol}')

        if end_timestamp:
            end_timestamp = int(end_timestamp.timestamp()) * 1000
        data = await asyncio.to_thread(self.spot_api.list_orders(currency_pair=to_gateio_symbol(symbol), limit=limit,
                                                                 status='open', to=end_timestamp, async_req=True).get)
        print(f'after {symbol}')
        return [order_from_gateio(o) for o in data]

    async def get_last_deals(self, symbol: SymbolStr, limit: int = 100, timestamp: Optional[float] = None) -> List[
        Deal]:
        # HERE
        data = await asyncio.to_thread(self.spot_api.list_trades(to_gateio_symbol(symbol),
                                                                 limit=limit, async_req=True).get)
        return [Deal(float(x.price), float(x.amount), Side(x.side.upper()), int(x.create_time) * 1000, False) for x in
                data]

    async def get_last_candles(self, symbol: SymbolStr, interval: Interval, limit: int = 100) -> List[Kline]:
        # HERE
        f = self.spot_api.list_candlesticks(to_gateio_symbol(symbol), interval=interval.value,
                                            limit=limit, async_req=True).get
        data = await asyncio.to_thread(f)
        print(f'after {symbol}')
        candles = [kline_from_rest(c) for c in data]
        return candles

    async def load_symbol_info(self) -> Dict[SymbolStr, SymbolInfo]:
        data = await asyncio.to_thread(self.spot_api.list_currency_pairs(async_req=True).get)
        result = {}
        for x in data:
            symbol = from_gateio_symbol(x.id)

            si = SymbolInfo(symbol, baseAsset=x.base, quoteAsset=x.quote,
                            baseAssetPrecision=x.amount_precision, quoteAssetPrecision=x.precision,
                            min_quote_amount=float(x.min_quote_amount), min_base_amount=float(x.min_base_amount))
            result[symbol] = si

        self.si = result
        return result

    async def get_order_info(self, o: Order) -> Order:
        try:
            o = await asyncio.to_thread(self.spot_api.get_order(o.order_id, to_gateio_symbol(o.symbol),
                                                                async_req=True).get)
            return order_from_gateio(o)
        except GateApiException as e:
            if e.label == 'ORDER_NOT_FOUND':
                return o.to_canceled()

            raise e

    async def place_order(self, symbol: SymbolStr, side: Side, order_type: OrderType, price: Optional[float] = None,
                          quantity: Optional[float] = None, quote_order_quantity: Optional[float] = None,
                          with_check: bool = False) -> Order:

        time_in_force = 'gtc'
        if order_type in [OrderType.MARKET, OrderType.LIMIT_MAKER,  OrderType.IMMEDIATE_OR_CANCEL]:
            time_in_force = 'ioc'


        if order_type == OrderType.IMMEDIATE_OR_CANCEL:
            order_type = OrderType.LIMIT

        if order_type in [OrderType.MARKET, OrderType.IMMEDIATE_OR_CANCEL, OrderType.LIMIT_MAKER]:
            if side == Side.BUY:
                if not quote_order_quantity:
                    order_amount = quantity * price
                else:
                    order_amount = quote_order_quantity
                price = None
            else:
                if not quantity:
                    order_amount = round(quote_order_quantity / price,2)
                else:
                    order_amount = quantity
                price = None
        else:
            order_amount = quote_order_quantity / price if not quantity else quantity

        go = GateioOrder(amount=str(order_amount), price=price, side=side.value.lower(), type=order_type.value.lower(),
                         currency_pair=to_gateio_symbol(symbol), time_in_force=time_in_force)
        if price:
            go.price = "{:.{}f}".format(price, self.si[symbol].price_precision)

        o = await asyncio.to_thread(self.spot_api.create_order(go, async_req=True).get)
        return order_from_gateio(o)

    async def cancel_all_open_orders(self, symbol: SymbolStr, side: Optional[Side] = None, reporter: Optional[Any] = None,
                                     logger: Optional[Any] = None):
        orders = await asyncio.to_thread(self.spot_api.cancel_orders(currency_pair=to_gateio_symbol(symbol),
                                                                     side=side.value.lower() if side else None,
                                             async_req=True).get)
        return [order_from_gateio(o) for o in orders]

    async def cancel_order(self, order: Order, reporter: Optional[Any] = None, logger: Optional[Any] = None) -> Order:
        try:
            o = await asyncio.to_thread(self.spot_api.cancel_order(order.order_id, to_gateio_symbol(order.symbol),
                                                                   async_req=True).get)
            return order_from_gateio(o)
        except GateApiException as e:
            if e.label == 'ORDER_NOT_FOUND':
                return order.to_canceled()

            raise e

    async def get_balance(self) -> Dict[str, AccountBalance]:
        data = await asyncio.to_thread(self.spot_api.list_spot_accounts(async_req=True).get)
        return {x.currency: AccountBalance(x.currency, float(x.available), float(x.locked)) for x in data}


if __name__ == '__main__':
    api = GateioRestApi(GATEIO_KEY, GATEIO_SECRET)


    async def main():
        print(await api.get_usdt_ticker_24())
        # print(await api.get_last_candles("BTCUSDT", Interval.ONE_MIN))
        # ob = await api.get_order_book("BTCUSDT")
        # print(ob)
        # print(await api.get_balance())
        # print(await api.load_symbol_info())
        # sis= await api.load_symbol_info()
        # print(sis["ORDIUSDT"])
        # o = await api.place_order("ORDIUSDT", Side.SELL, OrderType.LIMIT, price=13.00, quantity=8)
        # print(o)
        # print(await api.cancel_order(o))

        c = await asyncio.gather(
            *(api.get_all_orders(SymbolStr(sym)) for sym in ['BTCUSDT', 'DOGEUSDT',
                                                             'ETHUSDT', 'DOTUSDT', 'ZKUSDT',
                                                             'ETCUSDT', 'NEARUSDT', 'ORDIUSDT']))

        # c = await api.get_last_candles(SymbolStr("BTCUSDT"), Interval.ONE_MIN)
        print(c)


    asyncio.run(main())
