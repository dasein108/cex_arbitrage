from typing import List

from exchanges.consts import DEFAULT_PUBLIC_WEBSOCKET_CHANNELS
from exchanges.interfaces.ws.spot.base_ws_public import BaseExchangePublicSpotWebsocket
from infrastructure.data_structures.common import Symbol
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType


class BaseExchangePublicFuturesWebsocket(BaseExchangePublicSpotWebsocket):
    async def initialize(self, symbols: List[Symbol],
                         channels: List[PublicWebsocketChannelType]=DEFAULT_PUBLIC_WEBSOCKET_CHANNELS) -> None:
        await super().initialize(self._fix_futures_symbols(symbols), channels)

    async def add_symbols(self, symbols: List[Symbol]) -> None:
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

