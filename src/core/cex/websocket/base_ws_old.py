from abc import ABC
from typing import List, Set, Optional, Callable, Awaitable
from structs.exchange import Symbol, ExchangeName
from core.transport.websocket.ws_client import WebsocketClient
from core.transport.websocket.structs import WebsocketConfig
from core.cex.websocket.structs import ConnectionState,SubscriptionAction
from itertools import chain
from core.cex.services.symbol_mapper.symbol_mapper_factory import get_symbol_mapper

class BaseExchangeWebsocketInterface(ABC):
    """Abstract cex for private exchange operations (trading, account management)"""

    def __init__(self, exchange: ExchangeName, websocket_config: WebsocketConfig):
        self.exchange = exchange
        self.websocket_config = websocket_config
        self.symbols: List[Symbol] = []
        self.ws_client = WebsocketClient(websocket_config,
                                         message_handler=self._on_message,
                                         error_handler=self.on_error,
                                         connection_handler=self.on_state_change)

        self._subscriptions: Set[str] = set()

        # inject symbol mapper
        self._symbol_mapper = get_symbol_mapper(exchange)

    async def initialize(self, symbols: List[Symbol]):
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

    async def _on_message(self, raw_message: str):
        raise NotImplementedError("_on_message must be implemented in subclass")

    async def on_error(self, error: Exception):
        raise NotImplementedError("on_error must be implemented in subclass")

    async def on_state_change(self, status: ConnectionState):
        """Handle connection state changes."""
        pass


    async def close(self):
        """Close the websocket connection."""
        await self.ws_client.stop()