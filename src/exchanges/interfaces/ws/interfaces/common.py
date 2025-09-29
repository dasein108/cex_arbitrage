from abc import ABC, abstractmethod
from typing import Any, Optional, List, Dict, Union, TypeVar, Generic, Callable, Awaitable
from enum import IntEnum

from infrastructure.logging import HFTLoggerInterface
from infrastructure.networking.websocket.structs import ParsedMessage, WebsocketChannelType, SubscriptionAction
from exchanges.structs.common import Order, AssetBalance, Symbol, Trade, OrderBook, Ticker, BookTicker
from websockets.client import WebSocketClientProtocol
from websockets.protocol import State as WsState

# Generic type for channel enums
T = TypeVar('T', bound=IntEnum)


class WebsocketBindHandlerInterface(Generic[T], ABC):
    """Generic interface for binding handlers to channel types."""
    
    def __init__(self):
        self._bound_handlers: Dict[T, Callable[[Any], Awaitable[None]]] = {}
    
    def bind(self, channel: T, handler: Callable[[Any], Awaitable[None]]) -> None:
        """Bind a handler function to a WebSocket channel.
        
        Args:
            channel: The channel type to bind
            handler: Async function to handle messages for this channel
        """
        self._bound_handlers[channel] = handler
        if hasattr(self, 'logger'):
            self.logger.debug(f"Bound handler for channel: {channel.name}")

    def _get_bound_handler(self, channel: T) -> Callable[[Any], Awaitable[None]]:
        """Get bound handler for channel or raise exception if not bound.
        
        Args:
            channel: The channel type
            
        Returns:
            The bound handler function
            
        Raises:
            ValueError: If no handler is bound for the channel
        """
        if channel not in self._bound_handlers:
            raise ValueError(f"No handler bound for channel {channel.name} (value: {channel.value}). "
                           f"Use bind({channel.name}, your_handler_function) to bind a handler.")
        return self._bound_handlers[channel]

    async def _exec_bound_handler(self, channel: T, *args, **kwargs) -> None:
        """Execute the bound handler for a channel with the given message.

        Args:
            channel: The channel type
            message: The message to pass to the handler
        """
        handler = self._get_bound_handler(channel)
        return await handler(*args, **kwargs)

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



