from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, NewType, Optional, Union

from common.constants import MIN_ORDER_USD
from common.utils import get_side_vector
from config import MEXC_ACCOUNT_ID
from exchanges.common import OrderStatus, OrderType, Side
from utils.date import now, ts_to_datetime

SymbolStr = NewType("SymbolStr", str)
OrderId = NewType("OrderId", str)
ExchangeType = str  # Type for exchange names
SymbolExchangeType = NewType("SymbolExchangeStr", str)


class Kline:
    def __init__(self, o: float, h: float, low: float, c: float, v: float, open_time: int, close_time: int, qv: float):
        self.o = o
        self.h = h
        self.l = low
        self.c = c
        self.v = v
        self.open_time = open_time
        self.close_time = close_time
        self.qv = qv

    @staticmethod
    def from_mexc_rest(data: List[any]):
        return Kline(
            float(data[1]),
            float(data[2]),
            float(data[3]),
            float(data[4]),
            float(data[5]),
            data[0],
            data[6],
            float(data[7]),
        )

    @staticmethod
    def from_mexc_ws(data: dict):
        return Kline(
            float(data["openingPrice"]),
            float(data["highestPrice"]),
            float(data["lowestPrice"]),
            float(data["closingPrice"]),
            float(data["volume"]),
            data["windowStart"],
            data["windowEnd"],
            float(data["amount"]),
        )

    @property
    def is_green(self):
        return self.c > self.o

    @property
    def hl(self):
        return self.h - self.l

    @property
    def is_red(self):
        return self.c < self.o

    @property
    def side_vector(self):
        return Side.BUY if self.is_green else Side.SELL

    def __str__(self):
        return f"{self.open_time} {self.o} {self.h} {self.l} {self.c} {self.v} {self.qv}"


class Deal:
    def __init__(self, price: float, volume: float, side: Side, timestamp: int, maker=False):
        self.side = side
        self.price = price
        self.volume = volume
        self.timestamp = ts_to_datetime(timestamp)
        self.maker = maker

    def __str__(self):
        maker = "!maker" if self.maker else ""
        return f"{self.side.value} {self.volume} @ {self.price} {maker} {self.timestamp}"

    @property
    def amount_usdt(self):
        return self.price * self.volume

    @staticmethod
    def from_rest(data):
        side = Side.SELL if data["tradeType"] == "ASK" else Side.BUY
        return Deal(float(data["price"]), float(data["qty"]), side, data["time"])

    @staticmethod
    def from_ws(d):
        side = Side.BUY if d["tradeType"] == 1 else Side.SELL
        return Deal(float(d["price"]), float(d["quantity"]), side, int(d["time"]))


class MyDeal:
    def __init__(
        self,
        price: float,
        volume: float,
        side: Side,
        timestamp: int,
        comm: float = 0.0,
        comm_symbol: str = "USDT",
        maker: bool = False,
    ):
        self.side = side
        self.price = price
        self.volume = volume
        self.timestamp = ts_to_datetime(timestamp)
        self.maker = maker
        self.comm = comm
        self.comm_symbol = comm_symbol

    def __str__(self):
        return f"{self.side.value} {self.volume} @ {self.price} {self.timestamp}"

    @property
    def brut_usdt(self):
        return self.price * self.volume

    @property
    def net_usdt(self):
        if self.side == Side.BUY:
            return -self.price * self.volume - self.comm
        elif self.side == Side.SELL:
            return self.price * self.volume - self.comm

    @staticmethod
    def from_rest(data):
        side = Side.BUY if data["isBuyer"] else Side.SELL
        return MyDeal(
            price=float(data["price"]),
            volume=float(data["qty"]),
            side=side,
            timestamp=data["time"],
            comm=float(data["commission"]),
            comm_symbol=data["commissionAsset"],
            maker=data["isMaker"],
        )


WS_OrderType = {
    1: OrderType.LIMIT,
    2: OrderType.LIMIT_MAKER,
    3: OrderType.IMMEDIATE_OR_CANCEL,
    4: OrderType.FILL_OR_KILL,
    5: OrderType.MARKET,
    # 1000: OrderType.STOP_LIMIT,
}


class AlgoType(Enum):
    ZERO_ORDER = "Z/O"
    MARKET = "MARKET"
    FLASH = "FLASH"
    REGULAR = "REG"


class Ticker24:
    def __init__(self, last_price: str | float, quote_volume: str | float):
        self.last_price = float(last_price)
        self.quote_volume = float(quote_volume)

    def __str__(self):
        return f"{self.last_price} {self.quote_volume}"


class Order:
    def __init__(
        self,
        symbol: SymbolStr,
        side: Side,
        order_type: OrderType,
        price: float,
        amount: float,
        amount_filled: float,
        order_id: OrderId,
        status: OrderStatus,
        timestamp: Optional[datetime] = None,
        exchange: str = "mexc",
        commission: float = 0.0,
    ):
        self.symbol = symbol
        self.side = side
        self.amount = amount
        self.price = price
        self.order_type = order_type
        self.amount_filled = amount_filled
        self.client_order_id = None
        self.order_id = order_id
        self.status = status
        self.timestamp = timestamp
        self.algo_type: AlgoType = AlgoType.REGULAR
        self.exchange = exchange
        self.commission = commission
        self.duration = 0
        self.label = ""
        # ?????
        # if order_type in [OrderType.MARKET, OrderType.IMMEDIATE_OR_CANCEL, OrderType.LIMIT_MAKER]:
        #     self.amount = amount_filled

    def __str__(self):
        # {self.order_id}
        usdt_a = round(self.amount * self.price, 2)
        usdt_af = round(self.amount_filled * self.price, 2)
        fill_label = ""
        if self.amount_filled > 0:
            fill_label = "*"

        if self.is_canceled:
            fill_label += "-"
        elif self.is_filled:
            fill_label += "*"

        return f"{fill_label}{self.label}{self.symbol}_{self.side}  ({usdt_a}/{usdt_af}) @ {self.price} | {self.status}{fill_label}"

    # @property
    # def duration(self):
    #     return (now() - self.timestamp).total_seconds()
    #
    @property
    def is_filled(self):
        return self.status == OrderStatus.FILLED or self.amount_filled >= self.amount

    @property
    def is_canceled(self):
        return self.status in [OrderStatus.CANCELED, OrderStatus.PARTIALLY_CANCELED]

    @property
    def is_partially_filled(self):
        return (
            self.status in [OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.PARTIALLY_CANCELED]
            or self.amount_filled > 0
        )

    def is_done(self):
        return self.status in [OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.PARTIALLY_CANCELED]

    @property
    def amount_filled_usd(self):
        return self.amount_filled * self.price

    @property
    def amount_usdt(self):
        return self.price * self.amount

    @property
    def amount_left(self):
        return self.amount - self.amount_filled

    @staticmethod
    def from_rest(data, partial=False):
        timestamp = ts_to_datetime(data["updateTime"]) if data.get("updateTime") else now()
        return Order(
            data["symbol"],
            Side(data["side"]),
            OrderType(data["type"]),
            float(data["price"]),
            float(data["origQty"]),
            float(data.get("executedQty", 0)),
            order_id=data["orderId"],
            status=OrderStatus[data["status"]] if not partial else OrderStatus.NEW,
            timestamp=timestamp,
        )

    @staticmethod
    def from_ws(symbol, data):

        return Order(
            symbol,
            Side.SELL if data["tradeType"] == 2 else Side.BUY,
            WS_OrderType[data["orderType"]],
            float(data["price"]),
            float(data["amount"]),
            float(data["cumulativeAmount"]),
            order_id=data["id"],
            status=OrderStatus(data["status"]),
            timestamp=ts_to_datetime(int(data.get("createTime", 0))),
            # commission=float(data.get('lv', 0))
        )

    def to_canceled(self):
        if self.amount_filled > 0:
            self.status = OrderStatus.PARTIALLY_CANCELED
        else:
            self.status = OrderStatus.CANCELED

        return self

    def to_filled(self):
        self.status = OrderStatus.FILLED
        self.amount_filled = self.amount
        return self

    def update(self, o: "Order"):
        label = self.label
        self.__dict__ = o.__dict__

        # do not override label if it's already exist
        if o.label != "unknown" and label:
            self.label = label


@dataclass
class AccountBalance:
    asset: str
    free: float
    locked: float

    def __str__(self):
        return f"{self.asset}: {self.free}[{self.locked} locked]"

    @property
    def total(self):
        return self.free + self.locked


@dataclass
class SymbolBalance:
    symbol: str
    quantity: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    account_id: str = field(default_factory=lambda: MEXC_ACCOUNT_ID)
    net_income_usdt: float = 0.0

    def __str__(self):
        return f"{self.symbol}({self.account_id}): {self.quantity} ({self.timestamp})"


def get_minimal_step(precision: int) -> float:
    return 10**-precision


class SymbolInfo:
    def __init__(
        self,
        symbol: SymbolStr,
        status: str = "",
        baseAsset: str = "",
        baseAssetPrecision: int = 0,
        quoteAsset: str = "",
        quotePrecision: int = 0,
        quoteAssetPrecision: int = 0,
        baseCommissionPrecision: int = 0,
        quoteCommissionPrecision: int = 0,
        orderTypes: list = [],
        isSpotTradingAllowed: bool = True,
        isMarginTradingAllowed: bool = False,
        quoteAmountPrecision: str = "",
        baseSizePrecision: str = "",
        permissions: list = [],
        filters: list = [],
        maxQuoteAmount: str = "",
        makerCommission: str = "",
        takerCommission: str = "",
        quoteAmountPrecisionMarket: str = "",
        maxQuoteAmountMarket: str = "",
        fullName: str = "",
        tradeSideType: str = "",
        min_base_amount: float = 0.0,
        min_quote_amount: float = 0.0,
        st=False,
        contractAddress="",
    ):
        self.symbol = symbol
        self.status = status
        self.baseAsset = baseAsset
        self.baseAssetPrecision = baseAssetPrecision
        self.quoteAsset = quoteAsset
        self.quotePrecision = quotePrecision
        self.quoteAssetPrecision = quoteAssetPrecision
        self.baseCommissionPrecision = baseCommissionPrecision
        self.quoteCommissionPrecision = quoteCommissionPrecision
        self.orderTypes = orderTypes
        self.isSpotTradingAllowed = isSpotTradingAllowed
        self.isMarginTradingAllowed = isMarginTradingAllowed
        self.quoteAmountPrecision = quoteAmountPrecision
        self.baseSizePrecision = baseSizePrecision
        self.permissions = permissions
        self.filters = filters
        self.maxQuoteAmount = maxQuoteAmount
        self.makerCommission = makerCommission
        self.takerCommission = takerCommission
        self.quoteAmountPrecisionMarket = quoteAmountPrecisionMarket
        self.maxQuoteAmountMarket = maxQuoteAmountMarket
        self.fullName = fullName
        self.tradeSideType = tradeSideType

        self.price_step = get_minimal_step(self.quoteAssetPrecision)
        self.amount_step = get_minimal_step(self.baseAssetPrecision)
        self.min_base_amount = min_base_amount
        self.min_quote_amount = min_quote_amount

    @property
    def min_order(self):
        return self.min_quote_amount

    @property
    def min_order_plus(self):
        return self.min_order + 0.1

    @property
    def min_usdt_with_reserve(self):
        return self.min_order * 2

    @property
    def min_sell_amount(self):
        return self.min_usdt_with_reserve + self.min_order_plus

    @property
    def amount_precision(self) -> int:
        return self.baseAssetPrecision

    @property
    def price_precision(self) -> int:
        return self.quoteAssetPrecision

    def vector_step(self, side: Side) -> float:
        return self.price_step * get_side_vector(side)

    def get_price_step_offset(self, offset: int, side: Side = Side.BUY) -> float:
        return self.price_step * offset * get_side_vector(side)

    def get_min_order_usd(self, price: float) -> float:
        return self.get_amount(MIN_ORDER_USD, price)

    def get_quantity(self, price: float, quantity_usd: float) -> float:
        return self.get_amount(quantity_usd, price)

    def get_quantity_usdt(self, price: float, quantity: float) -> float:
        return price * quantity

    def diff_ticks(self, price1: float, price2: float) -> int:
        return round(abs(price1 - price2) / self.price_step)

    def diff_ticks_by_side(self, price1: float, price2: float, side: Side) -> int:
        return round((price1 - price2) / self.price_step) * get_side_vector(side)

    def round_price(self, price: float) -> float:
        return round(price, self.price_precision)

    def round_coins(self, amount_coins: float) -> float:
        amount = round(amount_coins * 10**self.amount_precision) / 10**self.amount_precision
        return amount

    def get_amount(self, amount_usdt: float, price: float) -> float:
        amount = amount_usdt / price
        if amount < 1:  # HACK OR FIX
            return round(amount_usdt / price, int(self.quoteAssetPrecision))

        # old code
        amount = round(amount * 10**self.amount_precision) / 10**self.amount_precision
        if amount == int(amount):
            return int(amount)

        return amount
