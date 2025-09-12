from abc import ABC
from typing import List, Dict, Any, Set, Optional, Callable, Awaitable
from structs.exchange import ExchangeName, Symbol
from common.ws_client import WebSocketConfig, WebsocketClient, SubscriptionAction
from itertools import chain


class BaseExchangeWebsocketInterface(ABC):
    """Abstract interface for private exchange operations (trading, account management)"""

    def __init__(self, exchange: ExchangeName, config: WebSocketConfig,
                 get_connect_url: Optional[Callable[[], Awaitable[str]]] = None):
        self.exchange = exchange
        self.config = config
        self.symbols: List[Symbol] = []
        self.ws_client = WebsocketClient(config,
                                         message_handler=self._on_message,
                                         error_handler=self.on_error,
                                         get_connect_url=get_connect_url)
        self._subscriptions: Set[str] = set()

    async def init(self, symbols: List[Symbol]):
        """Initialize the websocket connection."""
        self.symbols = symbols
        await self.ws_client.start()

        subscriptions = list(chain.from_iterable(
            self._create_subscriptions(symbol, SubscriptionAction.SUBSCRIBE)
            for symbol in symbols
        ))
        await self.ws_client.subscribe(subscriptions)

    async def start_symbol(self, symbol: Symbol):
        """Start streaming data for a specific symbol."""
        if symbol not in self.symbols:
            self.symbols.append(symbol)
            subscriptions = self._create_subscriptions(symbol, SubscriptionAction.SUBSCRIBE)
            await self.ws_client.subscribe(subscriptions)

    async def stop_symbol(self, symbol: Symbol):
        """Stop streaming data for a specific symbol."""
        if symbol in self.symbols:
            self.symbols.remove(symbol)
            subscriptions = self._create_subscriptions(symbol, SubscriptionAction.UNSUBSCRIBE)
            await self.ws_client.unsubscribe(subscriptions)

    def _create_subscriptions(self, symbol: Symbol, action: SubscriptionAction) -> List[str]:
        """Prepare the connections for subscriptions specific symbol."""
        raise NotImplementedError("_create_subscriptions must be implemented in subclass")

    async def _on_message(self, message: Dict[str, Any]):
        raise NotImplementedError("on_message must be implemented in subclass")

    async def on_error(self, error: Exception):
        raise NotImplementedError("on_error must be implemented in subclass")

