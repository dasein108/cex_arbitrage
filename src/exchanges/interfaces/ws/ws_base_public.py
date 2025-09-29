"""
Base Public WebSocket Interface - Refactored

Clean composite class for public WebSocket implementations using the new
strategy-driven architecture with handler objects.

HFT COMPLIANCE: Optimized for sub-millisecond message processing.
"""

from typing import List, Dict, Optional, Set, Callable, Awaitable, Any, Union
from abc import ABC, abstractmethod

from exchanges.consts import DEFAULT_PUBLIC_WEBSOCKET_CHANNELS
from exchanges.structs.common import Symbol, OrderBook, Trade, BookTicker
from config.structs import ExchangeConfig
from infrastructure.logging import HFTLogger
from infrastructure.networking.websocket.structs import ConnectionState, MessageType, ParsedMessage, \
    PublicWebsocketChannelType
import traceback
from exchanges.interfaces.ws.ws_base import BaseWebsocketInterface
from infrastructure.networking.websocket.structs import ParsedMessage, WebsocketChannelType
from exchanges.interfaces.ws.ws_base import BaseWebsocketInterface
from .interfaces.interfaces import WebsocketSubscriptionPublicInterface, PublicWebsocketMessageHandlerInterface
from infrastructure.networking.websocket.structs import SubscriptionAction


class BasePublicWebsocketPrivate(BaseWebsocketInterface, WebsocketSubscriptionPublicInterface,
                                 PublicWebsocketMessageHandlerInterface, ABC):
    """
    Base class for exchange public WebSocket implementations.
    
    Simplified architecture:
    - Uses new WebSocketManager V2
    - Delegates all subscription logic to strategies
    - Focuses on message routing and event handling
    """

    @property
    def active_symbols(self) -> List[Symbol]:
        return list(self.subscriptions.keys())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # State management for symbols (moved from WebSocket manager)
        self.subscriptions: Dict[Symbol, List[WebsocketChannelType]] = {}

    async def subscribe(self, symbol: Union[List[Symbol], Symbol],
                        channel: Union[List[WebsocketChannelType], WebsocketChannelType],
                        **kwargs) -> None:
        channels = channel if isinstance(channel, list) else [channel]
        symbols = symbol if isinstance(symbol, list) else [symbol]

        for s in symbols:
            if s not in self.subscriptions:
                self.subscriptions[s] = []
            # Filter out already subscribed channels for this symbol
            channels = [ch for ch in channels if ch not in self.subscriptions[s]]
            if not channels:
                self.logger.debug(f"Already subscribed to all requested channels for symbol {s}")
                continue

            ws_subscriptions = self._prepare_subscription_message(SubscriptionAction.SUBSCRIBE,
                                                                  s, channels)

            await self._ws_manager.send_message(ws_subscriptions)

            if s not in self.subscriptions:
                self.subscriptions[s] = []

            self.subscriptions[s] += channels

    async def unsubscribe(self, symbol: Union[List[Symbol], Symbol],
                          channel: Union[List[WebsocketChannelType], WebsocketChannelType],
                          **kwargs) -> None:
        channels = channel if isinstance(channel, list) else [channel]
        symbols = symbol if isinstance(symbol, list) else [symbol]

        for s in symbols:
            if s not in self.subscriptions:
                self.logger.warning(f"Attempted to unsubscribe from non-subscribed symbol: {s}")
                continue

            channels = [ch for ch in channels if ch in self.subscriptions[s]]
            if not channels:
                self.logger.debug(f"No subscribed channels to unsubscribe for symbol {s}")
                continue

            ws_unsubscriptions = self._prepare_subscription_message(SubscriptionAction.UNSUBSCRIBE, s,
                                                                    channels, **kwargs)

            await self._ws_manager.send_message(ws_unsubscriptions)

            for ch in channels:
                if ch in self.subscriptions[s]:
                    self.subscriptions[s].remove(ch)

            if not self.subscriptions[s]:
                del self.subscriptions[s]
