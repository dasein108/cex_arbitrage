import asyncio
import functools
import traceback
from datetime import datetime
from typing import Dict, Optional

from exchanges.common import Interval, OrderType, Side
from exchanges.common.entities import (
    AccountBalance,
    Deal,
    Kline,
    MyDeal,
    Order,
    SymbolBalance,
    SymbolInfo,
    SymbolStr,
    Ticker24,
)
from exchanges.common.exceptions import (
    ExchangeAPIError,
    InsufficientPosition,
    OversoldException,
    RateLimitError,
    SkipStepException,
    TooManyRequestsException,
    TradingDisabled,
    UnknownException,
)

# from exchange.reporter import Reporter  # Commented out due to missing module
from exchanges.common.interfaces.rest_api_interface import RestApiInterface
from exchanges.mexc_api.spot import Spot
from utils.date import now
from utils.decorators import retry_on_exception
from utils.loggger import Logger


class MexcRestApi(RestApiInterface):
    name = "mexc"
    si: Dict[SymbolStr, SymbolInfo] = {}

    def __init__(self, api_key, secret_key):
        super().__init__(api_key, secret_key)
        self.spot_api = Spot(api_key, secret_key)

    async def get_balance(self):
        wallet_info = await self.spot_api.account.get_account_info()

        balance = {
            x["asset"]: AccountBalance(x["asset"], float(x["free"]), float(x["locked"]))
            for x in wallet_info["balances"]
        }

        return balance

    async def get_balance_snapshot(self):
        wallet_info = await self.spot_api.account.get_account_info()
        balances = []
        for x in wallet_info["balances"]:
            symbol = x["asset"]
            if symbol in ["USDT", "MX"]:
                continue
            if symbol[:-4] not in ["USDT"]:
                symbol += "USDT"
            balances.append(SymbolBalance(symbol=symbol, quantity=(float(x["free"]) + float(x["locked"]))))
        return balances

    async def get_my_last_deals(self, symbol, start_ts, end_ts):
        start_ms = int(start_ts.timestamp() * 1000)
        end_ms = int(end_ts.timestamp() * 1000)
        deals = await self.spot_api.account.get_trades(symbol, start_ms=start_ms, end_ms=end_ms)
        deals = [d for d in deals if d["time"] >= start_ms]
        deals = [d for d in deals if d["time"] <= end_ms]
        return [MyDeal.from_rest(d) for d in deals]

    async def get_order_book(self, symbol, depth=5) -> ([], []):
        ob = await self.spot_api.market.order_book(symbol, 10)

        return ([[float(x[0]), float(x[1])] for x in ob["bids"]], [[float(x[0]), float(x[1])] for x in ob["asks"]])

    async def get_open_orders(self, symbol):
        response = await self.spot_api.account.get_open_orders(symbol)
        return [Order.from_rest(o) for o in response]

    async def get_usdt_ticker_24(self):
        response = await self.spot_api.market.ticker_24h()
        return {
            r["symbol"]: Ticker24(r["lastPrice"], r["quoteVolume"]) for r in response if r["symbol"].endswith("USDT")
        }

    async def fetch_order_updates(self, order: Order):
        response = await self.spot_api.account.get_order(order.symbol, order.order_id)
        return Order.from_rest(response)

    async def get_all_orders(self, symbol, limit=100, end_timestamp: Optional[datetime] = None):
        timestamp = int((end_timestamp or now()).timestamp()) * 1000
        # if timestamp:
        # timestamp = int(timestamp.timestamp() * 1000)
        response = await self.spot_api.account.get_orders(symbol, limit=limit, timestamp=timestamp)
        return [Order.from_rest(o) for o in response]

    async def get_last_deals(self, symbol: SymbolStr, limit: int = 100, timestamp: Optional[float] = None):
        deals = await self.spot_api.market.trades(symbol, limit=limit, end_timestamp=timestamp)
        # if from_timestamp:
        #     deals = [d for d in deals if d['time'] >= from_timestamp]
        # reverse deals list
        deals = deals[::-1]
        return [Deal.from_rest(d) for d in deals]

    async def get_last_candles(self, symbol: SymbolStr, interval: Interval, limit: int = 100):
        candles = await self.spot_api.market.klines(symbol, interval, limit=limit)
        candles = [Kline.from_mexc_rest(c) for c in candles]
        return candles
    
    async def get_last_candles_df(self, symbol: SymbolStr, interval: Interval, limit: int = 100):
        """Get candles as DataFrame compatible with similarity_filter.py"""
        import pandas as pd
        candles = await self.spot_api.market.klines(symbol, interval, limit=limit)
        
        # Convert to DataFrame with lowercase column names
        df = pd.DataFrame(candles, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            '_', '__'
        ])
        
        # Convert string values to float
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        
        # Keep only required columns for similarity filter
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        
        return df

    async def load_symbol_info(self):
        data = (await self.spot_api.market.exchange_info())["symbols"]
        result = {SymbolStr(s["symbol"]): SymbolInfo(**s, min_quote_amount=1) for s in data}
        self.si = result
        return result

    @retry_on_exception(
        retries=3,
        delay=1,
        exceptions=(
            RateLimitError,
            TooManyRequestsException,
        ),
    )
    async def get_order_info(self, o: Order):
        try:
            o = Order.from_rest(await self.spot_api.account.get_order(o.symbol, o.order_id))
            if o.order_type in [OrderType.IMMEDIATE_OR_CANCEL, OrderType.MARKET]:
                o.amount = o.amount_filled
            return o
        except ExchangeAPIError as e:
            # logging.error(f"get_order_info error: {o} {e}")
            return o.to_canceled()

    @retry_on_exception(
        retries=3,
        delay=1,
        exceptions=(
            RateLimitError,
            TooManyRequestsException,
        ),
    )
    async def place_order(
        self,
        symbol: SymbolStr,
        side: Side,
        order_type: OrderType,
        price: Optional[float] = None,
        quantity: Optional[float] = None,
        quote_order_quantity: Optional[float] = None,
        with_check: bool = False,
    ):
        # si = symbol_info[symbol]
        if order_type in [OrderType.MARKET]:

            if side == Side.BUY:
                if not quote_order_quantity:
                    quote_order_quantity = quantity * price
                quantity = None
            elif side == Side.SELL:
                if not quantity:
                    quantity = self.si[symbol].get_quantity(price, quote_order_quantity)
                quote_order_quantity = None

            price = None

        else:
            if not quantity:
                quantity = self.si[symbol].get_quantity(price, quote_order_quantity)
                quote_order_quantity = None

        response = await self.spot_api.account.new_order(
            symbol,
            side,
            order_type=order_type,
            quantity=quantity,
            quote_order_quantity=quote_order_quantity,
            price=price,
        )
        order = Order.from_rest(response, partial=True)

        if with_check:
            order = await self.get_order_info(order)

        return order

    @retry_on_exception(
        retries=3,
        delay=1,
        exceptions=(
            RateLimitError,
            TooManyRequestsException,
        ),
    )
    async def cancel_all_open_orders(self, symbol: str, side: Optional[Side] = None, logger: Optional[Logger] = None):
        orders = await self.spot_api.account.get_open_orders(symbol)
        result = []
        for order in orders:
            if side is None or order["side"] == side.value:
                o = await self.cancel_order(Order.from_rest(order), logger=logger)
                result.append(o)
        return result

    @retry_on_exception(
        retries=5,
        delay=1,
        exceptions=(
            RateLimitError,
            TooManyRequestsException,
        ),
    )
    async def cancel_order(self, order: Order, logger: Optional[Logger] = None):
        o = None
        try:
            response = await self.spot_api.account.cancel_order(order.symbol, order_id=order.order_id)
            o = Order.from_rest(response).to_canceled()
        except ExchangeAPIError as e:
            logger and logger.warning(f"cancel error: {order} {e}")
            code = e.code
            msg = e.message
            mexc_code = e.mexc_code
            if mexc_code == -2011:  # OrderCancelled
                # o.to_canceled()
                response = await self.spot_api.account.get_order(order.symbol, order_id=order.order_id)
                o = Order.from_rest(response)
            elif code == 400:
                if msg == "Order filled.":  # -2011
                    o = order.to_filled()
                elif msg in ["Order does not exist.", "Unknown order id."]:
                    o = order.to_canceled()
        except Exception as e:
            logger and logger.error(f"cancel error Exception: {order} {e}")
            # response = spot_api.account.get_order(order.symbol, order_id=order.order_id)
            # o = Order.from_rest(response)
            o = order.to_canceled()

        return o


if __name__ == "__main__":
    from config import MEXC_KEY, MEXC_SECRET

    api = MexcRestApi(MEXC_KEY, MEXC_SECRET)

    async def main():
        p1 = 0.0007505
        p2 = 0.0007506
        q = round(1.11 / p1)
        o1 = await api.place_order("CATEETHUSDT", Side.SELL, OrderType.LIMIT, p1, quantity=q)
        print(await api.get_order_info(o1))

        o2 = await api.place_order("CATEETHUSDT", Side.BUY, OrderType.IMMEDIATE_OR_CANCEL, p2, quantity=q)
        print(await api.get_order_info(o2))

        # await api.cancel_order(o1)

    asyncio.run(main())


def mexc_exception_handler(func):
    """Default decorator to handle exceptions in GateioRestApi methods."""

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ExchangeAPIError as e:
            # code = e.code
            msg = e.message
            if e.mexc_code == 429:
                raise TooManyRequestsException(e.message, e)
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
                traceback.print_exc()
                raise OversoldException(e.message, e)
            else:
                raise UnknownException(e.message, e)
        except Exception as e:
            raise e

    return wrapper
