from typing import List

from exchanges.consts import DEFAULT_PUBLIC_WEBSOCKET_CHANNELS
from exchanges.interfaces.ws.spot.ws_spot_public import PublicSpotWebsocket
from exchanges.structs.common import Symbol
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType


class PublicFuturesWebsocket(PublicSpotWebsocket):
    async def initialize(self, symbols: List[Symbol],
                         channels: List[PublicWebsocketChannelType]=DEFAULT_PUBLIC_WEBSOCKET_CHANNELS) -> None:
        await super().initialize(self._fix_futures_symbols(symbols), channels)

    async def add_symbols(self, symbols: List[Symbol]) -> None:
        await super().add_symbols(self._fix_futures_symbols(symbols))

    async def remove_symbols(self, symbols: List[Symbol]) -> None:
        await super().remove_symbols(self._fix_futures_symbols(symbols))

    @staticmethod
    def _fix_futures_symbols(self, symbols: List[Symbol]) -> List[Symbol]:
        """Fix symbols for futures format if needed."""
        return [Symbol(s.base,s.quote, is_futures=True) for s in symbols]