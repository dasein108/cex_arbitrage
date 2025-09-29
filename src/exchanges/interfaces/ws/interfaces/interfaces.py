from abc import ABC, abstractmethod
from typing import Any, Optional, List, Dict, Union

from infrastructure.logging import HFTLoggerInterface
from infrastructure.networking.websocket.structs import ParsedMessage, WebsocketChannelType, SubscriptionAction
from exchanges.structs.common import Order, AssetBalance, Position, Trade, OrderBook, Ticker, BookTicker
from websockets.client import WebSocketClientProtocol
from websockets.protocol import State as WsState


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


class WebsocketSubscriptionInterface(ABC):

    @abstractmethod
    def _prepare_subscription_message(self, action: SubscriptionAction,
                                            channel: WebsocketChannelType, *args, **kwargs) -> Dict[str, Any]:
        pass
    @abstractmethod
    async def subscribe(self, channel: Union[List[WebsocketChannelType],WebsocketChannelType], *args, **kwargs) -> None:
        raise NotImplementedError

    @abstractmethod
    async def unsubscribe(self, channel: Union[List[WebsocketChannelType],WebsocketChannelType], *args, **kwargs) -> None:
        raise NotImplementedError

    # @abstractmethod
    # async def handle_subscription_confirm(self, parsed_message: ParsedMessage) -> None:
    #     """Handle subscription confirmation message."""
    #     pass
    # @abstractmethod
    # async def handle_subscription_error(self, parsed_message: ParsedMessage) -> None:
    #     """Handle subscription confirmation message."""
    #     pass

class PrivateWebsocketMessageHandlerInterface(ABC):
    logger: HFTLoggerInterface

    async def handle_order(self, order: Order) -> None:
        """Handle order update."""
        self.logger.warning(f"OVERRIDE: Received order update: {order}")

    async def handle_balance(self, balance: AssetBalance) -> None:
        """Handle balance update."""
        self.logger.warning(f"OVERRIDE: Received balance update: {balance}")

    async def handle_execution(self, trade: Trade) -> None:
        """Handle execution report/trade data."""
        self.logger.warning(f"OVERRIDE: Received execution report: {trade}")


class PublicWebsocketMessageHandlerInterface(ABC):
    @abstractmethod
    async def handle_orderbook(self, orderbook: OrderBook) -> None:
        """Handle orderbook update."""
        pass

    @abstractmethod
    async def handle_orderbook_diff(self, orderbook_update) -> None:
        """Handle orderbook diff update (used by some WebSocket implementations)."""
        pass

    @abstractmethod
    async def handle_ticker(self, ticker: Ticker) -> None:
        """Handle ticker update."""
        pass

    @abstractmethod
    async def handle_trade(self, trade: Trade) -> None:
        """Handle trade data."""
        pass

    @abstractmethod
    async def handle_book_ticker(self, book_ticker: BookTicker) -> None:
        """Handle book ticker data."""
        pass


class ChannelSubscriptionManagerInterface(ABC):
    def subscribe(self, channels: WebsocketChannelType, *args, **kwargs) -> None:
        raise NotImplementedError

    def unsubscribe(self, channels: WebsocketChannelType, *args, **kwargs) -> None:
        raise NotImplementedError




class SymbolChannelSubscriptionManagerInterface(ABC):
    def subscribe(self, symbol, channels: WebsocketChannelType) -> None:
        raise NotImplementedError


    def unsubscribe(self, symbol, channels: WebsocketChannelType) -> None:
        raise NotImplementedError



