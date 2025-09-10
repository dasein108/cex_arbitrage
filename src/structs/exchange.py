from datetime import datetime
from enum import Enum, IntEnum
import msgspec
from msgspec import Struct
from typing import NewType, Optional


ExchangeName = NewType('Exchange', str)
AssetName = NewType('AssetName', str)
OrderId = NewType("OrderId", str)


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


# Backward compatibility alias
OrderSide = Side


class TimeInForce(Enum):
    """Time in force for orders"""
    GTC = "GTC"  # Good Till Cancelled
    IOC = "IOC"  # Immediate or Cancel
    FOK = "FOK"  # Fill or Kill
    GTD = "GTD"  # Good Till Date


class KlineInterval(Enum):
    """Kline/Candlestick chart intervals"""
    MINUTE_1 = "1m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    MINUTE_30 = "30m"
    HOUR_1 = "1h"
    HOUR_4 = "4h"
    HOUR_12 = "12h"
    DAY_1 = "1d"
    WEEK_1 = "1w"
    MONTH_1 = "1M"


class StreamType(Enum):
    ORDERBOOK = "orderbook"
    TRADES = "trades"
    TICKER = "ticker"
    KLINE = "kline"
    ACCOUNT = "account"
    ORDERS = "orders"
    BALANCE = "balance"


class Symbol(Struct, frozen=True):
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
    inactive: bool = False


class OrderBookEntry(Struct, frozen=True):
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


class Ticker(Struct):
    """24hr ticker price change statistics"""
    symbol: Symbol
    price: float
    price_change: float = 0.0
    price_change_percent: float = 0.0
    high_price: float = 0.0
    low_price: float = 0.0
    volume: float = 0.0
    quote_volume: float = 0.0
    open_price: float = 0.0
    timestamp: float = 0.0


class Kline(Struct):
    """Kline/Candlestick data"""
    symbol: Symbol
    interval: KlineInterval
    open_time: int
    close_time: int
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float
    quote_volume: float
    trades_count: int = 0


class TradingFee(Struct):
    """Trading fee structure"""
    symbol: Symbol
    maker_fee: float
    taker_fee: float
    

class AccountInfo(Struct):
    """Account information"""
    exchange: ExchangeName
    account_type: str = "SPOT"
    can_trade: bool = True
    can_withdraw: bool = True
    can_deposit: bool = True
    balances: list[AssetBalance] = []
    permissions: list[str] = []
