from abc import ABC, abstractmethod
from typing import Any, Optional, List, Dict, Union, TypeVar
from enum import IntEnum

from infrastructure.networking.websocket.structs import ParsedMessage, WebsocketChannelType, SubscriptionAction
from exchanges.structs.common import Symbol
from websockets.client import WebSocketClientProtocol
from websockets.protocol import State as WsState

# Generic type for channel enums
T = TypeVar('T', bound=IntEnum)


class WebsocketRawMessageProcessorInterface(ABC):
    async def process_raw(self, raw_message: Any) -> ParsedMessage:
        raise NotImplementedError


class WebsocketConnectionInterface(ABC):

    def __init__(self):
        self._websocket: WebSocketClientProtocol = None

    @property
    def websocket(self) -> Optional[WebSocketClientProtocol]:
        """Get the current WebSocket instance."""
        return self._websocket

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._websocket and self._websocket.state == WsState.OPEN

    @abstractmethod
    async def connect(self) -> WebSocketClientProtocol:
        # TODO: AI move from
        raise NotImplementedError

    def auth(self) -> bool:
        raise True # Default to True for public connections


class WebsocketSubscriptionPrivateInterface(ABC):

    @abstractmethod
    def _prepare_subscription_message(self, action: SubscriptionAction,
                                            channel: WebsocketChannelType, **kwargs) -> Dict[str, Any]:
        pass
    @abstractmethod
    async def subscribe(self, channel: Union[List[WebsocketChannelType],WebsocketChannelType], **kwargs) -> None:
        raise NotImplementedError

    @abstractmethod
    async def unsubscribe(self, channel: Union[List[WebsocketChannelType],WebsocketChannelType], **kwargs) -> None:
        raise NotImplementedError

class WebsocketSubscriptionPublicInterface(ABC):

    @abstractmethod
    def _prepare_subscription_message(self, action: SubscriptionAction,
                                      symbol: Symbol,
                                      channel: WebsocketChannelType, **kwargs) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def subscribe(self,  symbol: Union[List[Symbol], Symbol],
                        channel: Union[List[WebsocketChannelType], WebsocketChannelType],
                        **kwargs) -> None:
        raise NotImplementedError

    @abstractmethod
    async def unsubscribe(self,  symbol: Union[List[Symbol], Symbol],
                          channel: Union[List[WebsocketChannelType], WebsocketChannelType],
                          **kwargs) -> None:
        raise NotImplementedError

    # @abstractmethod
    # async def handle_subscription_confirm(self, parsed_message: ParsedMessage) -> None:
    #     """Handle subscription confirmation message."""
    #     pass
    # @abstractmethod
    # async def handle_subscription_error(self, parsed_message: ParsedMessage) -> None:
    #     """Handle subscription confirmation message."""
    #     pass



