from typing import Optional

from msgspec import Struct

from exchanges.structs import ExchangeEnum, OrderId


class MarketData(Struct):
    exchange: Optional[ExchangeEnum] = None
    tick_tolerance: int = 0
    ticks_offset: int = 0
    use_market: bool = False
    order_id: Optional[OrderId] = None
