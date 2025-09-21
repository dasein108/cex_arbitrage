from enum import Enum

from core.transport.websocket.structs import WebsocketChannelType
from structs import ExchangeName

# Exchange enumeration for type-safe exchange selection
class ExchangeEnum(Enum):
    """
    Enumeration of supported centralized exchanges.

    Used throughout the system for type-safe exchange identification
    and consistent naming across all components.
    """
    MEXC = ExchangeName("MEXC")
    GATEIO = ExchangeName("GATEIO")
    GATEIO_FUTURES = ExchangeName("GATEIO")


DEFAULT_PUBLIC_WEBSOCKET_CHANNELS = [WebsocketChannelType.BOOK_TICKER,
                                     WebsocketChannelType.ORDERBOOK, WebsocketChannelType.TRADES]
