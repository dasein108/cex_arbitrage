from datetime import datetime
from enum import Enum, IntEnum
import msgspec
from msgspec import Struct
from typing import NewType, Optional, Dict


ExchangeName = NewType('Exchange', str)
AssetName = NewType('AssetName', str)
OrderId = NewType("OrderId", str)


class ExchangeStatus(IntEnum):
    """A WebSocket connection is in one of these four states."""

    CONNECTING, ACTIVE, CLOSING, INACTIVE, ERROR = range(5)

class OrderStatus(IntEnum):
    UNKNOWN = -1
    NEW = 1
    FILLED = 2
    PARTIALLY_FILLED = 3
    CANCELED = 4
    PARTIALLY_CANCELED = 5
    EXPIRED = 6
    REJECTED = 7

class OrderType(IntEnum):
    LIMIT = 1
    MARKET = 2
    LIMIT_MAKER = 3
    IMMEDIATE_OR_CANCEL = 4
    FILL_OR_KILL = 5
    STOP_LIMIT = 6
    STOP_MARKET = 7

class Side(IntEnum):
    BUY = 1
    SELL = 2


# Backward compatibility alias
OrderSide = Side


class TimeInForce(IntEnum):
    """Time in force for orders"""
    GTC = 1  # Good Till Cancelled
    IOC = 2  # Immediate or Cancel
    FOK = 3  # Fill or Kill
    GTD = 4  # Good Till Date


class KlineInterval(IntEnum):
    """Kline/Candlestick chart intervals"""
    MINUTE_1 = 1
    MINUTE_5 = 2
    MINUTE_15 = 3
    MINUTE_30 = 4
    HOUR_1 = 5
    HOUR_4 = 6
    HOUR_12 = 7
    DAY_1 = 8
    WEEK_1 = 9
    MONTH_1 = 10


class StreamType(IntEnum):
    ORDERBOOK = 1
    TRADES = 2
    TICKER = 3
    KLINE = 4
    ACCOUNT = 5
    ORDERS = 6
    BALANCE = 7


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
    fees_maker: float = 0.0
    fees_taker: float = 0.0


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
    client_order_id: Optional[str] = None
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
    available: float = 0.0
    free: float = 0.0
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
    

class Position(Struct):
    """Futures position information"""
    symbol: Symbol
    size: float  # Position size (positive for long, negative for short)
    side: Side  # LONG (BUY) or SHORT (SELL)
    entry_price: float  # Average entry price
    mark_price: float  # Current mark price
    unrealized_pnl: float  # Unrealized profit/loss
    realized_pnl: float  # Realized profit/loss
    margin: float  # Position margin/collateral
    leverage: float  # Leverage used
    risk_limit: float  # Risk limit for the position
    contract_value: float  # Value of single contract
    timestamp: Optional[int] = None  # Last update timestamp
    
    @property
    def is_long(self) -> bool:
        """Check if this is a long position"""
        return self.side == Side.BUY and self.size > 0
    
    @property
    def is_short(self) -> bool:
        """Check if this is a short position"""
        return self.side == Side.SELL and self.size > 0
    
    @property
    def notional_value(self) -> float:
        """Calculate notional value of the position"""
        return abs(self.size) * self.mark_price


class TradingFee(Struct):
    """Trading fee information for a user"""
    exchange: ExchangeName
    maker_rate: float = 0.0  # Maker fee rate (e.g., 0.001 for 0.1%)
    taker_rate: float = 0.0  # Taker fee rate (e.g., 0.001 for 0.1%)
    spot_maker: Optional[float] = None  # Spot maker fee (if different)
    spot_taker: Optional[float] = None  # Spot taker fee (if different)
    futures_maker: Optional[float] = None  # Futures maker fee (if different)
    futures_taker: Optional[float] = None  # Futures taker fee (if different)
    thirty_day_volume: Optional[float] = None  # 30-day trading volume in USDT
    point_type: Optional[str] = None  # Fee tier/level
    symbol: Optional['Symbol'] = None  # Symbol these fees apply to (None = account-level)
    
    @property
    def maker_percentage(self) -> float:
        """Get maker fee as percentage (e.g., 0.1 for 0.1%)"""
        return self.maker_rate * 100
    
    @property
    def taker_percentage(self) -> float:
        """Get taker fee as percentage (e.g., 0.1 for 0.1%)"""
        return self.taker_rate * 100


class AccountInfo(Struct):
    """Account information"""
    exchange: ExchangeName
    account_type: str = "SPOT"
    can_trade: bool = True
    can_withdraw: bool = True
    can_deposit: bool = True
    balances: list[AssetBalance] = []
    permissions: list[str] = []

# composite types
type SymbolsInfo = Dict[Symbol, SymbolInfo]