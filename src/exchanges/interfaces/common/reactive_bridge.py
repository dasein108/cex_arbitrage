from typing import TypeVar, Generic, Callable, Dict
import reactivex as rx
from reactivex.subject import Subject

T = TypeVar('T')


class ReactiveChannelBridge(Generic[T]):
    """Per-channel type-safe bridge"""

    def __init__(self):
        self._subject: Subject[T] = Subject()

    @property
    def handler(self) -> Callable[[T], None]:
        """Get handler function for WebSocket binding"""
        return self._subject.on_next

    @property
    def stream(self) -> rx.Observable[T]:
        """Get observable stream"""
        return self._subject

# EXAMPLE:
#   # Create typed bridges for each channel
#   class ReactiveWebSocket:
#       def __init__(self):
#           self.orders = ReactiveChannelBridge[OrderUpdate]()
#           self.trades = ReactiveChannelBridge[TradeUpdate]()
#           self.orderbook = ReactiveChannelBridge[dict]()  # Or your OrderbookUpdate type
#
#       def bind_all(self, websocket):
#           """Bind all handlers to websocket"""
#           websocket.bind("ORDER", self.orders.handler)
#           websocket.bind("TRADE", self.trades.handler)
#           websocket.bind("ORDERBOOK", self.orderbook.handler)