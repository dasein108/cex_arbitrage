"""
Base Public WebSocket Interface - Refactored

Clean composite class for public WebSocket implementations using the new
strategy-driven architecture with handler objects.

HFT COMPLIANCE: Optimized for sub-millisecond message processing.
"""

from typing import List, Dict, Optional, Set, Callable, Awaitable, Any, Union
from abc import ABC

from exchanges.structs.common import Symbol
from infrastructure.networking.websocket.structs import ConnectionState, MessageType, ParsedMessage, \
    PublicWebsocketChannelType
from infrastructure.networking.websocket.structs import ParsedMessage, WebsocketChannelType
from exchanges.interfaces.ws.ws_base import BaseWebsocketInterface
from .interfaces.common import WebsocketSubscriptionPublicInterface, WebsocketBindHandlerInterface
from infrastructure.networking.websocket.structs import SubscriptionAction


class PublicBaseWebsocket(BaseWebsocketInterface, WebsocketSubscriptionPublicInterface,
                          WebsocketBindHandlerInterface[PublicWebsocketChannelType], ABC):
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
        WebsocketBindHandlerInterface.__init__(self)
        super().__init__(*args, **kwargs)

        # State management for symbols (moved from WebSocket manager)
        self.subscriptions: Dict[Symbol, List[WebsocketChannelType]] = {}

    async def _resubscribe_all(self) -> None:
        for symbol, channels in self.subscriptions.items():
            for channel in channels:
                ws_subscriptions = self._prepare_subscription_message(SubscriptionAction.SUBSCRIBE, symbol, channel)
                await self._ws_manager.send_message(ws_subscriptions)
        self.logger.info("Resubscribed to all channels")

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

            ws_subscriptions = []
            for c in channels:
                if c not in PublicWebsocketChannelType:
                    self.logger.warning(f"Invalid channel {c} for public subscription on symbol {s}")
                    channels.remove(c)
                else:
                    ws_subscriptions = self._prepare_subscription_message(SubscriptionAction.SUBSCRIBE, s, c)

            if ws_subscriptions:
                await self._send_message_if_connected(ws_subscriptions)

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

            for c in channels:
                ws_unsubscriptions = self._prepare_subscription_message(SubscriptionAction.UNSUBSCRIBE, s, c)

                await self._send_message_if_connected(ws_unsubscriptions)

            for ch in channels:
                if ch in self.subscriptions[s]:
                    self.subscriptions[s].remove(ch)

            if not self.subscriptions[s]:
                del self.subscriptions[s]
