from enum import Enum, IntEnum

from .types import ExchangeName


class ExchangeEnum(Enum):
    """
    Enumeration of supported centralized exchanges using semantic naming convention.

    Used throughout the system for type-safe exchange identification
    and consistent naming across all components.
    
    Semantic Format: <exchange>_<market_type>
    - mexc_spot: MEXC spot trading
    - gateio_spot: Gate.io spot trading  
    - gateio_futures: Gate.io futures trading
    """
    MEXC = ExchangeName("MEXC_SPOT")
    GATEIO = ExchangeName("GATEIO_SPOT")
    GATEIO_FUTURES = ExchangeName("GATEIO_FUTURES")

class ExchangeType(Enum):
    """Type of exchange market."""
    SPOT = "spot"
    FUTURES = "futures"
    MARGIN = "margin"
    SWAP = "swap"
    OPTIONS = "options"

class ExchangeStatus(IntEnum):
    """Exchange connection status."""
    CONNECTING = 0
    ACTIVE = 1
    CLOSING = 2
    INACTIVE = 3
    ERROR = 4


class OrderStatus(IntEnum):
    """Order execution status."""
    UNKNOWN = -1
    NEW = 1
    FILLED = 2
    PARTIALLY_FILLED = 3
    CANCELED = 4
    PARTIALLY_CANCELED = 5
    EXPIRED = 6
    REJECTED = 7


class OrderType(IntEnum):
    """Order type definitions."""
    LIMIT = 1
    MARKET = 2
    LIMIT_MAKER = 3
    IMMEDIATE_OR_CANCEL = 4
    FILL_OR_KILL = 5
    STOP_LIMIT = 6
    STOP_MARKET = 7


class Side(IntEnum):
    """Order side."""
    BUY = 1
    SELL = 2


OrderSide = Side


class TimeInForce(IntEnum):
    """Time in force for orders."""
    GTC = 1  # Good Till Cancelled
    IOC = 2  # Immediate or Cancel
    FOK = 3  # Fill or Kill
    GTD = 4  # Good Till Date


class OrderbookUpdateType(Enum):
    """Type of orderbook update."""
    SNAPSHOT = "snapshot"
    DIFF = "diff"


class KlineInterval(IntEnum):
    """Kline/candlestick interval definitions."""
    MINUTE_1 = 1    # 1m
    MINUTE_5 = 2    # 5m
    MINUTE_15 = 3   # 15m
    MINUTE_30 = 4   # 30m
    HOUR_1 = 5      # 1h
    HOUR_4 = 6      # 4h
    HOUR_12 = 7     # 12h
    DAY_1 = 8       # 1d
    WEEK_1 = 9      # 1w/7d
    MONTH_1 = 10    # 1M/30d


class WithdrawalStatus(IntEnum):
    """Withdrawal status enumeration."""
    PENDING = 1      # Awaiting processing
    PROCESSING = 2   # Being processed
    COMPLETED = 3    # Successfully completed
    FAILED = 4       # Failed/rejected
    CANCELED = 5     # User canceled
    MANUAL_REVIEW = 6 # Under manual review
    UNKNOWN = -1     # Unknown status