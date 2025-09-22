from typing import List

from exchanges.consts import DEFAULT_PUBLIC_WEBSOCKET_CHANNELS
from .spot.base_ws_public import BaseExchangePublicWebsocketInterface
from structs.common import Symbol, Trade, OrderBook, BookTicker
from core.transport.websocket.structs import PublicWebsocketChannelType


class BaseWebsocketPublicFutures(BaseExchangePublicWebsocketInterface):
    async def initialize(self, symbols: List[Symbol],
                         channels: List[PublicWebsocketChannelType]=DEFAULT_PUBLIC_WEBSOCKET_CHANNELS) -> None:
        await super().initialize(self._fix_futures_symbols(symbols), channels)

    async def add_symbols(self, symbols: List[Symbol]) -> None:
        futures_symbols = [Symbol(s.base, s.quote, is_futures=True) for s in symbols]
        await super().add_symbols(self._fix_futures_symbols(symbols))

    async def remove_symbols(self, symbols: List[Symbol]) -> None:
        await super().remove_symbols(self._fix_futures_symbols(symbols))

    def _fix_futures_symbols(self, symbols: List[Symbol]) -> List[Symbol]:
        """
        Convert spot symbols to futures symbols by setting is_futures=True.
        Gate.io uses the same symbol format for spot and futures, but we need to
        differentiate them in our system.
        :param symbols:
        :return:
        """
        return [Symbol(s.base, s.quote, is_futures=True) for s in symbols]

