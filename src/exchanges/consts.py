from enum import Enum

from core.transport.websocket.structs import PublicWebsocketChannelType
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
    GATEIO_FUTURES = ExchangeName("GATEIO_FUTURES")


DEFAULT_PUBLIC_WEBSOCKET_CHANNELS = [PublicWebsocketChannelType.BOOK_TICKER,
                                     PublicWebsocketChannelType.ORDERBOOK, PublicWebsocketChannelType.TRADES]
