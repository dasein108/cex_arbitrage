from datetime import datetime
from enum import Enum, IntEnum
import msgspec
from msgspec import Struct
from typing import NewType, Optional


type ExchangeName = NewType('Exchange', str)
type AssetName = NewType('AssetName', str)

type OrderId = NewType("OrderId", str)


class OrderStatus(IntEnum):
    UNKNOWN = -1
    NEW = 1
    FILLED = 2
    PARTIALLY_FILLED = 3
    CANCELED = 4
    PARTIALLY_CANCELED = 5
    EXPIRED = 6
    REJECTED = 7

class OrderType(Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    LIMIT_MAKER = "LIMIT_MAKER"
    IMMEDIATE_OR_CANCEL = "IMMEDIATE_OR_CANCEL"
    FILL_OR_KILL = "FILL_OR_KILL"
    STOP_LIMIT = "STOP_LIMIT"
    STOP_MARKET = "STOP_MARKET"

class Side(Enum):
    BUY = "BUY"
    SELL = "SELL"


class Symbol(Struct):
    base: AssetName
    quote: AssetName
    is_futures: bool = False


class SymbolInfo(Struct):
    exchange: ExchangeName
    symbol: Symbol
    base_precision: int = 0
    quote_precision: int = 0
    min_quote_amount: float = 0
    min_base_amount: float = 0
    is_futures: bool = False
    maker_commission: float = 0
    taker_commission: float = 0


class OrderBookEntry(Struct):
    price: float
    size: float


class OrderBook(Struct):
    bids: list[OrderBookEntry]
    asks: list[OrderBookEntry]
    timestamp: float


class Order(Struct):
    symbol: Symbol
    side: Side
    order_type: OrderType
    price: float
    amount: float
    amount_filled: float = 0.0
    order_id: Optional[OrderId] = None
    status: OrderStatus = OrderStatus.NEW
    timestamp: Optional[datetime] = None
    fee: float = 0.0


class Trade(Struct):
    price: float
    amount: float
    side: Side
    timestamp: int
    is_maker: bool = False



class AssetBalance(Struct):
    asset: AssetName
    free: float
    locked: float = 0.0

    @property
    def total(self) -> float:
        return self.free + self.locked
