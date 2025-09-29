import traceback
from abc import ABC, abstractmethod
from typing import Any, Optional, List, Dict, Union
from infrastructure.networking.websocket.structs import ParsedMessage, WebsocketChannelType, PrivateWebsocketChannelType
from exchanges.interfaces.ws.ws_base import BaseWebsocketInterface
from .interfaces.interfaces import WebsocketSubscriptionPrivateInterface, WebsocketBindHandlerInterface
from infrastructure.networking.websocket.structs import SubscriptionAction


class BaseWebsocketPrivate(BaseWebsocketInterface, WebsocketSubscriptionPrivateInterface,
                           WebsocketBindHandlerInterface[PrivateWebsocketChannelType], ABC):
    """Abstract interface for private exchange WebSocket operations (account data)"""
    
    def __init__(self, *args, **kwargs):
        """Initialize private WebSocket interface with handler object."""
        
        if not self.config.credentials.has_private_api:
            raise ValueError("Gate.io futures credentials not configured for private WebSocket")

        # Initialize composite class with private API configuration
        super().__init__(
            *args,
            **kwargs,
            is_private=True,  # Private API operations
        )

        self.subscriptions: List[WebsocketChannelType] = []

    @abstractmethod
    def _prepare_subscription_message(self, action: SubscriptionAction,
                                            channel: WebsocketChannelType, **kwargs) -> Dict[str, Any]:
        pass

    async def subscribe(self, channel: Union[List[WebsocketChannelType],WebsocketChannelType],
                  **kwargs) -> None:
        channels = channel if isinstance(channel, list) else [channel]
        for ch in channels:
            ws_subscriptions = self._prepare_subscription_message(SubscriptionAction.SUBSCRIBE,
                                                                  ch, **kwargs)

            await self._ws_manager.send_message(ws_subscriptions)
            self.subscriptions.append(ch)

    async def unsubscribe(self,  channel: Union[List[WebsocketChannelType],WebsocketChannelType],
                    **kwargs) -> None:
        channels = channel if isinstance(channel, list) else [channel]
        for ch in channels:
            if ch in self.subscriptions:
                ws_unsubscriptions = self._prepare_subscription_message(SubscriptionAction.UNSUBSCRIBE,ch, **kwargs)

                await self._ws_manager.send_message(ws_unsubscriptions)
                self.subscriptions.remove(ch)
            else:
                self.logger.warning(f"Attempted to unsubscribe from non-subscribed channel: {ch}")
