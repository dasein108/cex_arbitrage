"""This module stores the enums used by the mexc_api classes."""

from enum import Enum
from typing import Any, Type


class Method(Enum):
    """Method enum."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"


class StreamInterval(Enum):
    """Interval enum used by the websocket kline stream."""

    ONE_MIN = "Min1"
    FIVE_MIN = "Min5"
    FIFTEEN_MIN = "Min15"
    THIRTY_MIN = "Min30"
    SIXTY_MIN = "Min60"
    FOUR_HOUR = "Hour4"
    EIGHT_HOUR = "Hour8"
    ONE_DAY = "Day1"
    ONE_WEEK = "Week1"
    ONE_MONTH = "Month1"


class Interval(Enum):
    """Interval used by the spot http kline endpoint."""

    ONE_MIN = "1m"
    FIVE_MIN = "5m"
    FIFTEEN_MIN = "15m"
    THIRTY_MIN = "30m"
    SIXTY_MIN = "60m"
    FOUR_HOUR = "4h"
    EIGHT_HOUR = "8h"
    ONE_DAY = "1d"
    ONE_MONTH = "1M"


# INTERVAL_TO_STREAM_INTERVAL = {
#     "1m": "Min1",
#     "5m": "Min5",
#     "15m": "Min15",
#     "30m": "Min30",
#     "60m": "Min60",
#     "4h": "Hour4",
#     "8h": "Hour8",
#     "1d": "Day1",
#     "1M": "Month1"
# }
#
# # Create STREAM_INTERVAL_TO_INTERVAL by reversing INTERVAL_TO_STREAM_INTERVAL
# STREAM_INTERVAL_TO_INTERVAL = {v: k for k, v in INTERVAL_TO_STREAM_INTERVAL.items()}


def from_interval(interval: Interval):  # -> StreamInterval[Any]:
    """Converts Interval to StreamInterval."""
    return StreamInterval[interval.name]


def from_stream_interval(interval: StreamInterval):  # -> Interval[Any]:
    """Converts StreamInterval to Interval."""
    return Interval[interval.name]


class Side(Enum):
    """Side enum."""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    """Order type enum."""

    LIMIT = "LIMIT"
    MARKET = "MARKET"
    LIMIT_MAKER = "LIMIT_MAKER"
    IMMEDIATE_OR_CANCEL = "IMMEDIATE_OR_CANCEL"
    FILL_OR_KILL = "FILL_OR_KILL"


class Action(Enum):
    """Action type enum."""

    SUBSCRIBE = "SUBSCRIPTION"
    UNSUBSCRIBE = "UNSUBSCRIPTION"


class AccountType(Enum):
    """account type enum."""

    SPOT = "SPOT"
    FUTURES = "FUTURES"


class OrderStatus(Enum):
    UNKNOWN = -1
    NEW = 1
    FILLED = 2
    PARTIALLY_FILLED = 3
    CANCELED = 4
    PARTIALLY_CANCELED = 5


class AlgoOrderType(Enum):
    UNKNOWN = -1
    ZERO = 0
    FLASH = 1
    LIMIT = 1
    MARKET = 2
    STOP_LOSS = 3
    KILL = 4
